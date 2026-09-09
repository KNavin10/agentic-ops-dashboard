import sqlite3

from fastapi.testclient import TestClient
from pydantic import ValidationError

import agent
import api
import auth
import db
import tools
from models import (
    BreachReasonArgs,
    EmailSummaryArgs,
    QueryArgs,
    SearchPoliciesArgs,
)


def test_tool_models_forbid_extra_fields_and_validate_email():
    for model, value in (
        (QueryArgs, {"region": "APAC", "unexpected": True}),
        (BreachReasonArgs, {"ids": [1], "unexpected": True}),
        (SearchPoliciesArgs, {"question": "deadline", "unexpected": True}),
        (EmailSummaryArgs, {
            "recipient": "person@example.com",
            "subject": "hello",
            "body": "body",
            "unexpected": True,
        }),
    ):
        try:
            model.model_validate(value)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"{model.__name__} accepted an unknown field")

    for value in (
        {"recipient": "not-an-email", "subject": "hello", "body": "body"},
        {"recipient": "person@example.com", "subject": "x" * 201, "body": "body"},
        {"recipient": "person@example.com", "subject": "hello", "body": "x" * 5001},
    ):
        try:
            EmailSummaryArgs.model_validate(value)
        except ValidationError:
            pass
        else:
            raise AssertionError("invalid email summary was accepted")


def test_breach_reasons_does_not_return_client_name(monkeypatch):
    monkeypatch.setattr(
        tools.db,
        "fetch_breach_reasons",
        lambda ids: [{
            "id": ids[0],
            "breach_reason": "late",
            "client_name": "private",
            "submission_date": "2026-01-01",
            "region": "APAC",
            "days_late": 2,
            "status": "Breached",
        }],
    )

    result = tools.get_breach_reasons({"ids": [1]})

    assert result["rows"] == [{
        "id": 1,
        "breach_reason": "late",
        "submission_date": "2026-01-01",
        "region": "APAC",
        "days_late": 2,
        "status": "Breached",
    }]


def test_approval_endpoint_executes_stored_arguments_once(tmp_path, monkeypatch):
    database_path = tmp_path / "approval.db"
    monkeypatch.setattr(db, "DB_PATH", database_path)
    monkeypatch.setattr(auth, "API_TOKEN", "test-token")
    monkeypatch.setattr(tools, "__file__", str(tmp_path / "tools.py"))
    monkeypatch.setattr(
        tools.db,
        "fetch_submissions",
        lambda region, limit: [{
            "id": 1,
            "region": region,
            "days_late": 1,
            "status": "late",
        }],
    )

    pending = agent.dispatch_tool(
        "export_report",
        {"region": "APAC", "max_rows": 1},
        requester="local-dev-user",
    )
    approval_id = pending["approval"]["approval_id"]
    pending["approval"]["arguments"]["region"] = "EMEA"

    client = TestClient(api.app)
    response = client.post(
        f"/api/approvals/{approval_id}",
        headers={"Authorization": "Bearer test-token"},
        json={"decision": "approve"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "exported"
    assert (tmp_path / "output" / "apac_report.csv").exists()
    assert not (tmp_path / "output" / "emea_report.csv").exists()

    replay = client.post(
        f"/api/approvals/{approval_id}",
        headers={"Authorization": "Bearer test-token"},
        json={"decision": "approve"},
    )
    assert replay.status_code == 404

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT requester, tool, decision, created_at, decided_at, executed_at "
            "FROM approvals"
        ).fetchone()
    assert row[:3] == ("local-dev-user", "export_report", "approve")
    assert all(row[3:])


def test_declined_approval_writes_no_file(tmp_path, monkeypatch):
    database_path = tmp_path / "decline.db"
    monkeypatch.setattr(db, "DB_PATH", database_path)
    monkeypatch.setattr(auth, "API_TOKEN", "test-token")
    monkeypatch.setattr(tools, "__file__", str(tmp_path / "tools.py"))
    monkeypatch.setattr(
        tools.db,
        "fetch_submissions",
        lambda region, limit: [{
            "id": 1,
            "region": region,
            "days_late": 1,
            "status": "late",
        }],
    )

    pending = agent.dispatch_tool(
        "export_report",
        {"region": "APAC", "max_rows": 1},
        requester="local-dev-user",
    )
    approval_id = pending["approval"]["approval_id"]
    response = TestClient(api.app).post(
        f"/api/approvals/{approval_id}",
        headers={"Authorization": "Bearer test-token"},
        json={"decision": "decline"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert not (tmp_path / "output" / "apac_report.csv").exists()
