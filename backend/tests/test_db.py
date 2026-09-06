import json
import sqlite3
from datetime import datetime, timezone

import db


def make_database(tmp_path, monkeypatch):
    database_path = tmp_path / "operations.db"
    monkeypatch.setattr(db, "DB_PATH", database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            (db.Path(__file__).resolve().parents[1] / "schema.sql").read_text()
        )
    return db.Database()


def test_record_agent_run_and_today_metrics(tmp_path, monkeypatch):
    database = make_database(tmp_path, monkeypatch)
    database.record_agent_run(
        request_id="request-1",
        user_id="user-1",
        question_hash="hash-1",
        question_length=12,
        status="success",
        steps=2,
        tool_sequence=["query_submissions"],
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.25,
        latency_ms=100,
        cache_hit=True,
        cited=True,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    assert database.get_today_spend() == 0.25
    assert database.get_today_metrics() == {
        "runs_today": 1,
        "success_rate": 100.0,
        "error_rate": 0.0,
        "average_steps": 2.0,
        "p95_latency_ms": 100,
        "tokens_today": 15,
        "spend_today_usd": 0.25,
        "cache_hit_rate": 100.0,
    }

    with sqlite3.connect(db.DB_PATH) as connection:
        row = connection.execute(
            "SELECT tool_sequence FROM agent_runs WHERE request_id = 'request-1'"
        ).fetchone()
    assert json.loads(row[0]) == ["query_submissions"]


def test_today_metrics_has_requested_empty_shape(tmp_path, monkeypatch):
    database = make_database(tmp_path, monkeypatch)

    assert database.get_today_metrics() == {
        "runs_today": 0,
        "success_rate": 0.0,
        "error_rate": 0.0,
        "average_steps": 0.0,
        "p95_latency_ms": 0,
        "tokens_today": 0,
        "spend_today_usd": 0.0,
        "cache_hit_rate": 0.0,
    }


def test_today_metrics_counts_ok_as_success_and_rejected_as_error(tmp_path, monkeypatch):
    database = make_database(tmp_path, monkeypatch)
    for request_id, status in (("ok-run", "ok"), ("rejected-run", "rejected")):
        database.record_agent_run(
            request_id=request_id,
            user_id="user-1",
            question_hash=request_id,
            question_length=4,
            status=status,
            steps=0,
            tool_sequence=[],
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=1,
        )

    metrics = database.get_today_metrics()
    assert metrics["success_rate"] == 50.0
    assert metrics["error_rate"] == 50.0


def test_agent_runs_schema_has_only_usage_columns_and_created_index(tmp_path, monkeypatch):
    make_database(tmp_path, monkeypatch)
    with sqlite3.connect(db.DB_PATH) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(agent_runs)")]
        indexes = [row[1] for row in connection.execute("PRAGMA index_list(agent_runs)")]

    assert columns == [
        "request_id",
        "created_at",
        "user_id",
        "question_hash",
        "question_length",
        "status",
        "steps",
        "tool_sequence",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "latency_ms",
        "cache_hit",
        "cited",
    ]
    assert "idx_agent_runs_created_at" in indexes
