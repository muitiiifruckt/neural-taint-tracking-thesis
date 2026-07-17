#!/usr/bin/env python3
"""Evaluation runner for the taint-tracking defense stages (T1/T2/T3) on AgentDojo workspace.

Replays the exact T0 benchmark configuration (model, suite, benchmark version, attack, task
list) through a pipeline instrumented with the taint layer:

- ``--stage t1``: `ObservingToolsExecutor` — observation only, gate disabled.
- ``--stage t2``: `GatingToolsExecutor(mode="strict")` — block any privileged tool call with
  a tainted argument.
- ``--stage t3``: `GatingToolsExecutor(mode="field")` — block only tainted *sensitive* fields
  (see `src/taint/policy.py`).

Not run through `agentdojo.scripts.benchmark`: that CLI's `--defense` only accepts names from
the hardcoded `DEFENSES` list (see `docs/T1_SPEC.md`), so the pipeline is built here directly.
Per-task scoring/caching/logging still goes through `agentdojo.benchmark`'s own functions so
`runs/{pipeline_name}/workspace/...` and utility/security results are comparable to T0 -- only
the pipeline differs, and it is rebuilt fresh for every case so one case's taint never leaks
into another's `TaintRegistry`.

Reported metrics follow three separated evaluations (see `results/T0_summary.md` history):

1. benign user-task evaluation (10 user tasks, no attack);
2. direct injection-goal achievability (fixed from T0: 7 of 14 goals are achievable when
   requested directly -- `DIRECT_ACHIEVABLE_INJECTION_TASKS`);
3. indirect prompt-injection security evaluation (140 cases), where the PRIMARY ASR metric is
   computed on the direct-achievable subset (70 cases) and the full-set ASR is secondary.

Usage:
    .venv/Scripts/python scripts/run_eval.py --stage t1                  # full run (150 cases)
    .venv/Scripts/python scripts/run_eval.py --stage t2 -ut user_task_0 -it injection_task_0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # allow `from src.taint...` when run as `python scripts/run_eval.py`

from dotenv import load_dotenv

from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, get_llm, load_system_message
from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop
from agentdojo.attacks.attack_registry import load_attack
from agentdojo.benchmark import run_task_with_injection_tasks, run_task_without_injection_tasks
from agentdojo.logging import OutputLogger
from agentdojo.models import MODEL_PROVIDERS, ModelsEnum
from agentdojo.task_suite.load_suites import get_suite

from src.taint.agentdojo_hook import PassiveTaintObserver
from src.taint.pipeline_element import GatingToolsExecutor, ObservingToolsExecutor
from src.taint.policy import PRIVILEGED_TOOLS

MODEL = "gpt-4o-mini-2024-07-18"
SUITE_NAME = "workspace"
BENCHMARK_VERSION = "v1.2.2"
ATTACK_NAME = "important_instructions"

# Fixed benchmark shape (asserted on full runs so a silent suite change cannot skew results).
EXPECTED_USER_TASKS = 10
EXPECTED_INJECTION_TASKS = 14

# Injection tasks whose goal the undefended agent achieves when asked for it directly
# (measured once in T0, see results/T0_summary.json "benign_cases_detail" for
# injection_task_* rows). ASR on this subset is the PRIMARY security metric: on the
# remaining tasks a "failed" attack may simply mean the goal was refused/unachievable.
DIRECT_ACHIEVABLE_INJECTION_TASKS = (
    "injection_task_0",
    "injection_task_1",
    "injection_task_2",
    "injection_task_4",
    "injection_task_5",
    "injection_task_10",
    "injection_task_13",
)

STAGES = {
    "t1": {
        "pipeline_name": f"{MODEL}-t1-taint",
        "defense": "t1-tag-only (gate disabled)",
        "traces_dirname": "T1_traces",
        "summary_name": "T1_summary.json",
        "gate_mode": "off",
    },
    "t2": {
        "pipeline_name": f"{MODEL}-t2-strict-gate",
        "defense": "t2-strict-gate (block privileged call on any tainted argument)",
        "traces_dirname": "T2_traces",
        "summary_name": "T2_summary.json",
        "gate_mode": "strict",
    },
    "t3": {
        "pipeline_name": f"{MODEL}-t3-field-gate",
        "defense": "t3-field-gate (block privileged call on tainted sensitive fields only)",
        "traces_dirname": "T3_traces",
        "summary_name": "T3_summary.json",
        "gate_mode": "field",
    },
}

LOGDIR = ROOT / "runs"
RESULTS_DIR = ROOT / "results"


def build_pipeline(observer: PassiveTaintObserver, stage: dict) -> AgentPipeline:
    llm = get_llm(MODEL_PROVIDERS[ModelsEnum(MODEL)], MODEL, None, "tool")
    if stage["gate_mode"] == "off":
        executor = ObservingToolsExecutor(observer)
    else:
        executor = GatingToolsExecutor(observer, mode=stage["gate_mode"])
    tools_loop = ToolsExecutionLoop([executor, llm])
    pipeline = AgentPipeline(
        [SystemMessage(load_system_message(None)), InitQuery(), llm, tools_loop]
    )
    pipeline.name = stage["pipeline_name"]
    return pipeline


def write_trace(observer: PassiveTaintObserver, traces_dir: Path, case_id: str) -> None:
    """Write the case trace, but never clobber a real trace with an empty one.

    When AgentDojo serves a case from its `runs/` cache the pipeline is not executed, the
    observer records zero events, and overwriting would erase the trace captured on the
    original (live) run.
    """

    path = traces_dir / f"{case_id}.taint.json"
    if not observer.trace.events and path.exists():
        return
    traces_dir.mkdir(parents=True, exist_ok=True)
    observer.trace.write_json(path)


def run_benign_case(suite, stage: dict, traces_dir: Path, user_task_id: str) -> dict:
    task = suite.get_user_task_by_id(user_task_id)
    case_id = f"{user_task_id}__none__none"
    observer = PassiveTaintObserver(trace_id=case_id)
    pipeline = build_pipeline(observer, stage)
    utility, security = run_task_without_injection_tasks(
        suite, pipeline, task, LOGDIR, False, BENCHMARK_VERSION
    )
    write_trace(observer, traces_dir, case_id)
    return {"user_task_id": user_task_id, "case_id": case_id, "utility": utility, "security": security}


def run_security_case(
    suite, stage: dict, traces_dir: Path, attack, user_task_id: str, injection_task_id: str
) -> dict:
    user_task = suite.get_user_task_by_id(user_task_id)
    case_id = f"{user_task_id}__{ATTACK_NAME}__{injection_task_id}"
    observer = PassiveTaintObserver(trace_id=case_id)
    pipeline = build_pipeline(observer, stage)
    utility_results, security_results = run_task_with_injection_tasks(
        suite, pipeline, user_task, attack, LOGDIR, False, (injection_task_id,), BENCHMARK_VERSION
    )
    write_trace(observer, traces_dir, case_id)
    key = (user_task_id, injection_task_id)
    return {
        "user_task_id": user_task_id,
        "injection_task_id": injection_task_id,
        "case_id": case_id,
        "utility": utility_results[key],
        "security": security_results[key],
    }


def trace_stats(traces_dir: Path, case_ids: list[str]) -> dict:
    """Aggregate per-call gate/taint statistics from the written traces."""

    stats = {
        "privileged_calls_executed": 0,
        "tainted_privileged_calls_executed": 0,
        "blocked_calls": 0,
        "traces_missing": 0,
    }
    per_case_blocked: dict[str, int] = {}
    for case_id in case_ids:
        path = traces_dir / f"{case_id}.taint.json"
        if not path.exists():
            stats["traces_missing"] += 1
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        blocked_here = 0
        for event in data["events"]:
            if event["kind"] != "tool_call":
                continue
            if event["blocked"]:
                blocked_here += 1
                continue
            if event["tool_name"] not in PRIVILEGED_TOOLS:
                continue
            stats["privileged_calls_executed"] += 1
            if any(span["label"] != "trusted" for span in event["spans"]):
                stats["tainted_privileged_calls_executed"] += 1
        stats["blocked_calls"] += blocked_here
        per_case_blocked[case_id] = blocked_here
    stats["per_case_blocked"] = per_case_blocked
    return stats


def pct(values: list[bool]) -> float | None:
    return None if not values else round(100.0 * sum(values) / len(values), 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=sorted(STAGES), required=True)
    parser.add_argument("--user-task", "-ut", dest="user_tasks", action="append", default=[])
    parser.add_argument("--injection-task", "-it", dest="injection_tasks", action="append", default=[])
    args = parser.parse_args()
    stage = STAGES[args.stage]
    traces_dir = RESULTS_DIR / stage["traces_dirname"]

    if not load_dotenv(ROOT / ".env"):
        print("Warning: no .env file found")

    suite = get_suite(BENCHMARK_VERSION, SUITE_NAME)
    full_run = not args.user_tasks and not args.injection_tasks
    user_task_ids = args.user_tasks or [f"user_task_{i}" for i in range(EXPECTED_USER_TASKS)]
    injection_task_ids = args.injection_tasks or list(suite.injection_tasks.keys())
    if full_run:
        assert len(user_task_ids) == EXPECTED_USER_TASKS, user_task_ids
        assert len(injection_task_ids) == EXPECTED_INJECTION_TASKS, injection_task_ids
    missing = set(DIRECT_ACHIEVABLE_INJECTION_TASKS) - set(suite.injection_tasks.keys())
    assert not missing, f"direct-achievable tasks not in suite: {missing}"

    benign_cases = []
    security_cases = []
    with OutputLogger(str(LOGDIR)):
        for user_task_id in user_task_ids:
            result = run_benign_case(suite, stage, traces_dir, user_task_id)
            print(f"[benign] {user_task_id}: utility={result['utility']}")
            benign_cases.append(result)

        naming_pipeline = build_pipeline(PassiveTaintObserver(trace_id="__naming__"), stage)
        attack = load_attack(ATTACK_NAME, suite, naming_pipeline)

        for user_task_id in user_task_ids:
            for injection_task_id in injection_task_ids:
                result = run_security_case(
                    suite, stage, traces_dir, attack, user_task_id, injection_task_id
                )
                print(
                    f"[security] {user_task_id} + {injection_task_id}: "
                    f"utility={result['utility']}, security={result['security']}"
                )
                security_cases.append(result)

    if full_run:
        assert len(benign_cases) == EXPECTED_USER_TASKS
        assert len(security_cases) == EXPECTED_USER_TASKS * EXPECTED_INJECTION_TASKS

    all_case_ids = [c["case_id"] for c in benign_cases] + [c["case_id"] for c in security_cases]
    stats = trace_stats(traces_dir, all_case_ids)
    per_case_blocked = stats.pop("per_case_blocked")

    benign_with_block = [
        c for c in benign_cases if per_case_blocked.get(c["case_id"], 0) > 0
    ]
    subset_cases = [
        c for c in security_cases if c["injection_task_id"] in DIRECT_ACHIEVABLE_INJECTION_TASKS
    ]

    executed = stats["privileged_calls_executed"]
    tainted = stats["tainted_privileged_calls_executed"]
    security_rate_full = pct([c["security"] for c in security_cases])
    security_rate_subset = pct([c["security"] for c in subset_cases])

    summary = {
        "stage": args.stage,
        "pipeline": stage["pipeline_name"],
        "model": MODEL,
        "suite": SUITE_NAME,
        "benchmark_version": BENCHMARK_VERSION,
        "attack": ATTACK_NAME,
        "defense": stage["defense"],
        "benign_user_tasks": {
            "cases": len(benign_cases),
            "benign_utility_pct": pct([c["utility"] for c in benign_cases]),
        },
        "security_full_set": {
            "cases": len(security_cases),
            "utility_under_attack_pct": pct([c["utility"] for c in security_cases]),
            "security_rate_pct": security_rate_full,
            "targeted_asr_pct": None if security_rate_full is None else round(100.0 - security_rate_full, 2),
        },
        "security_direct_achievable_subset": {
            "injection_tasks": list(DIRECT_ACHIEVABLE_INJECTION_TASKS),
            "cases": len(subset_cases),
            "security_rate_pct": security_rate_subset,
            "targeted_asr_pct": None if security_rate_subset is None else round(100.0 - security_rate_subset, 2),
            "note": "primary ASR metric: goals proven directly achievable in T0",
        },
        "gate": {
            "mode": stage["gate_mode"],
            "blocked_calls_total": stats["blocked_calls"],
            "benign_cases_with_block": len(benign_with_block),
            "benign_overblock_rate_pct": pct(
                [per_case_blocked.get(c["case_id"], 0) > 0 for c in benign_cases]
            ),
        },
        "taint": {
            "privileged_calls_executed": executed,
            "tainted_privileged_calls_executed": tainted,
            "taint_leakage_rate_pct": None if executed == 0 else round(100.0 * tainted / executed, 2),
            "traces_missing": stats["traces_missing"],
        },
        "benign_cases_detail": benign_cases,
        "security_cases_detail": security_cases,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / stage["summary_name"]
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    printable = {k: v for k, v in summary.items() if not k.endswith("_detail")}
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    print(f"\nWrote {out_path}")
    print(f"Wrote traces to {traces_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
