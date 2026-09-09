CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region TEXT NOT NULL,
    submission_date TEXT NOT NULL,
    days_late INTEGER NOT NULL DEFAULT 0 CHECK (days_late >= 0),
    status TEXT NOT NULL CHECK (status IN ('Approved', 'Under Review', 'Breached', 'Rejected')),
    breach_reason TEXT,
    client_name TEXT NOT NULL,
    account_ref TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_submissions_region ON submissions (region);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions (status);
CREATE INDEX IF NOT EXISTS idx_submissions_submission_date ON submissions (submission_date);

CREATE TABLE IF NOT EXISTS agent_runs (
    request_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    user_id TEXT,
    question_hash TEXT NOT NULL,
    question_length INTEGER NOT NULL,
    status TEXT NOT NULL,
    steps INTEGER NOT NULL,
    tool_sequence TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    cited INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs (created_at);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    requester TEXT NOT NULL,
    tool TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    arguments_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    executed_at TEXT,
    decision TEXT CHECK (decision IN ('approve', 'decline'))
);

CREATE INDEX IF NOT EXISTS idx_approvals_requester ON approvals (requester);
