"""Passive T1 hook skeleton for AgentDojo tool execution.

AgentDojo integration TODO:
- verify the installed `agentdojo.agent_pipeline.BasePipelineElement`
  call signature;
- insert this observer around `ToolsExecutor` inside `ToolsExecutionLoop`;
- write one trace to `results/T1_traces/{case_id}.taint.json`.

This module is intentionally dependency-light: importing it must not require
AgentDojo, an API key, or a benchmark runtime. It records taint only and never
blocks tool calls.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from .propagation import derive_argument_spans, record_tool_output
from .registry import TaintRegistry
from .trace import TaintTrace

P = ParamSpec("P")
R = TypeVar("R")


class PassiveTaintObserver:
    """Records T1 traces around tool calls without changing behavior."""

    def __init__(
        self,
        trace_id: str,
        registry: TaintRegistry | None = None,
        trace: TaintTrace | None = None,
    ) -> None:
        self.registry = registry or TaintRegistry()
        self.trace = trace or TaintTrace(trace_id=trace_id)

    def observe_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        argument_spans = derive_argument_spans(
            registry=self.registry,
            tool_name=tool_name,
            arguments=arguments,
        )
        self.trace.record_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            argument_spans=argument_spans,
            blocked=False,
        )

    def observe_tool_output(self, tool_name: str, output: Any) -> None:
        spans = record_tool_output(
            registry=self.registry,
            tool_name=tool_name,
            output=output,
        )
        self.trace.record_tool_output(
            tool_name=tool_name,
            output=output,
            spans=spans,
        )

    def wrap_tool(
        self,
        tool_name: str,
        function: Callable[P, R],
    ) -> Callable[P, R]:
        """Wrap a tool function while preserving the original return value."""

        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            arguments: dict[str, Any] = dict(kwargs)
            if args:
                arguments["_args"] = list(args)
            self.observe_tool_call(tool_name, arguments)
            output = function(*args, **kwargs)
            self.observe_tool_output(tool_name, output)
            return output

        return wrapped
