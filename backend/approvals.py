import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from tool_schemas import SENSITIVE


def _database_path():
    # Import lazily so tests and APP_DATA_DIR changes can use the active path.
    from db import DB_PATH

    return DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _arguments_json(arguments: dict) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"))


def _ensure_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            requester TEXT NOT NULL,
            tool TEXT NOT NULL,
            arguments_json TEXT NOT NULL,
            arguments_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            executed_at TEXT,
            decision TEXT CHECK (decision IN ('approve', 'decline'))
        )
        """
    )
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(approvals)")
    }
    if "executed_at" not in columns:
        connection.execute("ALTER TABLE approvals ADD COLUMN executed_at TEXT")


def create_approval(
    tool_name: str,
    arguments: dict,
    requester: str = "local-dev-user",
) -> dict:
    if tool_name not in SENSITIVE:
        raise ValueError("Only sensitive tools require approval")

    approval_id = str(uuid.uuid4())
    created_at = _now()
    encoded_arguments = _arguments_json(arguments)
    arguments_hash = hashlib.sha256(encoded_arguments.encode("utf-8")).hexdigest()
    with sqlite3.connect(_database_path()) as connection:
        _ensure_table(connection)
        connection.execute(
            """
            INSERT INTO approvals (
                approval_id, requester, tool, arguments_json, arguments_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                requester,
                tool_name,
                encoded_arguments,
                arguments_hash,
                created_at,
            ),
        )

    return {
        "approval_id": approval_id,
        "requester": requester,
        "tool": tool_name,
        "arguments": dict(arguments),
        "created_at": created_at,
    }


def get_approval(approval_id: str, requester: str | None = None) -> dict | None:
    with sqlite3.connect(_database_path()) as connection:
        _ensure_table(connection)
        row = connection.execute(
            """
            SELECT approval_id, requester, tool, arguments_json, arguments_hash,
                   created_at, decided_at, executed_at, decision
            FROM approvals
            WHERE approval_id = ?
              AND (? IS NULL OR requester = ?)
            """,
            (approval_id, requester, requester),
        ).fetchone()

    if row is None:
        return None
    return {
        "approval_id": row[0],
        "requester": row[1],
        "tool": row[2],
        "arguments": json.loads(row[3]),
        "arguments_hash": row[4],
        "created_at": row[5],
        "decided_at": row[6],
        "executed_at": row[7],
        "decision": row[8],
    }


def mark_executed(approval_id: str) -> None:
    with sqlite3.connect(_database_path()) as connection:
        _ensure_table(connection)
        connection.execute(
            "UPDATE approvals SET executed_at = ? WHERE approval_id = ?",
            (_now(), approval_id),
        )


def decide_approval(
    approval_id: str,
    decision: str,
    requester: str,
) -> dict | None:
    if decision not in {"approve", "decline"}:
        raise ValueError("decision must be approve or decline")

    decided_at = _now()
    with sqlite3.connect(_database_path()) as connection:
        _ensure_table(connection)
        cursor = connection.execute(
            """
            UPDATE approvals
            SET decision = ?, decided_at = ?
            WHERE approval_id = ? AND requester = ? AND decision IS NULL
            """,
            (decision, decided_at, approval_id, requester),
        )
        if cursor.rowcount != 1:
            return None

    return get_approval(approval_id, requester)


def ask_for_approval(tool_name: str, arguments: dict) -> bool:
    if tool_name not in SENSITIVE:
        return True

    print(f"\nApproval required for {tool_name}:")
    print(json.dumps(arguments, indent=2))
    answer = input("Run this tool? Type yes/no: ").strip().lower()
    return answer == "yes"
