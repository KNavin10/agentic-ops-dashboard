import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def get_data_directory() -> Path:
    return Path(os.getenv("APP_DATA_DIR") or DEFAULT_DATA_DIR)


DATA_DIR = get_data_directory()
DB_PATH = DATA_DIR / "operations.db"


class Database:
    def record_agent_run(
        self,
        *,
        request_id: str,
        question_hash: str,
        question_length: int,
        status: str,
        steps: int,
        tool_sequence: list[str] | tuple[str, ...] | str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        cache_hit: bool = False,
        cited: bool = False,
        created_at: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Store the small, non-sensitive summary of one agent run."""
        if isinstance(tool_sequence, str):
            try:
                parsed_tools = json.loads(tool_sequence)
            except json.JSONDecodeError:
                parsed_tools = [tool_sequence]
        else:
            parsed_tools = list(tool_sequence)
        # Keep this column as a JSON list of names, never tool-call objects.
        tool_names = [
            item.get("name", "") if isinstance(item, dict) else str(item)
            for item in parsed_tools
        ]
        tool_sequence = json.dumps(tool_names)
        created_at = created_at or datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(DB_PATH) as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    request_id, created_at, user_id, question_hash,
                    question_length, status, steps, tool_sequence,
                    input_tokens, output_tokens, cost_usd, latency_ms,
                    cache_hit, cited
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    created_at,
                    user_id,
                    question_hash,
                    question_length,
                    status,
                    steps,
                    tool_sequence,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    latency_ms,
                    int(cache_hit),
                    int(cited),
                ),
            )

    def get_today_spend(self) -> float:
        with sqlite3.connect(DB_PATH) as connection:
            spend = connection.execute(
                """
                SELECT COALESCE(SUM(cost_usd), 0.0)
                FROM agent_runs
                WHERE date(created_at, 'localtime') = date('now', 'localtime')
                """
            ).fetchone()[0]
        return float(spend)

    def get_today_metrics(self) -> dict:
        with sqlite3.connect(DB_PATH) as connection:
            rows = connection.execute(
                """
                SELECT status, steps, latency_ms, input_tokens, output_tokens,
                       cost_usd, cache_hit
                FROM agent_runs
                WHERE date(created_at, 'localtime') = date('now', 'localtime')
                """
            ).fetchall()

        runs_today = len(rows)
        success_count = sum(row[0] in {"ok", "success"} for row in rows)
        error_count = sum(row[0] in {"error", "rejected"} for row in rows)
        latencies = sorted(row[2] for row in rows)
        p95_latency = 0
        if latencies:
            p95_latency = int(latencies[math.ceil(len(latencies) * 0.95) - 1])

        return {
            "runs_today": runs_today,
            "success_rate": success_count * 100.0 / runs_today if runs_today else 0.0,
            "error_rate": error_count * 100.0 / runs_today if runs_today else 0.0,
            "average_steps": sum(row[1] for row in rows) / runs_today if runs_today else 0.0,
            "p95_latency_ms": p95_latency,
            "tokens_today": sum(row[3] + row[4] for row in rows),
            "spend_today_usd": self.get_today_spend(),
            "cache_hit_rate": sum(row[6] for row in rows) * 100.0 / runs_today if runs_today else 0.0,
        }

    def fetch_submissions(self, *, region: str, limit: int) -> list[dict]:
        with sqlite3.connect(DB_PATH) as connection:
            connection.row_factory = sqlite3.Row

            rows = connection.execute(
                """
                SELECT *
                FROM submissions
                WHERE region = ?
                ORDER BY submission_date DESC
                LIMIT ?
                """,
                (region, limit),
            ).fetchall()

        return [dict(row) for row in rows]
    
    def fetch_breach_reasons(self, *, ids: list[int]) -> list[dict]:
        if not ids:
            return []

        placeholders = ", ".join("?" for _ in ids)
        with sqlite3.connect(DB_PATH) as connection:
            connection.row_factory = sqlite3.Row

            #Print query
            connection.set_trace_callback(
                lambda statement: print(f"[DB] executed: {statement}")
            )
            query = f"""
                SELECT *
                FROM submissions
                WHERE id IN ({placeholders})
                ORDER BY id
                """

            rows = connection.execute(
                query,
                tuple(ids),
            ).fetchall()
        return [dict(row) for row in rows]
    

    def fetch_aggregate(self, *, region:str):
        with sqlite3.connect(DB_PATH) as connection:
            connection.row_factory = sqlite3.Row

            rows = connection.execute(
                """
                SELECT
                strftime('%Y-%m', submission_date) AS month,
                COUNT(*) AS total_submissions,
                SUM(CASE WHEN days_late > 0 THEN 1 ELSE 0 END) AS late_submissions,
                AVG(CASE WHEN days_late > 0 THEN days_late ELSE NULL END)
                    AS average_days_late
                FROM submissions
                WHERE region = ?
                GROUP BY month
                ORDER BY month
                """,
                (region,),
            ).fetchall()

        return [dict(row) for row in rows]

db = Database()
