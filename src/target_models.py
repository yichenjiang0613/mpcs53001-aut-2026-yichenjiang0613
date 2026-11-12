from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class TargetBase(DeclarativeBase):
    pass

class DimDate(TargetBase):
    __tablename__ = "dim_date"
    date_key: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date]
    year: Mapped[int]
    quarter: Mapped[int]
    month: Mapped[int]
    day_of_month: Mapped[int]
    day_of_week: Mapped[int]
    is_weekend: Mapped[int]

class DimFilm(TargetBase):
    __tablename__ = "dim_film"
    film_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    film_id: Mapped[int]
    title: Mapped[str]
    rating: Mapped[str]
    length: Mapped[int]
    language: Mapped[str]
    release_year: Mapped[int]
    last_update: Mapped[datetime]
    __table_args__ = (Index("ux_dim_film_film_id", "film_id", unique = True),)

class DimActor(TargetBase):
    __tablename__ = "dim_actor"
    actor_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[int]
    first_name: Mapped[str]
    last_name: Mapped[str]
    last_update: Mapped[datetime]
    __table_args__ = (Index("ux_dim_actor_actor_id", "actor_id", unique=True),)

class DimCategory(TargetBase):
    __tablename__ = "dim_category"
    category_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int]
    name: Mapped[str]
    last_update: Mapped[datetime]
    __table_args__ = (Index("ux_dim_category_category_id", "category_id", unique=True),)


class DimStore(TargetBase):
    __tablename__ = "dim_store"
    store_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int]
    city: Mapped[str]
    country: Mapped[str]
    last_update: Mapped[datetime]
    __table_args__ = (Index("ux_dim_store_store_id", "store_id", unique=True),)

class DimCustomer(TargetBase):
    __tablename__ = "dim_customer"
    customer_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int]
    first_name: Mapped[str]
    last_name: Mapped[str]
    active: Mapped[int]
    city: Mapped[str]
    country: Mapped[str]
    last_update: Mapped[datetime]
    __table_args__ = (Index("ux_dim_customer_customer_id", "customer_id", unique=True),)

class BridgeFilmActor(TargetBase):
    __tablename__= "bridge_film_actor"
    film_key: Mapped[int] = mapped_column(
        ForeignKey("dim_film.film_key"), primary_key=True)
    actor_key: Mapped[int] = mapped_column(
        ForeignKey("dim_actor.actor_id"), primary_key=True
    )

class BridgeFilmCategory(TargetBase):
    __tablename__ = "bridge_film_category"
    film_key: Mapped[int] = mapped_column(
        ForeignKey("dim_film.film_key"), primary_key=True)
    category_key: Mapped[int] = mapped_column(
        ForeignKey("dim_category.category_key"), primary_key=True)

class FactRental(TargetBase):
    __tablename__ = "fact_rental"
    fact_rental_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rental_id: Mapped[int]
    date_key_rented: Mapped[int] = mapped_column(ForeignKey("dim_date.date_key"))
    date_key_returned: Mapped[int | None] = mapped_column(ForeignKey("dim_date.date_key"))
    film_key: Mapped[int] = mapped_column(ForeignKey("dim_film.film_key"))
    store_key: Mapped[int] = mapped_column(ForeignKey("dim_store.store_key"))
    customer_key: Mapped[int] = mapped_column(ForeignKey("dim_customer.customer_key"))
    staff_id: Mapped[int]
    rental_duration_days: Mapped[int | None]
    __table_args__ = (
        Index("ux_fact_rental_rental_id", "rental_id", unique=True),
        Index("ix_fact_rental_date_key_rented", "date_key_rented"),
        Index("ix_fact_rental_date_key_returned", "date_key_returned"),
        Index("ix_fact_rental_film_key", "film_key"),
        Index("ix_fact_rental_store_key", "store_key"),
        Index("ix_fact_rental_customer_key", "customer_key")
    )

class FactPayment(TargetBase):
    __tablename__ = "fact_payment"
    fact_payment_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_id: Mapped[int]
    date_key_paid: Mapped[int] = mapped_column(ForeignKey("dim_date.date_key"))
    customer_key: Mapped[int] = mapped_column(ForeignKey("dim_customer.customer_key"))
    store_key: Mapped[int] = mapped_column(ForeignKey("dim_store.store_key"))
    staff_id: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    __table_args__ = (
        Index("ux_fact_payment_payment_id", "payment_id", unique=True),
        Index("ix_fact_payment_date_key_paid", "date_key_paid"),
        Index("ix_fact_payment_customer_key", "customer_key"),
        Index("ix_fact_payment_store_key", "store_key"),
    )

class SyncState(TargetBase):
    __tablename__ = "sync_state"
    source_table: Mapped[str] = mapped_column(primary_key=True)
    last_update: Mapped[datetime | None]