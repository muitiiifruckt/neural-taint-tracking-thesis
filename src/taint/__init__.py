"""T1 tag-only taint tracking package."""

from .agentdojo_hook import PassiveTaintObserver
from .models import TaintedSpan, TrustLabel
from .policy import PRIVILEGED_TOOLS, SENSITIVE_FIELDS, GateDecision, gate_decision
from .propagation import derive_argument_spans, record_tool_output
from .registry import TaintRegistry
from .trace import TaintEvent, TaintTrace

__all__ = [
    "GateDecision",
    "PRIVILEGED_TOOLS",
    "PassiveTaintObserver",
    "SENSITIVE_FIELDS",
    "TaintedSpan",
    "TaintEvent",
    "TaintRegistry",
    "TaintTrace",
    "TrustLabel",
    "derive_argument_spans",
    "gate_decision",
    "record_tool_output",
]
