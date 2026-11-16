import asyncio

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.models import Base


def test_postgresql_engine_and_schema_compile() -> None:
    engine = create_async_engine("postgresql+asyncpg://localhost/tether")
    try:
        assert engine.dialect.name == "postgresql"
        dialect = postgresql.dialect()
        for table in Base.metadata.sorted_tables:
            str(CreateTable(table).compile(dialect=dialect))
            for index in table.indexes:
                str(CreateIndex(index).compile(dialect=dialect))
    finally:
        asyncio.run(engine.dispose())
