from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    tg_id: int
    name: str


class MeOut(BaseModel):
    user: UserOut
    household_id: int
    household_title: str
    invite_code: str
    invite_url: str
    members: list[UserOut]
    currency: str


class ListOut(BaseModel):
    id: int
    kind: str
    slug: str
    title: str
    emoji: str
    owner_id: int | None = None
    owner_name: str | None = None
    position: int
    is_shared: bool
    share_url: str | None = None
    hide_reservations_from_owner: bool = False
    show_prices_to_guests: bool = True
    active_count: int = 0
    bought_count: int = 0
    total_price: float | None = None


class ListCreate(BaseModel):
    kind: str = Field(default="shopping", pattern="^(shopping|wishlist)$")
    title: str
    emoji: str = "📦"
    personal: bool = False


class ListUpdate(BaseModel):
    title: str | None = None
    emoji: str | None = None
    position: int | None = None
    is_shared: bool | None = None
    hide_reservations_from_owner: bool | None = None
    show_prices_to_guests: bool | None = None


class ItemOut(BaseModel):
    id: int
    list_id: int
    title: str
    url: str | None = None
    image_url: str | None = None
    shop: str | None = None
    price: float | None = None
    currency: str | None = None
    # Та же цена в гривне — заполняется, только если валюта не гривна.
    price_uah: float | None = None
    note: str | None = None
    priority: int = 0
    status: str = "active"
    created_by: str | None = None
    created_at: dt.datetime | None = None
    is_reserved: bool = False


class ItemCreate(BaseModel):
    list_id: int | None = None
    url: str | None = None
    title: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    note: str | None = None
    priority: int = 0


class ItemUpdate(BaseModel):
    title: str | None = None
    url: str | None = None
    image_url: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    note: str | None = None
    priority: int | None = None
    status: str | None = Field(default=None, pattern="^(active|bought)$")
    list_id: int | None = None


class ExpenseCategoryOut(BaseModel):
    id: int
    slug: str
    title: str
    emoji: str
    position: int


class ExpenseCategoryCreate(BaseModel):
    title: str
    emoji: str = "💸"


class ExpenseOut(BaseModel):
    id: int
    title: str
    amount: float
    currency: str
    period: str
    spent_on: dt.date
    note: str | None = None
    is_template: bool = False
    category_id: int | None = None
    category_title: str | None = None
    category_emoji: str | None = None
    created_by: str | None = None


class ExpenseCreate(BaseModel):
    amount: Decimal
    title: str = ""
    currency: str | None = None
    period: str = Field(default="once", pattern="^(once|monthly|quarterly|yearly)$")
    spent_on: dt.date | None = None
    note: str | None = None
    category_id: int | None = None
    is_template: bool = False


class ExpenseUpdate(BaseModel):
    amount: Decimal | None = None
    title: str | None = None
    currency: str | None = None
    period: str | None = Field(default=None, pattern="^(once|monthly|quarterly|yearly)$")
    spent_on: dt.date | None = None
    note: str | None = None
    category_id: int | None = None


class SummaryBucket(BaseModel):
    key: str
    title: str
    emoji: str = ""
    total: float
    count: int


class SummaryOut(BaseModel):
    date_from: dt.date
    date_to: dt.date
    currency: str
    total: float
    # Тот же итог во второй валюте плюс дата курса, по которому считали.
    total_secondary: float | None = None
    secondary_currency: str | None = None
    rates_date: str | None = None
    # Валюты, курс которых получить не вышло: их суммы в итог не попали.
    unconverted: list[str] = []
    by_category: list[SummaryBucket]
    by_period: list[SummaryBucket]
    by_month: list[SummaryBucket]
    by_currency: list[SummaryBucket]
    planned_monthly: float
    planned_quarterly: float
    planned_yearly: float


class LinkPreviewOut(BaseModel):
    url: str
    title: str | None = None
    image_url: str | None = None
    price: float | None = None
    currency: str | None = None
    shop: str | None = None
    suggested_list_id: int | None = None
    suggested_list_title: str | None = None


class PublicItemOut(BaseModel):
    id: int
    title: str
    url: str | None = None
    image_url: str | None = None
    price: float | None = None
    currency: str | None = None
    # Та же цена в гривне — заполняется, только если валюта не гривна.
    price_uah: float | None = None
    note: str | None = None
    priority: int = 0
    status: str = "active"
    is_reserved: bool = False
    mine: bool = False


class PublicListOut(BaseModel):
    title: str
    emoji: str
    kind: str
    owner_name: str | None = None
    household_title: str
    hide_from_owner: bool = False
    items: list[PublicItemOut]


class ReserveIn(BaseModel):
    # Имя необязательно: показываем только сам факт брони, без «кто».
    # Поле оставлено на случай, если захочется вернуть подписи.
    name: str | None = Field(default=None, max_length=80)
    secret: str | None = None


class UnreserveIn(BaseModel):
    secret: str


class ReserveOut(BaseModel):
    ok: bool
    secret: str | None = None
