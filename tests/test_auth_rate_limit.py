"""LoginRateLimit tests — UI-13 §3-G online-guessing
protection + pin §11.6.10.

Covers:
  * Per-IP burst (5 failures / 60 s window → 429 + initial
    backoff).
  * Per-credentials burst (10 failures / 5 min window).
  * Backoff doubling on subsequent burst (cap 1 hour).
  * Localhost client_ip bypass on check / record_failure /
    record_success (post-derivation rule per §3-G).
  * Window reset after the failure window elapses with no
    cap reached.
  * record_success clears both bucket counters.
  * Concurrent record_failure stays consistent (lock-protected
    transaction).

The brief pins:
  - PER_IP_MAX_FAILURES = 5,  PER_IP_WINDOW   = 60 s
  - PER_CRED_MAX_FAILURES = 10, PER_CRED_WINDOW = 300 s
  - BACKOFF_INITIAL = 60 s,  BACKOFF_MAX = 3600 s

The rate-limit is restart-cleared by design (mirror of UI-12c
pin §11.6.5 dedupe ring); these tests instantiate a fresh
``LoginRateLimit`` per case so process state never leaks
across tests."""

from __future__ import annotations

import threading

import pytest

from karasu.ui._auth import LoginRateLimit


# ---------------------------------------------------------------------------
# Synthetic monotonic clock helper
# ---------------------------------------------------------------------------


class _Clock:
    """Hand-cranked monotonic clock so tests advance time
    deterministically without ``time.sleep``."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def rl() -> LoginRateLimit:
    return LoginRateLimit()


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


# ---------------------------------------------------------------------------
# Constants pinned by the brief
# ---------------------------------------------------------------------------


def test_constants_match_brief() -> None:
    assert LoginRateLimit.PER_IP_MAX_FAILURES == 5
    assert LoginRateLimit.PER_IP_WINDOW == 60.0
    assert LoginRateLimit.PER_CRED_MAX_FAILURES == 10
    assert LoginRateLimit.PER_CRED_WINDOW == 300.0
    assert LoginRateLimit.BACKOFF_INITIAL == 60.0
    assert LoginRateLimit.BACKOFF_MAX == 3600.0


# ---------------------------------------------------------------------------
# check() initial behaviour
# ---------------------------------------------------------------------------


def test_check_initial_allows(rl: LoginRateLimit, clock: _Clock) -> None:
    """Fresh limiter allows any (ip, user) pair."""
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is True


def test_check_after_few_failures_still_allows(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """Below the cap (4 < 5), check is still True."""
    for _ in range(4):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is True


# ---------------------------------------------------------------------------
# Per-IP burst → 429
# ---------------------------------------------------------------------------


def test_per_ip_5_failures_in_window_blocks(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """5 failures in 60 s from the same IP → check returns
    False (caller emits 429)."""
    for _ in range(5):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is False


def test_per_ip_block_does_not_affect_other_ips(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """Another IP retains its own slot."""
    for _ in range(5):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="alice",
            now=clock,
        )
    assert rl.check(
        client_ip="203.0.113.99",
        username_attempted="bob",
        now=clock,
    ) is True


def test_per_ip_window_resets_below_cap(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """4 failures, then >60 s elapses without hitting cap →
    bucket window resets so the next 4 don't trip backoff."""
    for _ in range(4):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    clock.advance(LoginRateLimit.PER_IP_WINDOW + 1)
    for _ in range(4):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is True


# ---------------------------------------------------------------------------
# Per-credentials burst → 429
# ---------------------------------------------------------------------------


