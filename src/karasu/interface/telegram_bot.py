"""Telegram bot — Phase 2 outbound sink + read-only slash commands.

Phase 2 chunk 1 shipped the outbound side: pull new events from the
JSONL bus via a :class:`JsonlTailReader`, run them through
:class:`HumanReporter`, and forward each :class:`Report` to a
configured Telegram chat.

Phase 2 chunk 2 adds read-only slash commands (``/status``,
``/agents``, ``/scars``). The pure dispatch lives in
:meth:`TelegramInterface.handle_command`; the python-telegram-bot
``Application`` wiring in :meth:`TelegramInterface.run_application`
is a thin shell that tests skip.

Inbound (``record_decision``) is wired against the bus but does NOT
feed back into the pipeline. Override / scar capture is deferred to
chunk 3 per ``docs/phase-2-surface.md``.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Iterable

from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader
from karasu.reporter import HumanReporter, Report

CommandProvider = Callable[[], str]
WriteHandler = Callable[[str], str]


class TelegramInterface:
    """Bridge between the bus and a Telegram chat.

    The constructor only stores configuration. The actual
    ``python-telegram-bot`` ``Bot`` is built lazily by :meth:`send`
    and :meth:`run_application`, so importing this module never
    opens a network connection — useful for tests and for
    ``karasu status``.
    """

    WRITE_COMMANDS = frozenset({"correct", "scar"})

    def __init__(
        self,
        token: str,
        bus: JsonlEventBus,
        chat_id: int | None = None,
        allowed_users: Iterable[int] = (),
        status_provider: CommandProvider | None = None,
        agents_provider: CommandProvider | None = None,
        scars_provider: CommandProvider | None = None,
        correct_handler: WriteHandler | None = None,
        scar_handler: WriteHandler | None = None,
    ) -> None:
        self.token = token
        self.bus = bus
        self.chat_id = chat_id
        self.allowed_users = frozenset(allowed_users)
        self._providers: dict[str, CommandProvider | None] = {
            "status": status_provider,
            "agents": agents_provider,
            "scars": scars_provider,
        }
        self._write_handlers: dict[str, WriteHandler | None] = {
            "correct": correct_handler,
            "scar": scar_handler,
        }

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

    def handle_command(self, name: str, user_id: int) -> str:
        """Dispatch a slash command to the registered provider.

        Returns the message text the bot should reply with. Pure
        function over configuration + provider state — no telegram
        dependency, fully testable.

        Whitelist (``allowed_users``) is enforced here because
        slash commands are the first inbound surface that actually
        reads private state.
        """
        if not self.is_allowed(user_id):
            return "unauthorized"
        if name not in self._providers:
            return f"unknown command: /{name}"
        provider = self._providers[name]
        if provider is None:
            return f"/{name} is not configured"
        return provider()

    def handle_write_command(self, name: str, user_id: int, args: str) -> str:
        """Dispatch a write command (``/correct``, ``/scar``).

        Stricter than :meth:`handle_command`: the whitelist must be
        non-empty AND contain ``user_id``. An empty whitelist (which
        chunk 1 / 2 treat as "allow anyone") rejects every write.
        Writes mutate ScarEngine state — the surface refuses to do
        that without an explicit operator-set allowlist.

        Audit trail is always written, but the recorded text is
        redacted for unauthorized callers and unknown commands —
        the message body could contain arbitrary user input from a
        leaked chat, and only the metadata (command name + outcome)
        is operationally useful in those cases. Authorized calls
        record the full ``/{name} {args}`` so the operator can
        reconstruct what they typed.
        """
        if name not in self.WRITE_COMMANDS:
            self.record_decision(user_id, f"/{name} (unknown command)")
            return f"unknown command: /{name}"
        if not self.allowed_users or user_id not in self.allowed_users:
            self.record_decision(user_id, f"/{name} (unauthorized)")
            return (
                "unauthorized: write commands require an explicit "
                "allowed_users entry containing your user id"
            )
        # Authorized — record full text so the operator can see exactly
        # what they sent.
        self.record_decision(user_id, f"/{name} {args}".rstrip())
        handler = self._write_handlers.get(name)
        if handler is None:
            return f"/{name} is not configured"
        return handler(args)

    def record_decision(self, user_id: int, text: str) -> Event:
        return self.bus.append(
            Event(
                type="human_decision",
                source="interface",
                data={"user": user_id, "text": text},
            )
        )

    def run_application(  # pragma: no cover - network side effect
        self,
        reader: JsonlTailReader,
        reporter: HumanReporter,
        poll_interval: float = 0.5,
    ) -> None:
        """Build the ``python-telegram-bot`` Application and block.

        Wires:
        - ``CommandHandler`` for /status, /agents, /scars routed
          through :meth:`handle_command`.
        - A repeating ``JobQueue`` task that calls :meth:`drain`
          and forwards each :class:`Report` via the application's
          bot.

        Skipped from coverage because the only thing this method
        does is glue. The pure pieces (:meth:`drain`,
        :meth:`handle_command`) are tested separately.
        """
        from telegram import Update
        from telegram.ext import (
            ApplicationBuilder,
            CommandHandler,
            ContextTypes,
        )

        application = ApplicationBuilder().token(self.token).build()

        def make_handler(name: str):
            async def _handler(
                update: Update, context: ContextTypes.DEFAULT_TYPE
            ) -> None:
                if update.effective_user is None or update.message is None:
                    return
                reply = self.handle_command(name, update.effective_user.id)
                await update.message.reply_text(reply)

            return _handler

        for command in ("status", "agents", "scars"):
            application.add_handler(CommandHandler(command, make_handler(command)))

        def make_write_handler(name: str):
            async def _handler(
                update: Update, context: ContextTypes.DEFAULT_TYPE
            ) -> None:
                if update.effective_user is None or update.message is None:
                    return
                # Strip the "/<name>" prefix from message.text so the
                # write handler sees only the args. Empty args is a
                # valid input — capture_correct / capture_scar render
                # their own usage messages.
                raw = update.message.text or ""
                args = raw.partition(" ")[2]
                reply = self.handle_write_command(
                    name, update.effective_user.id, args
                )
                await update.message.reply_text(reply)

            return _handler

        for command in ("correct", "scar"):
            application.add_handler(
                CommandHandler(command, make_write_handler(command))
            )

        async def _drain_job(context: ContextTypes.DEFAULT_TYPE) -> None:
            for report in self.drain(reader, reporter):
                if self.chat_id is not None:
                    await context.bot.send_message(
                        chat_id=self.chat_id, text=self.format(report)
                    )

        application.job_queue.run_repeating(_drain_job, interval=poll_interval)
        application.run_polling()
