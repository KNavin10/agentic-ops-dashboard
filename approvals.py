import json

from tool_schemas import SENSITIVE


def ask_for_approval(tool_name: str, arguments: dict) -> bool:
    if tool_name not in SENSITIVE:
        return True

    print(f"\nApproval required for {tool_name}:")
    print(json.dumps(arguments, indent=2))
    answer = input("Run this tool? Type yes/no: ").strip().lower()
    return answer == "yes"
