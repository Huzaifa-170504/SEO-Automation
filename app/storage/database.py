from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.storage.models import Base

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./data/seo_automation.db",
)

# Ensure the local data directory exists for SQLite.
if DATABASE_URL.startswith("sqlite+aiosqlite:///./"):
    Path("data").mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
)


if DATABASE_URL.startswith("sqlite+aiosqlite://"):

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(
        dbapi_connection: object,
        connection_record: object,
    ) -> None:
        """Enable SQLite foreign-key enforcement for every connection."""
        del connection_record

        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create tables and apply the small, backwards-compatible local migrations."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(_migrate_schema)


def _migrate_schema(sync_connection: object) -> None:
    """Keep existing SQLite installations aligned with the current ORM schema."""
    inspector = inspect(sync_connection)
    if "workflow_runs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("workflow_runs")}
    if "requester_id" not in columns:
        sync_connection.execute(
            text("ALTER TABLE workflow_runs ADD COLUMN requester_id VARCHAR(100)")
        )
    workflow_additions = {
        "current_agent": "VARCHAR(100)",
        "revision_count": "INTEGER NOT NULL DEFAULT 0",
        "technical_retry_count": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, sql_type in workflow_additions.items():
        if name not in columns:
            sync_connection.execute(
                text(f"ALTER TABLE workflow_runs ADD COLUMN {name} {sql_type}")
            )
    sync_connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_workflow_requester_created "
            "ON workflow_runs (requester_id, created_at)"
        )
    )
    tables = set(inspector.get_table_names())
    if "content_jobs" in tables:
        job_columns = {
            column["name"] for column in inspector.get_columns("content_jobs")
        }
        additions = {
            "requester_id": "VARCHAR(100)",
            "max_revisions": "INTEGER NOT NULL DEFAULT 3",
            "technical_retry_count": "INTEGER NOT NULL DEFAULT 0",
            "previous_review_status": "VARCHAR(30)",
            "revision_target": "VARCHAR(100)",
            "revision_reason": "TEXT",
        }
        for name, sql_type in additions.items():
            if name not in job_columns:
                sync_connection.execute(
                    text(f"ALTER TABLE content_jobs ADD COLUMN {name} {sql_type}")
                )
        sync_connection.execute(
            text(
                "UPDATE content_jobs SET requester_id = "
                "(SELECT requester_id FROM workflow_runs "
                "WHERE workflow_runs.id = content_jobs.audit_run_id) "
                "WHERE requester_id IS NULL"
            )
        )
        sync_connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_content_jobs_requester_id "
                "ON content_jobs (requester_id)"
            )
        )
    if "content_reviews" in tables:
        review_columns = {
            column["name"] for column in inspector.get_columns("content_reviews")
        }
        additions = {
            "revision_number": "INTEGER NOT NULL DEFAULT 0",
            "overall_score": "FLOAT",
        }
        for name, sql_type in additions.items():
            if name not in review_columns:
                sync_connection.execute(
                    text(f"ALTER TABLE content_reviews ADD COLUMN {name} {sql_type}")
                )


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Provide a database session with automatic cleanup."""
    async with SessionFactory() as session:
        yield session


async def close_db() -> None:
    """Dispose of the database engine and its connections."""
    await engine.dispose()
