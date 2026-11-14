# Sakila to SQLite Analytics Sync

A command-line data sync that reads the Sakila operational database (MySQL 8.0) through an ORM and writes a star-schema analytics database (SQLite) through an ORM. It supports an initial full load, incremental updates, and validation.

##  Language, ORM, and Versions

| Component | Version |
|---|---|
| Language | Python 3.12.3 |
| ORM | SQLAlchemy 2.0.8 |
| MySQL driver | PyMySQL 1.2.3 (+ cryptography 50.0.2) |
| Config | python-dotenv 1.2.4 |
| Tests | pytest 9.2.0 |
| Source DB | MySQL 8.0, official Sakila sample database |
| Target DB | SQLite (file), via Python's built-in `sqlite3` |

## Setup

1. **Create a virtual environment and install dependencies**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Load Sakila into MySQL** as the database `sakila` (official `sakila-schema.sql` and `sakila-data.sql`).
3. **Create the test database `sakila_test`.** The tests reset it before every test using the scripts in `tests/sql/` (the official Sakila scripts with the schema name changed to `sakila_test`). 
4. **Install the `mysql` command-line client** (needed by the tests only):
   - Ubuntu/WSL: `sudo apt install mysql-client-core-8.0`
   - macOS: `brew install mysql-client` (add its `bin` folder to `PATH`)
   - Windows: install the MySQL client from the MySQL installer and add it to `PATH`
5. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Copy .env.example to .env and fill in values.
   ```

### Environment variables

| Variable | Meaning | Example |
|---|---|---|
| `MYSQL_URL` | Source Sakila connection | `mysql+pymysql://USER:PASSWORD@localhost:3306/sakila` |
| `MYSQL_TEST_URL` | Test copy, must end in `sakila_test` | `mysql+pymysql://USER:PASSWORD@localhost:3306/sakila_test` |
| `SQLITE_PATH` | Analytics file | `analytics.db` |


## Running the commands

Run from the project root with the virtual environment active. Each command prints a human-readable message and exits with `0` on success or non-zero on failure.

```bash
python -m src.cli init            # create SQLite tables, check MySQL, seed dim_date and sync_state
python -m src.cli full-load       # load all dimensions, then bridges, then facts
python -m src.cli incremental     # load only rows added/changed since the markers in sync_state
python -m src.cli validate [--from YYYY-MM-DD] [--to YYYY-MM-DD]
```

`validate` defaults to the 30 days ending on the latest payment date in Sakila. `full-load` and `incremental` also run the validation after committing and fail if it finds problems.

## Running the tests

```bash
pytest -v
```

The five tests (one per command behavior) run against `sakila_test` and a temporary SQLite file. The `sakila_test` database is reset before every test, so the real `sakila` database is never modified (the fixture refuses to run if `MYSQL_TEST_URL` does not point at `sakila_test`).

| Test | What it checks |
|---|---|
| `test_1_init` | database and all tables are created, `sync_state` seeded |
| `test_2_full_load` | all Sakila rows are loaded; rerun creates no duplicates |
| `test_3_incremental_new_data` | new actor, rental and payment appear in SQLite |
| `test_4_incremental_updates` | returned rental and changed customer address are updated |
| `test_5_validate` | clean data passes; a deliberate mismatch is reported |


## Analytics schema (ER diagram)

