"""Run the golden cases with local data and deterministic replay fixtures."""

import argparse
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIRECTORY = PROJECT_ROOT / "evals"
BACKEND_DIRECTORY = PROJECT_ROOT / "backend"
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from evaluation import evaluate_case
from guardrails import check_input
from replay import run_offline_replay

CONFIG_PATH = EVALS_DIRECTORY / "config.yaml"
CASES_PATH = EVALS_DIRECTORY / "cases.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load the configured evaluation threshold and file names."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))

FIXTURES_DIRECTORY = Path(__file__).resolve().parent.parent / "evals" / "fixtures"


def load_fixture(filename: str) -> dict:
    path = FIXTURES_DIRECTORY / filename
    return json.loads(path.read_text(encoding="utf-8"))

def load_cases(path: Path = CASES_PATH) -> list[dict]:
    """Load the case list from YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["cases"]


def execute_case(case: dict) -> dict:
    """Run one case without a model provider or external retrieval."""
    fixture = load_fixture(f"{case['id']}.json")

    guardrail_result = check_input(case["question"])
    if not guardrail_result["allowed"]:
        result = {
            "status": "blocked",
            "message": guardrail_result["reason"],
            "trace": [],
        }
    else:
        result = run_offline_replay(case["question"], fixture)

    return evaluate_case(case, result)


def _failed_detail(evaluation: dict) -> str:
    failed = [
        check["message"]
        for check in evaluation.get("assertions", [])
        if not check["passed"]
    ]
    return failed[0] if failed else "ok"


def _config_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    project_path = PROJECT_ROOT / path
    return project_path if project_path.exists() else path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run deterministic fixtures without external providers.",
    )
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args([] if argv is None else argv)

    config_path = _config_path(args.config)
    config = load_config(config_path)
    cases_path = config_path.parent / config.get("cases_file", "cases.yaml")
    cases = load_cases(cases_path)
    evaluations = []

    for case in cases:
        try:
            evaluation = execute_case(case)
        except (AssertionError, KeyError, OSError, TypeError, ValueError) as error:
            evaluation = {
                "id": case["id"],
                "passed": False,
                "assertions": [{"passed": False, "message": str(error)}],
            }
        evaluations.append(evaluation)

    case_width = max(len("CASE"), *(len(case["id"]) for case in cases))
    print(f"{'CASE':<{case_width}}  {'PASS':<5} DETAIL")
    for evaluation in evaluations:
        state = "ok" if evaluation["passed"] else "fail"
        print(
            f"{evaluation['id']:<{case_width}}  "
            f"{state:<5} {_failed_detail(evaluation)}"
        )

    passed = sum(evaluation["passed"] for evaluation in evaluations)
    total = len(evaluations)
    pass_rate = passed / total if total else 0
    pass_floor = float(config["min_pass_rate"])
    print(f"pass rate {pass_rate:.0%} ({passed}/{total}), floor {pass_floor:.0%}")

    return 0 if pass_rate >= pass_floor else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
