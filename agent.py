from tools import TOOL_REGISTRY
from app import ask_model
from approvals import ask_for_approval
import json

MAX_STEPS = 8
TOKEN_BUDGET = 8000


def run_agent(question: str) -> dict:
    messages = [
        {"role": "user", "content": question}
    ]

    trace = []
    spent_tokens = 0

    for step in range(MAX_STEPS):
        response = ask_model(messages)

        spent_tokens += response["input_tokens"]
        spent_tokens += response["output_tokens"]
        if spent_tokens> TOKEN_BUDGET:
            return {
                "status": "budget_exceeded",
                "trace": trace,
                "tokens": spent_tokens,
            }
        

        if not response["tool_calls"]:
            return {
                "status": "ok",
                "answer": response["text"],
                "trace": trace,
                "tokens": spent_tokens,
            }
        
        for tool_call in response["tool_calls"]:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            result = dispatch_tool(tool_name, arguments)

            trace.append({
                "step": step,
                "tool": tool_name,
                "args": arguments,
                "result": result,
            })

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
        "tokens": spent_tokens,
    }

def dispatch_tool(tool_name: str, raw_arguments: dict) -> dict:
    if tool_name not in TOOL_REGISTRY:
        return {
            "error": "unknown_tool",
            "tool": tool_name,
        }

    if not ask_for_approval(tool_name, raw_arguments):
        return {
            "status": "cancelled",
            "message": f"{tool_name} cancelled by user.",
        }

    handler = TOOL_REGISTRY[tool_name]
    approved_arguments = dict(raw_arguments)
    approved_arguments["_approved"] = True
    return handler(approved_arguments)


if __name__ == "__main__":
    result = run_agent("What is the filing deadline for lunar entities?"
    )
    print(result)
