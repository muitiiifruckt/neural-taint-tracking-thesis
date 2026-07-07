"""In-memory taint span registry."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import TaintedSpan, TrustLabel


class TaintRegistry:
    """Tracks tainted spans and derives labels for copied strings."""

    def __init__(self) -> None:
        self._counter = 0
        self._spans: dict[str, TaintedSpan] = {}

    @property
    def spans(self) -> tuple[TaintedSpan, ...]:
        return tuple(self._spans.values())

    def add_span(
        self,
        text: str,
        label: TrustLabel | str,
        source: str,
        parents: Iterable[str | TaintedSpan] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaintedSpan:
        self._counter += 1
        parent_ids = tuple(
            parent.span_id if isinstance(parent, TaintedSpan) else parent
            for parent in (parents or ())
        )
        span = TaintedSpan(
            span_id=f"span_{self._counter:06d}",
            text=text,
            label=TrustLabel(label),
            source=source,
            parents=parent_ids,
            metadata=metadata or {},
        )
        self._spans[span.span_id] = span
        return span

    def mark_tool_output(
        self,
        tool_name: str,
        output: Any,
        metadata: dict[str, Any] | None = None,
    ) -> list[TaintedSpan]:
        spans: list[TaintedSpan] = []
        for path, text in iter_string_leaves(output):
            if text == "":
                continue
            span_metadata = {"path": path}
            if metadata:
                span_metadata.update(metadata)
            spans.append(
                self.add_span(
                    text=text,
                    label=TrustLabel.UNTRUSTED,
                    source=f"tool:{tool_name}",
                    metadata=span_metadata,
                )
            )
        return spans

    def derive_from_text(
        self,
        text: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> TaintedSpan:
        parents = [span for span in self.find_in_text(text) if span.label.is_tainted]
        label = (
            TrustLabel.DERIVED_UNTRUSTED
            if parents
            else TrustLabel.TRUSTED
        )
        return self.add_span(
            text=text,
            label=label,
            source=source,
            parents=parents,
            metadata=metadata,
        )

    def find_in_text(self, text: str) -> list[TaintedSpan]:
        matches = [
            span
            for span in self._spans.values()
            if span.text and span.text in text
        ]
        return sorted(matches, key=lambda span: (len(span.text), span.span_id), reverse=True)

    def label_for_text(self, text: str) -> TrustLabel:
        matches = self.find_in_text(text)
        for span in matches:
            if span.text == text and span.label is TrustLabel.UNTRUSTED:
                return TrustLabel.UNTRUSTED
        if any(span.label.is_tainted for span in matches):
            return TrustLabel.DERIVED_UNTRUSTED
        return TrustLabel.TRUSTED


def iter_string_leaves(value: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    """Yield `(path, text)` for every string leaf in a nested value."""

    if isinstance(value, str):
        yield path, value
        return

    if isinstance(value, dict):
        for key, item in value.items():
            key_path = f"{path}.{key}" if isinstance(key, str) else f"{path}[{key!r}]"
            yield from iter_string_leaves(item, key_path)
        return

    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from iter_string_leaves(item, f"{path}[{index}]")
        return

    if isinstance(value, set):
        for index, item in enumerate(sorted(value, key=repr)):
            yield from iter_string_leaves(item, f"{path}[{index}]")
