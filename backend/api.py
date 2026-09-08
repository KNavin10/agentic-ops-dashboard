import json
import logging
import os
import sqlite3
import time
from copy import deepcopy

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import observability
import rag
from auth import LocalUser, get_current_user
from db import db
from models import AskRequest, AskResponse
from service import answer_question

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def configured_allowed_origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:4200,http://127.0.0.1:4200",
        ).split(",")
        if origin.strip()
    ]


ALLOWED_ORIGINS = configured_allowed_origins()
APP_VERSION = os.getenv("APP_VERSION", "dev")

app = FastAPI(title="Agentic Regulatory Ops Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": APP_VERSION}


def _check_sqlite() -> None:
    with sqlite3.connect(db.DB_PATH) as connection:
        connection.execute("SELECT 1")


def _check_chroma() -> None:
    rag.collection.count()


def _check_ollama() -> None:
    rag.ollama_client.list()


def _readiness_checks() -> dict[str, str]:
    checks = {}
    for name, check in (
        ("sqlite", _check_sqlite),
        ("chroma", _check_chroma),
        ("ollama", _check_ollama),
    ):
        try:
            check()
        except Exception:  # noqa: BLE001 - readiness must report dependency failures
            checks[name] = "error"
        else:
            checks[name] = "ok"
    return checks


@app.get("/ready")
def ready() -> JSONResponse:
    checks = _readiness_checks()
    ready_status = all(value == "ok" for value in checks.values())
    body = {
        "status": "ready" if ready_status else "not_ready",
        "checks": checks,
    }
    return JSONResponse(status_code=200 if ready_status else 503, content=body)


def _trace_tools(trace: list[dict]) -> list[str]:
    """Return only tool names from the already-safe trace."""
    return [
        step["tool"]
        for step in trace
        if isinstance(step, dict) and isinstance(step.get("tool"), str)
    ]


def _latency_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _derive_cited(response: AskResponse) -> bool:
    """Derive citation presence without persisting or logging answer text."""
    has_policy_evidence = any(
        isinstance(step, dict)
        and step.get("tool") == "search_policies"
        and step.get("status") == "ok"
        and (step.get("result_size") or 0) > 0
        for step in response.trace
    )
    answer = response.answer or ""
    return has_policy_evidence and "citation:" in answer.lower()


def _record_run(
    *,
    request_id: str,
    user: LocalUser,
    question_hash: str,
    question_length: int,
    response: AskResponse,
    latency_ms: int,
    cache_hit: bool,
    status_name: str | None = None,
    cited: bool = False,
) -> list[str]:
    tools = _trace_tools(response.trace)
    db.record_agent_run(
        request_id=request_id,
        user_id=user.user_id,
        question_hash=question_hash,
        question_length=question_length,
        status=status_name or response.status,
        steps=len(response.trace),
        tool_sequence=tools,
        input_tokens=response.input_tokens or 0,
        output_tokens=response.output_tokens or 0,
        cost_usd=response.cost_usd or 0.0,
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        cited=cited,
    )
    return tools


def _emit_agent_log(
    *,
    request_id: str,
    user: LocalUser,
    question_length: int,
    question_hash: str,
    response: AskResponse,
    tools: list[str],
    cache_hit: bool,
) -> None:
    logger.info(json.dumps({
        "event": "agent_request",
        "request_id": request_id,
        "user_id": user.user_id,
        "question_length": question_length,
        "question_hash": question_hash,
        "status": response.status,
        "steps": len(response.trace),
        "tools": tools,
        "input_tokens": response.input_tokens or 0,
        "output_tokens": response.output_tokens or 0,
        "cost_usd": response.cost_usd or 0.0,
        "latency_ms": response.latency_ms or 0,
        "cache_hit": cache_hit,
    }, separators=(",", ":")))


