import datetime as dt

import pytest

pytestmark = pytest.mark.asyncio


async def test_bootstrap_creates_default_lists(client):
    me = (await client.get("/api/me")).json()
    assert me["household_id"]

    lists = (await client.get("/api/lists")).json()
    shopping = {row["slug"] for row in lists if row["kind"] == "shopping"}
    assert {"tech", "kitchen", "home", "textile", "baby"} <= shopping

    wishlists = [row for row in lists if row["kind"] == "wishlist"]
    assert any(row["owner_id"] is None for row in wishlists)  # общий
    assert any(row["owner_id"] is not None for row in wishlists)  # личный

    categories = (await client.get("/api/expense-categories")).json()
    assert {"car", "health"} <= {row["slug"] for row in categories}


async def test_item_lands_in_guessed_category(client):
    created = (await client.post("/api/items", json={"title": "Автокресло Cybex"})).json()
    lists = (await client.get("/api/lists")).json()
    baby = next(row for row in lists if row["slug"] == "baby")
    assert created["list_id"] == baby["id"]

    items = (await client.get(f"/api/lists/{baby['id']}/items")).json()
    assert any(row["id"] == created["id"] for row in items)

    updated = (await client.patch(f"/api/items/{created['id']}", json={"status": "bought"})).json()
    assert updated["status"] == "bought"

    assert (await client.delete(f"/api/items/{created['id']}")).json() == {"ok": True}


async def test_expenses_and_summary(client):
    categories = (await client.get("/api/expense-categories")).json()
    car = next(row for row in categories if row["slug"] == "car")
    today = dt.date.today().isoformat()

    await client.post("/api/expenses", json={
        "amount": 450, "title": "бензин", "category_id": car["id"], "spent_on": today,
    })
    await client.post("/api/expenses", json={
        "amount": 1000, "title": "аренда", "period": "monthly", "is_template": True,
    })

    summary = (await client.get(f"/api/expenses/summary?date_from={today}&date_to={today}")).json()
    assert summary["total"] == 450
    assert summary["planned_monthly"] == 1000
    assert summary["by_category"][0]["title"] == "Машина"

    templates = (await client.get("/api/expenses?templates=true")).json()
    assert len(templates) == 1

    paid = (await client.post(f"/api/expenses/{templates[0]['id']}/pay", json={})).json()
    assert paid["amount"] == 1000 and paid["is_template"] is False


async def test_share_and_reserve_flow(client):
    lists = (await client.get("/api/lists")).json()
    baby = next(row for row in lists if row["slug"] == "baby")
    item = (await client.post("/api/items", json={"title": "Пеленальный столик", "list_id": baby["id"]})).json()

    shared = (await client.patch(f"/api/lists/{baby['id']}", json={"is_shared": True})).json()
    token = shared["share_url"].rsplit("/", 1)[-1]

    public = (await client.get(f"/api/public/{token}")).json()
    assert public["title"] == "Baby"
    assert any(row["id"] == item["id"] for row in public["items"])

    reserved = (await client.post(
        f"/api/public/{token}/items/{item['id']}/reserve",
        json={"name": "Оля", "secret": "guest-1"},
    )).json()
    assert reserved["ok"]

    conflict = await client.post(
        f"/api/public/{token}/items/{item['id']}/reserve",
        json={"name": "Ира", "secret": "guest-2"},
    )
    assert conflict.status_code == 409

    mine = (await client.get(f"/api/public/{token}?secret=guest-1")).json()
    booked = next(row for row in mine["items"] if row["id"] == item["id"])
    assert booked["is_reserved"] and booked["mine"]
    # Имя бронирующего наружу не отдаём вообще — виден только сам факт брони.
    assert "reserved_by" not in booked

    released = await client.post(
        f"/api/public/{token}/items/{item['id']}/unreserve", json={"secret": "guest-1"}
    )
    assert released.json()["ok"]

    await client.patch(f"/api/lists/{baby['id']}", json={"is_shared": False})
    assert (await client.get(f"/api/public/{token}")).status_code == 404


async def test_summary_converts_foreign_currencies(client, monkeypatch):
    """Траты в чужой валюте попадают в итог, приведённые к гривне.

    Курсы подставляем свои: тест не должен зависеть от банка и от сети.
    Считаем прирост, а не абсолютный итог, — база в тестах общая, и в месяце
    уже лежат траты из соседних проверок. Раньше траты в другой валюте молча
    выпадали из месяца целиком.
    """
    import datetime as dt

    from app.services import rates

    monkeypatch.setattr(rates, "_rates", {"UAH": 1.0, "GBP": 50.0, "USD": 40.0})
    monkeypatch.setattr(rates, "_fetched_at", dt.datetime.now(dt.timezone.utc))

    today = dt.date.today()
    first = today.replace(day=1)
    url = f"/api/expenses/summary?date_from={first}&date_to={today}"
    before = (await client.get(url)).json()["total"]

    for amount, currency in [(10, "GBP"), (100, "UAH")]:
        await client.post(
            "/api/expenses",
            json={"amount": amount, "currency": currency, "title": "подарок",
                  "period": "once", "spent_on": today.isoformat()},
        )

    summary = (await client.get(url)).json()
    # 10 GBP по курсу 50 = 500 грн, плюс 100 грн = 600.
    assert round(summary["total"] - before, 2) == 600
    assert summary["currency"] == "UAH"
    # Тот же итог в долларах, по курсу 40.
    assert summary["total_secondary"] == round(summary["total"] / 40, 2)
    assert summary["secondary_currency"] == "USD"
    assert summary["unconverted"] == []
    # Разбивка по валютам показывает исходные суммы, без пересчёта.
    assert {b["key"]: b["total"] for b in summary["by_currency"]}["GBP"] == 10


