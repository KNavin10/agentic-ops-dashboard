from models import QueryArgs, BreachReasonArgs
from db import db


def query_submissions(raw: dict) -> dict:
    try:
        args = QueryArgs.model_validate(raw)
    except Exception:
        return {
            "error": "Invalid arguments",
            "allowed_regions": ["APAC", "EMEA", "AMER"],
            "max_rows_limit": 200,
        }

    rows = db.fetch_submissions(
        region=args.region,
        limit=args.max_rows + 1,
    )

    truncated = len(rows) > args.max_rows
    rows = rows[:args.max_rows]
    safe_fields = ("id", "region", "days_late", "status")

    return {
        "rows": [
            {key: row[key] for key in safe_fields}
            for row in rows
        ],
        "truncated": truncated,
    }

def get_breach_reasons(raw: dict) -> dict:
    try:
        args = BreachReasonArgs.model_validate(raw)
    except Exception:
        return {
            "error": "Invalid arguments",
            "id": "provide an id"
        }
    
    rows = db.fetch_breach_reasons(ids=args.ids)
    safe_fields = (
        "id",
        "breach_reason",
        "client_name",
        "submission_date",
        "region",
        "days_late",
        "status",
    )

    return {
        "rows": [
            {key: row[key] for key in safe_fields}
            for row in rows
        ],
        "truncated": False,
    }

def aggregate_by_month(raw: dict) -> dict:
    try:
        args = QueryArgs.model_validate(raw)
    except Exception:
       return {
            "error": "Invalid arguments",
            "allowed_regions": ["APAC", "EMEA", "AMER"],
            "max_rows_limit": 200,
        }

    
    row = db.fetch_aggregate( 
        region=args.region
    )

    return {
        "result": row
    }
TOOL_REGISTRY = {
    "query_submissions": query_submissions,
    "get_breach_reasons": get_breach_reasons,
    "aggregate_by_month": aggregate_by_month,
}
