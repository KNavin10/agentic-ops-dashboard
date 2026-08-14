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
