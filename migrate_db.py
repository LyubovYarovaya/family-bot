"""Разовый перенос данных из локального SQLite в базу на хостинге.

Запуск (адрес берётся во вкладке Connect у сервиса Postgres на Railway,
нужен именно ВНЕШНИЙ адрес — тот, что с доменом proxy.rlwy.net):

    python migrate_db.py "postgresql://user:pass@host:port/railway"

По умолчанию читает ./family.db. Другой источник — вторым аргументом.

Что делает: создаёт таблицы в целевой базе, если их ещё нет, и переносит
строки таблица за таблицей в порядке зависимостей, сохраняя id — иначе
разъедутся ссылки между списками, товарами и тратами. В конце подтягивает
счётчики последовательностей, чтобы Postgres не начал выдавать id с единицы
и не упёрся в уже занятые.

Скрипт не трогает исходную базу и отказывается работать, если в целевой уже
есть данные: повторный запуск создал бы дубликаты.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import (
    Base,
    Expense,
    ExpenseCategory,
    Household,
    Item,
    ItemList,
    User,
)

# Порядок важен: сначала то, на что ссылаются, потом то, что ссылается.
TABLES_IN_ORDER = [Household, User, ItemList, Item, ExpenseCategory, Expense]


def _normalize(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


async def migrate(source_path: Path, target_url: str) -> None:
    if not source_path.exists():
        raise SystemExit(f"Не нашла базу {source_path}")

    source = create_async_engine(f"sqlite+aiosqlite:///{source_path}")
    target = create_async_engine(_normalize(target_url))

    try:
        async with target.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Не льём поверх существующих данных — иначе получим дубли.
        async with target.connect() as conn:
            for model in TABLES_IN_ORDER:
                count = await conn.scalar(select(func.count()).select_from(model))
                if count:
                    raise SystemExit(
                        f"В целевой базе уже есть данные ({model.__tablename__}: {count} строк). "
                        "Перенос отменён, чтобы не наделать дублей."
                    )

        moved: dict[str, int] = {}
        for model in TABLES_IN_ORDER:
            async with source.connect() as src:
                rows = (await src.execute(select(model))).mappings().all()
            if not rows:
                moved[model.__tablename__] = 0
                continue
            async with target.begin() as dst:
                await dst.execute(insert(model), [dict(row) for row in rows])
            moved[model.__tablename__] = len(rows)

        # id переносили как есть, поэтому счётчики последовательностей отстали:
        # без этого Postgres выдаст следующей записи id=1 и упрётся в занятый.
        # У SQLite последовательностей нет — там шаг не нужен.
        if target.dialect.name == "postgresql":
            async with target.begin() as conn:
                for model in TABLES_IN_ORDER:
                    table = model.__tablename__
                    await conn.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
                        )
                    )

        print("Перенесено:")
        for table, count in moved.items():
            print(f"  {table:20} {count}")
    finally:
        await source.dispose()
        await target.dispose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    target_url = sys.argv[1]
    source = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("family.db")
    asyncio.run(migrate(source, target_url))
