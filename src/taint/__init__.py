"""T1 tag-only taint tracking package."""

from .agentdojo_hook import PassiveTaintObserver
from .models import TaintedSpan, TrustLabel
from .propagation import derive_argument_spans, record_tool_output
from .registry import TaintRegistry
from .trace import TaintEvent, TaintTrace

__all__ = [
    "PassiveTaintObserver",
    "TaintedSpan",
    "TaintEvent",
    "TaintRegistry",
    "TaintTrace",
    "TrustLabel",
    "derive_argument_spans",
    "record_tool_output",
]
