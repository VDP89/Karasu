"""Telegram bot — the Phase 1 mobile interface.

The bot bridges the JSONL event bus to a Telegram chat:

* outbound — a tail loop polls the bus for new ``agent_response`` events
  and sends each one to ``chat_id``.
* inbound — free-text messages from whitelisted users are appended to
  the bus as ``human_decision`` events. Inbound handlers are wired in a
  follow-up PR; the whitelist behaviour is already enforced.

The whitelist is **fail-closed**: an empty ``allowed_users`` set
refuses every user. A leaked token must not turn the bot into an open
relay.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Iterable

from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader

log = logging.getLogger(__name__)

SendMessage = Callable[[int, str], Awaitable[object]]


class TelegramInterface:
    """Bridge between the bus and a Telegram chat.

    The constructor only stores configuration. The ``python-telegram-bot``
    Application is built lazily by :meth:`run`, so importing this module
    never opens a network connection — useful for tests and for
    ``karasu status``.
    """

    def __init__(
        self,
        token: str,
        bus: JsonlEventBus,
        allowed_users: Iterable[int] = (),
        chat_id: int | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self.token = token
        self.bus = bus
        self.allowed_users = frozenset(allowed_users)
        self.chat_id = chat_id
        self.poll_interval = poll_interval

    # ------------------------------------------------------------------
    # Inbound (used by handlers wired in a follow-up PR).
    # ------------------------------------------------------------------

    def is_allowed(self, user_id: int) -> bool:
        """Whitelist check. Fail-closed: empty set refuses everyone."""
        return user_id in self.allowed_users

    def record_decision(self, user_id: int, text: str) -> Event:
        return self.bus.append(
            Event(
                type="human_decision",
                source="interface",
                data={"user": user_id, "text": text},
            )
        )

    # ------------------------------------------------------------------
    # Outbound — tail the bus and forward agent_response events.
    # ------------------------------------------------------------------

    def format_event(self, event: Event) -> str:
        agent = event.dispatch.get("agent") or "unknown"
        content = (event.response or {}).get("content", "")
        needs_decision = bool((event.response or {}).get("requires_human", True))
        prefix = "[DECISION]" if needs_decision else "[INFO]"
        return f"{prefix} {agent}: {content}".strip()

    async def tail_loop(
        self,
        send: SendMessage,
        reader: JsonlTailReader | None = None,
        stop_event: asyncio.Event | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Poll the bus and forward ``agent_response`` events to the chat.

        ``reader`` defaults to a fresh :class:`JsonlTailReader` starting
        at EOF, so history is not replayed. ``sleep`` is injectable for
        deterministic tests.

        Returns immediately if ``chat_id`` is not configured — the bot
        can still receive messages but has no outbound target.
        """
        if self.chat_id is None:
            log.warning("telegram outbound disabled: no chat_id configured")
            return
        if reader is None:
            reader = JsonlTailReader(self.bus.path)
        if sleep is None:
            sleep = asyncio.sleep
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            for event in reader.read_new():
                if event.type != "agent_response":
                    continue
                text = self.format_event(event)
                try:
                    await send(self.chat_id, text)
                except Exception as exc:  # noqa: BLE001
                    # A transient Telegram error must not crash the loop.
                    log.warning("telegram send failed: %s", exc)
            await sleep(self.poll_interval)

    # ------------------------------------------------------------------
    # Entrypoint.
    # ------------------------------------------------------------------

    def run(self) -> None:  # pragma: no cover - network side effect
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:  # pragma: no cover - network side effect
        from telegram.ext import ApplicationBuilder

        application = ApplicationBuilder().token(self.token).build()
        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        async def send(chat_id: int, text: str) -> object:
            return await application.bot.send_message(chat_id=chat_id, text=text)

        try:
            await self.tail_loop(send)
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
