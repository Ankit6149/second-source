CREATE TABLE investigations (
 investigation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
 title TEXT NOT NULL, scope_json TEXT NOT NULL, scope_digest TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('created','authorized')),
 revision INTEGER NOT NULL CHECK(revision > 0), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX investigations_owner ON investigations(owner_id, investigation_id);
CREATE TABLE approvals (
 investigation_id TEXT PRIMARY KEY REFERENCES investigations(investigation_id),
 owner_id TEXT NOT NULL, scope_digest TEXT NOT NULL, receipt_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE runs (
 run_id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
 kind TEXT NOT NULL CHECK(kind='g3_mock'),
 status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','cancelled','needs_reconciliation')),
 stage TEXT, revision INTEGER NOT NULL CHECK(revision > 0), cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN(0,1)),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, result_json TEXT, error_code TEXT,
 worker_id TEXT, lease_token TEXT, lease_expires REAL
);
CREATE INDEX runs_queue ON runs(status, created_at, run_id);
CREATE INDEX runs_investigation ON runs(investigation_id, run_id);
CREATE TABLE events (
 event_id INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
 run_id TEXT REFERENCES runs(run_id), event_type TEXT NOT NULL, stage TEXT, created_at TEXT NOT NULL, revision INTEGER NOT NULL
);
CREATE INDEX events_investigation ON events(investigation_id,event_id);
CREATE TABLE idempotency (
 owner_id TEXT NOT NULL, operation TEXT NOT NULL, key TEXT NOT NULL,
 request_digest TEXT NOT NULL, resource_id TEXT NOT NULL,
 PRIMARY KEY(owner_id, operation, key)
);
CREATE TRIGGER immutable_scope BEFORE UPDATE OF owner_id,scope_json,scope_digest,investigation_id ON investigations BEGIN SELECT RAISE(ABORT,'immutable scope'); END;
CREATE TRIGGER immutable_approval_update BEFORE UPDATE ON approvals BEGIN SELECT RAISE(ABORT,'immutable approval'); END;
CREATE TRIGGER immutable_approval_delete BEFORE DELETE ON approvals BEGIN SELECT RAISE(ABORT,'immutable approval'); END;
CREATE TRIGGER immutable_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER immutable_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER immutable_idempotency_update BEFORE UPDATE ON idempotency BEGIN SELECT RAISE(ABORT,'immutable idempotency'); END;
CREATE TRIGGER immutable_idempotency_delete BEFORE DELETE ON idempotency BEGIN SELECT RAISE(ABORT,'immutable idempotency'); END;
