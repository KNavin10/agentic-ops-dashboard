from types import SimpleNamespace

import app


def test_ask_model_uses_completion_token_parameter():
    captured = {}

    def fake_model(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
            )],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
        )

    result = app.ask_model([{"role": "user", "content": "hello"}], model_fn=fake_model)

    assert result["text"] == "ok"
    assert captured["max_completion_tokens"] == 500
    assert "max_tokens" not in captured


def test_ask_model_reads_groq_model_from_environment(monkeypatch):
    captured = {}

    def fake_model(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
            )],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
        )

    monkeypatch.setenv("GROQ_MODEL", "test/groq-model")
    app.ask_model([{"role": "user", "content": "hello"}], model_fn=fake_model)

    assert captured["model"] == "test/groq-model"
