"""Разовые переносы данных на боевой базе.

Схему (таблицы, колонки) достраивает db.init_db. Здесь — переделки самого
содержимого, которые нужно выполнить ровно один раз: каждая отмечается
в таблице app_migrations и при следующих стартах пропускается. Иначе,
например, удалённая руками категория воскресала бы после каждой выкатки.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal
from ..models import AppliedMigration, ExpenseCategory, Item, ItemList, User

log = logging.getLogger("family-bot.migrations")


# --- Раскладка категорий покупок, октябрь 2026 ---------------------------------
#
# Было: Техника, Кухня, Квартира, Текстиль, Baby, Здоровье, Разное.
# Стало: Техника, Дом, Baby, Одежда (Аркадий, Любовь), Здоровье (Аркадий,
# Любовь), Косметика — личная, видна только Любови. В тратах — «Беременность».
#
# Ничего не удаляется вместе с товарами: «Кухня», «Текстиль» и «Разное»
# сначала отдают свои позиции в «Дом» и только потом исчезают. Если такую
# категорию уже переименовали руками — значит, она нужна, её не трогаем.

CATEGORIES_V2 = "2026-10-categories-v2"

LAYOUT: list[tuple[str, str, str, tuple[str, ...], bool]] = [
    # slug, название, эмодзи, подкатегории, личная
    ("tech", "Техника", "🔌", (), False),
    ("home", "Дом", "🏠", (), False),
    ("baby", "Baby", "🍼", (), False),
    ("clothes", "Одежда", "👗", ("Аркадий", "Любовь"), False),
    ("health", "Здоровье", "🩺", ("Аркадий", "Любовь"), False),
    ("cosmetics", "Косметика", "💄", (), True),
]

MERGE_INTO_HOME = {"kitchen": "Кухня", "textile": "Текстиль", "other": "Разное"}

CHILD_SLUGS = {"Аркадий": "arkadiy", "Любовь": "lyubov"}

# Как Любовь может быть подписана в Telegram. Имя берётся из профиля, поэтому
# проверяем и кириллицу, и латиницу во всех ходовых транслитерациях.
OWNER_NAME_HINTS = ("люб", "lyub", "liub", "luib", "lubov", "lyuba")


def _looks_like_owner(user: User) -> bool:
    name = f"{user.first_name or ''} {user.username or ''}".lower()
    return any(hint in name for hint in OWNER_NAME_HINTS)


async def _members(session: AsyncSession, household_id: int) -> list[User]:
    return list(
        await session.scalars(
            select(User).where(User.household_id == household_id).order_by(User.id)
        )
    )


async def _relayout_household(
    session: AsyncSession, household_id: int, owner: User | None
) -> list[str]:
    """Перекладывает категории одной семьи. owner — хозяйка личной «Косметики».

    Без owner подкатегории с именами и личная категория не создаются: это
    раскладка конкретной семьи, другим она ни к чему.
    """
    notes: list[str] = []
    lists = list(
        await session.scalars(
            select(ItemList)
            .where(
                ItemList.household_id == household_id,
                ItemList.kind == "shopping",
                ItemList.parent_id.is_(None),
            )
            .order_by(ItemList.position, ItemList.id)
        )
    )
    by_slug: dict[str, ItemList] = {}
    for item_list in lists:
        by_slug.setdefault(item_list.slug, item_list)

    def create(slug: str, title: str, emoji: str, **extra) -> ItemList:
        created = ItemList(
            household_id=household_id, kind="shopping", slug=slug,
            title=title, emoji=emoji, **extra,
        )
        session.add(created)
        notes.append(f"создана «{title}»")
        return created

    # «Квартира» становится «Домом»; если её нет — заводим.
    home = by_slug.get("home")
    if home is None:
        home = create("home", "Дом", "🏠")
        await session.flush()
        by_slug["home"] = home
    elif home.title != "Дом":
        notes.append(f"«{home.title}» → «Дом»")
        home.title = "Дом"

    # Кухня, текстиль и разное съезжают в «Дом».
    for slug, default_title in MERGE_INTO_HOME.items():
        old = by_slug.pop(slug, None)
        if old is None:
            continue
        if old.title != default_title:
            notes.append(f"«{old.title}» переименована руками — оставлена как есть")
            continue
        moved = await session.execute(
            update(Item).where(Item.list_id == old.id).values(list_id=home.id)
        )
        await session.delete(old)
        notes.append(f"«{old.title}» влита в «Дом» ({moved.rowcount} поз.)")
    await session.flush()

    personal = owner is not None
    for position, (slug, title, emoji, children, private) in enumerate(LAYOUT):
        target = by_slug.get(slug)
        if target is None:
            target = create(slug, title, emoji)
            by_slug[slug] = target
        target.position = position
        if private and personal:
            target.is_private, target.owner_id = True, owner.id
            notes.append(f"«{target.title}» видна только {owner.display_name}")
        await session.flush()

        if not personal:
            continue
        existing = set(
            await session.scalars(select(ItemList.title).where(ItemList.parent_id == target.id))
        )
        for index, child_title in enumerate(children):
            if child_title in existing:
                continue
            session.add(
                ItemList(
                    household_id=household_id,
                    kind="shopping",
                    slug=f"{slug}-{CHILD_SLUGS.get(child_title, index)}",
                    title=child_title,
                    emoji=emoji,
                    parent_id=target.id,
                    is_private=target.is_private,
                    owner_id=target.owner_id if target.is_private else None,
                    position=index,
                )
            )
            notes.append(f"«{target.title} · {child_title}»")

    # Свои категории семьи остаются, просто встают после основных.
    layout_slugs = {slug for slug, *_ in LAYOUT}
    custom = [l for l in lists if l.slug not in layout_slugs and l.slug not in MERGE_INTO_HOME]
    for offset, item_list in enumerate(custom):
        item_list.position = len(LAYOUT) + 10 + offset
    await session.flush()
    return notes


async def _ensure_pregnancy_expenses(session: AsyncSession, household_id: int) -> str | None:
    """Категория трат «Беременность» сразу после «Здоровья»."""
    categories = list(
        await session.scalars(
            select(ExpenseCategory)
            .where(ExpenseCategory.household_id == household_id)
            .order_by(ExpenseCategory.position, ExpenseCategory.id)
        )
    )
    if any(c.slug == "pregnancy" for c in categories):
        return None
    health = next((c for c in categories if c.slug == "health"), None)
    position = (health.position + 1) if health else len(categories)
    for category in categories:
        if category.position >= position:
            category.position += 1
    session.add(
        ExpenseCategory(
            household_id=household_id, slug="pregnancy",
            title="Беременность", emoji="🤰", position=position,
        )
    )
    return "в тратах добавлена «Беременность»"


async def apply_categories_v2(session: AsyncSession) -> list[str]:
    """Новая раскладка для всех семей, где кто-то есть. Возвращает журнал."""
    household_ids = list(
        await session.scalars(
            select(User.household_id).where(User.household_id.is_not(None)).distinct()
        )
    )
    members_by_household = {hid: await _members(session, hid) for hid in household_ids}

    # Хозяйку ищем по имени. Если по имени не нашлась, но семья на базе одна —
    # это точно наша, и хозяйка та, кто завела бота первой.
    owners: dict[int, User | None] = {
        hid: next((m for m in members if _looks_like_owner(m)), None)
        for hid, members in members_by_household.items()
    }
    if len(household_ids) == 1 and owners[household_ids[0]] is None:
        owners[household_ids[0]] = members_by_household[household_ids[0]][0]

    journal: list[str] = []
    for hid in sorted(household_ids):
        notes = await _relayout_household(session, hid, owners[hid])
        pregnancy = await _ensure_pregnancy_expenses(session, hid)
        if pregnancy:
            notes.append(pregnancy)
        names = ", ".join(m.display_name for m in members_by_household[hid])
        journal.append(f"семья {hid} ({names}): " + ("; ".join(notes) or "без изменений"))
    return journal


# --- «Витамины» отдельной категорией, октябрь 2026 -------------------------------
#
# Любовь завела категорию руками в приложении, и у неё случайный ярлык вида
# custom123 — автоподбор такую не находит. Даём ей постоянный ярлык vitamins.
# Если категории нет, создаём её сразу после «Здоровья». Порядок уже
# существующей не трогаем: его могли выставить руками.

VITAMINS = "2026-10-vitamins"


async def apply_vitamins(session: AsyncSession) -> list[str]:
    household_ids = list(
        await session.scalars(
            select(User.household_id).where(User.household_id.is_not(None)).distinct()
        )
    )
    journal: list[str] = []
    for hid in sorted(household_ids):
        lists = list(
            await session.scalars(
                select(ItemList)
                .where(
                    ItemList.household_id == hid,
                    ItemList.kind == "shopping",
                    ItemList.parent_id.is_(None),
                )
                .order_by(ItemList.position, ItemList.id)
            )
        )
        found = next((l for l in lists if l.slug == "vitamins"), None) or next(
            (l for l in lists if l.title.strip().lower() == "витамины"), None
        )
        if found is not None:
            if found.slug != "vitamins":
                journal.append(f"семья {hid}: «{found.title}» получила ярлык vitamins (был {found.slug})")
                found.slug = "vitamins"
            continue
        health = next((l for l in lists if l.slug == "health"), None)
        position = health.position + 1 if health else len(lists)
        for item_list in lists:
            if item_list.position >= position:
                item_list.position += 1
        session.add(
            ItemList(
                household_id=hid, kind="shopping", slug="vitamins",
                title="Витамины", emoji="💊", position=position,
            )
        )
        journal.append(f"семья {hid}: создана «Витамины»")
    await session.flush()
    return journal


MIGRATIONS = [(CATEGORIES_V2, apply_categories_v2), (VITAMINS, apply_vitamins)]


async def run_data_migrations() -> None:
    async with SessionLocal() as session:
        done = set(await session.scalars(select(AppliedMigration.name)))
        for name, migrate in MIGRATIONS:
            if name in done:
                continue
            journal = await migrate(session)
            session.add(AppliedMigration(name=name))
            await session.commit()
            for line in journal:
                log.info("%s: %s", name, line)
            log.info("%s: готово", name)
