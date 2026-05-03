"""Tests for ``scripts/lint_ui_css.py``.

UI-0 round-2 NICE-TO-HAVE — UI-2 deferred lint script catches
bare ``outline: none`` rules that strip the focus ring without
the canonical ``--focus-ring`` replacement.

Two layers:

1. ``lint_css_text`` / ``lint_file`` unit behaviour with synthetic
   CSS and HTML fixtures.
2. End-to-end ``main()`` exit-code contract.

Plus a pin against the live ``src/karasu/ui/static`` tree so a
future regression is caught in CI without a separate workflow.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import lint_ui_css  # noqa: E402  — sys.path tweak above


# ---------------------------------------------------------------------------
# Unit — lint_css_text
# ---------------------------------------------------------------------------


def test_lint_flags_bare_outline_none() -> None:
    css = """
    button:focus { outline: none; }
    """
    violations = lint_ui_css.lint_css_text(css)
    assert len(violations) == 1
    line_no, snippet = violations[0]
    assert "outline" in snippet.lower()
    assert "none" in snippet.lower()
    assert line_no == 2


def test_lint_flags_bare_outline_zero() -> None:
    css = """
    a:focus { outline: 0; }
    """
    violations = lint_ui_css.lint_css_text(css)
    assert len(violations) == 1
    assert "0" in violations[0][1]


def test_lint_flags_outline_none_without_space() -> None:
    css = "button:focus{outline:none;}"
    assert len(lint_ui_css.lint_css_text(css)) == 1


def test_lint_passes_outline_none_with_focus_ring_replacement() -> None:
    """The canonical pattern: strip the default outline AND
    replace it with the design-token focus ring in the same
    block. Brief §6 explicitly allows this."""
    css = """
    button:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
    }
    """
    assert lint_ui_css.lint_css_text(css) == []


def test_lint_passes_outline_with_real_value() -> None:
    """Non-bare outline values are fine; the brief only forbids
    silent removal."""
    css = """
    .accent {
      outline: 2px solid var(--accent);
    }
    """
    assert lint_ui_css.lint_css_text(css) == []


def test_lint_does_not_match_outline_color_none() -> None:
    """``outline-color: none`` is a different property and not
    what the brief forbids. The boundary on ``\\boutline\\s*:``
    must not accidentally pull longhand outline-* properties in."""
    css = """
    .x {
      outline-color: none;
    }
    """
    assert lint_ui_css.lint_css_text(css) == []


def test_lint_flags_each_violation_in_multiblock_file() -> None:
    css = """
    a:focus { outline: none; }
    button:focus { outline: 0; }
    .ok:focus { outline: none; box-shadow: var(--focus-ring); }
    """
    violations = lint_ui_css.lint_css_text(css)
    # The third block is OK; the first two each contribute one.
    assert len(violations) == 2


def test_lint_handles_at_media_nested_blocks() -> None:
    """At-rule blocks contain nested rule blocks. The inner ones
    are inspected individually; an at-rule that contains a
    compliant inner block does NOT mask a sibling violation."""
    css = """
    @media (prefers-reduced-motion: reduce) {
      .ok:focus { outline: none; box-shadow: var(--focus-ring); }
    }
    .bad:focus { outline: none; }
    """
    violations = lint_ui_css.lint_css_text(css)
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Unit — lint_file
# ---------------------------------------------------------------------------


def test_lint_file_reads_css(tmp_path: Path) -> None:
    css_file = tmp_path / "x.css"
    css_file.write_text("a:focus { outline: none; }\n")
    violations = lint_ui_css.lint_file(css_file)
    assert len(violations) == 1


def test_lint_file_reads_inline_style_in_html(tmp_path: Path) -> None:
    html_file = tmp_path / "x.html"
    html_file.write_text(
        "<html>\n<head>\n<style>\n"
        "a:focus { outline: none; }\n"
        "</style>\n</head>\n</html>\n"
    )
    violations = lint_ui_css.lint_file(html_file)
    assert len(violations) == 1
    # Line offset must include the lines BEFORE the <style> tag.
    line_no, _ = violations[0]
    assert line_no == 4


def test_lint_file_ignores_unknown_suffix(tmp_path: Path) -> None:
    txt = tmp_path / "x.txt"
    txt.write_text("outline: none;\n")
    assert lint_ui_css.lint_file(txt) == []


# ---------------------------------------------------------------------------
# End-to-end — main()
# ---------------------------------------------------------------------------


def test_main_returns_zero_on_clean_tree(tmp_path: Path, capsys) -> None:
    (tmp_path / "ok.css").write_text(
        "a:focus-visible { box-shadow: var(--focus-ring); }\n"
    )
    rc = lint_ui_css.main([str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "clean" in captured.out


def test_main_returns_one_on_violation(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "bad.css"
    bad.write_text("a:focus { outline: none; }\n")
    rc = lint_ui_css.main([str(tmp_path)])
    assert rc == 1
    captured = capsys.readouterr()
    assert str(bad) in captured.out
    assert "violation" in captured.out


def test_main_handles_missing_root_silently(
    tmp_path: Path, capsys
) -> None:
    """A non-existent path is not an error per se — the CLI simply
    has nothing to scan. Treating it as clean lets composed CI
    invocations stay simple."""
    rc = lint_ui_css.main([str(tmp_path / "does-not-exist")])
    assert rc == 0


# ---------------------------------------------------------------------------
# CI pin — current src/karasu/ui/static must lint clean
# ---------------------------------------------------------------------------


def test_live_ui_static_tree_is_clean() -> None:
    """A regression in the live UI tree (e.g. someone adds
    ``outline: none`` while iterating on UI-2..UI-9) trips the
    lint here without a separate CI workflow."""
    rc = lint_ui_css.main([str(REPO_ROOT / "src" / "karasu" / "ui" / "static")])
    assert rc == 0
