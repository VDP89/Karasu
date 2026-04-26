"""Telegram bot quickstart.

Set ``KARASU_TELEGRAM_TOKEN`` in the environment, then run::

    python examples/telegram_quickstart.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from karasu.eventbus import JsonlEventBus
from karasu.interface import TelegramInterface


def main() -> None:
    token = os.environ.get("KARASU_TELEGRAM_TOKEN", "")
    if not token:
        print("set KARASU_TELEGRAM_TOKEN before running", file=sys.stderr)
        raise SystemExit(2)
    bus = JsonlEventBus(Path(".karasu/events.jsonl"))
    interface = TelegramInterface(token=token, bus=bus)
    interface.run()


if __name__ == "__main__":
    main()
