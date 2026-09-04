"""Курсы валют НБУ: приводим любые суммы к гривне.

Источник — официальный справочник Национального банка. Он бесплатный, без
ключей и лимитов, отдаёт курс всех валют к гривне на сегодня.

Курсы держим в памяти и обновляем раз в несколько часов: они меняются раз в
сутки, а ходить в банк на каждый запрос сводки незачем. Если банк недоступен,
работаем со старыми курсами — устаревший курс полезнее, чем пустое место.
Когда курсов нет совсем, функции возвращают None, и интерфейс просто не
показывает пересчёт, вместо того чтобы врать.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

import httpx

log = logging.getLogger("family-bot.rates")

NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
TTL = dt.timedelta(hours=6)
TIMEOUT = 10.0

# Сколько гривен стоит одна единица валюты. Гривна к самой себе — единица.
_rates: dict[str, float] = {"UAH": 1.0}
_fetched_at: dt.datetime | None = None
_updated_on: str | None = None
_lock = asyncio.Lock()


def _is_fresh() -> bool:
    return _fetched_at is not None and dt.datetime.now(dt.timezone.utc) - _fetched_at < TTL


async def refresh(force: bool = False) -> None:
    """Тянет свежие курсы. Молча оставляет старые, если банк не ответил."""
    global _fetched_at, _updated_on

    if _is_fresh() and not force:
        return

    async with _lock:
        if _is_fresh() and not force:  # пока ждали замок, кто-то уже обновил
            return
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(NBU_URL)
                response.raise_for_status()
                payload = response.json()
        except Exception as error:  # noqa: BLE001 — сеть, таймаут, мусор в ответе
            log.warning("Курсы НБУ не обновились: %s", error)
            return

        fresh = {"UAH": 1.0}
        for row in payload:
            code = str(row.get("cc") or "").upper()
            rate = row.get("rate")
            if code and isinstance(rate, (int, float)) and rate > 0:
                fresh[code] = float(rate)
                _updated_on = row.get("exchangedate") or _updated_on

        if len(fresh) > 1:
            _rates.update(fresh)
            _fetched_at = dt.datetime.now(dt.timezone.utc)
            log.info("Курсы НБУ обновлены: %d валют на %s", len(fresh), _updated_on)


async def to_uah(amount: float | None, currency: str | None) -> float | None:
    """Сумма в гривнах. None, если валюта незнакомая или курсов ещё нет."""
    if amount is None:
        return None
    code = (currency or "UAH").upper()
    if code == "UAH":
        return float(amount)
    await refresh()
    rate = _rates.get(code)
    return round(float(amount) * rate, 2) if rate else None


async def from_uah(amount: float | None, currency: str) -> float | None:
    """Обратный пересчёт: из гривен в указанную валюту."""
    if amount is None:
        return None
    code = currency.upper()
    if code == "UAH":
        return float(amount)
    await refresh()
    rate = _rates.get(code)
    return round(float(amount) / rate, 2) if rate else None


def to_uah_cached(amount: float | None, currency: str | None) -> float | None:
    """То же, но без похода в сеть — по уже загруженным курсам.

    Нужен сериализаторам: они синхронные и вызываются в циклах. Кэш греется
    на старте приложения и в списочных ручках; пока он пуст, возвращаем None
    и пересчёт просто не показывается.
    """
    if amount is None:
        return None
    code = (currency or "UAH").upper()
    if code == "UAH":
        return None  # пересчитывать гривну в гривну незачем
    rate = _rates.get(code)
    return round(float(amount) * rate, 2) if rate else None


def known(currency: str | None) -> bool:
    return (currency or "UAH").upper() in _rates


def updated_on() -> str | None:
    """Дата курсов в том виде, в каком её отдаёт банк, — для подписи в сводке."""
    return _updated_on
