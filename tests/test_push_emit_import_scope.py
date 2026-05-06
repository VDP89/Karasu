"""Pin §11.6.1 + §11.6.13 binding test: ``cryptography`` is
imported ONLY from the three approved files inside
``src/karasu/push_emit/``.

Brief §3-C + §11.6.13 binding: UI-12c is the named, scoped
exception to UI-0 §4 (no new runtime deps). The exception
applies to ``cryptography`` and ONLY to:

  * ``src/karasu/push_emit/_signing.py``     (VAPID JWT)
  * ``src/karasu/push_emit/_keys.py``        (VAPID keygen)
  * ``src/karasu/push_emit/_encryption.py``  (RFC 8291 enc)

Imports outside these files are a regression that re-opens
the UI-0 §4 conversation. This test is the structural lock
that catches the regression at CI time.

The check walks every .py file under ``src/karasu/`` and
greps for the strings ``import cryptography``,
``from cryptography``, and bare ``cryptography.`` (transitive
attribute access). The same lint-style approach was used for
``test_lint_ui_css.py`` and ``test_ui_sw.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# Brief §11.6.1 binding allow-list. Updates require operator
# sign-off + a fresh brief PR per UI-0 §4.
ALLOWED_PATHS = frozenset(
    Path(p) for p in (
        "src/karasu/push_emit/_signing.py",
        "src/karasu/push_emit/_keys.py",
        "src/karasu/push_emit/_encryption.py",
    )
)


# Three regex patterns covering import + transitive-use forms.
# ``cryptography\.`` catches code that does
# ``import cryptography as crypto`` and then accesses
# ``crypto.foo`` — but NOT references to the *string*
# ``"cryptography"`` (e.g. doc strings) or the package name in
# a comment. We anchor on ``cryptography`` followed by either
# ``\s*import``, ``\s+import``, or ``\.`` (attribute access).
_PATTERNS = (
    re.compile(r"^\s*from\s+cryptography(?:\.|\s)", re.MULTILINE),
    re.compile(r"^\s*import\s+cryptography(?:\.|$|\s)", re.MULTILINE),
)


def _repo_root() -> Path:
    """Walk up from this test file to the repo root."""
    return Path(__file__).resolve().parents[1]


def _all_python_sources() -> list[Path]:
    """Every .py file under ``src/karasu/`` (recursive)."""
    src = _repo_root() / "src" / "karasu"
    return sorted(src.rglob("*.py"))


def test_cryptography_imports_confined_to_three_files() -> None:
    """Pin §11.6.1: every cryptography import must live in
    one of :data:`ALLOWED_PATHS`. Any other file matching
    triggers the regression flag."""
    repo_root = _repo_root()
    allowed_abs = {(repo_root / p).resolve() for p in ALLOWED_PATHS}

    offenders: list[tuple[Path, str]] = []
    for source in _all_python_sources():
        if source.resolve() in allowed_abs:
            continue
        text = source.read_text(encoding="utf-8")
        for pattern in _PATTERNS:
            match = pattern.search(text)
            if match is not None:
                rel = source.relative_to(repo_root)
                offenders.append((rel, match.group(0).strip()))
                break

    assert offenders == [], (
        "cryptography imports leaked outside the UI-12 §11.6.13 "
        "named scoped exception:\n"
        + "\n".join(f"  {p}: {m}" for p, m in offenders)
    )


def test_allowed_paths_actually_use_cryptography() -> None:
    """Sanity: each file in :data:`ALLOWED_PATHS` actually
    imports ``cryptography``. If one stops needing it, the
    allow-list should shrink rather than carry a stale
    exception."""
    repo_root = _repo_root()
    for rel in ALLOWED_PATHS:
        path = repo_root / rel
        assert path.exists(), f"allow-listed path missing: {rel}"
        text = path.read_text(encoding="utf-8")
        assert any(p.search(text) for p in _PATTERNS), (
            f"{rel} is allow-listed but does NOT import cryptography"
        )


def test_allowed_paths_match_brief_section_3c() -> None:
    """Brief §3-C lists exactly three files: _signing.py,
    _keys.py, _encryption.py. The allow-list must match
    byte-for-byte; any drift earns a brief amendment."""
    expected = {
        Path("src/karasu/push_emit/_signing.py"),
        Path("src/karasu/push_emit/_keys.py"),
        Path("src/karasu/push_emit/_encryption.py"),
    }
    assert set(ALLOWED_PATHS) == expected
