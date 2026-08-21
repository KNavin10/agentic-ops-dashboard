import json
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from auth import LocalUser, get_current_user
from models import AskRequest, AskResponse
from service import answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Regulatory Ops Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    user: LocalUser = Depends(get_current_user),  # noqa: B008
) -> AskResponse:
    if request.approve_sensitive:
        result = answer_question(
            request.question,
            approve_sensitive=True,
        )
    else:
        result = answer_question(request.question)
    response = AskResponse.model_validate(result)

    logger.info(
        "ask user_id=%s status=%s tokens=%s",
        user.user_id,
        response.status,
        response.tokens,
    )

    return response


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

    yield {"type": "done"}


@app.post("/api/ask/stream")
def ask_stream(
    request: AskRequest,
    user: LocalUser = Depends(get_current_user),  # noqa: B008
) -> StreamingResponse:
    result = answer_question(
        request.question,
        approve_sensitive=request.approve_sensitive,
    )
    response = AskResponse.model_validate(result)

    logger.info(
        "ask_stream user_id=%s status=%s tokens=%s",
        user.user_id,
        response.status,
        response.tokens,
    )

    def body():
        for event in stream_events(response):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(body(), media_type="application/x-ndjson")
