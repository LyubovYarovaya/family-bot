from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

from aiogram.types import MenuButtonWebApp, Update, WebAppInfo
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import runtime
from .api.core import router as core_router
from .api.expenses import router as expenses_router
from .api.public import router as public_router
from .bot import COMMANDS, get_bot, get_dispatcher
from .config import settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("family-bot")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


async def _start_bot(app: FastAPI) -> None:
    if settings.bot_mode == "off" or not settings.bot_token:
        runtime.bot_error = (
            f"не с чем стартовать: BOT_MODE={settings.bot_mode!r}, "
            f"длина BOT_TOKEN={len(settings.bot_token)}"
        )
        log.warning("Бот не запущен: BOT_MODE=off или пустой BOT_TOKEN")
        return

    bot = get_bot()
    try:
        me = await bot.get_me()
    except Exception as error:
        # Неверный токен или нет интернета — не роняем весь процесс: веб-часть
        # пусть живёт, а человеку показываем внятную причину вместо трейсбека.
        runtime.bot_error = f"Telegram не ответил: {type(error).__name__}: {error}"
        log.error(
            "Не получилось подключиться к Telegram: %s\n"
            "Проверь BOT_TOKEN в .env и интернет, потом перезапусти. "
            "Веб-приложение пока работает, бот — нет.",
            error,
        )
        return
    runtime.bot_username = me.username
    runtime.bot_error = None
    await bot.set_my_commands(COMMANDS)

    # Кнопка «Меню» слева от поля ввода — постоянный вход в приложение.
    # Заодно она переезжает на новый адрес сама: при локальном запуске туннель
    # каждый раз выдаёт другой домен, и руками её в BotFather не наперенастраиваешься.
    if settings.base_url.startswith("https://"):
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Приложение", web_app=WebAppInfo(url=settings.webapp_url)
                )
            )
        except Exception as error:  # noqa: BLE001 — без кнопки меню бот всё равно работает
            log.warning("Не получилось настроить кнопку меню: %s", error)
    else:
        log.info("PUBLIC_URL не https — кнопку меню не ставлю, Telegram примет только https")

    log.info("Бот @%s готов, режим %s", me.username, settings.bot_mode)

    if settings.bot_mode == "webhook":
        await bot.set_webhook(
            f"{settings.base_url}/telegram/webhook",
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
        )
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        dispatcher = get_dispatcher()
        app.state.polling_task = asyncio.create_task(dispatcher.start_polling(bot))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _start_bot(app)
    try:
        yield
    finally:
        task = getattr(app.state, "polling_task", None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        with contextlib.suppress(Exception):
            await get_bot().session.close()


app = FastAPI(title="Family Hub", lifespan=lifespan, docs_url="/api/docs")
app.include_router(core_router)
app.include_router(expenses_router)
app.include_router(public_router)


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    if x_telegram_bot_api_secret_token != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="bad secret")
    update = Update.model_validate(await request.json(), context={"bot": get_bot()})
    await get_dispatcher().feed_update(get_bot(), update)
    return JSONResponse({"ok": True})


@app.get("/healthz")
async def healthz() -> dict:
    """Состояние сервиса. Про токен отдаём только длину — само значение секрет."""
    return {
        "ok": True,
        "bot": runtime.bot_username,
        "bot_error": runtime.bot_error,
        "mode": settings.bot_mode,
        "token_len": len(settings.bot_token),
        "public_url": settings.base_url,
        "db": settings.database_url.split("://", 1)[0],
        # Railway подставляет хеш коммита сам — по нему видно, доехала ли правка.
        "commit": (os.getenv("RAILWAY_GIT_COMMIT_SHA") or "")[:7] or None,
    }


@app.get("/s/{token}")
async def share_page(token: str) -> FileResponse:
    """Публичная страница списка — открывается в любом браузере, без Telegram."""
    return FileResponse(WEB_DIR / "share.html")


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.middleware("http")
async def no_cache_webapp(request: Request, call_next):
    """Вебвью Telegram кэширует html и js намертво: после правки в приложении
    человек продолжает видеть старую версию. Для статики мини-приложения кэш
    выключаем — файлы крошечные, а отладка становится предсказуемой."""
    response = await call_next(request)
    if request.url.path.startswith(("/app", "/static", "/s/")):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="webapp")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
