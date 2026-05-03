"""Lint UI stylesheets for bare ``outline:none``.

UI-0 design brief §6 mandates a visible focus ring on every
focusable surface. Removing the default outline via
``outline: none`` without an equivalent replacement strips
keyboard accessibility entirely. The brief calls this out
explicitly:

    Never removed via outline:none without an equivalent
    replacement; lint forbids bare outline:none.

This is the lint. A rule block that contains ``outline: none``
or ``outline: 0`` MUST also reference the canonical
``--focus-ring`` token (typically through ``box-shadow``) in
the same block; otherwise it is flagged as a violation.

Scope: ``*.css`` files and the inline ``<style>`` block of any
``*.html`` under the configured roots (default
``src/karasu/ui/static``).

Exit codes:

- 0 — clean.
- 1 — at least one violation found; details on stdout.

Usage:

    python scripts/lint_ui_css.py
    python scripts/lint_ui_css.py path/to/dir [more/paths ...]

Also exposed via ``pytest tests/test_lint_ui_css.py`` so CI
catches regressions automatically.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

# Default scan root — the UI surface owns the focus ring.
DEFAULT_ROOTS: tuple[Path, ...] = (
    Path("src/karasu/ui/static"),
)

# Match a top-level rule block ``{ ... }``. The negated character
# class on ``{}`` keeps nested at-rule blocks (``@media``,
# ``@keyframes``) out of the match — those wrap inner blocks
# which we want to inspect individually, not as one giant block.
_RULE_BLOCK_RE = re.compile(r"\{([^{}]*)\}", re.DOTALL)

# ``outline: none`` and ``outline: 0`` (and the no-space / mixed
# variants). The ``\b`` boundary stops accidental matches inside
# longer tokens like ``outline-color: none``.
_OUTLINE_BARE_RE = re.compile(
    r"\boutline\s*:\s*(none|0)\s*(?=;|$|\})",
    re.IGNORECASE | re.MULTILINE,
)

# Canonical focus-ring token from the UI-0 brief. A block that
# references it is satisfying the "equivalent replacement"
# requirement; not flagged.
_FOCUS_RING_RE = re.compile(r"--focus-ring\b")

# Inline ``<style>`` block in HTML. ``DOTALL`` so the body can
# span lines.
_INLINE_STYLE_RE = re.compile(
    r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE
)


def lint_css_text(text: str) -> list[tuple[int, str]]:
    """Return ``[(line_number, snippet), ...]`` for every bare
    ``outline:none`` in ``text``. Line numbers are 1-indexed
    against ``text``."""
    violations: list[tuple[int, str]] = []
    for block_match in _RULE_BLOCK_RE.finditer(text):
        block = block_match.group(0)
        if not _OUTLINE_BARE_RE.search(block):
            continue
        if _FOCUS_RING_RE.search(block):
            continue
        for sub in _OUTLINE_BARE_RE.finditer(block):
            offset_in_text = block_match.start() + sub.start()
            line_no = text.count("\n", 0, offset_in_text) + 1
            violations.append((line_no, sub.group(0).strip()))
    return violations


def lint_file(path: Path) -> list[tuple[int, str]]:
    """Lint a single file; dispatches by suffix."""
    suffix = path.suffix.lower()
    if suffix == ".css":
        return lint_css_text(path.read_text(encoding="utf-8"))
    if suffix == ".html":
        text = path.read_text(encoding="utf-8")
        out: list[tuple[int, str]] = []
        for style_match in _INLINE_STYLE_RE.finditer(text):
            css_text = style_match.group(1)
            line_offset = text.count("\n", 0, style_match.start(1))
            for line_no, snippet in lint_css_text(css_text):
                out.append((line_no + line_offset, snippet))
        return out
    return []


def lint_paths(roots: Iterable[Path]) -> list[tuple[Path, int, str]]:
    """Walk ``roots`` and return every violation as
    ``(path, line, snippet)``. Skips paths that do not exist;
    callers (CLI, tests) handle the empty-result case."""
    violations: list[tuple[Path, int, str]] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            for line_no, snippet in lint_file(root):
                violations.append((root, line_no, snippet))
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in (".css", ".html"):
                continue
            for line_no, snippet in lint_file(path):
                violations.append((path, line_no, snippet))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    roots: tuple[Path, ...]
    if args:
        roots = tuple(Path(a) for a in args)
    else:
        roots = DEFAULT_ROOTS
    violations = lint_paths(roots)
    if not violations:
        print(
            f"UI lint clean: no bare outline:none in "
            f"{', '.join(str(r) for r in roots)}."
        )
        return 0
    for path, line_no, snippet in violations:
        print(
            f"{path}:{line_no}: bare {snippet!r} — UI-0 brief §6 "
            "requires --focus-ring replacement in the same rule block."
        )
    print(f"\n{len(violations)} violation(s).")
    return 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
