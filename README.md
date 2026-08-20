# Agentic Regulatory Ops Dashboard

This is a beginner-friendly backend slice of the **Agentic Regulatory Ops Dashboard** from the 14-day agentic AI study guide.

It demonstrates how an agent can use small, validated tools to work with regulatory submission data and policy documents. The current repository is a Python/SQLite learning project; it is not yet the full Angular + FastAPI dashboard described in the study guide.

## What is implemented

| Study-guide area | Current implementation |
| --- | --- |
| Day 3: tool calling | Six function tools with JSON schemas, Pydantic argument models, SQLite queries, result shaping, and a tool registry. |
| Day 4: agent loop | A bounded loop with `MAX_STEPS = 8`, a token budget, an in-memory trace, and a simple prompt-injection guardrail. |
| Day 4: human approval | `export_report` and `email_summary` are treated as sensitive tools and require approval before writing local files. |
| Day 5: RAG | Markdown policy chunking, Ollama embeddings, persistent ChromaDB storage, source/chunk metadata, a distance cutoff, and `INSUFFICIENT_DATA`. |
| Day 6: MCP | A local stdio MCP server exposing `query_submissions` and `search_policies`. |

The data is deliberately fake and deterministic. `seed_database.py` creates 200 submission rows across APAC, EMEA, and AMER.

## Architecture

```text
User question
    -> guardrails.py
    -> agent.py
    -> Groq model with tool schemas
    -> validated tool in tools.py
       -> SQLite database for live submission data
       -> ChromaDB + Ollama for policy retrieval
    -> tool result returned to the model
    -> answer plus in-memory trace
```

The MCP path reuses the same tool functions:

```text
Codex / another MCP client
    -> mcp_server.py over local stdio
    -> tools.py
    -> SQLite or policy RAG
```

## Tools

The model-facing registry in `tool_schemas.py` contains:

- `query_submissions(region, max_rows)` — read submission rows with an APAC/EMEA/AMER whitelist and a maximum of 200 rows.
- `get_breach_reasons(ids)` — read breach details for one or more submission IDs.
- `aggregate_by_month(region)` — return monthly submission and lateness aggregates.
- `export_report(region)` — write a local CSV file after approval.
- `email_summary(recipient, subject, body)` — write a local JSON outbox file after approval; it does not send email.
- `search_policies(question, k)` — retrieve policy passages with source and chunk IDs.

The MCP server currently exposes only `query_submissions` and `search_policies`.

## Safety boundaries demonstrated

- Region values are validated with Pydantic literals.
- Query row counts are capped at 200.
- SQL uses parameters instead of model-generated SQL.
- Submission results return only `id`, `region`, `days_late`, and `status`.
- Export and email actions are separated from read-only tools and require approval.
- The agent stops after eight steps or when its token budget is exceeded.
- A small input guardrail blocks several obvious instruction-override phrases.
- The MCP server reuses the same tool boundary instead of exposing raw SQL or shell access.

This is an educational implementation. It does not yet provide authentication, authorization, a persistent audit log, a web API, a frontend, or a production-grade security review.

## Setup

From PowerShell:

```powershell
cd D:\agentic-ops-dashboard
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a `.env` file. `app.py` currently uses Groq, so add the key it needs:

```env
GROQ_API_KEY=your_groq_key
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=qwen3-embedding
```

The existing `.env.example` contains older placeholder provider names; check the code when adding environment variables.

## Prepare the local data

The repository currently contains a seeded `data/operations.db`. To recreate the deterministic database:

```powershell
python .\seed_database.py
```

Warning: the seed script clears the existing `submissions` table before inserting 200 fake rows.

For policy search, start Ollama and make the embedding model configured by `OLLAMA_EMBEDDING_MODEL` available. Then build the local ChromaDB collection:

```powershell
python .\ingest_policies.py
```

The policy index is stored in `vectorstore/` and uses the `reg_policies` collection. Chunks preserve Markdown headings and store `source`, `chunk_id`, `section`, and an estimated token count.

## Run the learning examples

Run the bounded agent example:

```powershell
python .\agent.py
```

Run the input guardrail plus agent example:

```powershell
python .\guardrails.py
```

Both examples call the Groq model, so `GROQ_API_KEY` must be set first.

For a simple offline database-tool check:

```powershell
python -c "from tools import query_submissions; print(query_submissions({'region': 'APAC', 'max_rows': 3}))"
```

## Use the MCP server with Codex

The server uses local **stdio** transport. Register it once from the project directory:

```powershell
codex mcp add reg-ops -- .venv\Scripts\python.exe .\mcp_server.py
codex mcp list
```

For a non-interactive Codex query, allow the exact tool and approve MCP tools automatically for that invocation:

```powershell
codex exec --ephemeral -C "D:\agentic-ops-dashboard" `
  -c "mcp_servers.reg-ops.enabled_tools=['query_submissions']" `
  -c "mcp_servers.reg-ops.default_tools_approval_mode='approve'" `
  --sandbox read-only `
  "Using reg-ops, call query_submissions once with region APAC and max_rows 3. Report only the returned IDs and statuses."
```

The `default_tools_approval_mode` override is needed with the current Codex CLI non-interactive MCP approval behavior. The MCP server itself can also be used by other compatible local clients.

## RAG behavior

`rag.py` implements this small pipeline:

```text
Markdown policy
    -> heading/paragraph chunks
    -> Ollama embedding
    -> persistent ChromaDB collection
    -> nearest-neighbor retrieval
    -> source and chunk ID returned to the caller
```

Policy results are filtered using `MAX_POLICY_DISTANCE = 1.0`. When no result passes the cutoff, `search_policies` returns `INSUFFICIENT_DATA` instead of inventing a policy answer.

Live submission counts and statuses use SQLite tools, not RAG. This follows the study guide’s distinction: retrieve documents for policy claims and query a live tool for current records.

## Project status against the study guide

The study guide’s Project A target also includes Angular, FastAPI, tests, CI, authentication/authorization, persistent audit logging, deployment, and evaluation. Those pieces are **not present in this checkout yet**.

The later guide topics—hybrid retrieval, LangGraph orchestration, observability and cost metrics, Docker/CI/CD, and the full security/demo review—are also future learning steps rather than implemented features here.

## Important files

| File | Purpose |
| --- | --- |
| `agent.py` | Bounded model–tool–model loop and in-memory trace. |
| `app.py` | Groq client configuration and model call. |
| `guardrails.py` | Simple input guardrail before the agent loop. |
| `tools.py` | Tool implementations and registry. |
| `tool_schemas.py` | Model-facing tool descriptions and sensitive-tool list. |
| `models.py` | Pydantic argument contracts. |
| `db.py` | SQLite access helpers. |
| `seed_database.py` / `schema.sql` | Deterministic database setup. |
| `rag.py` / `ingest_policies.py` | Policy chunking, embedding, indexing, and retrieval. |
| `mcp_server.py` | Local stdio MCP server. |
| `policies/sla_policy.md` | Local policy source document. |

## Current limitations

- There is no automated test suite in the repository yet.
- The agent trace is kept in memory and is not a durable audit record.
- The input guardrail is intentionally small and is not a complete prompt-injection defence.
- The MCP server is configured for local stdio use; there is no remote HTTP authentication layer.
- The Groq model call and Ollama embedding call require external/local providers at runtime.
