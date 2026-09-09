"""Small deterministic model responses for offline evaluation runs."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

FIXTURES_DIRECTORY = Path(__file__).resolve().parent.parent / "evals" / "fixtures"


def load_fixture(filename: str) -> dict:
    path = FIXTURES_DIRECTORY / filename
    return json.loads(path.read_text(encoding="utf-8"))


class ReplayModel:
    """Return scripted responses in the shape expected by ``ask_model``."""

    def __init__(self, fixture: dict):
        self.responses = fixture["responses"]
        self.position = 0

    def __call__(self, **_request):
        if self.position >= len(self.responses):
            raise AssertionError("Replay fixture has no more responses")

        scripted = self.responses[self.position]
        self.position += 1

        tool_calls = []
        for number, tool_call in enumerate(scripted.get("tool_calls", []), 1):
            tool_calls.append(
                SimpleNamespace(
                    id=f"replay-call-{self.position}-{number}",
                    function=SimpleNamespace(
                        name=tool_call["name"],
                        arguments=json.dumps(tool_call.get("arguments", {})),
                    ),
                )
            )

        message = SimpleNamespace(
            content=scripted.get("text", ""),
            tool_calls=tool_calls,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(
                prompt_tokens=scripted.get("input_tokens", 1),
                completion_tokens=scripted.get("output_tokens", 1),
            ),
        )


def replay_model(fixture: dict) -> ReplayModel:
    """Build a model callable for ``run_agent(..., model_fn=...)``."""
    return ReplayModel(fixture)


def offline_dispatch_tool(
    fixture: dict,
    tool_name: str,
    raw_arguments: dict,
) -> dict:
    """Stub only policy retrieval and keep the existing tools real."""
    if tool_name == "search_policies":
        try:
            result = fixture["tool_results"]["search_policies"]
        except KeyError as error:
            raise AssertionError(
                "Offline policy replay needs a search_policies fixture result"
            ) from error
        return deepcopy(result)

    from agent import dispatch_tool

    return dispatch_tool(tool_name, raw_arguments)


def run_offline_replay(
    question: str,
    fixture: dict,
) -> dict:
    """Run a fixture with real local tools and no external retrieval."""
    from agent import run_agent

    # Offline evaluation evidence is deliberately kept separate from the
    # public trace, which must never expose arguments or tool results.
    evaluation_trace = []

    def dispatch_with_evidence(tool_name, raw_arguments):
        result = offline_dispatch_tool(
            fixture,
            tool_name,
            raw_arguments,
        )
        evaluation_trace.append({
            "tool": tool_name,
            "args": deepcopy(raw_arguments),
            "result": deepcopy(result),
        })
        return result

    result = run_agent(
        question,
        model_fn=replay_model(fixture),
        dispatch_fn=dispatch_with_evidence,
    )
    result["_evaluation_trace"] = evaluation_trace
    return result
