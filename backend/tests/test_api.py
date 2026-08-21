import json

from fastapi.testclient import TestClient

import api
import service


def test_unauthenticated_api_request_returns_401():
    client = TestClient(api.app)

    response = client.post("/api/ask", json={"question": "hello"})

    assert response.status_code == 401


def test_valid_api_request_returns_expected_response_shape(monkeypatch):
    monkeypatch.setattr(
        api,
        "answer_question",
        lambda question: {
            "status": "ok",
            "answer": "A deterministic answer.",
            "trace": [{"step": 0, "tool": "query_submissions", "status": "ok"}],
            "tokens": 4,
        },
    )
    client = TestClient(api.app)

    response = client.post(
        "/api/ask",
        headers={"Authorization": "Bearer local-dev-token"},
        json={"question": "hello"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "answer": "A deterministic answer.",
        "trace": [{"step": 0, "tool": "query_submissions", "status": "ok"}],
        "rows": [],
        "approval": None,
        "tokens": 4,
    }


def test_trace_contains_summaries_not_raw_payloads():
    result = service.to_api_response({
        "status": "ok",
        "trace": [{
            "step": 0,
            "tool": "query_submissions",
            "args": {"region": "APAC", "secret": "do-not-return"},
            "result": {"rows": [{"id": 1}], "secret": "do-not-return"},
        }],
    })

    assert result["trace"] == [{
        "step": 0,
        "tool": "query_submissions",
        "status": "ok",
    }]
    assert "args" not in result["trace"][0]
    assert "result" not in result["trace"][0]


def test_stream_api_returns_stable_event_shapes(monkeypatch):
    monkeypatch.setattr(
        api,
        "answer_question",
        lambda question, approve_sensitive=False: {
            "status": "awaiting_approval",
            "answer": "Rows are ready.",
            "trace": [{"step": 0, "tool": "query_submissions", "status": "ok"}],
            "rows": [{"id": 1, "status": "late"}],
            "approval": {
                "tool": "export_report",
                "arguments": {"region": "APAC"},
            },
            "tokens": 4,
        },
    )
    client = TestClient(api.app)

    response = client.post(
        "/api/ask/stream",
        headers={"Authorization": "Bearer local-dev-token"},
        json={"question": "hello"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert [json.loads(line) for line in response.text.splitlines()] == [
        {"type": "tool", "tool": "query_submissions", "row_count": 1},
        {"type": "rows", "rows": [{"id": 1, "status": "late"}]},
        {"type": "text", "text": "Rows are ready."},
        {
            "type": "approval",
            "tool": "export_report",
            "arguments": {"region": "APAC"},
        },
        {"type": "done"},
    ]
