# Progress Report — Symbolic Provenance-Gated Defense against Indirect Prompt Injection

**Date:** 2026-07-17
**Repo:** https://github.com/muitiiifruckt/neural-taint-tracking-thesis

Per reviewer feedback, the project is narrowed and reframed: this is a **symbolic
provenance-gated defense** (not "neural taint tracking"), focused on T1–T3. The research
question: *does field-sensitive provenance gating (T3) reduce targeted ASR while preserving
benign utility better than a strict gate (T2)?* A learned sanitizer and formal
noninterference are explicitly out of scope.

## What has been done so far

**Repository.** All claimed code is now committed and pushed (the previous submission's
gap): `src/taint/` (core + policy + pipeline integration), `tests/` (22 unit tests, no
network needed), `scripts/`, `docs/` (per-stage specs), `results/` (summaries + 150 taint
traces). Dependencies are pinned; the eval runner asserts the expected case counts.

**Cleaned-up T0 reporting.** The three evaluations are now separated (previously 10 user
tasks and 14 direct injection-goal runs were mixed into one "benign" number):

1. *Benign user-task evaluation*: 10/10 = **100%** benign utility.
2. *Direct injection-goal achievability*: **7/14** goals performed when asked directly
   (`injection_task_0,1,2,4,5,10,13`). This subset defines the primary ASR metric.
3. *Indirect prompt-injection security* (140 cases): **direct-achievable subset ASR 48.6%**
   (34/70 cases, primary metric); full-set ASR **24.3%** (secondary).

**Corrected metric semantics.** While wiring the T2 gate we found that AgentDojo's raw
per-case `security` field is True when the *injection goal was achieved* (per the
`BaseInjectionTask.security` docstring; confirmed by `TaskSuite.check`, which executes the
attack's ground truth and requires True, and verified empirically on our logs: for
`injection_task_0`, `security=True` exactly in the cases where the email to the attacker
address was actually sent). Our earlier aggregation scripts read it inverted, so previously
reported ASR values were complements of the true ones (e.g. "75.7% full ASR" is actually
24.3%). All numbers in this report use the corrected semantics.

The corrected data also shows why the direct-achievable subset must be the primary metric: on
the 7 non-achievable goals the injected attack succeeded in 0/70 cases, so the full-set ASR
is diluted by goals the agent cannot or will not perform anyway. On the goals it *can*
perform, almost every second attack succeeds (48.6%).

**T1 — tag-only taint tracking: complete, with real benchmark runs.**

- `ObservingToolsExecutor` integrated into a live AgentDojo pipeline (fork of the library's
  `ToolsExecutor`; observes the *raw structured* tool return value before string flattening,
  preserving per-field span granularity).
- Full evaluation on the same 150 cases as T0. Real traces in `results/T1_traces/`
  (150 files) show untrusted tool outputs propagating into later tool-call arguments with
  parent lineage (e.g. an attacker email extracted from an injected calendar-event
  description into `send_email.recipients`).

| Metric | T0 | T1 (gate off) |
|---|---|---|
| Benign utility | 100.0% | **100.0%** |
| Utility under attack | 20.0% | **20.0%** |
| Targeted ASR, direct-achievable subset (primary) | 48.6% (34/70) | 51.4% (36/70) |
| Targeted ASR, full set | 24.3% (34/140) | 28.6% (40/140) |
| Taint leakage rate | — | **36.8%** (202/549 privileged calls) |

Benign utility and utility under attack are *identical* to T0, confirming the tag-only layer
does not change agent behavior; the small ASR difference is LLM run-to-run noise (the gate is
disabled and cannot affect outcomes). Running the real benchmark also surfaced and fixed a
genuine bug in taint matching (short values extracted from larger untrusted blobs were not
detected; fixed with bidirectional matching + minimum match length, covered by unit tests).

**T2 (strict gate) and T3 (field-sensitive gate): implemented and unit-tested.**

- `src/taint/policy.py`: explicit privileged-tool list (10 workspace tools) and a
  per-tool sensitive-fields table (routing/exfiltration targets and destructive-target ids
  are sensitive; content fields are not) — rationale in `docs/T2_SPEC.md`/`docs/T3_SPEC.md`.
- `GatingToolsExecutor`: a blocked privileged call is *not executed*; the LLM receives an
  explanatory tool error, and the trace records `blocked=true`, the reason, and the exact
  tainted argument paths. Unit tests cover: strict blocks any tainted argument; field mode
  allows tainted content fields but blocks tainted routing/target fields; blocked tools
  produce no side effects.
- The runner (`scripts/run_eval.py --stage t1|t2|t3`) reports the same separated metrics for
  every stage, plus **overblock rate** (share of benign user tasks with ≥1 blocked call).

The full T2/T3 evaluations on the 150-case set are ready to launch but currently blocked by
an external issue: the OpenRouter API key began returning `403 Access denied by security
policy` mid-day (after the T1 full run completed). The commands are one-liners once access
is restored.

## How much has been done from the previous stage

The previous update claimed T1 was ~60–70% done but the code was not visible in the
repository. Since then: the repository is complete and pushed; T1 is 100% done including the
full 150-case evaluation, trace evidence, and the taint-leakage metric; T0 reporting is
cleaned up with the direct-achievable subset as the primary ASR metric; T2 and T3 are fully
implemented and unit-tested (evaluation pending API access). Against the reviewer's
checklist, 8 of 10 requested artifacts are delivered; the remaining two (T2/T3 benchmark
numbers and the final T0–T3 comparison table) only need API access to run.

## Plan for the next week

1. Restore API access; run `scripts/run_eval.py --stage t2` and `--stage t3` (150 cases
   each, same configuration as T0/T1).
2. Produce the T0/T1/T2/T3 comparison table: direct-achievable ASR (primary), full ASR,
   benign utility, utility under attack, overblock rate, taint leakage.
3. Collect false positives from T2 traces (blocked benign actions) and analyze whether T3
   recovers them — the core answer to the research question.
4. Include annotated trace examples (blocked exfiltration attempt; allowed benign
   content-copy) in the report.
