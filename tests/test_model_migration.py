from types import SimpleNamespace
from unittest.mock import Mock
from src import llm


def test_retired_override_uses_approved_model_and_existing_budget():
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="HEADLINE: Roads reopen"), finish_reason="stop")])
    assert llm.try_generate_with_model(client, "gpt-4.1-nano", "Source facts", "Use only facts")
    options = client.chat.completions.create.call_args.kwargs
    assert options["model"] == "gpt-6-luna"
    assert options["max_completion_tokens"] == 6000
    assert options["reasoning_effort"] == "none"
    assert "temperature" not in options and "max_tokens" not in options
    assert "gpt-4.1-nano" not in llm.MODEL_CHAIN

    assert "gpt-4" not in llm.MODEL_CHAIN
