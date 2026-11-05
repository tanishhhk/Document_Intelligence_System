import os

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.database import enable_sqlite_foreign_keys

# Set TEST_DATABASE_URL to run the API tests against PostgreSQL. The tests
# create and drop all tables, so point it at a disposable database.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def make_test_engine():
    if TEST_DATABASE_URL:
        return create_engine(TEST_DATABASE_URL)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    enable_sqlite_foreign_keys(engine)
    return engine
