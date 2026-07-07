import json

from src.taint import TaintTrace, TrustLabel, derive_argument_spans, record_tool_output
from src.taint.registry import TaintRegistry


def test_trace_serializes_tool_output_and_call(tmp_path) -> None:
    registry = TaintRegistry()
    trace = TaintTrace(trace_id="security_user_task_0_injection_task_1")

    output_spans = record_tool_output(
        registry,
        tool_name="read_email",
        output={"sender": "attacker@example.com"},
    )
    trace.record_tool_output("read_email", {"sender": "attacker@example.com"}, output_spans)

    argument_spans = derive_argument_spans(
        registry,
        tool_name="send_email",
        arguments={"to": "attacker@example.com"},
    )
    trace.record_tool_call(
        tool_name="send_email",
        arguments={"to": "attacker@example.com"},
        argument_spans=argument_spans,
    )

    out_path = trace.write_json(tmp_path / "case.taint.json")
    data = json.loads(out_path.read_text(encoding="utf-8"))

    assert data["trace_id"] == "security_user_task_0_injection_task_1"
    assert [event["kind"] for event in data["events"]] == [
        "tool_output",
        "tool_call",
    ]
    assert data["events"][1]["blocked"] is False
    assert data["events"][1]["spans"][0]["label"] == TrustLabel.DERIVED_UNTRUSTED.value
