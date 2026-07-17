"""Builds the AgentDojo pipeline for each defense stage (T1/T2/T3).

This is the wrapper around the AgentDojo pipeline referenced by `docs/T1_SPEC.md`
("Точка интеграции с AgentDojo"): it is the single place that assembles
`SystemMessage -> InitQuery -> llm -> ToolsExecutionLoop([executor, llm])` with the taint
executor swapped in for the given stage, so `scripts/run_eval.py` and any future runner share
one definition instead of duplicating pipeline wiring.
"""

from __future__ import annotations

from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, get_llm, load_system_message
from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop
from agentdojo.models import MODEL_PROVIDERS, ModelsEnum

from src.taint.agentdojo_hook import PassiveTaintObserver
from src.taint.pipeline_element import GatingToolsExecutor, ObservingToolsExecutor

MODEL = "gpt-4o-mini-2024-07-18"
SUITE_NAME = "workspace"
BENCHMARK_VERSION = "v1.2.2"
ATTACK_NAME = "important_instructions"

STAGES = {
    "t1": {
        "pipeline_name": f"{MODEL}-t1-taint",
        "defense": "t1-tag-only (gate disabled)",
        "traces_dirname": "T1_traces",
        "summary_name": "T1_summary.json",
        "gate_mode": "off",
    },
    "t2": {
        "pipeline_name": f"{MODEL}-t2-strict-gate",
        "defense": "t2-strict-gate (block privileged call on any tainted argument)",
        "traces_dirname": "T2_traces",
        "summary_name": "T2_summary.json",
        "gate_mode": "strict",
    },
    "t3": {
        "pipeline_name": f"{MODEL}-t3-field-gate",
        "defense": "t3-field-gate (block privileged call on tainted sensitive fields only)",
        "traces_dirname": "T3_traces",
        "summary_name": "T3_summary.json",
        "gate_mode": "field",
    },
}


def build_pipeline(observer: PassiveTaintObserver, stage: dict) -> AgentPipeline:
    llm = get_llm(MODEL_PROVIDERS[ModelsEnum(MODEL)], MODEL, None, "tool")
    if stage["gate_mode"] == "off":
        executor = ObservingToolsExecutor(observer)
    else:
        executor = GatingToolsExecutor(observer, mode=stage["gate_mode"])
    tools_loop = ToolsExecutionLoop([executor, llm])
    pipeline = AgentPipeline(
        [SystemMessage(load_system_message(None)), InitQuery(), llm, tools_loop]
    )
    pipeline.name = stage["pipeline_name"]
    return pipeline
