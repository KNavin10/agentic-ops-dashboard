# Agentic Regulatory Ops Dashboard

[![CI](https://github.com/KNavin10/agentic-ops-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/KNavin10/agentic-ops-dashboard/actions/workflows/ci.yml)

This beginner-friendly project is a working Angular + FastAPI dashboard for
asking questions about fake regulatory submission data and local policy
documents. It is based on the 14-day agentic AI study guide.

The backend uses small validated tools, SQLite, Groq tool calling, and local
Ollama/ChromaDB policy retrieval. The frontend displays the answer, returned
rows, a simple chart, agent steps, and approval requests.

## What is implemented

| Study-guide area | Current implementation |
| --- | --- |
| Day 3: tool calling | Six function tools with JSON schemas, Pydantic argument models, SQLite queries, result shaping, and a tool registry. |
| Day 4: agent loop | A bounded loop with `MAX_STEPS = 8`, a token budget, an in-memory trace, and a simple prompt-injection guardrail. |
| Day 4: human approval | `export_report` and `email_summary` are sensitive tools and require approval before writing local files. |
| Day 5: RAG | Markdown policy chunking, Ollama embeddings, persistent ChromaDB storage, source/chunk metadata, a distance cutoff, and `INSUFFICIENT_DATA`. |
| Day 6: MCP | A local stdio MCP server exposing the read-only `query_submissions` and `search_policies` tools. |
| Day 7: dashboard | Angular 22 frontend, FastAPI endpoints, bearer-token authentication, normal and NDJSON request paths, approval UI, trace display, and a returned-rows chart. |
| CI | GitHub Actions runs Ruff, Pytest, and the Angular production build. |

The data is deliberately fake and deterministic. `backend/seed_database.py`
creates 200 submission rows across APAC, EMEA, and AMER.

## Architecture

```text
Browser
  -> Angular 22 question screen
  -> AgentApiService
     -> POST /api/ask or POST /api/ask/stream
        -> FastAPI authentication (Bearer token)
        -> service.py
           -> input guardrail
           -> agent.py bounded model/tool loop
              -> Groq model with tool schemas
              -> tools.py registry
                 -> SQLite submission data
                 -> ChromaDB + Ollama policy retrieval
        -> sanitized response: answer, rows, chart data, trace, approval
  -> Angular answer, chart, steps, and approval dialog
```

The MCP path reuses the read-only tool functions directly:

```text
Codex / another MCP client
  -> mcp_server.py over local stdio
  -> query_submissions or search_policies
  -> SQLite or policy RAG
```

## Tools

The model-facing registry in `backend/tool_schemas.py` contains:

- `query_submissions(region, max_rows)` - read submission rows for APAC, EMEA,
  or AMER, with a maximum of 200 rows.
- `get_breach_reasons(ids)` - read breach details for one or more submission IDs.
- `aggregate_by_month(region)` - return monthly submission and lateness
  aggregates.
- `export_report(region)` - write a local CSV file after approval.
- `email_summary(recipient, subject, body)` - write a local JSON outbox file
  after approval; it does not send email.
- `search_policies(question, k)` - retrieve policy passages with source and
  chunk IDs.

The MCP server exposes only `query_submissions` and `search_policies`.

## Safety boundaries demonstrated

- Region values and tool arguments are validated with Pydantic.
- Query row counts are capped at 200.
- SQL uses parameters instead of model-generated SQL.
- Submission results return only safe display fields.
- Export and email actions are separated from read-only tools and require
  approval.
- The agent stops after eight steps or when its token budget is exceeded.
- A small input guardrail blocks several obvious instruction-override phrases.
- The MCP server does not expose raw SQL, shell access, arbitrary files, or
  write tools.

This is an educational implementation, not a production-grade security
review.

## Setup

Use Python 3.12 and Node.js 22. From PowerShell at the repository root:

```powershell
cd D:\agentic-ops-dashboard
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
cd .\frontend
npm ci
```

Create `backend/.env` with the provider settings used by the application:

```env
GROQ_API_KEY=your_groq_key
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=qwen3-embedding
```

The Groq key is used for the agent model. Ollama and the configured embedding
model are needed for policy retrieval.

## Prepare the local data

From `D:\agentic-ops-dashboard\backend`, recreate the deterministic database:

```powershell
..\.venv\Scripts\python.exe .\seed_database.py
```

The seed script clears the existing `submissions` table before inserting 200
fake rows.

Start Ollama and make `OLLAMA_EMBEDDING_MODEL` available, then build the local
ChromaDB collection:

```powershell
..\.venv\Scripts\python.exe .\ingest_policies.py
```

The policy index is stored in `backend/vectorstore/` and uses the
`reg_policies` collection. Chunks preserve Markdown headings and store
`source`, `chunk_id`, `section`, and an estimated token count.

## Start the application

Start the FastAPI backend in one PowerShell window:

```powershell
cd D:\agentic-ops-dashboard\backend
..\.venv\Scripts\python.exe -m uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Start the Angular frontend in a second PowerShell window:

```powershell
cd D:\agentic-ops-dashboard\frontend
npm start
```

Open <http://localhost:4200/>. The frontend calls FastAPI at
`http://localhost:8000`, and FastAPI allows the local Angular origins on port
4200.

## Authentication example

This learning app uses the fixed local development token
`local-dev-token`. The Angular interceptor adds it automatically. To call the
normal API directly from PowerShell:

```powershell
$headers = @{ Authorization = 'Bearer local-dev-token' }
$body = @{ question = 'Show three late APAC submissions.'; approve_sensitive = $false } | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/ask `
  -Headers $headers `
  -ContentType 'application/json' `
  -Body $body
```

Requests without this header receive HTTP 401. This token is for local
learning only; it is not real user authentication.

## Approval behavior

Read-only tools run normally. `export_report` and `email_summary` pause with
`status: "awaiting_approval"` and return the tool name and arguments in the
`approval` field before writing anything.

In the Angular UI:

1. The approval dialog shows the requested tool and arguments.
2. Decline clears the request and sends no write request.
3. Approve and resubmit sends the question again with
   `approve_sensitive: true`.

An approved export writes a CSV under `output/`. An approved email summary
writes `backend/outbox/email_summary.json`; no email is sent. When running
`backend/agent.py` directly, approval is requested in the terminal with a
`yes` or `no` answer.

## Trace and streaming behavior

The internal agent trace records each tool step, including its arguments and
result, in memory. Before the result is returned by FastAPI, `service.py`
sanitizes the trace to only `step`, `tool`, and `status`. The Angular UI shows
these safe summaries and separately displays returned rows and chart data.

`POST /api/ask/stream` returns newline-delimited JSON (NDJSON) events such as:

```json
{"type":"tool","tool":"query_submissions","row_count":3}
{"type":"rows","rows":[]}
{"type":"text","text":"..."}
{"type":"approval","tool":"export_report","arguments":{}}
{"type":"done"}
```

Angular uses `fetch()` and a readable response stream for this endpoint. Do not
use browser `EventSource`, because it sends a GET request. The current backend
computes the complete answer first and then emits the NDJSON events; it is a
simple streaming-shaped response, not live provider token streaming.

## Step 9: Live measurement

Measured on 2026-09-06 (Asia/Kolkata) after starting the backend with the
normal uvicorn command. I ran 10 representative read-only questions and then
repeated the first 5 questions exactly.

| Measurement | Measured value |
| --- | --- |
| Measurement date | 2026-09-06 |
| Model ID | `openai/gpt-oss-120b` |
| Number of requests | 15 (10 uncached, 5 cached repeats) |
| Average input/output tokens | 1,657 / 277 per request across all 15 responses; uncached only: 2,486 / 415 |
| Average cost per successful request | `$0.00041451` (15 successful responses) |
| p95 uncached latency | 29,799 ms |
| p95 cached latency | 0 ms |
| Cache hit rate | 33.33% (5 of 15) |
| Measured repeat-question saving | 5 of 5 repeats were cache hits: 15,501 model tokens and `$0.00338625` of model cost avoided (100% saving for the repeats) |
| Daily ceiling used for the demo | `$0.00621765` of the `$1.00` ceiling (0.62%) |

The final authenticated `/metrics` response reported 15 requests, 100%
success, 29,799 ms overall p95 latency, 29,004 tokens today,
`$0.00621765` spent today, and a 33.33% cache-hit rate. Cached latency is
reported as 0 ms because the application timer rounds the in-process cache
lookup to the nearest millisecond.

## Tests and CI

Run the backend checks locally:

```powershell
cd D:\agentic-ops-dashboard\backend
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m pytest -q
```

Run the Angular production build:

```powershell
cd D:\agentic-ops-dashboard\frontend
npm run build
```

The GitHub Actions workflow in `.github/workflows/ci.yml` runs the same
backend Ruff and Pytest commands, then runs `npm ci` and `npm run build` for
the frontend on every push and pull request.

## Use the MCP server with Codex

The server uses local **stdio** transport. From the backend directory:

```powershell
codex mcp add reg-ops -- ..\.venv\Scripts\python.exe .\mcp_server.py
codex mcp list
```

For a non-interactive Codex query, allow the exact tool and approve MCP tools
automatically for that invocation:

```powershell
codex exec --ephemeral -C "D:\agentic-ops-dashboard\backend" `
  -c "mcp_servers.reg-ops.enabled_tools=['query_submissions']" `
  -c "mcp_servers.reg-ops.default_tools_approval_mode='approve'" `
  --sandbox read-only `
  "Using reg-ops, call query_submissions once with region APAC and max_rows 3. Report only the returned IDs and statuses."
```

The MCP server itself exposes only read-only tools and can also be used by
other compatible local clients.

## RAG behavior

`backend/rag.py` implements this pipeline:

```text
Markdown policy
  -> heading/paragraph chunks
  -> Ollama embedding
  -> persistent ChromaDB collection
  -> nearest-neighbor retrieval
  -> source and chunk ID returned to the caller
```

Policy results use `MAX_POLICY_DISTANCE = 1.0`. When no result passes the
cutoff, `search_policies` returns `INSUFFICIENT_DATA` instead of inventing a
policy answer. Live submission counts and statuses use SQLite tools, not RAG.

## Project status

The Angular + FastAPI dashboard milestone is implemented, along with local
MCP, RAG, approval, trace, tests, and CI examples. Later study-guide topics
such as hybrid retrieval, LangGraph orchestration, durable audit logging,
deployment, cost metrics, and a full production security review remain future
learning steps.

## Important files

| File | Purpose |
| --- | --- |
| `backend/api.py` | FastAPI app, authentication dependency, normal and streaming endpoints. |
| `backend/agent.py` | Bounded model-tool-model loop and internal trace. |
| `backend/app.py` | Groq client configuration and model call. |
| `backend/service.py` | Guardrail entry point, response shaping, row/chart extraction, and trace sanitization. |
| `backend/tools.py` | Tool implementations and registry. |
| `backend/tool_schemas.py` | Model-facing tool descriptions and sensitive-tool list. |
| `backend/models.py` | Pydantic request and tool argument contracts. |
| `backend/db.py` | SQLite access helpers. |
| `backend/rag.py` / `backend/ingest_policies.py` | Policy chunking, embedding, indexing, and retrieval. |
| `backend/mcp_server.py` | Local stdio MCP server. |
| `frontend/src/app/agent-api.service.ts` | Angular API and NDJSON stream client. |
| `frontend/src/app/ask/` | Question screen, results, chart, trace, and approval dialog. |
| `.github/workflows/ci.yml` | Backend checks and Angular build. |

## Current limitations

- Authentication is a fixed local bearer token, with no real users, sessions,
  roles, or production identity provider.
- The agent trace is kept in memory. It is sanitized for the API response but
  is not a durable audit record.
- The input guardrail is intentionally small and is not a complete
  prompt-injection defence.
- The streaming endpoint emits events after the full agent call completes; it
  does not yet stream provider tokens or support cancellation.
- Approving a request resubmits the question with a simple boolean flag; there
  is no durable, request-bound approval record.
- Groq and Ollama are required at runtime for the full agent and policy-search
  paths. There is no offline model fallback.
- Submission data, exports, and the email outbox are local files/SQLite data;
  the email tool does not send email.
- CI runs the Angular production build but does not run Angular unit tests.
- The app is configured for local development only: fixed localhost API/CORS
  settings, no deployment configuration, and no production security review.
