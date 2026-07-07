"""Core data models for T1 taint tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrustLabel(str, Enum):
    """Trust labels used by the symbolic T1 tracker."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    DERIVED_UNTRUSTED = "derived_untrusted"

    @property
    def is_tainted(self) -> bool:
        return self is not TrustLabel.TRUSTED


@dataclass(frozen=True)
class TaintedSpan:
    """A labeled text span with optional provenance parents."""

    span_id: str
    text: str
    label: TrustLabel
    source: str
    parents: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "text": self.text,
            "label": self.label.value,
            "source": self.source,
            "parents": list(self.parents),
            "metadata": self.metadata,
        }
