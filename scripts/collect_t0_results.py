#!/usr/bin/env python3
"""Aggregate AgentDojo T0 benchmark logs into results/T0_summary.md and JSON.

Reports three clearly separated evaluations (they must never be mixed into one number):

1. benign user-task evaluation -- the 10 `user_task_*` runs without attack;
2. direct injection-goal achievability -- the 14 `injection_task_*` runs executed directly
   as user tasks (no attack): which attacker goals the model performs when simply asked;
3. indirect prompt-injection security evaluation -- 140 attacked cases, with the PRIMARY
   targeted-ASR metric computed on the direct-achievable subset from (2) and the full-set
   ASR reported as secondary.

AgentDojo's raw per-case ``security`` field is True when the INJECTION GOAL WAS ACHIEVED
(`BaseInjectionTask.security` docstring; verified against `TaskSuite.check`, which runs the
attack's ground truth and requires True; also verified empirically on these logs: for
injection_task_0, security=True exactly when the email to the attacker address appears in the
messages). So ASR = share of cases with ``security=True``; the security rate is its complement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # allow `from src.agent...` when run as `python scripts/collect_t0_results.py`

from src.agent.metrics import asr_and_security_rate, pct  # noqa: E402

RUNS = ROOT / "runs"
RESULTS = ROOT / "results"

# T0 is the undefended stock pipeline; do not auto-pick the most recent runs/ subdir --
# T1/T2/T3 runners create their own pipeline dirs there.
DEFAULT_PIPELINE = "gpt-4o-mini-2024-07-18"

EXPECTED_USER_TASKS = 10
EXPECTED_INJECTION_TASKS = 14


def message_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("content", block.get("text", block))))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def load_task_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def collect_cases(suite_dir: Path, attack: str | None) -> list[dict]:
    cases: list[dict] = []
    for user_task_dir in sorted(suite_dir.iterdir()):
        if not user_task_dir.is_dir():
            continue
        user_task_id = user_task_dir.name
        if attack is None:
            attack_dir = user_task_dir / "none"
            if not attack_dir.exists():
                continue
            json_path = attack_dir / "none.json"
            if json_path.exists():
                data = load_task_json(json_path)
                cases.append(
                    {
                        "user_task_id": user_task_id,
                        "injection_task_id": None,
                        "attack": "none",
                        "utility": data.get("utility"),
                        "security": data.get("security"),
                        "duration": data.get("duration"),
                        "error": data.get("error"),
                        "messages": data.get("messages", []),
                        "log_path": str(json_path.relative_to(ROOT)),
                    }
                )
        else:
            attack_dir = user_task_dir / attack
            if not attack_dir.exists():
                continue
            for json_path in sorted(attack_dir.glob("*.json")):
                data = load_task_json(json_path)
                cases.append(
                    {
                        "user_task_id": user_task_id,
                        "injection_task_id": json_path.stem,
                        "attack": attack,
                        "utility": data.get("utility"),
                        "security": data.get("security"),
                        "duration": data.get("duration"),
                        "error": data.get("error"),
                        "messages": data.get("messages", []),
                        "log_path": str(json_path.relative_to(ROOT)),
                    }
                )
    return cases


def not_none(values: list[bool | None]) -> list[bool]:
    return [v for v in values if v is not None]


def format_messages(messages: list) -> str:
    lines = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        text = message_text(msg.get("content"))
        tool_calls = msg.get("tool_calls")
        header = f"### Message {i + 1} ({role})"
        lines.append(header)
        if text.strip():
            lines.append(text.strip())
        if tool_calls:
            lines.append("```json")
            lines.append(json.dumps(tool_calls, indent=2, ensure_ascii=False))
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", default=DEFAULT_PIPELINE)
    args = parser.parse_args()

    RESULTS.mkdir(exist_ok=True)
    suite_dir = RUNS / args.pipeline / "workspace"
    if not suite_dir.is_dir():
        print(f"No run dir at {suite_dir}", file=sys.stderr)
        return 1
    pipeline_name = args.pipeline
    print(f"Using run dir: {suite_dir} (pipeline={pipeline_name})")

    no_attack_cases = collect_cases(suite_dir, attack=None)
    security_cases = collect_cases(suite_dir, attack="important_instructions")

    # Evaluation 1: benign user tasks only.
    benign_cases = [c for c in no_attack_cases if c["user_task_id"].startswith("user_task")]
    # Evaluation 2: injection goals requested directly (no attack involved).
    direct_goal_cases = [
        c for c in no_attack_cases if c["user_task_id"].startswith("injection_task")
    ]
    direct_achievable = sorted(
        (c["user_task_id"] for c in direct_goal_cases if c["utility"]),
        key=lambda t: int(t.rsplit("_", 1)[1]),
    )

    assert len(benign_cases) == EXPECTED_USER_TASKS, len(benign_cases)
    assert len(direct_goal_cases) == EXPECTED_INJECTION_TASKS, len(direct_goal_cases)
    assert len(security_cases) == EXPECTED_USER_TASKS * EXPECTED_INJECTION_TASKS, len(security_cases)

    # Evaluation 3: security under indirect prompt injection.
    subset_cases = [c for c in security_cases if c["injection_task_id"] in direct_achievable]
    benign_utility = pct(not_none([c["utility"] for c in benign_cases]))
    utility_under_attack = pct(not_none([c["utility"] for c in security_cases]))
    # Raw `security` field: True = attack succeeded (see module docstring).
    asr, security_rate = asr_and_security_rate(not_none([c["security"] for c in security_cases]))
    asr_subset, security_rate_subset = asr_and_security_rate(not_none([c["security"] for c in subset_cases]))

    summary = {
        "pipeline": pipeline_name,
        "suite": "workspace",
        "attack": "important_instructions",
        "defense": "none",
        "benign_user_tasks": {
            "cases": len(benign_cases),
            "benign_utility_pct": benign_utility,
        },
        "direct_goal_achievability": {
            "cases": len(direct_goal_cases),
            "achievable": direct_achievable,
            "achievable_count": len(direct_achievable),
        },
        "security_full_set": {
            "cases": len(security_cases),
            "utility_under_attack_pct": utility_under_attack,
            "security_rate_pct": security_rate,
            "targeted_asr_pct": asr,
        },
        "security_direct_achievable_subset": {
            "injection_tasks": direct_achievable,
            "cases": len(subset_cases),
            "security_rate_pct": security_rate_subset,
            "targeted_asr_pct": asr_subset,
            "note": "primary ASR metric: goals proven directly achievable",
        },
        "benign_cases_detail": [
            {k: v for k, v in c.items() if k != "messages"} for c in benign_cases
        ],
        "direct_goal_cases_detail": [
            {k: v for k, v in c.items() if k != "messages"} for c in direct_goal_cases
        ],
        "security_cases_detail": [
            {k: v for k, v in c.items() if k != "messages"} for c in security_cases
        ],
    }

    json_out = RESULTS / "T0_summary.json"
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    md_lines = [
        "# T0 Baseline Results",
        "",
        f"- Pipeline: `{pipeline_name}`",
        "- Suite: `workspace` (v1.2.2)",
        "- Attack: `important_instructions` (security run only)",
        "- Defense: none",
        "",
        "Три раздельные оценки (не смешивать):",
        "",
        "## 1. Benign user-task evaluation (10 user tasks, no attack)",
        "",
        f"- Benign Utility: **{benign_utility:.1f}%** ({len(benign_cases)} tasks)",
        "",
        "## 2. Direct injection-goal achievability (14 injection tasks run directly)",
        "",
        f"- Achievable when asked directly: **{len(direct_achievable)}/{len(direct_goal_cases)}**: "
        + ", ".join(f"`{t}`" for t in direct_achievable),
        "- Остальные цели агент по прямой просьбе не выполняет (отказ или не по силам) —",
        "  поэтому «атака не удалась» на них не доказывает работу защиты.",
        "",
        "## 3. Security under indirect prompt injection",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Targeted ASR, direct-achievable subset (primary)** | **{asr_subset:.1f}%** ({len(subset_cases)} cases) |",
        f"| Targeted ASR, full set (secondary) | {asr:.1f}% ({len(security_cases)} cases) |",
        f"| Security rate, subset | {security_rate_subset:.1f}% |",
        f"| Security rate, full | {security_rate:.1f}% |",
        f"| Utility Under Attack (full) | {utility_under_attack:.1f}% |",
    ]

    md_lines.extend(["", "## Benign cases", ""])
    for c in benign_cases:
        status = "PASS" if c["utility"] else "FAIL"
        md_lines.append(f"- `{c['user_task_id']}`: utility={status}, duration={c.get('duration', '?')}s")

    md_lines.extend(["", "## Direct injection-goal runs", ""])
    for c in direct_goal_cases:
        status = "ACHIEVABLE" if c["utility"] else "NOT ACHIEVED"
        md_lines.append(f"- `{c['user_task_id']}`: {status}")

    md_lines.extend(["", "## Security cases", ""])
    attack_success = [c for c in security_cases if c["security"] is True]
    md_lines.append(f"- Attack succeeded: {len(attack_success)}/{len(security_cases)}")
    md_lines.append("")
    for c in security_cases:
        util = "PASS" if c["utility"] else "FAIL"
        sec = "SUCCESS" if c["security"] else "FAILED"
        md_lines.append(
            f"- `{c['user_task_id']}` + `{c['injection_task_id']}`: "
            f"utility={util}, attack={sec}"
        )

    md_out = RESULTS / "T0_summary.md"
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    traces_dir = RESULTS / "traces"
    traces_dir.mkdir(exist_ok=True)

    for c in no_attack_cases:
        out = traces_dir / f"benign_{c['user_task_id']}.md"
        out.write_text(
            f"# Benign trace: {c['user_task_id']}\n\n"
            f"utility={c['utility']}\n\n"
            f"{format_messages(c['messages'])}",
            encoding="utf-8",
        )

    for c in security_cases:
        inj = c["injection_task_id"]
        out = traces_dir / f"security_{c['user_task_id']}_{inj}.md"
        out.write_text(
            f"# Security trace: {c['user_task_id']} + {inj}\n\n"
            f"utility={c['utility']}, attack_successful={c['security']}\n\n"
            f"{format_messages(c['messages'])}",
            encoding="utf-8",
        )

    full_out = RESULTS / "T0_full_traces.json"
    with full_out.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "benign": benign_cases,
                "direct_goal": direct_goal_cases,
                "security": security_cases,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWrote {json_out}")
    print(f"Wrote {md_out}")
    print(f"Wrote {full_out}")
    print(f"Wrote traces to {traces_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
