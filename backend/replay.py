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
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )


def replay_model(fixture: dict) -> ReplayModel:
    """Build a model callable for ``run_agent(..., model_fn=...)``."""
    return ReplayModel(fixture)


def offline_dispatch_tool(
    fixture: dict,
    tool_name: str,
    raw_arguments: dict,
    approve_sensitive: bool = False,
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

    return dispatch_tool(
        tool_name,
        raw_arguments,
        approve_sensitive=approve_sensitive,
    )


def run_offline_replay(
    question: str,
    fixture: dict,
    approve_sensitive: bool = False,
) -> dict:
    """Run a fixture with real local tools and no external retrieval."""
    from agent import run_agent

    return run_agent(
        question,
        approve_sensitive=approve_sensitive,
        model_fn=replay_model(fixture),
        dispatch_fn=lambda tool_name, raw_arguments, approve_sensitive=False: (
            offline_dispatch_tool(
                fixture,
                tool_name,
                raw_arguments,
                approve_sensitive=approve_sensitive,
            )
        ),
    )
