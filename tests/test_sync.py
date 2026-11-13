from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session

from src.cli import main
from src.config import get_source_engine, get_target_engine
from src.source_models import (
    Actor, Address, Category, City, Customer, Film, FilmActor, FilmCategory,
    Payment, Rental, Store,
)
from src.target_models import (
    BridgeFilmActor, BridgeFilmCategory, DimActor, DimCategory, DimCustomer,
    DimDate, DimFilm, DimStore, FactPayment, FactRental, SyncState, TargetBase,
)


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_1_init():
    """init creates the database and all analytics tables."""
    assert main(["init"]) == 0
    engine = get_target_engine()
    assert set(inspect(engine).get_table_names()) == set(TargetBase.metadata.tables)
    with Session(engine) as t:
        assert count(t, SyncState) == 15
        assert count(t, DimDate) > 0


def test_2_full_load():
    """full-load copies all Sakila data and is rerunnable without duplicates."""
    assert main(["init"]) == 0
    assert main(["full-load"]) == 0
    pairs = [(Film, DimFilm), (Actor, DimActor), (Category, DimCategory),
             (Store, DimStore), (Customer, DimCustomer),
             (FilmActor, BridgeFilmActor), (FilmCategory, BridgeFilmCategory),
             (Rental, FactRental), (Payment, FactPayment)]
    with Session(get_source_engine()) as s, Session(get_target_engine()) as t:
        for src_model, tgt_model in pairs:
            assert count(s, src_model) == count(t, tgt_model), tgt_model.__tablename__
        markers = t.scalars(select(SyncState.last_update)).all()
        assert len(markers) == 15 and all(m is not None for m in markers)

    assert main(["full-load"]) == 0
    with Session(get_source_engine()) as s, Session(get_target_engine()) as t:
        assert count(t, FactRental) == count(s, Rental)
        assert count(t, FactPayment) == count(s, Payment)


def test_3_incremental_new_data():
    """New source rows (actor, rental, payment) appear in SQLite."""
    assert main(["init"]) == 0
    assert main(["full-load"]) == 0

    ts = datetime(2006, 3, 1, 10, 0, 0)
    with Session(get_source_engine()) as s, s.begin():
        s.add(Actor(first_name="NEW", last_name="ACTOR", last_update=ts))
        rental = Rental(rental_date=ts, inventory_id=1, customer_id=1,
                        return_date=None, staff_id=1, last_update=ts)
        s.add(rental)
        s.flush()
        new_rental_id = rental.rental_id
        payment = Payment(customer_id=1, staff_id=1, rental_id=new_rental_id,
                          amount=Decimal("9.99"), payment_date=ts, last_update=ts)
        s.add(payment)
        s.flush()
        new_payment_id = payment.payment_id
        # Sakila's BEFORE INSERT triggers overwrite these dates with NOW().
        # Explicit UPDATE statements always run (the triggers don't fire on update).
        s.execute(update(Rental).where(Rental.rental_id == new_rental_id)
                  .values(rental_date=ts))
        s.execute(update(Payment).where(Payment.payment_id == new_payment_id)
                  .values(payment_date=ts))

    assert main(["incremental"]) == 0

    with Session(get_target_engine()) as t:
        assert t.scalar(select(DimActor).where(DimActor.first_name == "NEW")) is not None
        fact = t.scalars(select(FactRental).where(
            FactRental.rental_id == new_rental_id)).one()
        assert fact.date_key_rented == 20060301
        assert fact.date_key_returned is None
        assert fact.rental_duration_days is None
        pay = t.scalars(select(FactPayment).where(
            FactPayment.payment_id == new_payment_id)).one()
        assert pay.date_key_paid == 20060301
        assert pay.amount == Decimal("9.99")


def test_4_incremental_updates():
    """A returned rental and a changed customer address reach SQLite."""
    assert main(["init"]) == 0
    assert main(["full-load"]) == 0

    with Session(get_source_engine()) as s, s.begin():
        # return a rental that was unreturned (rented 2006-02-14)
        s.get(Rental, 11496).return_date = datetime(2006, 2, 20, 12, 0, 0)
        # move customer 97 by changing only the address row
        address = s.get(Address, s.get(Customer, 97).address_id)
        other = s.scalars(select(City).where(City.city_id != address.city_id)).first()
        address.city_id = other.city_id
        new_city = other.city

    assert main(["incremental"]) == 0

    with Session(get_target_engine()) as t:
        fact = t.scalars(select(FactRental).where(FactRental.rental_id == 11496)).one()
        assert fact.date_key_returned == 20060220
        assert fact.rental_duration_days == 6
        cust = t.scalars(select(DimCustomer).where(DimCustomer.customer_id == 97)).one()
        assert cust.city == new_city


def test_5_validate(capsys):
    """validate passes on clean data and reports a deliberate mismatch."""
    assert main(["init"]) == 0
    assert main(["full-load"]) == 0
    assert main(["validate"]) == 0

    # corrupt the target: change a payment inside the default 30-day period
    with Session(get_target_engine()) as t, t.begin():
        pay = t.scalars(select(FactPayment)
                        .order_by(FactPayment.date_key_paid.desc())).first()
        pay.amount = pay.amount + 5

    capsys.readouterr()  # discard output from earlier commands
    assert main(["validate"]) == 1
    assert "mismatch" in capsys.readouterr().out