"""Trace serialization for T1 taint observations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import TaintedSpan


@dataclass(frozen=True)
class TaintEvent:
    event_id: str
    kind: str
    tool_name: str
    arguments: Any | None
    spans: tuple[TaintedSpan, ...]
    blocked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "tool_name": self.tool_name,
            "arguments": json_safe(self.arguments),
            "spans": [span.to_dict() for span in self.spans],
            "blocked": self.blocked,
            "metadata": self.metadata,
        }


class TaintTrace:
    """Append-only trace of T1 observations."""

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self._counter = 0
        self._events: list[TaintEvent] = []

    @property
    def events(self) -> tuple[TaintEvent, ...]:
        return tuple(self._events)

    def record_tool_output(
        self,
        tool_name: str,
        output: Any,
        spans: list[TaintedSpan],
        metadata: dict[str, Any] | None = None,
    ) -> TaintEvent:
        return self._append(
            kind="tool_output",
            tool_name=tool_name,
            arguments=None,
            spans=tuple(spans),
            blocked=False,
            metadata={"output_type": type(output).__name__, **(metadata or {})},
        )

    def record_tool_call(
        self,
        tool_name: str,
        arguments: Any,
        argument_spans: dict[str, TaintedSpan],
        blocked: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> TaintEvent:
        trace_metadata = {
            "argument_paths": {
                path: span.span_id for path, span in argument_spans.items()
            }
        }
        if metadata:
            trace_metadata.update(metadata)
        return self._append(
            kind="tool_call",
            tool_name=tool_name,
            arguments=arguments,
            spans=tuple(argument_spans.values()),
            blocked=blocked,
            metadata=trace_metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "events": [event.to_dict() for event in self._events],
        }

    def write_json(self, path: str | Path) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out_path

    def _append(
        self,
        kind: str,
        tool_name: str,
        arguments: Any | None,
        spans: tuple[TaintedSpan, ...],
        blocked: bool,
        metadata: dict[str, Any],
    ) -> TaintEvent:
        self._counter += 1
        event = TaintEvent(
            event_id=f"event_{self._counter:06d}",
            kind=kind,
            tool_name=tool_name,
            arguments=arguments,
            spans=spans,
            blocked=blocked,
            metadata=metadata,
        )
        self._events.append(event)
        return event


def json_safe(value: Any) -> Any:
    """Return a JSON-serializable representation without mutating input."""

    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value
