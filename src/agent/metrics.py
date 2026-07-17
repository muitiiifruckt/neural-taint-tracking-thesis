"""Shared metric aggregation helpers, used by scripts/run_eval.py and scripts/collect_t0_results.py.

Both scripts used to compute ASR and security rate with their own inline arithmetic; one of
them read AgentDojo's raw `security` field with the sign flipped, so every historical report
before 2026-07-17 stated the complement of the true ASR/security rate. `asr_and_security_rate`
exists so this arithmetic (and its semantics) lives in exactly one place, covered by
`tests/test_metrics.py`, instead of being re-derived -- and re-riskable -- per script.
"""

from __future__ import annotations


def pct(values: list[bool]) -> float | None:
    """Percentage of True values, or None for an empty list."""

    return None if not values else round(100.0 * sum(values) / len(values), 2)


def asr_and_security_rate(attack_successful: list[bool]) -> tuple[float | None, float | None]:
    """Compute (targeted ASR %, security rate %) from AgentDojo's raw `security` field.

    AgentDojo's raw per-case `security` field is True when the injection goal was achieved
    (see `BaseInjectionTask.security` docstring and `TaskSuite.check`, which runs the attack's
    ground truth and requires True). So ASR is the share of True values, and security rate is
    its complement -- never the other way around.
    """

    asr = pct(attack_successful)
    security_rate = None if asr is None else round(100.0 - asr, 2)
    return asr, security_rate
