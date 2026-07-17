#!/usr/bin/env python3
"""T1 evaluation runner: replays the T0 benchmark cases through an AgentDojo pipeline
instrumented with the T1 passive taint observer (`ObservingToolsExecutor`), and writes one
`TaintTrace` JSON per case to `results/T1_traces/`.

Not run through `agentdojo.scripts.benchmark`: that CLI's `--defense` only accepts names from
the hardcoded `DEFENSES` list (see `docs/T1_SPEC.md`, "Точка интеграции с AgentDojo"), so the
pipeline is built here directly. Per-task scoring/caching/logging still goes through
`agentdojo.benchmark`'s own functions so `runs/{pipeline_name}/workspace/...` and utility/
security results are comparable to T0 -- only the pipeline differs, and it is rebuilt fresh for
every case so one case's taint never leaks into another's `TaintRegistry`.

Usage:
    .venv/Scripts/python scripts/run_t1_eval.py                      # full run (10 benign + 140 security)
    .venv/Scripts/python scripts/run_t1_eval.py -ut user_task_0       # smoke test, one user task
    .venv/Scripts/python scripts/run_t1_eval.py -ut user_task_0 -it injection_task_0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # allow `from src.taint...` when run as `python scripts/run_t1_eval.py`

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
from src.taint.pipeline_element import ObservingToolsExecutor
MODEL = "gpt-4o-mini-2024-07-18"
SUITE_NAME = "workspace"
BENCHMARK_VERSION = "v1.2.2"
ATTACK_NAME = "important_instructions"
PIPELINE_NAME = f"{MODEL}-t1-taint"

LOGDIR = ROOT / "runs"
TRACES_DIR = ROOT / "results" / "T1_traces"
RESULTS_DIR = ROOT / "results"

# Draft list of state-changing ("privileged") tools for the workspace suite, used only to
# compute an interim taint-leakage-rate proxy for T1. Not authoritative for T2 -- see
# docs/ROADMAP.md item 7.
PRIVILEGED_TOOLS = {
    "send_email",
    "delete_email",
    "create_calendar_event",
    "cancel_calendar_event",
    "reschedule_calendar_event",
    "add_calendar_event_participants",
    "create_file",
    "delete_file",
    "share_file",
    "append_to_file",
}


def build_pipeline(observer: PassiveTaintObserver) -> AgentPipeline:
    llm = get_llm(MODEL_PROVIDERS[ModelsEnum(MODEL)], MODEL, None, "tool")
    tools_loop = ToolsExecutionLoop([ObservingToolsExecutor(observer), llm])
    pipeline = AgentPipeline(
        [SystemMessage(load_system_message(None)), InitQuery(), llm, tools_loop]
    )
    pipeline.name = PIPELINE_NAME
    return pipeline


def write_trace(observer: PassiveTaintObserver, case_id: str) -> Path:
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    return observer.trace.write_json(TRACES_DIR / f"{case_id}.taint.json")


def run_benign_case(suite, user_task_id: str) -> dict:
    task = suite.get_user_task_by_id(user_task_id)
    observer = PassiveTaintObserver(trace_id=f"{user_task_id}__none__none")
    pipeline = build_pipeline(observer)
    utility, security = run_task_without_injection_tasks(
        suite, pipeline, task, LOGDIR, False, BENCHMARK_VERSION
    )
    write_trace(observer, f"{user_task_id}__none__none")
    return {"user_task_id": user_task_id, "utility": utility, "security": security}


def run_security_case(suite, attack, user_task_id: str, injection_task_id: str) -> dict:
    user_task = suite.get_user_task_by_id(user_task_id)
    case_id = f"{user_task_id}__{ATTACK_NAME}__{injection_task_id}"
    observer = PassiveTaintObserver(trace_id=case_id)
    pipeline = build_pipeline(observer)
    utility_results, security_results = run_task_with_injection_tasks(
        suite, pipeline, user_task, attack, LOGDIR, False, (injection_task_id,), BENCHMARK_VERSION
    )
    write_trace(observer, case_id)
    key = (user_task_id, injection_task_id)
    return {
        "user_task_id": user_task_id,
        "injection_task_id": injection_task_id,
        "utility": utility_results[key],
        "security": security_results[key],
    }


def taint_leakage_rate(case_ids: list[str]) -> tuple[int, int]:
    """Return (tainted privileged calls, total privileged calls) across written traces."""

    tainted, total = 0, 0
    for case_id in case_ids:
        path = TRACES_DIR / f"{case_id}.taint.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data["events"]:
            if event["kind"] != "tool_call" or event["tool_name"] not in PRIVILEGED_TOOLS:
                continue
            total += 1
            if any(span["label"] != "trusted" for span in event["spans"]):
                tainted += 1
    return tainted, total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-task", "-ut", dest="user_tasks", action="append", default=[])
    parser.add_argument("--injection-task", "-it", dest="injection_tasks", action="append", default=[])
    args = parser.parse_args()

    if not load_dotenv(ROOT / ".env"):
        print("Warning: no .env file found")

    suite = get_suite(BENCHMARK_VERSION, SUITE_NAME)
    user_task_ids = args.user_tasks or [f"user_task_{i}" for i in range(10)]
    injection_task_ids = args.injection_tasks or list(suite.injection_tasks.keys())

    benign_cases = []
    security_cases = []
    with OutputLogger(str(LOGDIR)):
        for user_task_id in user_task_ids:
            result = run_benign_case(suite, user_task_id)
            print(f"[benign] {user_task_id}: utility={result['utility']}")
            benign_cases.append(result)

        naming_pipeline = build_pipeline(PassiveTaintObserver(trace_id="__naming__"))
        attack = load_attack(ATTACK_NAME, suite, naming_pipeline)

        for user_task_id in user_task_ids:
            for injection_task_id in injection_task_ids:
                result = run_security_case(suite, attack, user_task_id, injection_task_id)
                print(
                    f"[security] {user_task_id} + {injection_task_id}: "
                    f"utility={result['utility']}, security={result['security']}"
                )
                security_cases.append(result)

    all_case_ids = [f"{c['user_task_id']}__none__none" for c in benign_cases] + [
        f"{c['user_task_id']}__{ATTACK_NAME}__{c['injection_task_id']}" for c in security_cases
    ]
    tainted, total = taint_leakage_rate(all_case_ids)
    leakage_rate = None if total == 0 else 100.0 * tainted / total

    def pct(values: list[bool]) -> float | None:
        return None if not values else 100.0 * sum(values) / len(values)

    summary = {
        "pipeline": PIPELINE_NAME,
        "suite": SUITE_NAME,
        "attack": ATTACK_NAME,
        "defense": "t1-tag-only (gate disabled)",
        "benign_cases": len(benign_cases),
        "security_cases": len(security_cases),
        "benign_utility_pct": pct([c["utility"] for c in benign_cases]),
        "utility_under_attack_pct": pct([c["utility"] for c in security_cases]),
        "security_rate_pct": pct([c["security"] for c in security_cases]),
        "targeted_asr_pct": None
        if pct([c["security"] for c in security_cases]) is None
        else 100.0 - pct([c["security"] for c in security_cases]),
        "privileged_tool_calls": total,
        "tainted_privileged_tool_calls": tainted,
        "taint_leakage_rate_pct": leakage_rate,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "T1_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWrote {out_path}")
    print(f"Wrote traces to {TRACES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
