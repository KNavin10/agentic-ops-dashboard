import csv

import agent
import tools


def test_read_only_tool_executes_without_approval(monkeypatch):
    called = {}

    def read_only_handler(arguments):
        called.update(arguments)
        return {"status": "ok", "rows": []}

    monkeypatch.setitem(agent.TOOL_REGISTRY, "query_submissions", read_only_handler)

    result = agent.dispatch_tool(
        "query_submissions",
        {"region": "APAC", "max_rows": 1},
    )

    assert result == {"status": "ok", "rows": []}
    assert called["region"] == "APAC"


def test_sensitive_tool_returns_awaiting_approval():
    result = agent.dispatch_tool(
        "export_report",
        {"region": "APAC", "max_rows": 1},
    )

    assert result["status"] == "awaiting_approval"
    assert result["approval"]["tool"] == "export_report"


def test_declined_approval_writes_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "__file__", str(tmp_path / "tools.py"))
    monkeypatch.setattr(
        tools.db,
        "fetch_submissions",
        lambda region, limit: [
            {"id": 1, "region": region, "days_late": 2, "status": "late"}
        ],
    )
    monkeypatch.setattr(tools, "ask_for_approval", lambda tool, arguments: False)

    result = tools.export_report({"region": "APAC", "max_rows": 1})

    assert result["status"] == "cancelled"
    assert not (tmp_path / "output" / "apac_report.csv").exists()


def test_approved_export_writes_expected_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "__file__", str(tmp_path / "tools.py"))
    monkeypatch.setattr(
        tools.db,
        "fetch_submissions",
        lambda region, limit: [
            {"id": 1, "region": region, "days_late": 2, "status": "late"},
            {"id": 2, "region": region, "days_late": 0, "status": "on_time"},
        ],
    )

    result = tools.export_report({
        "region": "APAC",
        "max_rows": 2,
    }, approved=True)

    output_path = tmp_path / "output" / "apac_report.csv"
    assert result["status"] == "exported"
    assert result["rows_written"] == 2
    with output_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert rows == [
        {"id": "1", "region": "APAC", "days_late": "2", "status": "late"},
        {"id": "2", "region": "APAC", "days_late": "0", "status": "on_time"},
    ]


def test_unknown_tool_returns_safe_error():
    result = agent.dispatch_tool("not_a_real_tool", {})

    assert result == {"error": "unknown_tool", "tool": "not_a_real_tool"}
