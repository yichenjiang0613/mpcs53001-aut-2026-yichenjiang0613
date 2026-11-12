import logging
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from src.dates import date_key
from src.source_models import (
    Actor, Category, Customer, Film, FilmActor, FilmCategory, Inventory,
    Payment, Rental, Staff, Store,
)
from src.target_models import (
    BridgeFilmActor, BridgeFilmCategory, DimActor, DimCategory, DimCustomer,
    DimDate, DimFilm, DimStore, FactPayment, FactRental,
)

log = logging.getLogger("sakila_sync")

TOLERANCE = Decimal("0.01")

COUNT_PAIRS = [
    ("film", Film, DimFilm), ("actor", Actor, DimActor),
    ("category", Category, DimCategory), ("store", Store, DimStore),
    ("customer", Customer, DimCustomer),
    ("film_actor", FilmActor, BridgeFilmActor),
    ("film_category", FilmCategory, BridgeFilmCategory),
    ("rental", Rental, FactRental), ("payment", Payment, FactPayment),
]

UNIQUE_KEYS = [
    [DimFilm.film_id], [DimActor.actor_id], [DimCategory.category_id],
    [DimStore.store_id], [DimCustomer.customer_id],
    [FactRental.rental_id], [FactPayment.payment_id]
]

REFERENCES = [
    (FactRental.date_key_rented, DimDate.date_key),
    (FactRental.date_key_returned, DimDate.date_key),
    (FactRental.film_key, DimFilm.film_key),
    (FactRental.store_key, DimStore.store_key),
    (FactRental.customer_key, DimCustomer.customer_key),
    (FactPayment.date_key_paid, DimDate.date_key),
    (FactPayment.customer_key, DimCustomer.customer_key),
    (FactPayment.store_key, DimStore.store_key)
]


def default_period(src):
    """The 30 days ending on the latest payment date in Sakila."""
    last = src.scalar(select(func.max(Payment.payment_date)))
    if last is None:
        return None, None
    end = last.date()
    return end - timedelta(days=29), end


def validation(src, tgt, date_from=None, date_to=None):
    """Return a list of problem descriptions (empty list means all good)."""
    problems = []

    default_from, default_to = default_period(src)
    date_to = date_to or default_to
    date_from = date_from or (date_to - timedelta(days=29) if date_to else None)
    if date_from is None or date_to is None:
        problems.append("source has no payments, cannot choose a period")
        return problems
    start_dt = datetime.combine(date_from, time.min)
    end_dt = datetime.combine(date_to + timedelta(days=1), time.min)
    key_from, key_to = date_key(date_from), date_key(date_to)
    log.info("validating period %s to %s", date_from, date_to)

    # Check row counts
    for name, s_model, t_model in COUNT_PAIRS:
        s_n = src.scalar(select(func.count()).select_from(s_model))
        t_n = tgt.scalar(select(func.count()).select_from(t_model))
        if s_n != t_n:
            problems.append(f"{name}: row count mismatch (source={s_n}, target={t_n})")

    # Check rentals in the period
    s_rentals = set(src.scalars(select(Rental.rental_id).where(
        Rental.rental_date >= start_dt, Rental.rental_date < end_dt)))
    t_rentals = set(tgt.scalars(select(FactRental.rental_id).where(
        FactRental.date_key_rented.between(key_from, key_to))))
    if len(s_rentals) != len(t_rentals):
        problems.append(f"rentals in period: count mismatch "
                        f"(source={len(s_rentals)}, target={len(t_rentals)})")
    missing = sorted(s_rentals - t_rentals)
    if missing:
        problems.append(f"{len(missing)} rentals missing in target, e.g. {missing[:5]}")

    # Check payments in the period
    s_payments = set(src.scalars(select(Payment.payment_id).where(
        Payment.payment_date >= start_dt, Payment.payment_date < end_dt)))
    t_payments = set(tgt.scalars(select(FactPayment.payment_id).where(
        FactPayment.date_key_paid.between(key_from, key_to))))
    if len(s_payments) != len(t_payments):
        problems.append(f"payments in period: count mismatch "
                        f"(source={len(s_payments)}, target={len(t_payments)})")
    missing = sorted(s_payments - t_payments)
    if missing:
        problems.append(f"{len(missing)} payments missing in target, e.g. {missing[:5]}")

    store_expr = func.coalesce(Inventory.store_id, Staff.store_id)
    s_rows = src.execute(
        select(store_expr, func.sum(Payment.amount))
        .select_from(Payment)
        .join(Rental, Payment.rental_id == Rental.rental_id, isouter=True)
        .join(Inventory, Rental.inventory_id == Inventory.inventory_id, isouter=True)
        .join(Staff, Payment.staff_id == Staff.staff_id)
        .where(Payment.payment_date >= start_dt, Payment.payment_date < end_dt)
        .group_by(store_expr)).all()
    t_rows = tgt.execute(
        select(DimStore.store_id, func.sum(FactPayment.amount))
        .select_from(FactPayment)
        .join(DimStore, FactPayment.store_key == DimStore.store_key)
        .where(FactPayment.date_key_paid.between(key_from, key_to))
        .group_by(DimStore.store_id)).all()

    s_totals = {sid: Decimal(str(total or 0)) for sid, total in s_rows}
    t_totals = {sid: Decimal(str(total or 0)) for sid, total in t_rows}
    for sid in sorted(set(s_totals) | set(t_totals)):
        s_amt = s_totals.get(sid, Decimal(0))
        t_amt = t_totals.get(sid, Decimal(0))
        if abs(s_amt - t_amt) > TOLERANCE:
            problems.append(f"store {sid}: payment total mismatch "
                            f"(source={s_amt}, target={t_amt})")

    # Check duplicate keys
    for cols in UNIQUE_KEYS:
        dupes = tgt.execute(
            select(*cols).group_by(*cols).having(func.count() > 1)).all()
        if dupes:
            names = ", ".join(f"{c.class_.__tablename__}.{c.key}" for c in cols)
            problems.append(f"{len(dupes)} duplicate key(s) in {names}")

    # Check fact rows without a matching dimension row
    for col, dim_col in REFERENCES:
        n = tgt.scalar(
            select(func.count()).select_from(col.class_)
            .where(col.is_not(None), ~col.in_(select(dim_col))))
        if n:
            problems.append(
                f"{n} row(s) in {col.class_.__tablename__}.{col.key} have no "
                f"matching {dim_col.class_.__tablename__}.{dim_col.key}")

    for p in problems:
        log.warning("validation problem: %s", p)
    return problems