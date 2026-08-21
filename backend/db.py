import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "operations.db"


class Database:
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
