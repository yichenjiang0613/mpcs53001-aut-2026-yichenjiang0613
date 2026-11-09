from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class SourceBase(DeclarativeBase):
    pass

class Film(SourceBase):
    __tablename__ = "film"
    film_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    release_year: Mapped[int | None]
    language_id: Mapped[int] = mapped_column(ForeignKey("language.language_id"))
    length: Mapped[int | None]
    rating: Mapped [str | None]
    last_update: Mapped[datetime]

class Language(SourceBase):
    __tablename__ = "language"
    language_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    last_update: Mapped[datetime]

class Actor(SourceBase):
    __tablename__ = "actor"
    actor_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    last_update: Mapped[datetime]

class Address(SourceBase):
    __tablename__ = "address"
    address_id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("city.city_id"))
    last_update: Mapped[datetime]

class City(SourceBase):
    __tablename__ = "city"
    city_id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str]
    country_id: Mapped[int] = mapped_column(ForeignKey("country.country_id"))
    last_update: Mapped[datetime]

class Country(SourceBase):
    __tablename__ = "country"
    country_id: Mapped[int] = mapped_column(primary_key=True)
    country: Mapped[str]
    last_update: Mapped[datetime]

class Category(SourceBase):
    __tablename__ = "category"
    category_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    last_update: Mapped[datetime]

class FilmActor(SourceBase):
    __tablename__ = "film_actor"
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("actor.actor_id"), primary_key=True)
    film_id: Mapped[int] = mapped_column(
        ForeignKey("film.film_id"), primary_key=True)
    last_update: Mapped[datetime]

class FilmCategory(SourceBase):
    __tablename__ = "film_category"
    film_id: Mapped[int] = mapped_column(
        ForeignKey("film.film_id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.category_id"), primary_key=True)
    last_update: Mapped[datetime]

class Customer(SourceBase):
    __tablename__ = "customer"
    customer_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    active: Mapped[int]
    address_id: Mapped[int] = mapped_column(ForeignKey("address.address_id"))
    store_id: Mapped[int] = mapped_column(ForeignKey("store.store_id"))
    last_update: Mapped[datetime | None]

class Store(SourceBase):
    __tablename__ = "store"
    store_id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(ForeignKey("address.address_id"))
    last_update: Mapped[datetime]

class Inventory(SourceBase):
    __tablename__ = "inventory"
    inventory_id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("film.film_id"))
    store_id: Mapped[int] = mapped_column(ForeignKey("store.store_id"))
    last_update: Mapped[datetime]

class Payment(SourceBase):
    __tablename__ = "payment"
    payment_id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id"))
    rental_id: Mapped[int | None] = mapped_column(ForeignKey("rental.rental_id"))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.staff_id"))
    amount: Mapped[Decimal]
    payment_date: Mapped[datetime]
    last_update: Mapped[datetime | None]

class Rental(SourceBase):
    __tablename__ = "rental"
    rental_id: Mapped[int] = mapped_column(primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.inventory_id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id"))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.staff_id"))
    rental_date: Mapped[datetime]
    return_date: Mapped[datetime | None]
    last_update: Mapped[datetime]

class Staff(SourceBase):
    __tablename__ = "staff"
    staff_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("store.store_id"))
    last_update: Mapped[datetime]
