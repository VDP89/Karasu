"""Telegram bot — the Phase 1 mobile interface.

The bot is intentionally thin: it forwards :class:`Report` instances
from the reporter to the configured chat, and forwards the user's
replies back as ``human_decision`` events on the bus.
"""

from __future__ import annotations

from typing import Iterable

from karasu.eventbus import Event, JsonlEventBus
from karasu.reporter import Report


class TelegramInterface:
    """Bridge between the bus and a Telegram chat.

    The constructor only stores configuration. The actual
    ``python-telegram-bot`` Application is built lazily by
    :meth:`run`, so importing this module never opens a network
    connection — useful for tests and for ``karasu status``.
    """

    def __init__(
        self,
        token: str,
        bus: JsonlEventBus,
        allowed_users: Iterable[int] = (),
    ) -> None:
        self.token = token
        self.bus = bus
        self.allowed_users = frozenset(allowed_users)

    def is_allowed(self, user_id: int) -> bool:
        return not self.allowed_users or user_id in self.allowed_users

    def format(self, report: Report) -> str:
        return report.text

    def record_decision(self, user_id: int, text: str) -> Event:
        return self.bus.append(
            Event(
                type="human_decision",
                source="interface",
                data={"user": user_id, "text": text},
            )
        )

    def run(self) -> None:  # pragma: no cover - network side effect
        from telegram.ext import ApplicationBuilder

        application = ApplicationBuilder().token(self.token).build()
        application.run_polling()