```mermaid
erDiagram
    dim_date ||--o{ fact_rental : "date_key_rented"
    dim_date ||--o{ fact_rental : "date_key_returned"
    dim_date ||--o{ fact_payment : "date_key_paid"
    dim_film ||--o{ fact_rental : film_key
    dim_store ||--o{ fact_rental : store_key
    dim_customer ||--o{ fact_rental : customer_key
    dim_customer ||--o{ fact_payment : customer_key
    dim_store ||--o{ fact_payment : store_key
    dim_film ||--o{ bridge_film_actor : film_key
    dim_actor ||--o{ bridge_film_actor : actor_key
    dim_film ||--o{ bridge_film_category : film_key
    dim_category ||--o{ bridge_film_category : category_key

    dim_date {
        int date_key PK "YYYYMMDD"
        date date
        int year
        int quarter
        int month
        int day_of_month
        int day_of_week "ISO, Monday=1"
        int is_weekend
    }
    dim_film {
        int film_key PK
        int film_id UK
        string title
        string rating
        int length
        string language
        int release_year
        datetime last_update
    }
    dim_actor {
        int actor_key PK
        int actor_id UK
        string first_name
        string last_name
        datetime last_update
    }
    dim_category {
        int category_key PK
        int category_id UK
        string name
        datetime last_update
    }
    dim_store {
        int store_key PK
        int store_id UK
        string city
        string country
        datetime last_update
    }
    dim_customer {
        int customer_key PK
        int customer_id UK
        string first_name
        string last_name
        int active
        string city
        string country
        datetime last_update
    }
    bridge_film_actor {
        int film_key PK, FK
        int actor_key PK, FK
    }
    bridge_film_category {
        int film_key PK, FK
        int category_key PK, FK
    }
    fact_rental {
        int fact_rental_key PK
        int rental_id UK
        int date_key_rented FK
        int date_key_returned FK
        int film_key FK
        int store_key FK
        int customer_key FK
        int staff_id
        int rental_duration_days
    }
    fact_payment {
        int fact_payment_key PK
        int payment_id UK
        int date_key_paid FK
        int customer_key FK
        int store_key FK
        int staff_id
        decimal amount
    }
    sync_state {
        string source_table PK
        datetime last_update
    }
```

## Indexes

Unique indexes (`ux_`) on natural keys. Every write is an upsert (`ON CONFLICT (natural key) DO UPDATE`), and SQLite requires a unique index to resolve the conflict. They also prevent duplicates.

| Index | Column | Purpose |
|---|---|---|
| `ux_dim_film_film_id` | `dim_film.film_id` | upsert target, one row per film |
| `ux_dim_actor_actor_id` | `dim_actor.actor_id` | upsert target |
| `ux_dim_category_category_id` | `dim_category.category_id` | upsert target |
| `ux_dim_store_store_id` | `dim_store.store_id` | upsert target |
| `ux_dim_customer_customer_id` | `dim_customer.customer_id` | upsert target |
| `ux_fact_rental_rental_id` | `fact_rental.rental_id` | upsert target |
| `ux_fact_payment_payment_id` | `fact_payment.payment_id` | upsert target |

Regular indexes (`ix_`) on fact-table keys, to speed up joins to dimensions and filtering by date or store (including the `validate` period queries):

| Index | Column | Purpose |
|---|---|---|
| `ix_fact_rental_date_key_rented` | `fact_rental.date_key_rented` | filter/aggregate rentals by day |
| `ix_fact_rental_date_key_returned` | `fact_rental.date_key_returned` | filter by return day |
| `ix_fact_rental_film_key` | `fact_rental.film_key` | rentals per film |
| `ix_fact_rental_store_key` | `fact_rental.store_key` | rentals per store |
| `ix_fact_rental_customer_key` | `fact_rental.customer_key` | rentals per customer |
| `ix_fact_payment_date_key_paid` | `fact_payment.date_key_paid` | revenue by day, validate period |
| `ix_fact_payment_customer_key` | `fact_payment.customer_key` | payments per customer |
| `ix_fact_payment_store_key` | `fact_payment.store_key` | revenue per store |


## Raw SQL

The sync code (`src/`) uses no raw SQL. All reads and writes use SQLAlchemy `select`, `insert`, `update` and ORM models, and tables and indexes are created from the models. 

The one exception is the **test fixture** (`tests/conftest.py`). It reloads `sakila_test` by running the Sakila scripts with the `mysql` command-line client. The scripts contain triggers and `DELIMITER` blocks that cannot be executed through the ORM.
