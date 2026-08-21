from tools import TOOL_REGISTRY
from app import ask_model
from approvals import ask_for_approval, build_approval_request
from tool_schemas import SENSITIVE
import json

MAX_STEPS = 8
TOKEN_BUDGET = 8000


def run_agent(
    question: str,
    approve_sensitive: bool = False,
    model_fn=None,
) -> dict:
    messages = [
        {"role": "user", "content": question}
    ]

    trace = []
    spent_tokens = 0

    for step in range(MAX_STEPS):
        response = ask_model(messages, model_fn=model_fn)

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

            result = dispatch_tool(
                tool_name,
                arguments,
                approve_sensitive=approve_sensitive,
            )

            trace.append({
                "step": step,
                "tool": tool_name,
                "args": arguments,
                "result": result,
            })

            if result.get("status") == "awaiting_approval":
                return result

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
