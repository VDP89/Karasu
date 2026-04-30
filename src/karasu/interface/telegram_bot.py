"""Telegram bot — Phase 2 outbound sink.

Phase 2, chunk 1 ships the outbound side: pull new events from the
JSONL bus via a :class:`JsonlTailReader`, run them through
:class:`HumanReporter`, and forward each :class:`Report` to a
configured Telegram chat.

Inbound (``record_decision``) is wired against the bus but does NOT
feed back into the pipeline. Override / scar capture is deferred to
a later chunk per ``docs/phase-2-surface.md``.
"""

from __future__ import annotations

import asyncio
from typing import Iterable

from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader
from karasu.reporter import HumanReporter, Report


class TelegramInterface:
    """Bridge between the bus and a Telegram chat.

    The constructor only stores configuration. The actual
    ``python-telegram-bot`` ``Bot`` is built lazily by :meth:`send`
    and :meth:`run`, so importing this module never opens a network
    connection — useful for tests and for ``karasu status``.
    """

    def __init__(
        self,
        token: str,
        bus: JsonlEventBus,
        chat_id: int | None = None,
        allowed_users: Iterable[int] = (),
    ) -> None:
        self.token = token
        self.bus = bus
        self.chat_id = chat_id
        self.allowed_users = frozenset(allowed_users)

    def is_allowed(self, user_id: int) -> bool:
        return not self.allowed_users or user_id in self.allowed_users

    def format(self, report: Report) -> str:
        return report.text

    def drain(
        self,
        reader: JsonlTailReader,
        reporter: HumanReporter,
    ) -> list[Report]:
        """Pull new events from ``reader`` and produce :class:`Report`.

        Surface = sink. The reader advances atomically (PR #9), so
        events are consumed exactly once across calls. Events that
        the reporter rejects (non-``agent_response``, etc.) are
        dropped silently.
        """
        reports: list[Report] = []
        for event in reader.read_new():
            report = reporter.report(event)
            if report is not None:
                reports.append(report)
        return reports

    def send(self, report: Report) -> None:
        """Deliver one report to the configured chat.

        Lazy-imports ``python-telegram-bot`` so unit tests can
        monkeypatch the ``telegram`` module without the dependency
        loaded.
        """
        if self.chat_id is None:
            raise RuntimeError(
                "TelegramInterface.send requires chat_id to be set"
            )
        from telegram import Bot

        bot = Bot(self.token)
        asyncio.run(
            bot.send_message(chat_id=self.chat_id, text=self.format(report))
        )

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
