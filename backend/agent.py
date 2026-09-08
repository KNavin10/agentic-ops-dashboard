import json
import os
import time

from app import ask_model
from approvals import ask_for_approval, build_approval_request
from tool_schemas import SENSITIVE
from tools import TOOL_REGISTRY

MAX_STEPS = int(os.getenv("MAX_AGENT_STEPS", "8"))
TOKEN_BUDGET = int(os.getenv("TOKEN_BUDGET", "8000"))


def run_agent(
    question: str,
    approve_sensitive: bool = False,
    model_fn=None,
    dispatch_fn=None,
) -> dict:
    messages = [
        {"role": "user", "content": question}
    ]

    trace = []
    input_tokens = 0
    output_tokens = 0

    def usage_fields() -> dict:
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens": input_tokens + output_tokens,
        }

    active_dispatch = dispatch_fn or dispatch_tool

    for step in range(MAX_STEPS):
        response = ask_model(messages, model_fn=model_fn)

        input_tokens += response["input_tokens"]
        output_tokens += response["output_tokens"]
        if input_tokens + output_tokens > TOKEN_BUDGET:
            return {
                "status": "budget_exceeded",
                "trace": trace,
                **usage_fields(),
            }

        if not response["tool_calls"]:
            return {
                "status": "ok",
                "answer": response["text"],
                "trace": trace,
                **usage_fields(),
            }
        
        for tool_call in response["tool_calls"]:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            started = time.perf_counter()
            result = active_dispatch(
                tool_name,
                arguments,
                approve_sensitive=approve_sensitive,
            )
            duration_ms = round((time.perf_counter() - started) * 1000)

            if isinstance(result, dict):
                if isinstance(result.get("rows"), list):
                    result_size = len(result["rows"])
                elif isinstance(result.get("matches"), list):
                    result_size = len(result["matches"])
                elif isinstance(result.get("result"), list):
                    result_size = len(result["result"])
                elif isinstance(result.get("rows_written"), int):
                    result_size = result["rows_written"]
                else:
                    result_size = 0
                status = result.get("status", "error" if result.get("error") else "ok")
            else:
                result_size = len(result) if isinstance(result, (list, str, tuple)) else 0
                status = "ok"

            trace.append({
                "step": step,
                "tool": tool_name,
                "duration_ms": duration_ms,
                "result_size": result_size,
                "status": status,
            })

            if result.get("status") == "awaiting_approval":
                return {**result, "trace": trace, **usage_fields()}

            messages.append({
                "role": "assistant",
                "content": response["text"],
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in response["tool_calls"]
                ],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })

    return {
        "status": "max_steps",
        "trace": trace,
        **usage_fields(),
    }

def dispatch_tool(
    tool_name: str,
    raw_arguments: dict,
    approve_sensitive: bool = False,
) -> dict:
    if tool_name not in TOOL_REGISTRY:
        return {
            "error": "unknown_tool",
            "tool": tool_name,
        }

    if tool_name in SENSITIVE and not approve_sensitive:
        return {
            "status": "awaiting_approval",
            "approval": build_approval_request(tool_name, raw_arguments),
        }

    handler = TOOL_REGISTRY[tool_name]
    approved_arguments = dict(raw_arguments)
    approved_arguments["_approved"] = True
    return handler(approved_arguments)


if __name__ == "__main__":
    question = "What is the filing deadline for lunar entities?"
    result = run_agent(question)

    if result.get("status") == "awaiting_approval":
        approval = result["approval"]
        if ask_for_approval(approval["tool"], approval["arguments"]):
            result = run_agent(question, approve_sensitive=True)
        else:
            result = {
                "status": "cancelled",
                "message": f'{approval["tool"]} cancelled by user.',
            }

    print(result)
