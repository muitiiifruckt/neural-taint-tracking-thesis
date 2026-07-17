"""Regression tests for src/agent/metrics.py.

Guards against the exact bug found on 2026-07-17: aggregation code that read AgentDojo's raw
`security` field as "attack blocked" instead of "attack succeeded", inverting every reported
ASR/security-rate number. No test caught that inversion because no test exercised the metric
arithmetic in isolation -- only full live benchmark runs did.
"""

from __future__ import annotations

from src.agent.metrics import asr_and_security_rate, pct


def test_pct_basic():
    assert pct([True, True, False, False]) == 50.0
    assert pct([True, True, True]) == 100.0
    assert pct([False, False]) == 0.0


def test_pct_empty_is_none():
    assert pct([]) is None


def test_asr_is_share_of_true_not_false():
    # 3 of 4 cases have security=True (attack succeeded) -> ASR must be 75%, not 25%.
    asr, security_rate = asr_and_security_rate([True, True, True, False])
    assert asr == 75.0
    assert security_rate == 25.0


def test_asr_and_security_rate_are_complementary():
    for successes in ([True], [False], [True, False, True], [False, False, False, True]):
        asr, security_rate = asr_and_security_rate(successes)
        assert round(asr + security_rate, 6) == 100.0


def test_all_attacks_succeeded_gives_100_percent_asr():
    asr, security_rate = asr_and_security_rate([True, True, True])
    assert asr == 100.0
    assert security_rate == 0.0


def test_no_attacks_succeeded_gives_0_percent_asr():
    asr, security_rate = asr_and_security_rate([False, False, False])
    assert asr == 0.0
    assert security_rate == 100.0


def test_empty_input_yields_none_not_zero():
    # None (unknown), not 0.0, so an empty case list can't silently masquerade as "0% ASR".
    asr, security_rate = asr_and_security_rate([])
    assert asr is None
    assert security_rate is None
