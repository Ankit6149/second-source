-- Additive migration prepared for review. No password, hosted application, or grants
-- to browser roles. Apply after both retained baselines, never at app startup.
-- Do not apply to the live project without explicit owner approval.
BEGIN;

CREATE ROLE second_source_backend LOGIN NOINHERIT NOSUPERUSER NOCREATEDB
 NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL;

-- PostgreSQL cloud identities must be existing Auth UUIDs. Local SQLite keeps
-- its bounded local owner labels. Existing non-UUID/orphan runtime rows cause
-- this proposal to fail, never silently reassign or delete investigations.
ALTER TABLE ss_runtime.investigations
 ADD COLUMN owner_uuid uuid GENERATED ALWAYS AS (owner_id::uuid) STORED
 REFERENCES auth.users(id),
 ADD CONSTRAINT runtime_owner_canonical CHECK(owner_id=owner_uuid::text),
 ADD CONSTRAINT runtime_investigation_owner UNIQUE(investigation_id,owner_id),
 ADD CONSTRAINT runtime_investigation_scope UNIQUE(investigation_id,owner_id,scope_digest);
ALTER TABLE ss_runtime.approvals ADD CONSTRAINT runtime_approval_owner
 FOREIGN KEY(investigation_id,owner_id) REFERENCES ss_runtime.investigations(investigation_id,owner_id);
ALTER TABLE ss_runtime.idempotency
 ADD COLUMN owner_uuid uuid GENERATED ALWAYS AS (owner_id::uuid) STORED REFERENCES auth.users(id),
 ADD CONSTRAINT runtime_idempotency_owner_canonical CHECK(owner_id=owner_uuid::text);
ALTER TABLE ss_runtime.runs ADD CONSTRAINT runtime_run_investigation UNIQUE(run_id,investigation_id);
ALTER TABLE ss_runtime.events ADD CONSTRAINT runtime_event_run_investigation
 FOREIGN KEY(run_id,investigation_id) REFERENCES ss_runtime.runs(run_id,investigation_id);

-- This extra unique key changes no ss rows/permissions/policies or lifecycle.
-- It allows declarative verification of the complete existing evidence run
-- identity and frozen scope without granting ss reads or bypassing its RLS.
ALTER TABLE ss.runs ADD CONSTRAINT ss_run_runtime_binding_identity
 UNIQUE(id,investigation_id,owner_id,scope_sha256);

CREATE TABLE ss_runtime.investigation_bindings(
 investigation_id text PRIMARY KEY,
 owner_id text NOT NULL,
 owner_uuid uuid GENERATED ALWAYS AS (owner_id::uuid) STORED,
 evidence_investigation_id uuid NOT NULL UNIQUE,
 scope_digest text NOT NULL,
 UNIQUE(investigation_id,owner_id,evidence_investigation_id,scope_digest),
 FOREIGN KEY(investigation_id,owner_id,scope_digest)
  REFERENCES ss_runtime.investigations(investigation_id,owner_id,scope_digest),
 FOREIGN KEY(evidence_investigation_id,owner_uuid) REFERENCES ss.investigations(id,owner_id));

CREATE TABLE ss_runtime.run_bindings(
 run_id text PRIMARY KEY,
 investigation_id text NOT NULL,
 owner_id text NOT NULL,
 owner_uuid uuid GENERATED ALWAYS AS (owner_id::uuid) STORED,
 evidence_investigation_id uuid NOT NULL,
 scope_digest text NOT NULL,
 evidence_run_id uuid NOT NULL UNIQUE,
 UNIQUE(run_id,owner_id,evidence_run_id),
 FOREIGN KEY(run_id,investigation_id) REFERENCES ss_runtime.runs(run_id,investigation_id),
 FOREIGN KEY(investigation_id,owner_id,evidence_investigation_id,scope_digest)
  REFERENCES ss_runtime.investigation_bindings(investigation_id,owner_id,evidence_investigation_id,scope_digest),
 FOREIGN KEY(evidence_run_id,evidence_investigation_id,owner_uuid,scope_digest)
  REFERENCES ss.runs(id,investigation_id,owner_id,scope_sha256));

