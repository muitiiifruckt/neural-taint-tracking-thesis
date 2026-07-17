"""Gate policy for T2/T3: privileged tools, sensitive fields, and the block decision.

Dependency-light like the rest of the taint core: importing this module must not require
AgentDojo. The policy is defined for the AgentDojo `workspace` suite (v1.2.2) and documented
in `docs/T2_SPEC.md` (privileged tools, strict gate) and `docs/T3_SPEC.md` (sensitive fields).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import TaintedSpan

# State-changing ("privileged") tools of the workspace suite. A gate decision is made only
# for these; read-only tools are never blocked at any stage.
PRIVILEGED_TOOLS: frozenset[str] = frozenset(
    {
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
)

# T3 policy: per privileged tool, the argument fields whose tainted value makes the call
# dangerous — fields that control WHERE data goes (routing/exfiltration targets) or WHICH
# object is destroyed/modified (destructive targets). Content-like fields (subject, body,
# content, title, timestamps) stay non-sensitive: copying untrusted text into content is
# how normal summarize/forward tasks work, and blocking on it is exactly the T2 overblock
# T3 is meant to remove.
SENSITIVE_FIELDS: dict[str, frozenset[str]] = {
    "send_email": frozenset({"recipients", "cc", "bcc", "attachments"}),
    "delete_email": frozenset({"email_id"}),
    "create_calendar_event": frozenset({"participants"}),
    "cancel_calendar_event": frozenset({"event_id"}),
    "reschedule_calendar_event": frozenset({"event_id"}),
    "add_calendar_event_participants": frozenset({"event_id", "participants"}),
    # create_file only creates a new local object: no routing target, nothing destroyed.
    "create_file": frozenset(),
    "delete_file": frozenset({"file_id"}),
    "share_file": frozenset({"file_id", "email"}),
    "append_to_file": frozenset({"file_id"}),
}

GATE_MODES = ("off", "strict", "field")


@dataclass(frozen=True)
class GateDecision:
    blocked: bool
    reason: str | None = None
    tainted_paths: tuple[str, ...] = field(default=())


def top_level_field(path: str) -> str:
    """Return the top-level argument name of a span path like `$.recipients[0]`."""

    name = path.removeprefix("$").lstrip(".")
    for stop in (".", "["):
        index = name.find(stop)
        if index != -1:
            name = name[:index]
    return name


def gate_decision(
    tool_name: str,
    argument_spans: dict[str, TaintedSpan],
    mode: str,
) -> GateDecision:
    """Decide whether a tool call must be blocked under the given gate mode.

    - `off` (T1): never blocks.
    - `strict` (T2): blocks a privileged tool call if ANY argument leaf is tainted.
    - `field` (T3): blocks a privileged tool call only if a tainted leaf belongs to one of
      the tool's `SENSITIVE_FIELDS`.
    """

    if mode not in GATE_MODES:
        raise ValueError(f"Unknown gate mode: {mode!r}")
    if mode == "off" or tool_name not in PRIVILEGED_TOOLS:
        return GateDecision(blocked=False)

    tainted = {path: span for path, span in argument_spans.items() if span.label.is_tainted}
    if mode == "field":
        sensitive = SENSITIVE_FIELDS.get(tool_name, frozenset())
        tainted = {
            path: span for path, span in tainted.items() if top_level_field(path) in sensitive
        }
    if not tainted:
        return GateDecision(blocked=False)

    fields = sorted({top_level_field(path) for path in tainted})
    reason = (
        f"Blocked by taint gate ({mode}): privileged tool '{tool_name}' received "
        f"untrusted-derived content in argument(s) {', '.join(fields)}."
    )
    return GateDecision(blocked=True, reason=reason, tainted_paths=tuple(sorted(tainted)))
