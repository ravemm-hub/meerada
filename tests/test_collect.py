"""T3 tests: normalization strips all content, fingerprints identify templates,
and both adapters produce valid Traces."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from handover.collect import LiteLLMAdapter, Normalizer, RawEvent, read_jsonl
from handover.schema import Trace

FIXTURES = Path(__file__).parent / "fixtures"
SALT = "tenant-salt-for-tests"

SECRET_SYSTEM = "SECRET_SYSTEM_PROMPT you are a helpful invoice parser for order 1234"
SECRET_USER = "SECRET_USER_CONTENT parse invoice for client@example.com"
SECRET_OUTPUT = '{"invoice_id": "SECRET-OUTPUT-77", "total": 99.5}'
SECRET_TOOL_ARG = "SECRET_TOOL_ARGUMENT_QUERY"


def make_normalizer() -> Normalizer:
    return Normalizer(tenant_id=uuid4(), salt=SALT)


def make_raw_event() -> RawEvent:
    return RawEvent.model_validate(
        {
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-6",
            "ts_start": "2026-08-26T14:03:22Z",
            "ts_end": "2026-08-26T14:04:03Z",
            "messages": [
                {"role": "system", "content": SECRET_SYSTEM},
                {"role": "user", "content": SECRET_USER},
            ],
            "output_text": SECRET_OUTPUT,
            "tokens": {"input": 8400, "input_cached": 6100, "output": 3100, "reasoning": 2600},
            "cost_usd": "0.0831",
            "tool_calls": [{"name": "lookup", "args": {"query": SECRET_TOOL_ARG}}],
        }
    )


def test_normalized_trace_is_valid_and_shaped() -> None:
    trace = make_normalizer().normalize(make_raw_event())
    assert isinstance(trace, Trace)
    assert trace.cost_usd == Decimal("0.0831")
    assert trace.input_shape.n_messages == 2
    assert trace.input_shape.n_chars == len(SECRET_SYSTEM) + len(SECRET_USER)
    assert trace.output_shape.type == "json"
    assert trace.output_shape.json_valid is True
    assert trace.output_shape.schema_fingerprint is not None
    assert trace.verification.status == "unknown"
    assert trace.latency.total_ms == 41000


def test_no_content_survives_normalization() -> None:
    trace = make_normalizer().normalize(make_raw_event())
    serialized = trace.model_dump_json()
    for secret in (
        SECRET_SYSTEM,
        SECRET_USER,
        SECRET_OUTPUT,
        SECRET_TOOL_ARG,
        "SECRET",
        "invoice",
        "client@example.com",
        SALT,
    ):
        assert secret not in serialized


def test_template_fingerprint_ignores_variables() -> None:
    normalizer = make_normalizer()
    base = make_raw_event()
    variant = make_raw_event()
    variant.messages[0].content = SECRET_SYSTEM.replace("1234", "9876")
    other = make_raw_event()
    other.messages[0].content = "a completely different system prompt"

    fp_base = normalizer.normalize(base).input_shape.system_prompt_fingerprint
    fp_variant = normalizer.normalize(variant).input_shape.system_prompt_fingerprint
    fp_other = normalizer.normalize(other).input_shape.system_prompt_fingerprint
    assert fp_base == fp_variant
    assert fp_base != fp_other


def test_schema_fingerprint_is_structure_only() -> None:
    normalizer = make_normalizer()
    a = make_raw_event()
    b = make_raw_event()
    b.output_text = '{"invoice_id": "OTHER-1", "total": 1.25}'
    c = make_raw_event()
    c.output_text = '{"different_key": true}'

    fp_a = normalizer.normalize(a).output_shape.schema_fingerprint
    fp_b = normalizer.normalize(b).output_shape.schema_fingerprint
    fp_c = normalizer.normalize(c).output_shape.schema_fingerprint
    assert fp_a == fp_b
    assert fp_a != fp_c


def test_different_salt_different_fingerprints() -> None:
    raw = make_raw_event()
    tenant = uuid4()
    fp_one = Normalizer(tenant, "salt-one").normalize(raw).input_shape.input_fingerprint
    fp_two = Normalizer(tenant, "salt-two").normalize(raw).input_shape.input_fingerprint
    assert fp_one != fp_two


def test_output_shape_code_and_text() -> None:
    normalizer = make_normalizer()
    code_only = make_raw_event()
    code_only.output_text = "```python\nprint('x')\n```"
    mixed = make_raw_event()
    mixed.output_text = "Here is the fix:\n```python\nprint('x')\n```"
    plain = make_raw_event()
    plain.output_text = "a plain answer"

    assert normalizer.normalize(code_only).output_shape.type == "code"
    assert normalizer.normalize(mixed).output_shape.type == "mixed"
    assert normalizer.normalize(plain).output_shape.type == "text"
    assert normalizer.normalize(plain).output_shape.schema_fingerprint is None


def test_jsonl_adapter_reads_fixture() -> None:
    normalizer = make_normalizer()
    traces = list(read_jsonl(FIXTURES / "raw_events_sample.jsonl", normalizer))
    assert len(traces) == 3
    assert traces[0].verification.status == "pass"
    assert traces[1].verification.status == "fail"
    assert traces[1].tool_calls[0].name == "run_tests"
    assert traces[2].verification.status == "unknown"
    serialized = "".join(t.model_dump_json() for t in traces)
    assert "SECRET_FIXTURE" not in serialized


def litellm_success_payload() -> tuple[dict[str, object], dict[str, object]]:
    kwargs: dict[str, object] = {
        "model": "claude-sonnet-4-6",
        "custom_llm_provider": "anthropic",
        "response_cost": 0.0123,
        "messages": [
            {"role": "system", "content": SECRET_SYSTEM},
            {"role": "user", "content": SECRET_USER},
        ],
    }
    response: dict[str, object] = {
        "choices": [{"message": {"content": SECRET_OUTPUT}}],
        "usage": {
            "prompt_tokens": 1200,
            "completion_tokens": 300,
            "prompt_tokens_details": {"cached_tokens": 800},
            "completion_tokens_details": {"reasoning_tokens": 150},
        },
    }
    return kwargs, response


def test_litellm_success_callback_emits_trace() -> None:
    sink: list[Trace] = []
    adapter = LiteLLMAdapter(make_normalizer(), sink.append)
    kwargs, response = litellm_success_payload()
    adapter.log_success_event(
        kwargs,
        response,
        datetime(2026, 8, 26, 14, 0, 0),
        datetime(2026, 8, 26, 14, 0, 30),
    )
    assert len(sink) == 1
    trace = sink[0]
    assert trace.tokens.input == 1200
    assert trace.tokens.input_cached == 800
    assert trace.tokens.reasoning == 150
    assert trace.cost_usd == Decimal("0.0123")
    assert trace.ts_start.tzinfo is UTC
    assert trace.verification.status == "unknown"
    assert "SECRET" not in trace.model_dump_json()


def test_litellm_failure_callback_marks_api_error() -> None:
    sink: list[Trace] = []
    adapter = LiteLLMAdapter(make_normalizer(), sink.append)
    kwargs, _ = litellm_success_payload()
    adapter.log_failure_event(
        kwargs,
        None,
        datetime(2026, 8, 26, 14, 0, 0, tzinfo=UTC),
        datetime(2026, 8, 26, 14, 0, 5, tzinfo=UTC),
    )
    assert len(sink) == 1
    assert sink[0].verification.status == "fail"
    assert sink[0].verification.signal == "api_error"
    assert sink[0].tokens.output == 0
