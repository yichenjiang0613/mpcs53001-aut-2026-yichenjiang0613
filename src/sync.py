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
         "last_name": c.last_name, "active": int(c.active),
         "city": c.city, "country": c.country, "last_update": c.last_update}
        for c in customers
    ]
    upsert(tgt, DimCustomer, rows, ["customer_id"],
           ["first_name", "last_name", "active", "city", "country", "last_update"])
    log.info("dim_customer: %d rows upserted", len(rows))
    return max((c.last_update for c in customers), default=None)