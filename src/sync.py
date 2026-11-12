import logging

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.sqlite import insert

from src.dates import add_dates, date_key, to_date
from src.source_models import (
    Actor, Address, Category, City, Country, Customer, Film, FilmActor,
    FilmCategory, Inventory, Language, Payment, Rental, Staff, Store,
)
from src.target_models import (
    BridgeFilmActor, BridgeFilmCategory, DimActor, DimCategory, DimCustomer,
    DimFilm, DimStore, FactPayment, FactRental, SyncState,
)

log = logging.getLogger("sakila_sync")



def upsert(tgt, model, rows, key_cols, update_cols, batch=100):
    for i in range(0, len(rows), batch):
        stmt = insert(model).values(rows[i : i + batch])
        stmt = stmt.on_conflict_do_update(
            index_elements=key_cols,
            set_={c: stmt.excluded[c] for c in update_cols},
        )
        tgt.execute(stmt)



def load_dim_actor(src, tgt, since=None):
    q = select(Actor)
    if since is not None:
        q = q.where(Actor.last_update >= since)
    actors = src.scalars(q).all()
    rows = [
        {"actor_id": a.actor_id, "first_name": a.first_name,
         "last_name": a.last_name, "last_update": a.last_update}
        for a in actors
    ]
    upsert(tgt, DimActor, rows, ["actor_id"], ["first_name", "last_name", "last_update"])
    log.info("dim_actor upsert %d rows", len(rows))
    return max((a.last_update for a in actors), default=None)



def load_dim_category(src, tgt, since=None):
    q = select(Category)
    if since is not None:
        q = q.where(Category.last_update >= since)
    categories = src.scalars(q).all()
    rows = [
        {"category_id": c.category_id, "name": c.name, "last_update": c.last_update}
        for c in categories
    ]
    upsert(tgt, DimCategory, rows, ["category_id"], ["name", "last_update"])
    log.info("dim_category upsert %d rows", len(rows))
    return max((c.last_update for c in categories), default=None)



def load_dim_film(src, tgt, since=None):
    q = (
        select(Film.film_id, Film.title, Film.rating, Film.length, 
               Language.name.label("language"), Film.release_year, Film.last_update,
               Language.last_update.label("language_last_update"))
        .join(Language, Film.language_id == Language.language_id)
    )
    if since is not None:
        q = q.where(or_(Film.last_update >= since, Language.last_update >= since))
    films = src.execute(q).all()
    rows = [
        {"film_id": f.film_id, "title": f.title, "rating": f.rating,
         "length": f.length, "language": f.language, "release_year": f.release_year,
         "last_update": f.last_update}
        for f in films
    ]
    upsert(tgt, DimFilm, rows, ["film_id"], 
           ["title", "rating", "length", "language", "release_year", "last_update"])
    log.info("dim_film upsert %d rows", len(rows))
    return max((max(f.last_update, f.language_last_update) for f in films), default=None)



def load_dim_store(src, tgt, since=None):
    q = (
        select(Store.store_id, City.city, Country.country, Store.last_update)
        .select_from(Store)
        .join(Address, Store.address_id == Address.address_id)
        .join(City, Address.city_id == City.city_id)
        .join(Country, Country.country_id == City.country_id)
    )
    if since is not None:
        q = q.where(
                or_(Store.last_update >= since, Address.last_update >= since, 
                    City.last_update >= since, Country.last_update >= since
            ))
    stores = src.execute(q).all()
    rows = [
        {"store_id": s.store_id, "city": s.city, 
         "country": s.country, "last_update": s.last_update}
        for s in stores
    ]
    upsert(tgt, DimStore, rows, ["store_id"], ["city", "country", "last_update"])
    log.info("dim_store upsert %d rows", len(rows))
    return max((s.last_update for s in stores), default=None)



def load_dim_customer(src, tgt, since=None):
    q = (
        select(Customer.customer_id, Customer.first_name, Customer.last_name,
               Customer.active, Customer.last_update, City.city, Country.country)
        .select_from(Customer)
        .join(Address, Customer.address_id == Address.address_id)
        .join(City, Address.city_id == City.city_id)
        .join(Country, City.country_id == Country.country_id)
    )
    if since is not None:
        q = q.where(or_(Customer.last_update >= since,
                        Address.last_update >= since,
                        City.last_update >= since,
                        Country.last_update >= since))
    customers = src.execute(q).all()
    rows = [
        {"customer_id": c.customer_id, "first_name": c.first_name,
         "last_name": c.last_name, "active": c.active,
         "city": c.city, "country": c.country, "last_update": c.last_update}
        for c in customers
    ]
    upsert(tgt, DimCustomer, rows, ["customer_id"],
           ["first_name", "last_name", "active", "city", "country", "last_update"])
    log.info("dim_customer upsert %d rows", len(rows))
    return max((c.last_update for c in customers), default=None)



def key_map(tgt, model, natural_col, key_col):
    """{natural id: surrogate key} read back from a loaded dimension."""
    stmt = select(getattr(model, natural_col), getattr(model, key_col))
    return {nat: key for nat, key in tgt.execute(stmt).all()}


def insert_missing(tgt, model, rows, key_cols, batch=100):
    """Insert rows, skipping any that already exist (for bridges)."""
    for i in range(0, len(rows), batch):
        stmt = insert(model).values(rows[i:i + batch])
        stmt = stmt.on_conflict_do_nothing(index_elements=key_cols)
        tgt.execute(stmt)


