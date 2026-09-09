import json
from pathlib import Path

import api
import db
import rag
import seed_database
import tools


def test_env_example_documents_deployment_configuration():
    env_lines = (
        Path(__file__).resolve().parents[1] / ".env.example"
    ).read_text(encoding="utf-8").splitlines()

    assert env_lines == [
        "GROQ_API_KEY=",
        "GROQ_MODEL=openai/gpt-oss-120b",
        "OLLAMA_HOST=http://ollama:11434",
        "OLLAMA_EMBEDDING_MODEL=qwen3-embedding",
        "API_TOKEN=",
        "ALLOWED_ORIGINS=http://localhost:4200",
        "APP_DATA_DIR=/app/storage",
        "DAILY_COST_CEILING_USD=1.00",
        "GROQ_INPUT_USD_PER_MILLION=0.15",
        "GROQ_OUTPUT_USD_PER_MILLION=0.60",
        "CACHE_TTL_SECONDS=3600",
        "MAX_AGENT_STEPS=8",
        "TOKEN_BUDGET=8000",
        "APP_VERSION=dev",
    ]


def test_allowed_origins_are_read_from_environment(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://dashboard.example, https://admin.example",
    )

    assert api.configured_allowed_origins() == [
        "https://dashboard.example",
        "https://admin.example",
    ]


def test_all_data_paths_use_the_configured_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    assert db.get_data_directory() == tmp_path
    assert rag.get_data_directory() == tmp_path
    assert seed_database.get_data_directory() == tmp_path
    assert tools.get_output_directory() == tmp_path / "output"


def test_export_and_email_outbox_use_the_configured_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        tools.db,
        "fetch_submissions",
        lambda region, limit: [
            {"id": 1, "region": region, "days_late": 2, "status": "late"}
        ],
    )

    export_result = tools.export_report({
        "region": "APAC",
        "max_rows": 1,
    }, approved=True)
    email_result = tools.email_summary({
        "recipient": "recipient@example.invalid",
        "subject": "Subject",
        "body": "Body",
    }, approved=True)

    assert Path(export_result["path"]) == tmp_path / "output" / "apac_report.csv"
    assert Path(email_result["path"]) == tmp_path / "outbox" / "email_summary.json"


def test_frontend_uses_same_origin_and_no_automatic_dev_token():
    root = Path(__file__).resolve().parents[2]
    service = (root / "frontend/src/app/agent-api.service.ts").read_text()
    interceptor = (root / "frontend/src/app/auth.interceptor.ts").read_text()
    proxy = json.loads((root / "frontend/proxy.conf.json").read_text())

    assert "http://localhost:8000" not in service
    assert "local-dev-token" not in service
    assert "local-dev-token" not in interceptor
    assert "fetch('/api/ask/stream'" in service
    assert proxy["/api"]["target"] == "http://localhost:8000"
