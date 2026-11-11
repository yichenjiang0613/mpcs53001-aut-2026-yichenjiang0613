import argparse
import logging
import sys

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from src.config import get_source_engine, get_target_engine
from src.source_models import Language, Payment, Rental
from src.target_models import DimDate, SyncState, TargetBase
from src.dates import to_date, add_dates, date_range


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


def cmd_not_ready(args) -> int:
    print(f"{args.command}: not implemented yet")
    return 1


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="sakila_sync")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("full-load").set_defaults(func=cmd_not_ready)
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