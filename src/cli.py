import argparse
import logging
import sys

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from src.config import get_source_engine, get_target_engine
from src.source_models import (Language, Payment, Rental, Address, City, Country,
    Inventory, Language, Staff)
from src.target_models import DimDate, SyncState, TargetBase
from src.dates import to_date, add_dates, date_range

from src.sync import (
    load_dim_actor, load_dim_category, load_dim_film, load_dim_store,
    load_dim_customer, load_bridge_film_actor, load_bridge_film_category,
    load_fact_rental, load_fact_payment, max_last_update, save_markers,
)


log = logging.getLogger("sakila_sync")

SOURCE_TABLES = ["language", "film", "actor", "category", "film_actor",
                 "film_category", "country", "city", "address", "store",
                 "staff", "customer", "inventory", "rental", "payment"]

def cmd_init(args) -> int:
    src_engine = get_source_engine()
    with Session(src_engine) as src:
        n = src.scalar(select(func.count()).select_from(Language))
        log.info("Connection successful: %d language found", n)
        rental_bounds = src.execute(select(
            func.min(Rental.rental_date), func.max(Rental.rental_date),
            func.min(Rental.return_date), func.max(Rental.return_date),
        )).one()
        payment_bounds = src.execute(select(
            func.min(Payment.payment_date), func.max(Payment.payment_date),
        )).one()
        values = [to_date(v) for v in (*rental_bounds, *payment_bounds)
                  if v is not None]

    tgt_engine = get_target_engine()
    TargetBase.metadata.create_all(tgt_engine)
    with Session(tgt_engine) as tgt, tgt.begin():
        for table in SOURCE_TABLES:
            tgt.execute(insert(SyncState).values(source_table = table, last_update = None)
                        .on_conflict_do_nothing(index_elements=["source_table"]))
        if values:
            add_dates(tgt, date_range(min(values), max(values)))
        total = tgt.scalar(select(func.count()).select_from(DimDate))

    log.info("SQLite tables created; sync_state seeded (%d tables); dim_date has %d rows",
             len(SOURCE_TABLES), total)
    print("init finished")
    return 0


def cmd_full_load(args) -> int:
    src_engine = get_source_engine()
    tgt_engine = get_target_engine()
    TargetBase.metadata.create_all(tgt_engine) 

    with Session(src_engine) as src, Session(tgt_engine) as tgt, tgt.begin():
        markers = {}

        log.info("Loading dimensions")
        markers["actor"] = load_dim_actor(src, tgt)
        markers["category"] = load_dim_category(src, tgt)
        markers["film"] = load_dim_film(src, tgt)
        markers["store"] = load_dim_store(src, tgt)
        markers["customer"] = load_dim_customer(src, tgt)

        log.info("Loading bridges")
        markers["film_actor"] = load_bridge_film_actor(src, tgt)
        markers["film_category"] = load_bridge_film_category(src, tgt)

        log.info("Loading facts")
        markers["rental"] = load_fact_rental(src, tgt)
        markers["payment"] = load_fact_payment(src, tgt)

        for name, model in (("language", Language), ("address", Address),
                            ("city", City), ("country", Country),
                            ("inventory", Inventory), ("staff", Staff)):
            markers[name] = max_last_update(src, model)

        save_markers(tgt, markers)

    log.info("full-load committed")
    print("full-load finished")
    return 0


def cmd_not_ready(args) -> int:
    print(f"{args.command}: not implemented yet")
    return 1


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="sakila_sync")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("full-load").set_defaults(func=cmd_full_load)
    sub.add_parser("incremental").set_defaults(func=cmd_not_ready)
    v = sub.add_parser("validate")
    v.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    v.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    v.set_defaults(func=cmd_not_ready)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        log.exception("%s failed", args.command)
        print(f"{args.command} FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())