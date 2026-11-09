"""Database connections for the Sakila -> SQLite sync."""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

load_dotenv()  # loads .env; does not override variables that are already set


def get_source_engine() -> Engine:
    """MySQL (Sakila). Read-only in the sync."""
    return create_engine(os.environ["MYSQL_URL"], pool_pre_ping=True)


def get_target_engine() -> Engine:
    """SQLite analytics file."""
    return create_engine(f"sqlite:///{os.environ['SQLITE_PATH']}")


def source_session(engine: Engine | None = None) -> Session:
    return Session(engine or get_source_engine())


def target_session(engine: Engine | None = None) -> Session:
    return Session(engine or get_target_engine())
