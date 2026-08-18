"""Мелкое разделяемое состояние процесса (заполняется при старте бота)."""

bot_username: str | None = None

# Почему бот не поднялся. Пусто, когда всё в порядке. Показывается в /healthz,
# чтобы причину было видно снаружи — на хостинге логи под рукой не всегда.
bot_error: str | None = None


def invite_link(code: str) -> str:
    if bot_username:
        return f"https://t.me/{bot_username}?start=join_{code}"
    return f"код приглашения: {code}"
