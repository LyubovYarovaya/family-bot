from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Полноценных миграций в проекте нет: create_all создаёт недостающие таблицы,
# но НЕ дописывает новые колонки в уже существующие. Поэтому каждое новое поле
# добавляем сюда — иначе на боевой базе приложение падает на первом же запросе.
#
# Формат: (таблица, колонка, тип для ALTER, запрос для заполнения старых строк).
# Только добавление — ничего не удаляем и не переименовываем.
NEW_COLUMNS: list[tuple[str, str, str, str | None]] = [
    (
        "lists",
        "show_prices_to_guests",
        "BOOLEAN NOT NULL DEFAULT TRUE",
        # У вишлистов цены от гостей прячем: список подарков — не прайс-лист.
        # В категориях покупок цены гостям полезны, там оставляем как было.
        "UPDATE lists SET show_prices_to_guests = FALSE WHERE kind = 'wishlist'",
    ),
]


def _add_missing_columns(connection) -> None:
    existing_tables = set(inspect(connection).get_table_names())
    for table, column, ddl, backfill in NEW_COLUMNS:
        if table not in existing_tables:
            continue  # таблицу только что создал create_all — колонка уже там
        columns = {row["name"] for row in inspect(connection).get_columns(table)}
        if column in columns:
            continue
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        if backfill:
            connection.execute(text(backfill))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
