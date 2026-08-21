# Setting up backend

1. Creating table with fields: `id`, `region`, `submission_date`, `days_late`, `status`, `breach_reason`, `client_name`, and `account_ref`.
2. Seeded 200 deterministic fake submission rows into the SQLite database.
3. Added the Pydantic validation model, SQLite query helper, and command-line runner.
4. Connected the `get_breach_reasons` tool and added a `main.py --record-id` test path.
5. Added multi-ID support with `get_breach_reasons({"ids": [1, 2, 3]})` and `main.py --record-ids 1 2 3`.