def test_per_credentials_10_failures_blocks(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """10 failed attempts in 5 min against the same username
    → check returns False even from a fresh IP."""
    for i in range(10):
        rl.record_failure(
            client_ip=f"203.0.113.{i + 1}",  # different IPs each time
            username_attempted="victor",
            now=clock,
        )
    # Fresh IP, but the per-credentials bucket has tripped.
    assert rl.check(
        client_ip="198.51.100.99",
        username_attempted="victor",
        now=clock,
    ) is False


def test_per_credentials_block_does_not_affect_other_users(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    for i in range(10):
        rl.record_failure(
            client_ip=f"203.0.113.{i + 1}",
            username_attempted="victor",
            now=clock,
        )
    assert rl.check(
        client_ip="198.51.100.5",
        username_attempted="alice",
        now=clock,
    ) is True


# ---------------------------------------------------------------------------
# Backoff doubling
# ---------------------------------------------------------------------------


def test_backoff_clears_after_initial_window(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """5 failures → 60 s lockout. After the lockout elapses
    (and no new burst), check goes back to True."""
    for _ in range(5):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is False
    clock.advance(LoginRateLimit.BACKOFF_INITIAL + 1)
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is True


def test_backoff_doubles_on_subsequent_burst(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """First burst → 60 s lockout. While the lockout is
    still in effect, a second burst doubles the remaining
    window (brief §3-G "backoff doubles on each subsequent
    burst")."""
    for _ in range(5):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    # 30 s into the 60 s lockout → 30 s remaining.
    clock.advance(30)
    # Second burst doubles the remaining window → 60 s ahead.
    for _ in range(5):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    # 30 s after the second burst — first window would have
    # already expired (60+30 > 60), but the doubled lockout
    # extends to roughly 60 s past the second burst.
    clock.advance(50)
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is False
    # Past the doubled window → unblock.
    clock.advance(20)
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is True


def test_backoff_caps_at_one_hour(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """Repeated bursts must not extend the lockout beyond
    BACKOFF_MAX = 3600 s."""
    # First burst: 60 s.
    for _ in range(5):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    # Stack many subsequent bursts, each one immediately
    # after the previous, to push the doubling logic well
    # past the cap if it weren't enforced.
    for _ in range(20):
        for _ in range(5):
            rl.record_failure(
                client_ip="203.0.113.7",
                username_attempted="victor",
                now=clock,
            )
    # 3601 s after the LAST burst → check must be True if the
    # cap is enforced, False otherwise.
    clock.advance(LoginRateLimit.BACKOFF_MAX + 1)
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is True


# ---------------------------------------------------------------------------
# Localhost bypass (post-derivation, §3-G)
# ---------------------------------------------------------------------------


def test_localhost_bypass_check_v4(rl: LoginRateLimit, clock: _Clock) -> None:
    """Localhost client_ip bypasses both buckets per §3-G —
    the bypass kicks in AFTER derive_client_ip resolved the
    real client to localhost."""
    # First saturate the per-credentials bucket from a
    # different IP (so the username has 10 failures recorded).
    for i in range(10):
        rl.record_failure(
            client_ip=f"203.0.113.{i + 1}",
            username_attempted="victor",
            now=clock,
        )
    # Local request still passes — the bypass short-circuits
    # both bucket checks.
    assert rl.check(
        client_ip="127.0.0.1",
        username_attempted="victor",
        now=clock,
    ) is True


def test_localhost_bypass_check_v6(rl: LoginRateLimit, clock: _Clock) -> None:
    """::1 receives the same bypass as 127.0.0.1."""
    for i in range(10):
        rl.record_failure(
            client_ip=f"203.0.113.{i + 1}",
            username_attempted="victor",
            now=clock,
        )
    assert rl.check(
        client_ip="::1",
        username_attempted="victor",
        now=clock,
    ) is True


def test_localhost_bypass_record_failure_is_noop(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """Recording a failure FROM a localhost client_ip must
    NOT increment the per-credentials bucket. Otherwise a
    repeated dev-side typo would lock out the operator's
    real account once they connect remotely."""
    for _ in range(20):
        rl.record_failure(
            client_ip="127.0.0.1",
            username_attempted="victor",
            now=clock,
        )
    # Per-credentials bucket should be untouched: a remote
    # client gets a fresh slot.
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is True


def test_localhost_bypass_record_success_is_noop(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """record_success from localhost must not clear a
    different-IP rate-limit slot."""
    for _ in range(5):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    rl.record_success(client_ip="127.0.0.1", username="victor")
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is False


# ---------------------------------------------------------------------------
# record_success clears slots
# ---------------------------------------------------------------------------


def test_record_success_clears_per_ip_slot(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """A successful login from the same (ip, user) clears
    both buckets — operator's ongoing legitimate attempts
    don't leave residue that locks them out later."""
    for _ in range(4):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    rl.record_success(client_ip="203.0.113.7", username="victor")
    # Bucket cleared → 4 more failures stay below the cap.
    for _ in range(4):
        rl.record_failure(
            client_ip="203.0.113.7",
            username_attempted="victor",
            now=clock,
        )
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
        now=clock,
    ) is True


def test_record_success_clears_per_cred_slot(
    rl: LoginRateLimit, clock: _Clock
) -> None:
    """Per-credentials failures from various IPs are also
    cleared on a success."""
    for i in range(9):
        rl.record_failure(
            client_ip=f"203.0.113.{i + 1}",
            username_attempted="victor",
            now=clock,
        )
    rl.record_success(client_ip="203.0.113.7", username="victor")
    # 9 more failures from new IPs would only put the
    # per-credentials bucket at 9 — still below the cap of 10.
    for i in range(9):
        rl.record_failure(
            client_ip=f"198.51.100.{i + 1}",
            username_attempted="victor",
            now=clock,
        )
    assert rl.check(
        client_ip="198.51.100.50",
        username_attempted="victor",
        now=clock,
    ) is True


# ---------------------------------------------------------------------------
# Thread safety — concurrent record_failure
# ---------------------------------------------------------------------------


def test_concurrent_record_failure_consistent() -> None:
    """Many threads recording failures against the same
    (ip, user) must not corrupt the bucket. After the burst
    the limiter must be in the locked state — proving every
    increment landed under the lock."""
    rl = LoginRateLimit()

    def hammer() -> None:
        for _ in range(50):
            rl.record_failure(
                client_ip="203.0.113.7",
                username_attempted="victor",
            )

    threads = [threading.Thread(target=hammer) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 500 failures total across both buckets → both well
    # past their caps; the lockout must be active.
    assert rl.check(
        client_ip="203.0.113.7",
        username_attempted="victor",
    ) is False
