# Progress Report — Neural Taint Tracking

**Date:** 2026-07-17
**Repo:** https://github.com/muitiiifruckt/neural-taint-tracking-thesis

## What has been done so far

**T0 baseline (no defense).** Established on the AgentDojo `workspace` suite (v1.2.2), model
`gpt-4o-mini-2024-07-18`, attack `important_instructions`, 10 user tasks × 14 injection tasks = 140
security cases:

| Metric | Value |
|---|---|
| Benign Utility | 100.0% (10/10) |
| Utility Under Attack | 20.0% (28/140) |
| Security rate | 24.3% (34/140) |
| Targeted ASR | 75.7% (106/140) |

**T1 — tag-only taint tracking.** Fully implemented and evaluated this week:

- Core data model (`TaintedSpan`, `TrustLabel`, `TaintRegistry`, `TaintTrace`) with unit tests.
- `ObservingToolsExecutor`: integrated the taint observer directly into a live AgentDojo pipeline as a
  fork of the library's `ToolsExecutor`. It observes the *raw structured* tool return value before
  AgentDojo flattens it into a single string, which preserves per-field taint granularity (an
  after-the-fact observer on the formatted string was tried first and rejected — it collapses an entire
  tool output into one span and misses most real copies).
- A custom eval runner (`scripts/run_t1_eval.py`), since AgentDojo's benchmark CLI only accepts
  defenses from a hardcoded list and cannot take an arbitrary custom pipeline element.
- Full evaluation on the same 150 cases as T0:

| Metric | T0 | T1 |
|---|---|---|
| Benign Utility | 100.0% | **100.0%** |
| Utility Under Attack | 20.0% | **20.0%** |
| Security rate | 24.3% | 28.6% (LLM run-to-run noise; gate is disabled, T1 cannot affect this) |
| Targeted ASR | 75.7% | 71.4% (same noise) |
| Taint leakage rate | — | **36.8%** (202/549 privileged tool calls carried untrusted content) |

Benign Utility and Utility Under Attack are identical to T0, confirming T1's key acceptance criterion:
the observation-only layer does not change agent behavior. Taint leakage rate is the first quantitative
evidence for where T2's gate needs to intervene.

While validating the smoke test, a real bug was found and fixed in the taint-matching logic: it only
detected a known untrusted span copied *verbatim* into new text, not a short value (e.g. an email
address) *extracted from within* a larger untrusted blob — the more common injection pattern in this
suite. Fixed with bidirectional substring matching plus a minimum match length, covered by new unit
tests. All 10 unit tests pass without network access.

## How much has been done from the previous stage

The previous update (2026-07-15) put T1 at roughly 60–70%: core data structures and propagation logic
were done, but pipeline integration and a real benchmark run were still open. Both are now complete —
T1 is done against every acceptance criterion in `docs/ROADMAP.md`, including the full 150-case
evaluation and the taint leakage rate metric.

## Plan for next week

- Formalize the privileged-tool list (draft already used for the leakage metric) and define sensitive
  fields per tool — input for T2 and later T3.
- Design and implement T2: a strict gate that blocks a privileged tool call if any argument is
  `untrusted` or `derived_untrusted`, recording the block decision and reason in the trace.
- Run T2 on the same 150 cases and compare Targeted ASR, Security rate, and Benign Utility against
  T0/T1.
- Collect false positives (blocked benign actions) from that run as input for T3's field-level gate.
