from src.taint import TrustLabel
from src.taint.policy import (
    PRIVILEGED_TOOLS,
    SENSITIVE_FIELDS,
    gate_decision,
    top_level_field,
)
from src.taint.registry import TaintRegistry


def _spans(registry: TaintRegistry, values: dict[str, tuple[str, TrustLabel]]):
    return {
        path: registry.add_span(text=text, label=label, source="tool_arg:test")
        for path, (text, label) in values.items()
    }


def test_every_privileged_tool_has_a_sensitive_fields_entry() -> None:
    assert set(SENSITIVE_FIELDS) == set(PRIVILEGED_TOOLS)


def test_top_level_field_strips_indices_and_nesting() -> None:
    assert top_level_field("$.recipients[0]") == "recipients"
    assert top_level_field("$.body") == "body"
    assert top_level_field("$.event.attendees[2]") == "event"


def test_off_mode_never_blocks() -> None:
    registry = TaintRegistry()
    spans = _spans(registry, {"$.recipients[0]": ("evil@x.com", TrustLabel.DERIVED_UNTRUSTED)})
    assert gate_decision("send_email", spans, "off").blocked is False


def test_strict_blocks_privileged_call_with_any_tainted_argument() -> None:
    registry = TaintRegistry()
    spans = _spans(
        registry,
        {
            "$.recipients[0]": ("boss@corp.com", TrustLabel.TRUSTED),
            "$.body": ("quoted untrusted text", TrustLabel.DERIVED_UNTRUSTED),
        },
    )
    decision = gate_decision("send_email", spans, "strict")
    assert decision.blocked is True
    assert "body" in decision.reason
    assert decision.tainted_paths == ("$.body",)


def test_strict_never_blocks_non_privileged_tool() -> None:
    registry = TaintRegistry()
    spans = _spans(registry, {"$.query": ("injected text", TrustLabel.UNTRUSTED)})
    assert gate_decision("search_emails", spans, "strict").blocked is False


def test_strict_allows_privileged_call_with_all_trusted_arguments() -> None:
    registry = TaintRegistry()
    spans = _spans(registry, {"$.recipients[0]": ("boss@corp.com", TrustLabel.TRUSTED)})
    assert gate_decision("send_email", spans, "strict").blocked is False


def test_field_mode_allows_tainted_non_sensitive_field() -> None:
    registry = TaintRegistry()
    spans = _spans(
        registry,
        {
            "$.recipients[0]": ("boss@corp.com", TrustLabel.TRUSTED),
            "$.body": ("summary of untrusted email", TrustLabel.DERIVED_UNTRUSTED),
        },
    )
    assert gate_decision("send_email", spans, "field").blocked is False


def test_field_mode_blocks_tainted_sensitive_field() -> None:
    registry = TaintRegistry()
    spans = _spans(
        registry,
        {"$.recipients[0]": ("attacker@evil.com", TrustLabel.DERIVED_UNTRUSTED)},
    )
    decision = gate_decision("send_email", spans, "field")
    assert decision.blocked is True
    assert decision.tainted_paths == ("$.recipients[0]",)


def test_field_mode_create_file_has_no_sensitive_fields() -> None:
    registry = TaintRegistry()
    spans = _spans(
        registry,
        {
            "$.filename": ("notes.txt", TrustLabel.DERIVED_UNTRUSTED),
            "$.content": ("untrusted content", TrustLabel.UNTRUSTED),
        },
    )
    assert gate_decision("create_file", spans, "field").blocked is False
