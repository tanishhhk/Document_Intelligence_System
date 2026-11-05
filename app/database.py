from pathlib import Path

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _is_sqlite(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "sqlite"


def _engine_options(database_url: str) -> dict:
    if _is_sqlite(database_url):
        return {"connect_args": {"check_same_thread": False}}
    return {}


def enable_sqlite_foreign_keys(engine) -> None:
    """SQLite ignores foreign keys unless each connection turns them on."""

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # Keep SQL parameters, such as chunk text, out of error messages and logs.
    hide_parameters=True,
    **_engine_options(settings.database_url),
)
if _is_sqlite(settings.database_url):
    enable_sqlite_foreign_keys(engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base(
    metadata=MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        }
    )
)


def schema_is_current(connection) -> bool:
    """Whether the database is at the latest Alembic revision."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_current_head()
    return MigrationContext.configure(connection).get_current_revision() == head


def run_migrations(database_url: str | None = None) -> None:
    """Upgrade the database schema to the latest Alembic revision."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(_ALEMBIC_INI))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
