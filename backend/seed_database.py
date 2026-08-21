"""Create the local SQLite database and seed it with deterministic fake data."""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE_PATH = ROOT / "data" / "operations.db"
SCHEMA_PATH = ROOT / "schema.sql"
ROW_COUNT = 200

REGIONS = ["APAC", "EMEA", "AMER"]
CLIENT_NAMES = [
    "Acme Logistics",
    "Blue River Foods",
    "Cedar Health Group",
    "Delta Manufacturing",
    "Evergreen Retail",
    "Frostline Energy",
    "Granite Financial",
    "Harbor Telecom",
    "Ivory Construction",
    "Juniper Travel",
]
BREACH_REASONS = [
    "Missing documentation",
    "Client response delay",
    "System outage",
    "Incorrect submission",
    "Capacity constraint",
]


def build_rows() -> list[tuple[str, str, int, str, str | None, str, str]]:
    """Return the same 200 fake rows on every run."""

    rng = random.Random(42)
    first_submission = date(2025, 1, 1)
    rows = []

    for row_number in range(1, ROW_COUNT + 1):
        days_late = rng.choices([0, 1, 2, 3, 5, 7, 10, 14, 21], weights=[30, 15, 12, 10, 8, 7, 6, 5, 2])[0]
        if days_late >= 10:
            status = "Breached"
        else:
            status = rng.choices(["Approved", "Under Review", "Rejected"], weights=[58, 30, 12])[0]

        breach_reason = rng.choice(BREACH_REASONS) if status == "Breached" else None
        submission_date = first_submission + timedelta(days=rng.randrange(200))
        client_name = rng.choice(CLIENT_NAMES)
        rows.append(
            (
                rng.choice(REGIONS),
                submission_date.isoformat(),
                days_late,
                status,
                breach_reason,
                client_name,
                f"ACC-{10000 + row_number}",
            )
        )

    return rows


def seed_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.execute("DELETE FROM submissions")
        connection.execute("DELETE FROM sqlite_sequence WHERE name = 'submissions'")
        connection.executemany(
            """
            INSERT INTO submissions (
                region,
                submission_date,
                days_late,
                status,
                breach_reason,
                client_name,
                account_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            build_rows(),
        )

        total_rows = connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        if total_rows != ROW_COUNT:
            raise RuntimeError(f"Expected {ROW_COUNT} rows, found {total_rows}")

    print(f"Seeded {ROW_COUNT} rows into {DATABASE_PATH}")


if __name__ == "__main__":
    seed_database()
