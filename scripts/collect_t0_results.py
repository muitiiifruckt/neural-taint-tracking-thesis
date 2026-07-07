#!/usr/bin/env python3
"""Aggregate AgentDojo T0 benchmark logs into results/T0_summary.md and JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
RESULTS = ROOT / "results"


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


def find_run_dirs(suite: str = "workspace") -> list[Path]:
    if not RUNS.exists():
        return []
    dirs = []
    for pipeline_dir in RUNS.iterdir():
        if not pipeline_dir.is_dir():
            continue
        suite_dir = pipeline_dir / suite
        if suite_dir.is_dir():
            dirs.append(suite_dir)
    return sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)


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


def pct(values: list[bool | None]) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return 100.0 * sum(1 for v in valid if v) / len(valid)


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
    RESULTS.mkdir(exist_ok=True)
    suite_dirs = find_run_dirs("workspace")
    if not suite_dirs:
        print("No runs found under ./runs/*/workspace", file=sys.stderr)
        return 1

    suite_dir = suite_dirs[0]
    pipeline_name = suite_dir.parent.name
    print(f"Using run dir: {suite_dir} (pipeline={pipeline_name})")

    benign_cases = collect_cases(suite_dir, attack=None)
    security_cases = collect_cases(suite_dir, attack="important_instructions")

    benign_utility = pct([c["utility"] for c in benign_cases])
    utility_under_attack = pct([c["utility"] for c in security_cases])
    security_rate = pct([c["security"] for c in security_cases])
    asr = None if security_rate is None else 100.0 - security_rate

    summary = {
        "pipeline": pipeline_name,
        "suite": "workspace",
        "attack": "important_instructions",
        "defense": "none",
        "benign_cases": len(benign_cases),
        "security_cases": len(security_cases),
        "benign_utility_pct": benign_utility,
        "utility_under_attack_pct": utility_under_attack,
        "security_rate_pct": security_rate,
        "targeted_asr_pct": asr,
        "benign_cases_detail": [
            {k: v for k, v in c.items() if k != "messages"} for c in benign_cases
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
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    if benign_utility is not None:
        md_lines.append(f"| Benign Utility | {benign_utility:.1f}% ({len(benign_cases)} tasks) |")
    else:
        md_lines.append("| Benign Utility | n/a |")
    if utility_under_attack is not None:
        md_lines.append(
            f"| Utility Under Attack | {utility_under_attack:.1f}% ({len(security_cases)} cases) |"
        )
    else:
        md_lines.append("| Utility Under Attack | n/a |")
    if security_rate is not None:
        md_lines.append(f"| Security rate | {security_rate:.1f}% |")
    else:
        md_lines.append("| Security rate | n/a |")
    if asr is not None:
        md_lines.append(f"| Targeted ASR | {asr:.1f}% |")
    else:
        md_lines.append("| Targeted ASR | n/a |")

    md_lines.extend(["", "## Benign cases", ""])
    for c in benign_cases:
        status = "PASS" if c["utility"] else "FAIL"
        md_lines.append(f"- `{c['user_task_id']}`: utility={status}, duration={c.get('duration', '?')}s")

    md_lines.extend(["", "## Security cases", ""])
    attack_success = [c for c in security_cases if c["security"] is False]
    md_lines.append(f"- Attack succeeded: {len(attack_success)}/{len(security_cases)}")
    md_lines.append("")
    for c in security_cases:
        util = "PASS" if c["utility"] else "FAIL"
        sec = "BLOCKED" if c["security"] else "SUCCESS"
        md_lines.append(
            f"- `{c['user_task_id']}` + `{c['injection_task_id']}`: "
            f"utility={util}, attack={sec}"
        )

    md_out = RESULTS / "T0_summary.md"
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    traces_dir = RESULTS / "traces"
    traces_dir.mkdir(exist_ok=True)

    for c in benign_cases:
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
            f"utility={c['utility']}, security={c['security']}\n\n"
            f"{format_messages(c['messages'])}",
            encoding="utf-8",
        )

    full_out = RESULTS / "T0_full_traces.json"
    with full_out.open("w", encoding="utf-8") as f:
        json.dump(
            {"benign": benign_cases, "security": security_cases},
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
