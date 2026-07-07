"""Propagation helpers for T1 taint tracking."""

from __future__ import annotations

from typing import Any

from .models import TaintedSpan
from .registry import TaintRegistry, iter_string_leaves


def record_tool_output(
    registry: TaintRegistry,
    tool_name: str,
    output: Any,
    metadata: dict[str, Any] | None = None,
) -> list[TaintedSpan]:
    """Label every string leaf of a tool output as untrusted."""

    return registry.mark_tool_output(tool_name, output, metadata=metadata)


def derive_argument_spans(
    registry: TaintRegistry,
    tool_name: str,
    arguments: Any,
    metadata: dict[str, Any] | None = None,
) -> dict[str, TaintedSpan]:
    """Create derived spans for textual tool-call argument leaves."""

    spans: dict[str, TaintedSpan] = {}
    for path, text in iter_string_leaves(arguments):
        span_metadata = {"path": path}
        if metadata:
            span_metadata.update(metadata)
        spans[path] = registry.derive_from_text(
            text=text,
            source=f"tool_arg:{tool_name}",
            metadata=span_metadata,
        )
    return spans
