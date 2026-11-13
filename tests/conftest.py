import os
import shutil
import subprocess
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()
SQL_DIR = Path(__file__).parent / "sql"
SQL_FILES = ("sakila-test-schema.sql", "sakila-test-data.sql")


def reset_sakila_test(url):
    """Drop and reload sakila_test from the two edited Sakila scripts.

    Uses the mysql command-line client because the scripts contain triggers
    and DELIMITER blocks that cannot be executed through the ORM.
    """
    if shutil.which("mysql") is None:
        raise RuntimeError(
            "The 'mysql' command-line client is required to reset sakila_test. "
            "Install it and retry."
        )
    if not url.username:
        raise RuntimeError("MYSQL_TEST_URL must include a username")

    env = {**os.environ, "MYSQL_PWD": url.password or ""}
    cmd = [
        "mysql", "--protocol=TCP",
        "-h", url.host or "127.0.0.1",
        "-P", str(url.port or 3306),
        "-u", url.username,
    ]
    for name in SQL_FILES:
        with open(SQL_DIR / name, "rb") as f:
            result = subprocess.run(cmd, stdin=f, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"loading {name} failed:\n{result.stderr}")


@pytest.fixture(autouse=True)
def test_env(tmp_path, monkeypatch):
    """Before every test: fresh sakila_test and a temporary SQLite file."""
    test_url = os.environ.get("MYSQL_TEST_URL")
    if not test_url:
        pytest.exit("MYSQL_TEST_URL is not set (see .env.example)", returncode=2)
    url = make_url(test_url)
    if url.database != "sakila_test":
        pytest.exit("MYSQL_TEST_URL must point at the sakila_test database", returncode=2)

    reset_sakila_test(url)
    monkeypatch.setenv("MYSQL_URL", test_url)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "analytics.db"))