"""Live AgentDojo pipeline integration for the T1 passive taint observer.

Kept separate from `agentdojo_hook.py` so that `src/taint/__init__.py` (imported by every
unit test in this package) never has to import the `agentdojo` package. Only the T1 eval
runner (`scripts/run_t1_eval.py`) and its tests import this module directly.

`ObservingToolsExecutor` forks `agentdojo.agent_pipeline.tool_execution.ToolsExecutor` instead
of wrapping it. By the time a stock `ToolsExecutor` appends a `ChatToolResultMessage`, the
tool's return value has already been flattened into one formatted string (YAML/JSON) for the
LLM; T1's propagation rules (`docs/T1_SPEC.md`) recurse into the *structured* return value to
mark each string leaf separately, so taint must be recorded from the raw `FunctionReturnType`
before formatting. Wrapping (call the stock executor, then re-derive from its formatted
output) was considered and rejected: it collapses a tool's output into one untrusted span
covering the whole formatted blob, which makes later substring-based lineage matches
(`TaintRegistry.find_in_text`) miss most real copies (e.g. a single email address copied out
of a much longer formatted body).
"""

from __future__ import annotations

from ast import literal_eval
from collections.abc import Callable, Sequence

from pydantic import BaseModel

from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.llms.google_llm import EMPTY_FUNCTION_NAME
from agentdojo.agent_pipeline.tool_execution import is_string_list, tool_result_to_str
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionReturnType, FunctionsRuntime
from agentdojo.types import ChatMessage, ChatToolResultMessage, text_content_block_from_string

from .agentdojo_hook import PassiveTaintObserver


def _taint_input(value: FunctionReturnType):
    """Recursively convert pydantic models to dicts so string leaves can be walked.

    Mirrors the conversion `tool_result_to_str` applies before formatting, so the structure
    T1 marks as untrusted matches what the LLM will actually see.
    """
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, (list, tuple)):
        return [_taint_input(item) for item in value]
    return value


class ObservingToolsExecutor(BasePipelineElement):
    """Drop-in replacement for `ToolsExecutor` that also feeds T1 taint observation.

    Executes tool calls exactly like the stock `ToolsExecutor`, but additionally calls
    `observer.observe_tool_call` on each call's arguments (before execution, so it can detect
    previously-registered untrusted content copied into them) and `observer.observe_tool_output`
    on the raw return value (after execution, so later tool calls can detect this output being
    copied into their own arguments). Never blocks, rewrites, or delays a call.
    """

    def __init__(
        self,
        observer: PassiveTaintObserver,
        tool_output_formatter: Callable[[FunctionReturnType], str] = tool_result_to_str,
    ) -> None:
        self.observer = observer
        self.output_formatter = tool_output_formatter

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),
        messages: Sequence[ChatMessage] = [],
        extra_args: dict = {},
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        if len(messages) == 0:
            return query, runtime, env, messages, extra_args
        if messages[-1]["role"] != "assistant":
            return query, runtime, env, messages, extra_args
        if messages[-1]["tool_calls"] is None or len(messages[-1]["tool_calls"]) == 0:
            return query, runtime, env, messages, extra_args

        tool_call_results = []
        for tool_call in messages[-1]["tool_calls"]:
            if tool_call.function == EMPTY_FUNCTION_NAME:
                tool_call_results.append(
                    ChatToolResultMessage(
                        role="tool",
                        content=[text_content_block_from_string("")],
                        tool_call_id=tool_call.id,
                        tool_call=tool_call,
                        error="Empty function name provided. Provide a valid function name.",
                    )
                )
                continue
            if tool_call.function not in (tool.name for tool in runtime.functions.values()):
                tool_call_results.append(
                    ChatToolResultMessage(
                        role="tool",
                        content=[text_content_block_from_string("")],
                        tool_call_id=tool_call.id,
                        tool_call=tool_call,
                        error=f"Invalid tool {tool_call.function} provided.",
                    )
                )
                continue

            self.observer.observe_tool_call(tool_call.function, dict(tool_call.args))

            # Converts type of input lists from string to list type (same as ToolsExecutor).
            for arg_k, arg_v in tool_call.args.items():
                if isinstance(arg_v, str) and is_string_list(arg_v):
                    tool_call.args[arg_k] = literal_eval(arg_v)

            tool_call_result, error = runtime.run_function(env, tool_call.function, tool_call.args)
            self.observer.observe_tool_output(tool_call.function, _taint_input(tool_call_result))

            tool_call_id = tool_call.id
            formatted_tool_call_result = self.output_formatter(tool_call_result)
            tool_call_results.append(
                ChatToolResultMessage(
                    role="tool",
                    content=[text_content_block_from_string(formatted_tool_call_result)],
                    tool_call_id=tool_call_id,
                    tool_call=tool_call,
                    error=error,
                )
            )
        return query, runtime, env, [*messages, *tool_call_results], extra_args
