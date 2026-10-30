-- Additive private control plane for transactional Python backend.
-- Existing ss evidence schema/migration are unchanged. Apply only after review.
BEGIN;
CREATE SCHEMA ss_runtime;
REVOKE ALL ON SCHEMA ss_runtime FROM PUBLIC, anon, authenticated;
CREATE TABLE ss_runtime.schema_version(version integer primary key check(version=1));
INSERT INTO ss_runtime.schema_version values(1);
CREATE TABLE ss_runtime.investigations(
 investigation_id text primary key, owner_id text not null,
 title text not null, scope_json text not null, scope_digest text not null,
 status text not null check(status in('created','authorized')),
 revision integer not null check(revision>0),
 created_at text not null, updated_at text not null);
CREATE INDEX investigations_owner ON ss_runtime.investigations(owner_id,investigation_id);
CREATE TABLE ss_runtime.approvals(
 investigation_id text primary key references ss_runtime.investigations(investigation_id),
 owner_id text not null,scope_digest text not null,receipt_json text not null,created_at text not null);
CREATE TABLE ss_runtime.runs(
 run_id text primary key,investigation_id text not null references ss_runtime.investigations(investigation_id),
 kind text not null check(kind='g3_mock'),
 status text not null check(status in('queued','running','completed','failed','cancelled','needs_reconciliation')),
 stage text,revision integer not null check(revision>0),
 cancel_requested integer not null default 0 check(cancel_requested in(0,1)),
 created_at text not null,updated_at text not null,result_json text,error_code text,
 worker_id text,lease_token text,lease_expires double precision);
CREATE INDEX runs_queue ON ss_runtime.runs(status,created_at,run_id);
CREATE INDEX runs_investigation ON ss_runtime.runs(investigation_id,run_id);
CREATE TABLE ss_runtime.events(
 event_id bigint generated always as identity primary key,
 investigation_id text not null references ss_runtime.investigations(investigation_id),
 run_id text references ss_runtime.runs(run_id),
 event_type text not null,stage text,created_at text not null,revision integer not null);
CREATE INDEX events_investigation ON ss_runtime.events(investigation_id,event_id);
CREATE TABLE ss_runtime.idempotency(
 owner_id text not null,operation text not null,key text not null,
 request_digest text not null,resource_id text not null,
 primary key(owner_id,operation,key));
CREATE FUNCTION ss_runtime.reject_immutable() RETURNS trigger
 LANGUAGE plpgsql SET search_path=pg_catalog AS $$
 BEGIN RAISE EXCEPTION 'immutable backend record'; END $$;
CREATE TRIGGER immutable_scope BEFORE UPDATE OF owner_id,scope_json,scope_digest,investigation_id
 ON ss_runtime.investigations FOR EACH ROW EXECUTE FUNCTION ss_runtime.reject_immutable();
CREATE TRIGGER immutable_approvals BEFORE UPDATE OR DELETE
 ON ss_runtime.approvals FOR EACH ROW EXECUTE FUNCTION ss_runtime.reject_immutable();
CREATE TRIGGER immutable_events BEFORE UPDATE OR DELETE
 ON ss_runtime.events FOR EACH ROW EXECUTE FUNCTION ss_runtime.reject_immutable();
CREATE TRIGGER immutable_idempotency BEFORE UPDATE OR DELETE
 ON ss_runtime.idempotency FOR EACH ROW EXECUTE FUNCTION ss_runtime.reject_immutable();
DO $block$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['schema_version','investigations','approvals','runs','events','idempotency']
 LOOP EXECUTE format('ALTER TABLE ss_runtime.%I ENABLE ROW LEVEL SECURITY',t); END LOOP;
END $block$;
REVOKE ALL ON ALL TABLES IN SCHEMA ss_runtime FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA ss_runtime FROM PUBLIC, anon, authenticated;
COMMIT;
