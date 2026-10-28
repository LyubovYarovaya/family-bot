from decimal import Decimal

from app.services.categorizer import guess_category, guess_expense_category
from app.services.link_parser import clean_url, extract_urls, parse_html
from app.services.quick_expense import parse_expense


def test_category_by_title():
    assert guess_category("Коляска 2 в 1 Anex", "https://shop.ua/p/123").slug == "baby"
    assert guess_category("Ноутбук ASUS Vivobook 15").slug == "tech"
    assert guess_category("Сковорода Tefal 28 см").slug == "home"
    assert guess_category("Комплект постельного белья сатин").slug == "home"
    assert guess_category("Настольная лампа для спальни").slug == "home"


def test_category_by_url_when_title_is_useless():
    guess = guess_category("Товар", "https://rozetka.com.ua/detskie-kolyaski/c80253/")
    assert guess.slug == "baby"


def test_unknown_category_is_not_confident():
    guess = guess_category("Какая-то штука")
    assert guess.slug == "other"
    assert not guess.confident


def test_expense_categories():
    assert guess_expense_category("бензин на трассе") == "car"
    assert guess_expense_category("аптека витамины") == "health"
    assert guess_expense_category("netflix подписка") == "subscriptions"


def test_extract_and_clean_urls():
    text = "смотри https://shop.ua/item?utm_source=tg&id=5 вот такое"
    urls = extract_urls(text)
    assert urls == ["https://shop.ua/item?utm_source=tg&id=5"]
    assert clean_url(urls[0]) == "https://shop.ua/item?id=5"


def test_parse_html_reads_open_graph():
    html = """
    <html><head>
      <meta property="og:title" content="Робот-пылесос Dreame L10">
      <meta property="og:image" content="//cdn.shop/img.jpg">
      <meta property="product:price:amount" content="12 499,00">
      <meta property="product:price:currency" content="UAH">
    </head><body></body></html>
    """
    preview = parse_html(html, "https://shop.ua/p/1")
    assert preview.title == "Робот-пылесос Dreame L10"
    assert preview.image_url == "https://cdn.shop/img.jpg"
    assert preview.price == Decimal("12499.00")
    assert preview.currency == "UAH"
    assert preview.shop == "shop.ua"


def test_parse_html_reads_json_ld():
    html = """
    <html><head><script type="application/ld+json">
      {"@type": "Product", "name": "Кроватка Ikea",
       "offers": {"@type": "Offer", "price": "3499.50", "priceCurrency": "UAH"}}
    </script></head><body></body></html>
    """
    preview = parse_html(html, "https://ikea.ua/p/2")
    assert preview.title == "Кроватка Ikea"
    assert preview.price == Decimal("3499.50")


def test_title_falls_back_when_og_title_is_just_the_domain():
    """Магазин прописал в og:title имя сайта — берём осмысленный заголовок ниже."""
    html = """
    <html><head>
      <meta property="og:title" content="jura.com.ua">
      <title>JURA - Кавоварки та аксесуари</title>
    </head><body><h1>Кавомашина JURA E8</h1></body></html>
    """
    preview = parse_html(html, "https://jura.com.ua/kavomashyny/")
    assert preview.title == "JURA - Кавоварки та аксесуари"


def test_title_falls_back_to_url_slug():
    """Ни разметки, ни заголовка — собираем имя из адреса, а не оставляем пусто."""
    preview = parse_html("<html><head></head><body></body></html>",
                         "https://shop.ua/kava/jura-e8-piano-black/")
    assert preview.title == "Jura e8 piano black"


def test_health_category():
    assert guess_category("Витамины D3 K2 90 капсул").slug == "health"
    assert guess_category("Тонометр автоматический на плечо").slug == "health"


def test_quick_expense():
    parsed = parse_expense("450 бензин")
    assert parsed.amount == Decimal("450")
    assert parsed.category_slug == "car"
    assert parsed.period == "once"

    parsed = parse_expense("1 200,50 грн аптека ежемесячная")
    assert parsed.amount == Decimal("1200.50")
    assert parsed.currency == "UAH"
    assert parsed.period == "monthly"
    assert parsed.category_slug == "health"

    parsed = parse_expense("90 usd страховка машины ежегодная")
    assert parsed.currency == "USD"
    assert parsed.period == "yearly"

    assert parse_expense("просто текст") is None


def test_pregnancy_expense_category():
    assert guess_expense_category("витамины для беременных элевит") == "pregnancy"
    assert guess_expense_category("узи скрининг 12 недель беременности") == "pregnancy"
    # обычная аптека остаётся здоровьем
    assert guess_expense_category("аптека нурофен") == "health"


def test_receipt_parsing_tolerates_markdown_and_junk():
    """Модель просили чистый JSON, но ответ может прийти в ```json``` — не падаем."""
    from app.services.receipts import _extract_json, _to_date, _to_decimal
    import datetime as dt

    fenced = "```json" + chr(10) + '{"total": "1 299,50", "currency": "грн"}' + chr(10) + "```"
    data = _extract_json(fenced)
    assert _to_decimal(data["total"]) == 1299.50
    assert _to_decimal("не число") is None
    assert _to_decimal(-5) is None
    assert _to_date("2026-09-01") == dt.date(2026, 9, 1)
    assert _to_date("2099-01-01") is None   # чек из будущего — ошибка года
    assert _to_date("вчера") is None


def test_receipt_disabled_without_key(monkeypatch):
    """Без ключа сервис выключен и честно возвращает None, а не падает."""
    import asyncio
    from app.services import receipts
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert receipts.enabled() is False
    assert asyncio.run(receipts.read_receipt(b"not-an-image")) is None


def test_clothes_and_cosmetics_categories():
    assert guess_category("Куртка демисезонная мужская").slug == "clothes"
    assert guess_category("Кроссовки Nike Air Max").slug == "clothes"
    assert guess_category("Сыворотка с ниацинамидом The Ordinary").slug == "cosmetics"
    assert guess_category("Кондиционер для волос").slug == "cosmetics"
    assert guess_category("Товар", "https://makeup.com.ua/product/123/").slug == "cosmetics"


def test_receipt_caption_picks_category():
    from types import SimpleNamespace

    from app.bot.handlers import _category_from_caption

    categories = [
        SimpleNamespace(slug="health", title="Здоровье"),
        SimpleNamespace(slug="pregnancy", title="Беременность"),
        SimpleNamespace(slug="food", title="Продукты"),
    ]
    assert _category_from_caption("беременность", categories).slug == "pregnancy"
    assert _category_from_caption("Беремен", categories).slug == "pregnancy"
    assert _category_from_caption("скрининг", categories).slug == "pregnancy"
    assert _category_from_caption("", categories) is None
    assert _category_from_caption("что-то", categories) is None
