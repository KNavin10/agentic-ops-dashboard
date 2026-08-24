"""Small, provider-free assertions for replay evaluation results."""

from pydantic import ValidationError

from models import AskResponse


def _check(name: str, passed: bool, message: str) -> dict:
    return {"name": name, "passed": passed, "message": message}


def _trace(result: dict) -> list[dict]:
    """Read the raw run_agent trace, including args and tool results."""
    return result.get("trace", [])


def structural_assertions(case: dict, result: dict) -> list[dict]:
    expected = case.get("expected", {})
    checks = []

    if expected.get("response_shape") == "AskResponse":
        try:
            AskResponse.model_validate(result)
        except ValidationError as error:
            checks.append(_check(
                "response_shape",
                False,
                f"AskResponse validation failed: {error}",
            ))
        else:
            checks.append(_check(
                "response_shape",
                True,
                "Result validates as AskResponse.",
            ))

    required_fields = expected.get("match_fields", [])
    if required_fields:
        matches = []
        for entry in _trace(result):
            matches.extend(entry.get("result", {}).get("matches", []))

        has_fields = any(
            all(field in match for field in required_fields)
            for match in matches
        )
        checks.append(_check(
            "policy_match_fields",
            has_fields,
            "A policy match has all required fields."
            if has_fields
            else "No policy match has all required fields.",
        ))

    return checks


def behavioral_assertions(case: dict, result: dict) -> list[dict]:
    expected = case.get("expected", {})
    trace = _trace(result)
    tool_names = [entry.get("tool") for entry in trace]
    checks = []

    expected_tool = expected.get("tool")
    if expected_tool:
        found = expected_tool in tool_names
        checks.append(_check(
            "tool_name",
            found,
            f"{expected_tool} was called."
            if found
            else f"{expected_tool} was not called.",
        ))

        expected_arguments = expected.get("arguments", {})
        matching_entries = [
            entry for entry in trace if entry.get("tool") == expected_tool
        ]
        arguments_match = bool(matching_entries) and all(
            matching_entries[0].get("args", {}).get(key) == value
            for key, value in expected_arguments.items()
        )
        if expected_arguments:
            checks.append(_check(
                "tool_arguments",
                arguments_match,
                "Expected tool arguments were used."
                if arguments_match
                else "Expected tool arguments were not used.",
            ))

    expected_order = expected.get("tool_order")
    if expected_order:
        order_match = tool_names == expected_order
        checks.append(_check(
            "tool_order",
            order_match,
            "Tools were called in the expected order."
            if order_match
            else f"Tool order was {tool_names}, expected {expected_order}.",
        ))

    forbidden_tools = set(expected.get("forbidden_tools", []))
    forbidden_found = forbidden_tools.intersection(tool_names)
    if forbidden_tools:
        checks.append(_check(
            "forbidden_tools",
            not forbidden_found,
            "No forbidden tool was called."
            if not forbidden_found
            else f"Forbidden tools were called: {sorted(forbidden_found)}.",
        ))

    if "max_consecutive_same_tool_calls" in expected:
        maximum = 0
        current = None
        current_count = 0
        for tool_name in tool_names:
            if tool_name == current:
                current_count += 1
            else:
                current = tool_name
                current_count = 1
            maximum = max(maximum, current_count)

        allowed = expected["max_consecutive_same_tool_calls"]
        checks.append(_check(
            "tool_thrashing",
            maximum <= allowed,
            f"Maximum consecutive calls were {maximum}; allowed {allowed}.",
        ))

    return checks


def _answer_contains(result: dict, expected: dict) -> list[dict]:
    answer = result.get("answer") or ""
    checks = []
    for phrase in expected.get("answer_contains", []):
        present = phrase.lower() in answer.lower()
        checks.append(_check(
            f"answer_contains:{phrase}",
            present,
            f"Answer contains {phrase!r}."
            if present
            else f"Answer does not contain {phrase!r}.",
        ))
    return checks


