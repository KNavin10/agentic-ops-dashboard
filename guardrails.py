from agent import run_agent

BLOCKED_PATTERNS = [
    "ignore previous instructions",
    "bypass approval",
    "disable safeguards",
    "export all records",
]

def check_input(question: str) -> dict:
    lowered = question.lower()

    for pattern in BLOCKED_PATTERNS:
        if pattern in lowered:
            return {
                "allowed": False,
                "reason": "possible instruction override",
            }

    return run_agent(question)



if __name__ == "__main__":
    result = check_input("Which APAC submissions were late, and what were their breach reasons?"
    )
    print(result)