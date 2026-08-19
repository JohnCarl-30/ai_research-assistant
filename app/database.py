from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    import app.models  # noqa: F401 — ensure models register with Base.metadata

    async with engine.begin() as conn:
        is_postgres = conn.dialect.name == "postgresql"

        # The extension must exist before create_all emits a VECTOR column.
        if is_postgres:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        await conn.run_sync(Base.metadata.create_all)

        if is_postgres:
            # HNSW over cosine distance. Declared here rather than in
            # __table_args__ because the access method is Postgres-only and
            # would break create_all on SQLite in tests.
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_chunks_embedding_hnsw "
                    "ON job_chunks USING hnsw (embedding vector_cosine_ops)"
                )
            )
