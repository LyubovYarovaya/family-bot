"""Чтение чека с фотографии: сумма, валюта, дата, магазин, категория.

Распознаёт Claude — модель смотрит на картинку и возвращает JSON. Это надёжнее
обычного OCR: чеки мятые, снятые под углом, на украинском с латиницей вперемешку,
а нам нужна не расшифровка всего текста, а несколько полей.

Без ключа ANTHROPIC_API_KEY сервис честно говорит, что выключен, — бот тогда
объясняет человеку, как включить, а не молчит.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import anthropic

from ..config import settings

log = logging.getLogger("family-bot.receipts")

# Категории, которые модель может предложить. Совпадают со slug'ами стартовых
# категорий трат — так подсказка сразу ложится на нужную запись в базе.
CATEGORY_SLUGS = (
    "car", "health", "pregnancy", "home", "food", "baby",
    "subscriptions", "clothes", "fun", "other",
)

PROMPT = f"""На фото — чек или квитанция. Извлеки данные и верни ТОЛЬКО JSON без пояснений и без markdown:
{{
  "total": число — итоговая сумма к оплате (не сдача, не промежуточный итог), либо null,
  "currency": код валюты ISO 4217 ("UAH", "USD", "EUR", "GBP", "PLN"...); "грн"/"₴" → "UAH"; либо null,
  "date": дата покупки в формате YYYY-MM-DD, либо null если не видно,
  "merchant": название магазина или заведения коротко (до 60 символов), либо null,
  "items": до 8 самых заметных позиций одной строкой через запятую, либо "",
  "category": одна из {list(CATEGORY_SLUGS)} — по содержимому чека.
    pregnancy — товары и услуги для беременности (витамины для беременных, УЗИ, анализы, гинеколог, роддом, бандаж).
    health — аптека, врачи, анализы вне беременности. baby — детское. food — продукты и еда.
    car — топливо, СТО, парковка. home — коммуналка, аренда, ремонт, хозтовары.
    subscriptions — связь и подписки. clothes — одежда и обувь. fun — кафе, кино, отпуск.
    other — если не подходит ничего.
  "confidence": число от 0 до 1 — насколько уверенно читается итог.
}}
Если это не чек — верни {{"total": null}}."""


@dataclass(slots=True)
class Receipt:
    total: Decimal | None
    currency: str | None
    date: dt.date | None
    merchant: str | None
    items: str
    category: str
    confidence: float

    @property
    def readable(self) -> bool:
        return self.total is not None and self.total > 0


def enabled() -> bool:
    return bool(settings.anthropic_api_key)


def _to_decimal(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(str(raw).replace(",", ".").replace(" ", ""))
    except (InvalidOperation, ValueError):
        return None
    return value.quantize(Decimal("0.01")) if value > 0 else None


def _to_date(raw) -> dt.date | None:
    if not raw:
        return None
    try:
        parsed = dt.date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None
    # Чек из будущего — ошибка распознавания года; берём сегодня.
    return parsed if parsed <= dt.date.today() else None


def _extract_json(text: str) -> dict:
    """Модель просили без markdown, но защищаемся от ```json``` на всякий случай."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("в ответе нет JSON")
    return json.loads(cleaned[start:end + 1])


async def read_receipt(image: bytes, mime: str = "image/jpeg") -> Receipt | None:
    """Возвращает распознанный чек или None, если распознать не удалось."""
    if not enabled():
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    try:
        response = await client.messages.create(
            model=settings.receipt_model,
            max_tokens=1024,
            # Задача простая и одношаговая — глубоко думать незачем, экономим.
            output_config={"effort": "low"},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": base64.standard_b64encode(image).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )
    except anthropic.AuthenticationError:
        log.error("Ключ ANTHROPIC_API_KEY не принят — чеки не распознаются")
        return None
    except anthropic.RateLimitError as error:
        log.warning("Лимит запросов к Claude: %s", error)
        return None
    except anthropic.APIStatusError as error:
        log.warning("Claude ответил ошибкой %s: %s", error.status_code, error.message)
        return None
    except anthropic.APIConnectionError as error:
        log.warning("Нет связи с Claude: %s", error)
        return None

    if response.stop_reason == "refusal":
        log.warning("Claude отказался читать чек: %s", response.stop_details)
        return None

    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        data = _extract_json(text)
    except (ValueError, json.JSONDecodeError) as error:
        log.warning("Не разобрала ответ модели (%s): %.200s", error, text)
        return None

    category = str(data.get("category") or "other").lower()
    if category not in CATEGORY_SLUGS:
        category = "other"
    currency = str(data.get("currency") or "").upper()[:3] or None

    return Receipt(
        total=_to_decimal(data.get("total")),
        currency=currency,
        date=_to_date(data.get("date")),
        merchant=(str(data.get("merchant") or "").strip()[:60] or None),
        items=str(data.get("items") or "").strip()[:300],
        category=category,
        confidence=float(data.get("confidence") or 0.0),
    )