def _answer_with_observability(
    request: AskRequest,
    user: LocalUser,
) -> AskResponse:
    request_id = observability.generate_request_id()
    started = time.perf_counter()
    stripped_question = request.question.strip()
    question_hash = observability.hash_question(stripped_question)
    question_length = len(stripped_question)

    cached = observability.get_cached_response(
        user.user_id,
        question_hash,
        request.approve_sensitive,
    )
    if cached is not None:
        response_data = deepcopy(cached)
        response_data.update({
            "request_id": request_id,
            "input_tokens": 0,
            "output_tokens": 0,
            "tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": _latency_ms(started),
            "cached": True,
        })
        response = AskResponse.model_validate(response_data)
        tools = _record_run(
            request_id=request_id,
            user=user,
            question_hash=question_hash,
            question_length=question_length,
            response=response,
            latency_ms=response.latency_ms or 0,
            cache_hit=True,
            cited=_derive_cited(response),
        )
        _emit_agent_log(
            request_id=request_id,
            user=user,
            question_length=question_length,
            question_hash=question_hash,
            response=response,
            tools=tools,
            cache_hit=True,
        )
        return response

    previous_spend = db.get_today_spend()
    if previous_spend >= observability.DAILY_COST_CEILING_USD:
        response = AskResponse(
            status="rejected",
            request_id=request_id,
            input_tokens=0,
            output_tokens=0,
            tokens=0,
            cost_usd=0.0,
            latency_ms=_latency_ms(started),
            cached=False,
        )
        tools = _record_run(
            request_id=request_id,
            user=user,
            question_hash=question_hash,
            question_length=question_length,
            response=response,
            latency_ms=response.latency_ms or 0,
            cache_hit=False,
            status_name="rejected",
            cited=False,
        )
        _emit_agent_log(
            request_id=request_id,
            user=user,
            question_length=question_length,
            question_hash=question_hash,
            response=response,
            tools=tools,
            cache_hit=False,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily cost ceiling reached",
        )

    if request.approve_sensitive:
        result = answer_question(request.question, approve_sensitive=True)
    else:
        result = answer_question(request.question)

    response_data = dict(result)
    input_tokens = int(result.get("input_tokens", 0))
    output_tokens = int(result.get("output_tokens", 0))
    cost_usd = observability.calculate_cost(input_tokens, output_tokens)
    response_data.update({
        "request_id": request_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tokens": input_tokens + output_tokens,
        "cost_usd": cost_usd,
        "latency_ms": _latency_ms(started),
        "cached": False,
    })
    response = AskResponse.model_validate(response_data)
    tools = _record_run(
        request_id=request_id,
        user=user,
        question_hash=question_hash,
        question_length=question_length,
        response=response,
        latency_ms=response.latency_ms or 0,
        cache_hit=False,
        cited=_derive_cited(response) or bool(result.get("cited")),
    )

    _emit_agent_log(
        request_id=request_id,
        user=user,
        question_length=question_length,
        question_hash=question_hash,
        response=response,
        tools=tools,
        cache_hit=False,
    )

    observability.cache_response(
        user.user_id,
        question_hash,
        response.model_dump(),
        status=response.status,
        approve_sensitive=request.approve_sensitive,
        tool_sequence=tools,
    )

    spend_after = db.get_today_spend()
    warning_threshold = observability.DAILY_COST_CEILING_USD * 0.8
    if previous_spend < warning_threshold <= spend_after:
        logger.info(json.dumps({
            "event": "budget_warning",
            "spend_today_usd": spend_after,
            "daily_cost_ceiling_usd": observability.DAILY_COST_CEILING_USD,
        }, separators=(",", ":")))
    return response


@app.post("/api/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    user: LocalUser = Depends(get_current_user),  # noqa: B008
) -> AskResponse:
    return _answer_with_observability(request, user)


@app.get("/metrics")
def metrics(user: LocalUser = Depends(get_current_user)) -> dict:  # noqa: B008
    return db.get_today_metrics()


def stream_events(response: AskResponse):
    for trace_step in response.trace:
        tool = trace_step.get("tool")
        if not isinstance(tool, str):
            continue

        row_count = len(response.rows) if tool == "query_submissions" else 0
        yield {"type": "tool", "tool": tool, "row_count": row_count}

    if response.rows:
        yield {"type": "rows", "rows": response.rows}

    if response.answer:
        yield {"type": "text", "text": response.answer}

    if response.approval:
        yield {
            "type": "approval",
            "tool": response.approval["tool"],
            "arguments": response.approval["arguments"],
        }

    yield {"type": "done", "request_id": response.request_id}


@app.post("/api/ask/stream")
def ask_stream(
    request: AskRequest,
    user: LocalUser = Depends(get_current_user),  # noqa: B008
) -> StreamingResponse:
    response = _answer_with_observability(request, user)

    def body():
        for event in stream_events(response):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(body(), media_type="application/x-ndjson")


app.mount(
    "/",
    StaticFiles(directory="/app/frontend/dist/frontend/browser", html=True, check_dir=False),
    name="frontend",
)