async def test_unknown_currency_is_reported_not_silently_dropped(client, monkeypatch):
    """Валюта без курса не попадает в итог, но о ней прямо сказано."""
    import datetime as dt

    from app.services import rates

    monkeypatch.setattr(rates, "_rates", {"UAH": 1.0})
    monkeypatch.setattr(rates, "_fetched_at", dt.datetime.now(dt.timezone.utc))

    today = dt.date.today()
    first = today.replace(day=1)
    await client.post(
        "/api/expenses",
        json={"amount": 7, "currency": "XYZ", "title": "загадка",
              "period": "once", "spent_on": today.isoformat()},
    )
    summary = (await client.get(
        f"/api/expenses/summary?date_from={first}&date_to={today}"
    )).json()
    assert "XYZ" in summary["unconverted"]


async def test_guests_do_not_see_wishlist_prices(client):
    """Вишлист по ссылке — не прайс-лист: цены гостям по умолчанию не видны."""
    lists = (await client.get("/api/lists")).json()
    wishlist = next(row for row in lists if row["kind"] == "wishlist")
    assert wishlist["show_prices_to_guests"] is False

    await client.post(
        "/api/items",
        json={"title": "Кофемашина", "price": 42000, "currency": "UAH", "list_id": wishlist["id"]},
    )
    shared = (await client.patch(f"/api/lists/{wishlist['id']}", json={"is_shared": True})).json()
    token = shared["share_url"].rsplit("/", 1)[-1]

    guest = (await client.get(f"/api/public/{token}")).json()["items"][0]
    assert guest["price"] is None and guest["currency"] is None
    # ...а семья цену видит по-прежнему.
    inside = (await client.get(f"/api/lists/{wishlist['id']}/items")).json()[0]
    assert inside["price"] == 42000

    # Захотели показать — показали.
    await client.patch(f"/api/lists/{wishlist['id']}", json={"show_prices_to_guests": True})
    assert (await client.get(f"/api/public/{token}")).json()["items"][0]["price"] == 42000


async def test_shopping_list_keeps_prices_for_guests(client):
    """В категориях покупок цена гостю полезна — там ничего не прячем."""
    lists = (await client.get("/api/lists")).json()
    shopping = next(row for row in lists if row["kind"] == "shopping")
    assert shopping["show_prices_to_guests"] is True


async def test_owner_sees_reservations_and_can_hide_them(client):
    """По умолчанию владелец видит, что подарок занят, — иначе купит его сам.

    Режим сюрприза остаётся, но включается вручную: тогда брони от владельца
    прячутся, а гости по-прежнему видят их друг у друга.
    """
    lists = (await client.get("/api/lists")).json()
    personal = next(row for row in lists if row["kind"] == "wishlist" and row["owner_id"])
    assert personal["hide_reservations_from_owner"] is False

    item = (await client.post("/api/items", json={"title": "Книга", "list_id": personal["id"]})).json()
    shared = (await client.patch(f"/api/lists/{personal['id']}", json={"is_shared": True})).json()
    token = shared["share_url"].rsplit("/", 1)[-1]
    await client.post(
        f"/api/public/{token}/items/{item['id']}/reserve", json={"secret": "g"}
    )

    # Гость видит бронь...
    public = (await client.get(f"/api/public/{token}")).json()
    assert public["items"][0]["is_reserved"] is True
    # ...и другой гость, без всякой авторизации, видит её тоже.
    other_guest = (await client.get(f"/api/public/{token}?secret=another")).json()
    assert other_guest["items"][0]["is_reserved"] is True
    assert other_guest["items"][0]["mine"] is False
    # ...и владелец теперь тоже.
    owner_view = (await client.get(f"/api/lists/{personal['id']}/items")).json()
    assert owner_view[0]["is_reserved"] is True
    assert "reserved_by" not in owner_view[0]

    # Включаем сюрприз — от владельца брони прячутся, от гостей нет.
    await client.patch(f"/api/lists/{personal['id']}", json={"hide_reservations_from_owner": True})
    hidden = (await client.get(f"/api/lists/{personal['id']}/items")).json()
    assert hidden[0]["is_reserved"] is False
    assert (await client.get(f"/api/public/{token}")).json()["items"][0]["is_reserved"] is True


async def test_auth_required_without_dev_id(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "dev_tg_id", None)
    assert (await client.get("/api/me")).status_code == 401
