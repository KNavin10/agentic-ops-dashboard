import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import api
import app as model_app
import auth
import service
import tools


class FakeDatabase:
    def __init__(self, spend=0.0):
        self.spend = spend
        self.spend_reads = 0
        self.records = []

    def get_today_spend(self):
        self.spend_reads += 1
        return self.spend

    def record_agent_run(self, **fields):
        self.records.append(fields)

    def get_today_metrics(self):
        return {"runs_today": len(self.records)}


@pytest.fixture
def fake_db(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(api, "db", database)
    api.observability.response_cache.clear()
    yield database
    api.observability.response_cache.clear()


@pytest.fixture(autouse=True)
def fail_if_external_provider_is_reached(monkeypatch):
    """Keep API tests provider-free even if a fake is accidentally omitted."""
    def fail(*_args, **_kwargs):
        raise AssertionError("External model or retrieval provider must not run in tests")

    monkeypatch.setattr(model_app, "_get_client", fail)
    monkeypatch.setattr(tools.rag, "search_policy", fail)
    monkeypatch.setattr(tools.rag, "embed_chunks", fail)


@pytest.fixture(autouse=True)
def configure_test_api_token(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "test-api-token")


def auth_headers():
    return {"Authorization": "Bearer test-api-token"}


def fake_result(**overrides):
    result = {
        "status": "ok",
        "answer": "A deterministic answer.",
        "trace": [{
            "step": 0,
            "tool": "query_submissions",
            "duration_ms": 4,
            "result_size": 2,
            "status": "ok",
        }],
        "input_tokens": 3,
        "output_tokens": 1,
    }
    result.update(overrides)
    return result


def test_unauthenticated_api_request_returns_401(fake_db):
    response = TestClient(api.app).post("/api/ask", json={"question": "hello"})

    assert response.status_code == 401
    assert not fake_db.records


def test_shared_boundary_records_safe_usage_fields(monkeypatch, fake_db):
    calls = []
    monkeypatch.setattr(api, "answer_question", lambda question: calls.append(question) or fake_result())

    response = TestClient(api.app).post(
        "/api/ask", headers=auth_headers(), json={"question": "  hello  "}
    )

    assert response.status_code == 200
    payload = response.json()
    record = fake_db.records[0]
    assert calls == ["  hello  "]
    assert payload["request_id"]
    assert payload["input_tokens"] == 3
    assert payload["output_tokens"] == 1
    assert payload["tokens"] == 4
    assert payload["cost_usd"] > 0
    assert payload["cached"] is False
    assert record["question_length"] == 5
    assert record["steps"] == 1
    assert record["tool_sequence"] == ["query_submissions"]
    assert record["cache_hit"] is False


def test_cache_hit_bypasses_spend_and_agent_and_records_zero_usage(monkeypatch, fake_db):
    calls = []
    ids = iter(["first", "second"])
    monkeypatch.setattr(api.observability, "generate_request_id", lambda: next(ids))
    monkeypatch.setattr(api, "answer_question", lambda question: calls.append(question) or fake_result())
    client = TestClient(api.app)

    first = client.post("/api/ask", headers=auth_headers(), json={"question": "hello"})
    second = client.post("/api/ask", headers=auth_headers(), json={"question": "hello"})

    assert first.json()["request_id"] == "first"
    assert second.json()["request_id"] == "second"
    assert second.json()["cached"] is True
    assert second.json()["input_tokens"] == 0
    assert second.json()["output_tokens"] == 0
    assert second.json()["cost_usd"] == 0.0
    assert calls == ["hello"]
    assert fake_db.spend_reads == 2
    assert fake_db.records[-1]["cache_hit"] is True


def test_approved_sensitive_requests_always_bypass_cache(monkeypatch, fake_db):
    calls = []

    def fake_answer(question, approve_sensitive=False):
        calls.append((question, approve_sensitive))
        return fake_result()

    monkeypatch.setattr(api, "answer_question", fake_answer)
    client = TestClient(api.app)

    first = client.post(
        "/api/ask",
        headers=auth_headers(),
        json={"question": "send the report", "approve_sensitive": True},
    )
    second = client.post(
        "/api/ask",
        headers=auth_headers(),
        json={"question": "send the report", "approve_sensitive": True},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is False
    assert calls == [("send the report", True), ("send the report", True)]
    assert all(record["cache_hit"] is False for record in fake_db.records)


@pytest.mark.parametrize("path", ["/api/ask", "/api/ask/stream"])
def test_ceiling_rejection_is_recorded_for_both_routes(monkeypatch, fake_db, path):
    fake_db.spend = api.observability.DAILY_COST_CEILING_USD
    called = []
    monkeypatch.setattr(api, "answer_question", lambda *_args, **_kwargs: called.append(True))

    response = TestClient(api.app).post(
        path, headers=auth_headers(), json={"question": "over budget"}
    )

    assert response.status_code == 429
    assert not called
    assert fake_db.records[0]["status"] == "rejected"
    assert fake_db.records[0]["cost_usd"] == 0.0


def test_agent_log_is_one_safe_json_line(monkeypatch, fake_db, caplog):
    monkeypatch.setattr(api, "answer_question", lambda _question: fake_result(
        answer=(
            "do not log this answer; recipient=recipient@example.invalid; "
            "GROQ_API_KEY=groq-secret-test-value"
        ),
        rows=[{"row_secret": "database-row-secret"}],
        trace=[{
            "step": 0,
            "tool": "query_submissions",
            "duration_ms": 4,
            "result_size": 1,
            "status": "ok",
            "args": {
                "secret": "no",
                "recipient": "recipient@example.invalid",
                "GROQ_API_KEY": "groq-secret-test-value",
                "row_secret": "database-row-secret",
            },
        }],
    ))

    with caplog.at_level("INFO", logger="api"):
        TestClient(api.app).post(
            "/api/ask", headers=auth_headers(), json={"question": "private question"}
        )

    lines = [record.getMessage() for record in caplog.records if '"event":"agent_request"' in record.getMessage()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["tools"] == ["query_submissions"]
    assert "private question" not in lines[0]
    assert "do not log this answer" not in lines[0]
    assert "recipient@example.invalid" not in lines[0]
    assert "database-row-secret" not in lines[0]
    assert "groq-secret-test-value" not in lines[0]
    assert "rows" not in lines[0]
    assert "secret" not in lines[0]


def test_budget_warning_only_on_threshold_crossing(monkeypatch, fake_db, caplog):
    spends = iter([0.0, 0.85, 0.85, 0.85])
    monkeypatch.setattr(fake_db, "get_today_spend", lambda: next(spends))
    monkeypatch.setattr(api, "answer_question", lambda question: fake_result())
    client = TestClient(api.app)

    with caplog.at_level("INFO", logger="api"):
        client.post("/api/ask", headers=auth_headers(), json={"question": "first"})
        client.post("/api/ask", headers=auth_headers(), json={"question": "second"})

    warnings = [record for record in caplog.records if '"event":"budget_warning"' in record.getMessage()]
    assert len(warnings) == 1


def test_metrics_requires_auth_and_returns_today_metrics(fake_db):
    client = TestClient(api.app)
    assert client.get("/metrics").status_code == 401
    response = client.get("/metrics", headers=auth_headers())
    assert response.status_code == 200
    assert response.json() == {"runs_today": 0}


def test_health_is_lightweight(monkeypatch):
    def fail_if_called():
        raise AssertionError("health must not check dependencies")

    monkeypatch.setattr(api, "_check_sqlite", fail_if_called)
    monkeypatch.setattr(api, "_check_chroma", fail_if_called)
    monkeypatch.setattr(api, "_check_ollama", fail_if_called)

    response = TestClient(api.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_configured_app_version(monkeypatch):
    monkeypatch.setattr(api, "APP_VERSION", "test-version")

    response = TestClient(api.app).get("/version")

    assert response.status_code == 200
    assert response.json() == {"version": "test-version"}


def test_ready_checks_sqlite_chroma_and_ollama(monkeypatch):
    checked = []

    for name in ("sqlite", "chroma", "ollama"):
        monkeypatch.setattr(
            api,
            f"_check_{name}",
            lambda name=name: checked.append(name),
        )

    response = TestClient(api.app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"sqlite": "ok", "chroma": "ok", "ollama": "ok"},
    }
    assert checked == ["sqlite", "chroma", "ollama"]


def test_ready_returns_503_when_a_dependency_is_unavailable(monkeypatch):
    def fail_ollama():
        raise RuntimeError("ollama unavailable")

    monkeypatch.setattr(api, "_check_sqlite", lambda: None)
    monkeypatch.setattr(api, "_check_chroma", lambda: None)
    monkeypatch.setattr(api, "_check_ollama", fail_ollama)

    response = TestClient(api.app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"sqlite": "ok", "chroma": "ok", "ollama": "error"},
    }


def test_metrics_endpoint_returns_aggregated_usage_from_isolated_sqlite(tmp_path, monkeypatch):
    import db as db_module

    database_path = tmp_path / "metrics.db"
    monkeypatch.setattr(db_module, "DB_PATH", database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            (db_module.Path(__file__).resolve().parents[1] / "schema.sql").read_text()
        )

    database = db_module.Database()
    monkeypatch.setattr(api, "db", database)
    for number, (status_name, steps, latency, input_tokens, output_tokens, cost) in enumerate(
        [
            ("ok", 2, 10, 10, 2, 0.10),
            ("ok", 1, 20, 20, 3, 0.20),
            ("ok", 3, 30, 30, 4, 0.30),
            ("ok", 4, 40, 40, 5, 0.40),
            ("rejected", 0, 100, 0, 0, 0.00),
        ],
    ):
        database.record_agent_run(
            request_id=f"metrics-{number}",
            user_id="local-dev-user",
            question_hash=f"hash-{number}",
            question_length=5,
            status=status_name,
            steps=steps,
            tool_sequence=[],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    response = TestClient(api.app).get("/metrics", headers=auth_headers())

    assert response.status_code == 200
    assert response.json() == {
        "runs_today": 5,
        "success_rate": 80.0,
        "error_rate": 20.0,
        "average_steps": 2.0,
        "p95_latency_ms": 100,
        "tokens_today": 114,
        "spend_today_usd": 1.0,
        "cache_hit_rate": 0.0,
    }


def test_both_routes_call_shared_boundary_once(monkeypatch, fake_db):
    calls = []

    def fake_boundary(request, user):
        calls.append((request.question, user.user_id))
        return api.AskResponse(status="ok", answer="ok")

    monkeypatch.setattr(api, "_answer_with_observability", fake_boundary)
    client = TestClient(api.app)
    client.post("/api/ask", headers=auth_headers(), json={"question": "one"})
    client.post("/api/ask/stream", headers=auth_headers(), json={"question": "two"})

    assert calls == [("one", "local-dev-user"), ("two", "local-dev-user")]


def test_successful_read_only_result_is_cached(monkeypatch, fake_db):
    monkeypatch.setattr(api, "answer_question", lambda _question: fake_result())
    client = TestClient(api.app)

    client.post("/api/ask", headers=auth_headers(), json={"question": "read only"})
    response = client.post(
        "/api/ask", headers=auth_headers(), json={"question": "read only"}
    )

    assert response.json()["cached"] is True
    assert fake_db.records[-1]["cache_hit"] is True


@pytest.mark.parametrize("answer,cited", [("Citation: policy-1", True), ("No citation", False)])
def test_cited_is_derived_without_logging_answer(monkeypatch, fake_db, answer, cited):
    monkeypatch.setattr(api, "answer_question", lambda _question: fake_result(
        answer=answer,
        trace=[{
            "step": 0,
            "tool": "search_policies",
            "duration_ms": 2,
            "result_size": 1,
            "status": "ok",
        }],
    ))

    TestClient(api.app).post("/api/ask", headers=auth_headers(), json={"question": answer})

    assert fake_db.records[0]["cited"] is cited


def test_trace_contains_summaries_not_raw_payloads():
    result = service.to_api_response({
        "status": "ok",
        "trace": [{
            "step": 0,
            "tool": "query_submissions",
            "duration_ms": 4,
            "result_size": 1,
            "status": "ok",
            "args": {"region": "APAC", "secret": "do-not-return"},
            "result": {"rows": [{"id": 1}], "secret": "do-not-return"},
        }],
    })

    assert result["trace"] == [{
        "step": 0,
        "tool": "query_submissions",
        "duration_ms": 4,
        "result_size": 1,
        "status": "ok",
    }]
    assert "args" not in result["trace"][0]
    assert "result" not in result["trace"][0]


def test_stream_api_returns_stable_event_shapes(monkeypatch, fake_db):
    monkeypatch.setattr(api, "answer_question", lambda question, approve_sensitive=False: {
        **fake_result(
            status="awaiting_approval",
            answer="Rows are ready.",
            trace=[{"step": 0, "tool": "query_submissions", "status": "ok"}],
        ),
        "rows": [{"id": 1, "status": "late"}],
        "approval": {
            "tool": "export_report",
            "arguments": {"region": "APAC"},
        },
    })
    response = TestClient(api.app).post(
        "/api/ask/stream", headers=auth_headers(), json={"question": "hello"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[:-1] == [
        {"type": "tool", "tool": "query_submissions", "row_count": 1},
        {"type": "rows", "rows": [{"id": 1, "status": "late"}]},
        {"type": "text", "text": "Rows are ready."},
        {
            "type": "approval",
            "tool": "export_report",
            "arguments": {"region": "APAC"},
        },
    ]
    assert events[-1]["type"] == "done"
    assert events[-1]["request_id"]