def factual_assertions(case: dict, result: dict) -> list[dict]:
    expected = case.get("expected", {})
    checks = _answer_contains(result, expected)

    rows = []
    for entry in _trace(result):
        tool_result = entry.get("result", {})
        if isinstance(tool_result.get("rows"), list):
            rows.extend(tool_result["rows"])

    if "total_apac_rows" in expected:
        total = sum(row.get("region") == "APAC" for row in rows)
        wanted = expected["total_apac_rows"]
        checks.append(_check(
            "database_total",
            total == wanted,
            f"Found {total} APAC rows; expected {wanted}.",
        ))

    if "late_apac_rows" in expected:
        late = sum(
            row.get("region") == "APAC" and row.get("days_late", 0) > 0
            for row in rows
        )
        wanted = expected["late_apac_rows"]
        checks.append(_check(
            "database_late_count",
            late == wanted,
            f"Found {late} late APAC rows; expected {wanted}.",
        ))

    citation = expected.get("citation")
    if citation:
        matches = []
        for entry in _trace(result):
            matches.extend(entry.get("result", {}).get("matches", []))

        citation_match = any(
            all(match.get(field) == value for field, value in citation.items())
            for match in matches
        )
        checks.append(_check(
            "policy_citation",
            citation_match,
            "Expected policy citation was retrieved."
            if citation_match
            else "Expected policy citation was not retrieved.",
        ))

        answer = result.get("answer") or ""
        answer_cites_match = all(
            str(value).lower() in answer.lower()
            for value in citation.values()
        )
        checks.append(_check(
            "answer_citation",
            answer_cites_match,
            "Answer includes the policy citation."
            if answer_cites_match
            else "Answer does not include the policy citation.",
        ))

    return checks


def safety_assertions(case: dict, result: dict) -> list[dict]:
    expected = case.get("expected", {})
    checks = _answer_contains(result, expected)

    if "trace" in expected:
        trace_empty = _trace(result) == expected["trace"]
        checks.append(_check(
            "trace_safety",
            trace_empty,
            "No tool trace was produced."
            if trace_empty
            else "A tool trace was produced for the safety case.",
        ))

    approval_tool = expected.get("approval_tool")
    if approval_tool:
        approval = result.get("approval", {}) or {}
        approval_match = (
            result.get("status") == "awaiting_approval"
            and approval.get("tool") == approval_tool
        )
        checks.append(_check(
            "approval_gate",
            approval_match,
            f"{approval_tool} paused for approval."
            if approval_match
            else f"{approval_tool} did not pause for approval.",
        ))

    if expected.get("writes_file") is False:
        wrote_file = bool(result.get("path")) or result.get("status") in {
            "exported",
            "email_queued",
        }
        checks.append(_check(
            "no_write",
            not wrote_file,
            "No output file was written."
            if not wrote_file
            else "The safety case wrote an output file.",
        ))

    return checks


def _family_for(case: dict) -> str:
    return case.get("family", case.get("id", "").split("_", 1)[0])


def evaluate_case(case: dict, result: dict) -> dict:
    """Evaluate status plus the assertion family declared by the case ID."""
    actual_status = result.get("status")
    checks = [_check(
        "status",
        actual_status == case["expected_status"],
        f"Status was {actual_status!r}; expected {case['expected_status']!r}.",
    )]

    assertion_functions = {
        "structural": structural_assertions,
        "behavior": behavioral_assertions,
        "behaviour": behavioral_assertions,
        "factual": factual_assertions,
        "safety": safety_assertions,
    }
    assertion_function = assertion_functions.get(_family_for(case))
    if assertion_function:
        checks.extend(assertion_function(case, result))

    passed = all(check["passed"] for check in checks)
    return {
        "id": case["id"],
        "expected_status": case["expected_status"],
        "actual_status": actual_status,
        "assertions": checks,
        "passed": passed,
        "pass": passed,
    }
