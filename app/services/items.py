"""Добавление товаров — общая логика для бота и API."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Item, ItemList, User
from . import categorizer
from .link_parser import LinkPreview, fetch_preview, shop_name


def visible_to(user: User):
    """Условие «список виден этому участнику».

    Все списки своей семьи, кроме чужих личных. Одно правило на всё — API,
    бот и автоподбор категории, — чтобы личная категория нигде не протекла.
    """
    return (ItemList.household_id == user.household_id) & (
        ItemList.is_private.is_(False) | (ItemList.owner_id == user.id)
    )


def ordered(lists: list[ItemList]) -> list[ItemList]:
    """Родитель, сразу за ним его подкатегории — для меню и выпадающих списков."""
    children: dict[int, list[ItemList]] = {}
    for item_list in lists:
        if item_list.parent_id is not None:
            children.setdefault(item_list.parent_id, []).append(item_list)
    result: list[ItemList] = []
    for item_list in lists:
        if item_list.parent_id is None:
            result.append(item_list)
            result.extend(children.pop(item_list.id, []))
    for orphans in children.values():  # родитель скрыт — подкатегорию всё равно покажем
        result.extend(orphans)
    return result


async def visible_lists(
    session: AsyncSession, user: User, kind: str | None = None
) -> list[ItemList]:
    query = (
        select(ItemList)
        .options(selectinload(ItemList.parent), selectinload(ItemList.owner))
        .where(visible_to(user))
        .order_by(ItemList.kind, ItemList.position, ItemList.id)
    )
    if kind:
        query = query.where(ItemList.kind == kind)
    return ordered(list(await session.scalars(query)))


async def get_list(session: AsyncSession, user: User, list_id: int) -> ItemList | None:
    return await session.scalar(
        select(ItemList)
        .options(selectinload(ItemList.parent))
        .where(ItemList.id == list_id, visible_to(user))
    )


async def list_by_slug(
    session: AsyncSession, user: User, slug: str, kind: str = "shopping"
) -> ItemList | None:
    return await session.scalar(
        select(ItemList)
        .options(selectinload(ItemList.parent))
        .where(visible_to(user), ItemList.kind == kind, ItemList.slug == slug)
        .order_by(ItemList.id)
        .limit(1)
    )


async def fallback_list(session: AsyncSession, user: User) -> ItemList:
    """Куда класть товар, если категорию определить не удалось.

    «Разное», если семья его держит, иначе «Дом» — туда чаще всего и уходит
    всякая мелочь, иначе первая общая категория.
    """
    for slug in ("other", "home"):
        target = await list_by_slug(session, user, slug)
        if target is not None:
            return target
    target = await session.scalar(
        select(ItemList)
        .where(
            visible_to(user),
            ItemList.kind == "shopping",
            ItemList.parent_id.is_(None),
            ItemList.is_private.is_(False),
        )
        .order_by(ItemList.position)
        .limit(1)
    )
    if target is None:  # у семьи снесли все категории покупок — создаём заново
        target = ItemList(
            household_id=user.household_id, kind="shopping", slug="other",
            title="Разное", emoji="📦", position=99,
        )
        session.add(target)
        await session.flush()
    return target


# Если у семьи нет узкой категории, позиция уходит в более общую, а не в
# «Разное»: витамины без «Витаминов» — это всё ещё «Здоровье».
BROADER_SLUG = {"vitamins": "health"}


async def guessed_list(session: AsyncSession, user: User, slug: str) -> ItemList | None:
    while slug:
        target = await list_by_slug(session, user, slug)
        if target is not None:
            return target
        slug = BROADER_SLUG.get(slug)
    return None


async def pick_list_for(
    session: AsyncSession, user: User, preview: LinkPreview
) -> tuple[ItemList, bool]:
    """Подбирает категорию под товар. Второй элемент — уверен ли алгоритм."""
    guess = categorizer.guess_category(title=preview.title, url=preview.url)
    if guess.slug != "other":
        target = await guessed_list(session, user, guess.slug)
        if target is not None:
            return target, guess.confident
    return await fallback_list(session, user), False


async def add_item(
    session: AsyncSession,
    user: User,
    *,
    url: str | None = None,
    title: str | None = None,
    list_id: int | None = None,
    price=None,
    currency: str | None = None,
    note: str | None = None,
    priority: int = 0,
) -> tuple[Item, ItemList, bool]:
    """Создаёт товар. Если передана ссылка — подтягивает данные со страницы.

    Возвращает (товар, список, уверенность в автокатегории).
    """
    preview = LinkPreview(url=url or "", title=title)
    if url:
        preview = await fetch_preview(url)
        if title:
            preview.title = title

    confident = True
    target: ItemList | None = None
    if list_id is not None:
        target = await get_list(session, user, list_id)
    if target is None:
        if url:
            target, confident = await pick_list_for(session, user, preview)
        else:
            guess = categorizer.guess_category(title=title)
            target = (
                await guessed_list(session, user, guess.slug)
                if guess.slug != "other"
                else None
            ) or await fallback_list(session, user)
            confident = guess.confident

    item = Item(
        list_id=target.id,
        title=(preview.title or title or (shop_name(url) if url else "Без названия"))[:300],
        url=preview.url or url,
        image_url=preview.image_url,
        shop=preview.shop,
        price=price if price is not None else preview.price,
        currency=currency or preview.currency,
        note=note,
        priority=priority,
        created_by_id=user.id,
    )
    session.add(item)
    await session.commit()

    item = await session.scalar(
        select(Item).options(selectinload(Item.created_by)).where(Item.id == item.id)
    )
    return item, target, confident
