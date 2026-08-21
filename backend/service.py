from agent import run_agent
from guardrails import check_input


def extract_chart_data(trace: list[dict]) -> list[dict]:
    for entry in trace:
        if entry.get("tool") != "aggregate_by_month":
            continue

        result = entry.get("result", {})
        return result.get("result", [])

    return []


def sanitize_trace(trace: list[dict]) -> list[dict]:
    safe_trace = []

    for entry in trace:
        result = entry.get("result", {})
        status = "ok"

        if isinstance(result, dict):
            status = result.get("status", "error" if result.get("error") else "ok")

        safe_trace.append({
            "step": entry.get("step"),
            "tool": entry.get("tool"),
            "status": status,
        })

    return safe_trace


def extract_rows(trace: list[dict]) -> list[dict]:
    for entry in trace:
        result = entry.get("result", {})
        if isinstance(result, dict) and isinstance(result.get("rows"), list):
            return result["rows"]

    return []


def to_api_response(result: dict) -> dict:
    response = {
        "status": result.get("status", "error"),
        "chart_data": extract_chart_data(result.get("trace", [])),
        "rows": extract_rows(result.get("trace", [])),
        "trace": sanitize_trace(result.get("trace", [])),
    }

    for field in ("answer", "message", "tokens"):
        if field in result:
            response[field] = result[field]

    if "approval" in result:
        approval = result["approval"]
        response["approval"] = {
            "tool": approval.get("tool"),
            "arguments": approval.get("arguments", {}),
        }

    return response


def answer_question(
    question: str,
    model_fn=None,
    approve_sensitive: bool = False,
) -> dict:
    guardrail_result = check_input(question)

    if not guardrail_result["allowed"]:
        return to_api_response({
            "status": "blocked",
            "message": guardrail_result["reason"],
        })

    return to_api_response(
        run_agent(
            question,
            approve_sensitive=approve_sensitive,
            model_fn=model_fn,
        )
    )
