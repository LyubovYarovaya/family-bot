import os
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    public_url: str = "http://localhost:8080"
    database_url: str = "sqlite+aiosqlite:///./family.db"
    default_currency: str = "UAH"

    bot_mode: str = "polling"  # polling | webhook | off
    webhook_secret: str = "change-me"

    host: str = "0.0.0.0"
    port: int = 8080

    dev_tg_id: int | None = None

    @field_validator("dev_tg_id", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        """Пустая строка в .env (DEV_TG_ID=) значит «выключено», а не ошибку."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _async_driver(cls, value):
        """Хостинги дают адрес базы для синхронного драйвера, нам нужен async.

        Railway, Render и Heroku подставляют DATABASE_URL вида
        `postgres://…` или `postgresql://…`. SQLAlchemy с таким адресом возьмёт
        psycopg, которого у нас нет, и упадёт на старте. Дописываем asyncpg.
        """
        if isinstance(value, str):
            if value.startswith("postgres://"):
                value = "postgresql://" + value[len("postgres://"):]
            if value.startswith("postgresql://"):
                value = "postgresql+asyncpg://" + value[len("postgresql://"):]
        return value

    @model_validator(mode="after")
    def _public_url_from_platform(self):
        """Адрес приложения на хостинге известен только после деплоя.

        Railway кладёт домен в RAILWAY_PUBLIC_DOMAIN, Render — целиком в
        RENDER_EXTERNAL_URL. Берём оттуда, если PUBLIC_URL не задан руками, —
        иначе ссылки на вишлисты и мини-приложение уедут на localhost.
        """
        placeholders = {"", "http://localhost:8080", "https://example.com"}
        if self.public_url.rstrip("/") in {p.rstrip("/") for p in placeholders}:
            domain = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("RAILWAY_STATIC_URL")
            external = os.getenv("RENDER_EXTERNAL_URL")
            if domain:
                self.public_url = domain if domain.startswith("http") else f"https://{domain}"
            elif external:
                self.public_url = external
        return self

    @property
    def base_url(self) -> str:
        return self.public_url.rstrip("/")

    @property
    def webapp_url(self) -> str:
        """Адрес мини-приложения для кнопок бота.

        Хвост с версией выкатки заставляет вебвью Telegram считать каждую
        выкатку новой страницей. Без него iOS-клиент неделями показывает
        закэшированный старый интерфейс, игнорируя Cache-Control: no-store.
        Приложение лишние параметры адреса не читает — только tab.
        """
        stamp = os.getenv("RAILWAY_GIT_COMMIT_SHA", "")[:7]
        base = f"{self.base_url}/app/"
        return f"{base}?v={stamp}" if stamp else base

    def share_url(self, token: str) -> str:
        return f"{self.base_url}/s/{token}"

    def invite_url(self, code: str, bot_username: str) -> str:
        return f"https://t.me/{bot_username}?start=join_{code}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
