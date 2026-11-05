import os
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    text,
)

from app.database import _ALEMBIC_INI, Base, enable_sqlite_foreign_keys
from app.models import document, document_chunk, revoked_token, upload_idempotency, user  # noqa: F401

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                not POSTGRES_URL, reason="TEST_POSTGRES_URL is not set; CI provides it"
            ),
        ),
    ]
)
def database_url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
        return

    engine = create_engine(POSTGRES_URL)
    _drop_everything(engine)
    yield POSTGRES_URL
    _drop_everything(engine)
    engine.dispose()


def _drop_everything(engine):
    with engine.begin() as connection:
        metadata = MetaData()
        metadata.reflect(connection)
        metadata.drop_all(connection)


def _alembic(url):
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _create_legacy_schema(engine):
    """Tables as created by the original application, before auth hardening."""
    legacy = MetaData()
    Table(
        "users",
        legacy,
        Column("id", String, primary_key=True),
        Column("email", String, nullable=False, unique=True, index=True),
        Column("hashed_password", String, nullable=False),
        Column("created_at", DateTime),
    )
    Table(
        "documents",
        legacy,
        Column("id", String, primary_key=True),
        Column("user_id", String, ForeignKey("users.id"), nullable=False),
        Column("filename", String, nullable=False),
        Column("file_path", String, nullable=False),
        Column("file_size", Integer),
        Column("upload_date", DateTime),
        Column("status", String),
    )
    Table(
        "document_chunks",
        legacy,
        Column("id", String, primary_key=True),
        Column("document_id", String, ForeignKey("documents.id"), nullable=False),
        Column("chunk_index", Integer, nullable=False),
        Column("chunk_text", Text, nullable=False),
        Column("embedding", Text, nullable=False),
    )
    legacy.create_all(engine)


def _insert_sample_rows(engine):
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, hashed_password) VALUES ('u1', 'a@example.com', 'h')")
        )
        connection.execute(
            text(
                "INSERT INTO documents (id, user_id, filename, file_path, file_size, status) "
                "VALUES ('d1', 'u1', 'a.pdf', 'uploads/d1.pdf', 10, 'completed')"
            )
        )
        for index in range(3):
            connection.execute(
                text(f"INSERT INTO document_chunks ({_chunk_columns(connection)}) VALUES ({_chunk_values(connection)})"),
                {"id": f"c{index}", "document_id": "d1", "index": index},
            )


def _has_chunk_metadata(connection):
    columns = {column["name"] for column in inspect(connection).get_columns("document_chunks")}
    return "embedding_model" in columns


def _chunk_columns(connection):
    columns = "id, document_id, chunk_index, chunk_text, embedding"
    return columns + (", embedding_model, embedding_dim" if _has_chunk_metadata(connection) else "")


def _chunk_values(connection):
    values = ":id, :document_id, :index, 'text', '[1.0]'"
    return values + (", 'all-MiniLM-L6-v2', 384" if _has_chunk_metadata(connection) else "")


def _schema_differences(engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        return compare_metadata(context, Base.metadata)


def test_fresh_database_matches_models(database_url):
    command.upgrade(_alembic(database_url), "head")
    engine = create_engine(database_url)
    try:
        assert _schema_differences(engine) == []
    finally:
        engine.dispose()


def test_legacy_database_is_upgraded_without_losing_rows(database_url):
    engine = create_engine(database_url)
    try:
        _create_legacy_schema(engine)
        _insert_sample_rows(engine)

        command.upgrade(_alembic(database_url), "head")

        tables = set(inspect(engine).get_table_names())
        assert {"revoked_tokens", "upload_idempotency", "alembic_version"} <= tables
        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1
            assert connection.execute(text("SELECT COUNT(*) FROM documents")).scalar() == 1
            assert connection.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar() == 3
        assert _schema_differences(engine) == []
    finally:
        engine.dispose()


def test_current_create_all_database_is_upgraded(database_url):
    engine = create_engine(database_url)
    try:
        command.upgrade(_alembic(database_url), "0001")
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE alembic_version"))
        _insert_sample_rows(engine)

        command.upgrade(_alembic(database_url), "head")
        assert _schema_differences(engine) == []
    finally:
        engine.dispose()


def test_downgrade_and_upgrade_round_trip(database_url):
    config = _alembic(database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "0001")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        assert _schema_differences(engine) == []
    finally:
        engine.dispose()


def test_integrity_migration_refuses_duplicate_chunk_indexes(database_url):
    engine = create_engine(database_url)
    try:
        command.upgrade(_alembic(database_url), "0001")
        _insert_sample_rows(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO document_chunks (id, document_id, chunk_index, chunk_text, embedding) "
                    "VALUES ('dup', 'd1', 0, 'text', '[1.0]')"
                )
            )
        with pytest.raises(RuntimeError, match="repeated chunk indexes"):
            command.upgrade(_alembic(database_url), "head")
    finally:
        engine.dispose()


def test_deleting_a_document_cascades_to_its_chunks(database_url):
    command.upgrade(_alembic(database_url), "head")
    engine = create_engine(database_url)
    if database_url.startswith("sqlite"):
        enable_sqlite_foreign_keys(engine)
    try:
        _insert_sample_rows(engine)
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM documents WHERE id = 'd1'"))
            remaining = connection.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar()
        assert remaining == 0
    finally:
        engine.dispose()


def test_chunks_cannot_reference_missing_documents(database_url):
    command.upgrade(_alembic(database_url), "head")
    engine = create_engine(database_url)
    if database_url.startswith("sqlite"):
        enable_sqlite_foreign_keys(engine)
    try:
        with pytest.raises(Exception, match="(?i)foreign key"):
            with engine.begin() as connection:
                connection.execute(
                    text(f"INSERT INTO document_chunks ({_chunk_columns(connection)}) VALUES ({_chunk_values(connection)})"),
                    {"id": str(uuid.uuid4()), "document_id": "missing", "index": 0},
                )
    finally:
        engine.dispose()


def test_ingestion_migration_reconciles_legacy_document_states(database_url):
    engine = create_engine(database_url)
    try:
        command.upgrade(_alembic(database_url), "0003")
        _insert_sample_rows(engine)  # d1: completed with three chunks
        with engine.begin() as connection:
            for document_id, status in [("d2", "completed"), ("d3", "uploaded"), ("d4", None)]:
                connection.execute(
                    text(
                        "INSERT INTO documents (id, user_id, filename, file_path, status) "
                        "VALUES (:id, 'u1', 'x.pdf', 'uploads/x.pdf', :status)"
                    ),
                    {"id": document_id, "status": status},
                )

        command.upgrade(_alembic(database_url), "head")

        with engine.connect() as connection:
            rows = dict(
                connection.execute(text("SELECT id, status FROM documents")).all()
            )
            counts = dict(connection.execute(text("SELECT id, chunk_count FROM documents")).all())
            message = connection.execute(
                text("SELECT error_message FROM documents WHERE id = 'd3'")
            ).scalar()
        assert rows == {"d1": "completed", "d2": "failed", "d3": "failed", "d4": "failed"}
        assert counts["d1"] == 3
        assert "Retry processing" in message
        assert _schema_differences(engine) == []
    finally:
        engine.dispose()
