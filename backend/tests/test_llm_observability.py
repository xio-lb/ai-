import os
from types import SimpleNamespace

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from app.services import deepseek_client, observability


class _FakeCompletions:
    def create(self, **kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"ok": true}')
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=120,
                completion_tokens=30,
                total_tokens=150,
            ),
        )


def test_chat_json_records_tokens_and_cost(monkeypatch, tmp_path):
    monkeypatch.setattr(observability, "DB_PATH", tmp_path / "trace.db")
    observability.reset_for_tests()
    observability.init_db()
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions())
    )
    monkeypatch.setattr(deepseek_client, "client", fake_client)
    monkeypatch.setattr(deepseek_client, "INPUT_COST_PER_1M", 2.0)
    monkeypatch.setattr(deepseek_client, "OUTPUT_COST_PER_1M", 4.0)

    with observability.trace_generation(source="test") as trace:
        result = deepseek_client.chat_json(
            "prompt",
            system_prompt="system",
            prompt_name="unit_test",
        )

    assert result == {"ok": True}
    record = trace.snapshot()
    assert record["llm_tokens"] == 150
    assert record["llm_call_count"] == 1
    call = record["llm_calls"][0]
    assert call["name"] == "unit_test"
    assert call["prompt_tokens"] == 120
    assert call["completion_tokens"] == 30
    assert abs(record["estimated_cost"] - 0.00036) < 1e-9