def load_bridge_film_actor(src, tgt, since=None):
    film_keys = key_map(tgt, DimFilm, "film_id", "film_key")
    actor_keys = key_map(tgt, DimActor, "actor_id", "actor_key")

    stmt = select(FilmActor.film_id, FilmActor.actor_id, FilmActor.last_update)
    if since is not None:
        stmt = stmt.where(FilmActor.last_update >= since)
    results = src.execute(stmt).all()

    rows = []
    for r in results:
        if r.film_id not in film_keys or r.actor_id not in actor_keys:
            raise ValueError(
                f"film_actor ({r.film_id}, {r.actor_id}) has no matching dimension row")
        rows.append({"film_key": film_keys[r.film_id],
                     "actor_key": actor_keys[r.actor_id]})

    insert_missing(tgt, BridgeFilmActor, rows, ["film_key", "actor_key"])
    log.info("bridge_film_actor upsert %d rows", len(rows))
    return max((r.last_update for r in results), default=None)


def load_bridge_film_category(src, tgt, since=None):
    film_keys = key_map(tgt, DimFilm, "film_id", "film_key")
    category_keys = key_map(tgt, DimCategory, "category_id", "category_key")

    stmt = select(FilmCategory.film_id, FilmCategory.category_id,
                  FilmCategory.last_update)
    if since is not None:
        stmt = stmt.where(FilmCategory.last_update >= since)
    results = src.execute(stmt).all()

    rows = []
    for r in results:
        if r.film_id not in film_keys or r.category_id not in category_keys:
            raise ValueError(
                f"film_category ({r.film_id}, {r.category_id}) has no matching dimension row")
        rows.append({"film_key": film_keys[r.film_id],
                     "category_key": category_keys[r.category_id]})

    insert_missing(tgt, BridgeFilmCategory, rows, ["film_key", "category_key"])
    log.info("bridge_film_category upsert %d rows", len(rows))
    return max((r.last_update for r in results), default=None)



def load_fact_rental(src, tgt, since=None):
    film_keys = key_map(tgt, DimFilm, "film_id", "film_key")
    store_keys = key_map(tgt, DimStore, "store_id", "store_key")
    customer_keys = key_map(tgt, DimCustomer, "customer_id", "customer_key")

    stmt = (
        select(Rental.rental_id, Rental.rental_date, Rental.return_date,
               Rental.customer_id, Rental.staff_id, Rental.last_update,
               Inventory.film_id, Inventory.store_id)
        .select_from(Rental)
        .join(Inventory, Rental.inventory_id == Inventory.inventory_id)
    )
    if since is not None:
        stmt = stmt.where(or_(Rental.last_update >= since,
                              Inventory.last_update >= since))
    results = src.execute(stmt).all()

    add_dates(tgt, [r.rental_date for r in results] + [r.return_date for r in results])

    rows = []
    for r in results:
        try:
            film_key = film_keys[r.film_id]
            store_key = store_keys[r.store_id]
            customer_key = customer_keys[r.customer_id]
        except KeyError as exc:
            raise ValueError(f"rental {r.rental_id}: no dimension row for {exc}") from exc
        returned = r.return_date is not None
        rows.append({
            "rental_id": r.rental_id,
            "date_key_rented": date_key(r.rental_date),
            "date_key_returned": date_key(r.return_date) if returned else None,
            "film_key": film_key,
            "store_key": store_key,
            "customer_key": customer_key,
            "staff_id": r.staff_id,
            "rental_duration_days":
                (to_date(r.return_date) - to_date(r.rental_date)).days if returned else None,
        })

    upsert(tgt, FactRental, rows, ["rental_id"],
           ["date_key_rented", "date_key_returned", "film_key", "store_key",
            "customer_key", "staff_id", "rental_duration_days"])
    log.info("fact_rental upsert %d rows", len(rows))
    return max((r.last_update for r in results), default=None)


def load_fact_payment(src, tgt, since=None):
    store_keys = key_map(tgt, DimStore, "store_id", "store_key")
    customer_keys = key_map(tgt, DimCustomer, "customer_id", "customer_key")

    stmt = (
        select(Payment.payment_id, Payment.customer_id, Payment.staff_id,
               Payment.amount, Payment.payment_date, Payment.last_update,
               func.coalesce(Inventory.store_id, Staff.store_id).label("store_id"))
        .select_from(Payment)
        .join(Rental, Payment.rental_id == Rental.rental_id, isouter=True)
        .join(Inventory, Rental.inventory_id == Inventory.inventory_id, isouter=True)
        .join(Staff, Payment.staff_id == Staff.staff_id)
    )
    if since is not None:
        stmt = stmt.where(Payment.last_update >= since)
    results = src.execute(stmt).all()

    add_dates(tgt, [r.payment_date for r in results])

    rows = []
    for r in results:
        try:
            customer_key = customer_keys[r.customer_id]
            store_key = store_keys[r.store_id]
        except KeyError as exc:
            raise ValueError(f"payment {r.payment_id}: no dimension row for {exc}") from exc
        rows.append({
            "payment_id": r.payment_id,
            "date_key_paid": date_key(r.payment_date),
            "customer_key": customer_key,
            "store_key": store_key,
            "staff_id": r.staff_id,
            "amount": r.amount,
        })

    upsert(tgt, FactPayment, rows, ["payment_id"],
           ["date_key_paid", "customer_key", "store_key", "staff_id", "amount"])
    log.info("fact_payment upsert %d rows", len(rows))
    return max((r.last_update for r in results), default=None)