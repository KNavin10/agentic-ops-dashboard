from models import QueryArgs, BreachReasonArgs, SearchPoliciesArgs
from db import db
from pathlib import Path
import csv
import json
from approvals import ask_for_approval
import rag


MAX_POLICY_DISTANCE = 1.0


def get_output_directory() -> Path:
    backend_directory = Path(__file__).resolve().parent
    local_output = backend_directory / "output"
    root_output = backend_directory.parent / "output"

    if root_output.exists() and not local_output.exists():
        return root_output

    return local_output

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


def export_report(raw: dict) -> dict:
    try:
        args = QueryArgs.model_validate(raw)
    except Exception:
        return {
            "error": "Invalid arguments",
            "allowed_regions": ["APAC", "EMEA", "AMER"],
        }

    rows = db.fetch_submissions(
        region=args.region,
        limit=args.max_rows,
    )

    if not rows:
        return {
            "status": "nothing_to_export",
            "message": f"No submissions found for {args.region}.",
        }

    if not raw.get("_approved") and not ask_for_approval("export_report", raw):
        return {
            "status": "cancelled",
            "message": "Export cancelled by user.",
        }

    output_path = get_output_directory() / f"{args.region.lower()}_report.csv"

    output_path.parent.mkdir(exist_ok=True)

    fields = ("id", "region", "days_late", "status")

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                field: row[field]
                for field in fields
            })

    return {
        "status": "exported",
        "path": str(output_path),
        "rows_written": len(rows),
    }


def email_summary(raw: dict) -> dict:
    recipient = raw.get("recipient")
    subject = raw.get("subject")
    body = raw.get("body")

    if not recipient or not subject or not body:
        return {
            "status": "missing_email_details",
            "message": "recipient, subject, and body are required.",
        }

    if not raw.get("_approved") and not ask_for_approval("email_summary", raw):
        return {
            "status": "cancelled",
            "message": "Email file was not written.",
        }

    outbox_path = Path(__file__).resolve().parent / "outbox" / "email_summary.json"

    outbox_path.parent.mkdir(exist_ok=True)

    with outbox_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "recipient": recipient,
                "subject": subject,
                "body": body,
            },
            file,
            indent=2,
        )

    return {
        "status": "email_queued",
        "path": str(outbox_path),
    }

def search_policies(raw: dict) -> dict:
    try:
        args = SearchPoliciesArgs.model_validate(raw)
    except Exception:
        return {
            "error": "Invalid arguments",
            "question": "Question is required",
            "k": "Maximum is 8"
        }

    result = rag.search_policy(question=args.question, k=args.k)
    ids = result.get("ids", [[]])

    if not ids or not ids[0]:
        return {
            "status": "no_results",
            "message": "INSUFFICIENT_DATA",
            "matches": [],
        }

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    matches = []

    for index, chunk_id in enumerate(ids[0]):
        if distances and distances[index] > MAX_POLICY_DISTANCE:
            continue

        metadata = metadatas[index]
        matches.append(
            {
                "text": documents[index],
                "source": metadata.get("source", ""),
                "chunk_id": metadata.get("chunk_id", chunk_id),
            }
        )

    if not matches:
        return {
            "status": "no_results",
            "message": "INSUFFICIENT_DATA",
            "matches": [],
        }

    return {
        "status": "ok",
        "matches": matches,
    }

TOOL_REGISTRY = {
    "query_submissions": query_submissions,
    "get_breach_reasons": get_breach_reasons,
    "aggregate_by_month": aggregate_by_month,
    "export_report": export_report,
    "email_summary": email_summary,
    "search_policies": search_policies,
}