CREATE TABLE ss_runtime.artifact_bindings(
 evidence_artifact_id uuid PRIMARY KEY,
 run_id text NOT NULL,
 owner_id text NOT NULL,
 owner_uuid uuid GENERATED ALWAYS AS (owner_id::uuid) STORED,
 evidence_run_id uuid NOT NULL,
 FOREIGN KEY(run_id,owner_id,evidence_run_id)
  REFERENCES ss_runtime.run_bindings(run_id,owner_id,evidence_run_id),
 FOREIGN KEY(evidence_artifact_id,evidence_run_id,owner_uuid)
  REFERENCES ss.artifacts(id,run_id,owner_id));

-- Hashes/lengths only: private original bytes stay in private object storage.
CREATE TABLE ss_runtime.runtime_artifact_refs(
 run_id text NOT NULL,
 investigation_id text NOT NULL,
 owner_id text NOT NULL,
 artifact_id text NOT NULL CHECK(artifact_id ~ '^[A-Za-z0-9_.:-]{1,128}$'),
 sha256 text NOT NULL CHECK(sha256 ~ '^[a-f0-9]{64}$'),
 size_bytes bigint NOT NULL CHECK(size_bytes BETWEEN 0 AND 104857600),
 media_type text NOT NULL CHECK(length(media_type) BETWEEN 1 AND 120),
 PRIMARY KEY(run_id,artifact_id),
 FOREIGN KEY(run_id,investigation_id) REFERENCES ss_runtime.runs(run_id,investigation_id),
 FOREIGN KEY(investigation_id,owner_id) REFERENCES ss_runtime.investigations(investigation_id,owner_id));

DO $block$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['investigation_bindings','run_bindings','artifact_bindings','runtime_artifact_refs'] LOOP
  EXECUTE format('ALTER TABLE ss_runtime.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE TRIGGER immutable_binding BEFORE UPDATE OR DELETE ON ss_runtime.%I FOR EACH ROW EXECUTE FUNCTION ss_runtime.reject_immutable()',t);
 END LOOP;
END $block$;

REVOKE ALL ON SCHEMA ss_runtime FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON ALL TABLES IN SCHEMA ss_runtime FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA ss_runtime FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ss_runtime FROM PUBLIC,anon,authenticated,service_role;
GRANT USAGE ON SCHEMA ss_runtime TO second_source_backend;
GRANT SELECT ON ALL TABLES IN SCHEMA ss_runtime TO second_source_backend;
GRANT INSERT ON ss_runtime.investigations,ss_runtime.approvals,ss_runtime.runs,
 ss_runtime.events,ss_runtime.idempotency,ss_runtime.investigation_bindings,
 ss_runtime.run_bindings,ss_runtime.artifact_bindings,ss_runtime.runtime_artifact_refs TO second_source_backend;
GRANT UPDATE(status,revision,updated_at) ON ss_runtime.investigations TO second_source_backend;
GRANT UPDATE(status,stage,revision,cancel_requested,updated_at,result_json,error_code,
 worker_id,lease_token,lease_expires) ON ss_runtime.runs TO second_source_backend;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA ss_runtime TO second_source_backend;
GRANT EXECUTE ON FUNCTION ss_runtime.reject_immutable() TO second_source_backend;

-- The server role is trusted across owners; BackendService provides tenant
-- predicates. These role-specific policies grant no browser/Data API access.
-- ss remains policy-free/private, and the role cannot select or mutate it.
DO $block$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['schema_version','investigations','approvals','runs','events',
  'idempotency','investigation_bindings','run_bindings','artifact_bindings','runtime_artifact_refs'] LOOP
  EXECUTE format('CREATE POLICY runtime_server_read ON ss_runtime.%I FOR SELECT TO second_source_backend USING(true)',t);
  IF t <> 'schema_version' THEN
   EXECUTE format('CREATE POLICY runtime_server_insert ON ss_runtime.%I FOR INSERT TO second_source_backend WITH CHECK(true)',t);
  END IF;
  IF t IN ('investigations','runs') THEN
   EXECUTE format('CREATE POLICY runtime_server_update ON ss_runtime.%I FOR UPDATE TO second_source_backend USING(true) WITH CHECK(true)',t);
  END IF;
 END LOOP;
END $block$;

ALTER TABLE ss_runtime.schema_version DROP CONSTRAINT schema_version_version_check;
UPDATE ss_runtime.schema_version SET version=2;
ALTER TABLE ss_runtime.schema_version ADD CONSTRAINT schema_version_version_check CHECK(version=2);
COMMIT;
