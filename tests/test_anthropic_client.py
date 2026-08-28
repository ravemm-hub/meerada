"""Real ProviderClient behaviour, verified with a FAKE caller — no live API."""

from decimal import Decimal
from uuid import uuid4

from handover.replay.anthropic_client import (
    AnthropicProviderClient,
    PromptPayload,
)
from handover.replay.budget import DailyBudget
from handover.replay.runner import ReplayCase, replay


def make_case() -> ReplayCase:
    return ReplayCase(
        case_id=uuid4(),
        cluster_id="c01",
        input_ref="trace://abc/input",
        expected_ref="trace://abc/output",
        verifier_spec="json_schema",
        input_fingerprint="sha256:" + "1" * 64,
        cache_key="sha256:" + "2" * 64,
    )


class FakeCaller:
    def __init__(self, text: str = '{"ok": true}') -> None:
        self.text = text
        self.calls: list[str] = []

    def complete(self, model, system, messages, max_tokens):
        self.calls.append(model)

        class R:
            text = self.text
            input_tokens = 1000
            output_tokens = 200

        return R()


class DictStore:
    """In-tenant content store + sink. Content never leaves this object."""

    def __init__(self) -> None:
        self.inputs = {
            "trace://abc/input": PromptPayload("SYS", [{"role": "user", "content": "hi"}])
        }
        self.outputs: dict[str, str] = {}

    def resolve(self, case: ReplayCase) -> PromptPayload:
        return self.inputs[case.input_ref]

    def put(self, case: ReplayCase, output_text: str) -> str:
        ref = f"trace://{case.case_id}/candidate"
        self.outputs[ref] = output_text  # stays local
        return ref


def make_client(caller: FakeCaller, store: DictStore) -> AnthropicProviderClient:
    return AnthropicProviderClient(
        "claude-sonnet-5",
        caller,
        store.resolve,
        store,
        price_in_per_mtok=Decimal("2"),
        price_out_per_mtok=Decimal("10"),
    )


def test_run_returns_pointer_and_priced_cost() -> None:
    store = DictStore()
    client = make_client(FakeCaller(), store)
    result = client.run(make_case())
    assert result.output_ref.endswith("/candidate")
    assert result.cost_usd == Decimal("0.004")  # 1000*2 + 200*10 = 4000 / 1e6
    assert result.latency_ms >= 0
    assert result.output_ref in store.outputs  # output stored in-tenant


def test_result_carries_no_content() -> None:
    store = DictStore()
    client = make_client(FakeCaller(text="the secret customer answer"), store)
    result = client.run(make_case())
    assert "secret" not in result.model_dump_json()  # only a pointer + numbers


def test_client_drives_the_replay_runner() -> None:
    store = DictStore()
    for i in range(3):
        store.inputs[f"trace://c{i}/input"] = PromptPayload(
            "SYS", [{"role": "user", "content": "q"}]
        )
    caller = FakeCaller()
    client = make_client(caller, store)
    cases = [
        ReplayCase(
            case_id=uuid4(),
            cluster_id="c01",
            input_ref=f"trace://c{i}/input",
            expected_ref="trace://x/output",
            verifier_spec="json_schema",
            input_fingerprint="sha256:" + f"{i}" * 64,
            cache_key="sha256:" + "a" * 64,
        )
        for i in range(3)
    ]
    report = replay(cases, client, lambda c, r: True, DailyBudget(Decimal("1")))
    assert report.n_run == 3
    assert len(caller.calls) == 3
    assert report.total_cost_usd == Decimal("0.012")
