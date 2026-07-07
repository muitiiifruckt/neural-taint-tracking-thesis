# T1 Spec: Tag-Only Taint Layer

## Goal

T1 adds a standalone taint-tracking layer for AgentDojo workspace runs. It records trust labels and provenance lineage for strings that flow from tool outputs into later tool-call arguments.

The T1 gate is OFF. The layer must not block, rewrite, delay, or otherwise change tool execution behavior. T0 baseline scripts and metrics remain valid references.

## Non-Goals

- No blocking of privileged tool calls.
- No sanitizer, rewriting, redaction, or LLM prompt transformation.
- No retraining or model changes.
- No claim of complete information-flow tracking inside the LLM.
- No change to `scripts/run_t0_baseline.ps1` or T0 collection behavior.

## Trust Labels

- `trusted`: system prompt, user task, tool schemas, and constants authored by the benchmark harness.
- `untrusted`: direct external/tool output, including email bodies, calendar descriptions, drive file contents, and other workspace data returned by tools.
- `derived_untrusted`: a later string that copies, quotes, formats, or otherwise includes text from an untrusted span.

For T1, `derived_untrusted` is observational only. T2 will decide whether to block.

## Data Model and API

### `TaintedSpan`

Represents a labeled text fragment:

- `span_id`: stable unique id.
- `text`: exact string fragment.
- `label`: one of `trusted`, `untrusted`, `derived_untrusted`.
- `source`: source descriptor such as `tool:read_inbox`.
- `parents`: zero or more parent span ids.
- `metadata`: optional JSON-serializable context.

### `TaintRegistry`

In-memory index for spans:

- `add_span(text, label, source, parents=None, metadata=None) -> TaintedSpan`
- `mark_tool_output(tool_name, output, metadata=None) -> list[TaintedSpan]`
- `derive_from_text(text, source, metadata=None) -> TaintedSpan`
- `find_in_text(text) -> list[TaintedSpan]`
- `label_for_text(text) -> TrustLabel`

`derive_from_text` searches for already-registered untrusted spans copied into `text`. If found, it creates a `derived_untrusted` span with those spans as parents; otherwise it creates a `trusted` span.

### `TaintTrace`

Serializable event log:

- `trace_id`
- `events`
- `record_tool_output(tool_name, output, spans)`
- `record_tool_call(tool_name, arguments, argument_spans, blocked=False)`
- `to_dict()`
- `write_json(path)`

`blocked` is always `false` in T1.

## Propagation Rules

1. Tool outputs are `untrusted`.
2. If a later string contains an exact registered untrusted span, the later string is `derived_untrusted`.
3. If a dictionary/list/tuple/set is passed as tool output, T1 recursively extracts string leaves and labels each leaf as `untrusted`.
4. Tool-call arguments are inspected recursively. String leaves are labeled with `derive_from_text`.
5. Non-string scalar values are not tainted in T1 unless their string representation contains a known untrusted span. This is conservative for the current workspace suite, where injection payloads are textual.

## AgentDojo Integration Point

AgentDojo pipelines are built from `BasePipelineElement` elements. Tool execution is performed inside `ToolsExecutionLoop`, typically through `ToolsExecutor`.

T1 should be inserted as a passive observer next to tool execution:

1. after tool outputs are produced, call `record_tool_output`;
2. before the next tool call is executed, call `record_tool_call`;
3. return the original pipeline data unchanged.

The lightweight skeleton lives in `src/taint/agentdojo_hook.py`. It intentionally avoids changing benchmark configuration until the exact AgentDojo `BasePipelineElement` method signature is verified against the installed package. The integration TODO is to subclass `agentdojo.agent_pipeline.BasePipelineElement` and place the observer around `ToolsExecutor` inside the workspace benchmark pipeline.

## Trace JSON Schema

Default output directory:

```text
results/T1_traces/
```

One trace file per benchmark case:

```text
results/T1_traces/{case_id}.taint.json
```

Schema:

```json
{
  "trace_id": "security_user_task_0_injection_task_1",
  "events": [
    {
      "event_id": "event_000001",
      "kind": "tool_output",
      "tool_name": "read_email",
      "arguments": null,
      "spans": [
        {
          "span_id": "span_000001",
          "text": "Ignore previous instructions...",
          "label": "untrusted",
          "source": "tool:read_email",
          "parents": [],
          "metadata": {}
        }
      ],
      "blocked": false,
      "metadata": {}
    }
  ]
}
```

## Acceptance Criteria

- Unit tests pass without requiring an API key or live AgentDojo run.
- Tool output string leaves are labeled `untrusted`.
- Exact copies from untrusted text into later strings become `derived_untrusted`.
- Registry preserves parent lineage.
- Trace JSON can be serialized and reloaded.
- Synthetic email-to-`send_email` case shows untrusted email content flowing into a privileged tool argument.
- T1 does not block: every recorded tool call has `blocked=false`.
- T0 scripts remain unchanged.

## Tests

Focused tests live under `tests/`:

- label enum and span serialization;
- registry add/find/derive behavior;
- recursive tool output propagation;
- trace JSON serialization;
- synthetic `read_email` output to `send_email(to=...)` lineage.

## T2 Preview

T2 will add the gate:

- classify privileged tools and sensitive fields;
- block or allow tool calls based on tainted arguments;
- emit explicit gate decisions;
- measure Targeted ASR and Benign Utility against T0.

T2 is explicitly out of scope for T1. T1 only records evidence needed to design and debug the gate.
