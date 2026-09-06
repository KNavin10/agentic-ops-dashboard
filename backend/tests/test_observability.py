import pytest

import observability


def test_request_id_and_question_hash_are_stable(monkeypatch):
    monkeypatch.setattr(observability.uuid, "uuid4", lambda: "request-id")
    assert observability.generate_request_id() == "request-id"
    assert observability.hash_question("  hello  ") == observability.hash_question("hello")
    assert len(observability.hash_question("hello")) == 64


def test_cost_uses_configured_rates(monkeypatch):
    monkeypatch.setattr(observability, "GROQ_INPUT_USD_PER_MILLION", 0.15)
    monkeypatch.setattr(observability, "GROQ_OUTPUT_USD_PER_MILLION", 0.60)
    assert observability.calculate_cost(1_000_000, 500_000) == pytest.approx(0.45)


def test_cache_only_stores_safe_successes_and_expires_without_sleep(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(observability, "CACHE_TTL_SECONDS", 3600.0)
    cache = observability.ResponseCache(lambda: now[0])
    assert cache.put("u", "q", {"answer": "ok"}, status="ok")
    assert cache.get("u", "q") == {"answer": "ok"}
    assert cache.get("other-user", "q") is None
    assert not cache.put("u", "bad", "error", status="error")
    assert not cache.put("u", "export", "secret", status="ok", tool_sequence=["export_report"])
    assert not cache.put("u", "export", "secret", status="ok", approve_sensitive=True)
    assert not cache.put("u", "email", "secret", status="ok", tool_sequence=["email_summary"])
    now[0] = 3700.0
    assert cache.get("u", "q") is None
