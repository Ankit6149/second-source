
create schema if not exists ss;
revoke all on schema ss from public, anon, authenticated;
grant usage on schema ss to service_role;
create table ss.targets (
 id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users(id),display_name text not null check(length(display_name) between 1 and 120),
 target_kind text not null check(target_kind in ('cli','api','web','recorded','document')),permission_basis text not null check(length(permission_basis) between 8 and 1000),
 scope jsonb not null default '{}'::jsonb check(jsonb_typeof(scope)='object'),allowed_actions jsonb not null default '[]'::jsonb check(jsonb_typeof(allowed_actions)='array'),
 source_sha256 text check(source_sha256 ~ '^[0-9a-f]{64}$'),archived_at timestamptz,created_at timestamptz not null default now(),unique(id,owner_id));
create index on ss.targets(owner_id,created_at desc);
create table ss.investigations(
 id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users(id),target_id uuid not null,
 title text not null check(length(title) between 1 and 160),goal text not null check(length(goal) between 1 and 3000),
 status text not null default 'draft' check(status in('draft','authorized','queued','running','completed','failed','cancelled')),
 authorization_confirmed_at timestamptz,created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 unique(id,owner_id),foreign key(target_id,owner_id) references ss.targets(id,owner_id));
create index on ss.investigations(owner_id,created_at desc);
create table ss.runs(
 id uuid primary key default gen_random_uuid(),owner_id uuid not null,investigation_id uuid not null,
 origin text not null check(origin in('real','mock','inspection')),
 stage text not null default 'created' check(stage in('created','capture','organize','distill','execute','verify','package','terminal')),
 status text not null default 'pending' check(status in('pending','queued','running','waiting_approval','completed','failed','cancel_requested','cancelled','uncertain')),
 scope_sha256 text not null check(scope_sha256 ~ '^[0-9a-f]{64}$'),frozen_suite_sha256 text check(frozen_suite_sha256 ~ '^[0-9a-f]{64}$'),
 model_name text,deadline_at timestamptz,started_at timestamptz,finished_at timestamptz,created_at timestamptz not null default now(),
 idempotency_key text not null check(length(idempotency_key) between 16 and 160),
 unique(owner_id,idempotency_key),unique(id,owner_id),
 foreign key(investigation_id,owner_id) references ss.investigations(id,owner_id),
 check(finished_at is null or status in('completed','failed','cancelled','uncertain')));
create index on ss.runs(owner_id,created_at desc);
create index on ss.runs(investigation_id,created_at desc);
create index on ss.runs(status,created_at) where status in('queued','running','waiting_approval','cancel_requested');
create table ss.run_events(
 id bigint generated always as identity primary key,run_id uuid not null,owner_id uuid not null,
 event_kind text not null check(length(event_kind) between 2 and 64),phase text not null check(length(phase) between 2 and 50),
 data jsonb not null default '{}'::jsonb check(jsonb_typeof(data)='object'),
 previous_event_sha256 text check(previous_event_sha256 ~ '^[0-9a-f]{64}$'),
 event_sha256 text not null check(event_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz not null default now(),foreign key(run_id,owner_id) references ss.runs(id,owner_id));
create index on ss.run_events(run_id,id);
create table ss.jobs(
 id uuid primary key default gen_random_uuid(),run_id uuid not null unique,owner_id uuid not null,
 state text not null default 'queued' check(state in('queued','leased','blocked','completed','dead','cancelled')),
 lease_epoch bigint not null default 0 check(lease_epoch>=0),lease_owner text,lease_until timestamptz,
 attempts integer not null default 0 check(attempts>=0),max_attempts integer not null default 3 check(max_attempts between 1 and 10),
 next_attempt_at timestamptz not null default now(),last_error_code text,enqueued_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 foreign key(run_id,owner_id) references ss.runs(id,owner_id),
 check ((state='leased')=(lease_until is not null and lease_owner is not null)));
create index on ss.jobs(next_attempt_at,enqueued_at) where state='queued';
create index on ss.jobs(lease_until) where state='leased';
create table ss.approvals(
 id uuid primary key default gen_random_uuid(),run_id uuid not null,owner_id uuid not null,
 action_kind text not null check(action_kind in('model_call','reference_mutation','deploy','repair','export')),
 action_sha256 text not null check(action_sha256 ~ '^[0-9a-f]{64}$'),
 status text not null default 'requested' check(status in('requested','approved','denied','expired','consumed')),
 max_estimated_usd numeric(12,6) not null default 0 check(max_estimated_usd>=0),granted_at timestamptz,consumed_at timestamptz,expires_at timestamptz,created_at timestamptz not null default now(),
 unique(run_id,action_sha256),unique(id,run_id,owner_id),foreign key(run_id,owner_id) references ss.runs(id,owner_id));
create index on ss.approvals(owner_id,created_at desc) where status='requested';
create table ss.model_calls(
 id uuid primary key default gen_random_uuid(),run_id uuid not null,owner_id uuid not null,approval_id uuid,
 operation_key text not null check(length(operation_key) between 16 and 160),provider text not null,model text not null,phase text not null,
 outcome text not null check(outcome in('reserved','dispatched','succeeded','failed','uncertain')),
 response_id text,failure_code text,input_tokens integer check(input_tokens>=0),output_tokens integer check(output_tokens>=0),
 estimated_usd numeric(12,6) not null default 0 check(estimated_usd>=0),uncertain_usd numeric(12,6) not null default 0 check(uncertain_usd>=0),
 request_sha256 text check(request_sha256 ~ '^[0-9a-f]{64}$'),response_sha256 text check(response_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz not null default now(),finished_at timestamptz,unique(run_id,operation_key),unique(id,run_id,owner_id),
 foreign key(run_id,owner_id) references ss.runs(id,owner_id),
 foreign key(approval_id,run_id,owner_id) references ss.approvals(id,run_id,owner_id));
create index on ss.model_calls(run_id,created_at);
create table ss.artifacts(
 id uuid primary key default gen_random_uuid(),run_id uuid not null,owner_id uuid not null,
 category text not null check(category in('evidence','hypotheses','candidate','report','bundle','receipt')),
 bucket text not null default 'second-source-private',object_key text not null check(length(object_key) between 5 and 500 and object_key !~ '(\.\.|//)'),
 content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
 size_bytes bigint not null check(size_bytes between 0 and 104857600),created_at timestamptz not null default now(),
 unique(bucket,object_key),unique(id,run_id,owner_id),foreign key(run_id,owner_id) references ss.runs(id,owner_id));
create index on ss.artifacts(run_id,created_at desc);
create table ss.observations(
 id uuid primary key default gen_random_uuid(),run_id uuid not null,owner_id uuid not null,seq integer not null check(seq>=1),
 evidence_sha256 text not null check(evidence_sha256 ~ '^[0-9a-f]{64}$'),
 public_view jsonb not null check(jsonb_typeof(public_view)='object'),
 artifact_id uuid,created_at timestamptz not null default now(),
 unique(run_id,seq),foreign key(run_id,owner_id) references ss.runs(id,owner_id),
 foreign key(artifact_id,run_id,owner_id) references ss.artifacts(id,run_id,owner_id));
create index on ss.observations(run_id,seq);
create table ss.hypotheses(
 id uuid primary key default gen_random_uuid(),run_id uuid not null,owner_id uuid not null,hypothesis_key text not null,
 statement text not null check(length(statement) between 1 and 5000),
 evidence_sha256 jsonb not null default '[]'::jsonb check(jsonb_typeof(evidence_sha256)='array'),
 status text not null check(status in('hypothesized','supported','refuted','uncertain')),
 source_model_call uuid,created_at timestamptz not null default now(),unique(run_id,hypothesis_key),
 foreign key(run_id,owner_id) references ss.runs(id,owner_id),
 foreign key(source_model_call,run_id,owner_id) references ss.model_calls(id,run_id,owner_id));
create table ss.candidates(
 id uuid primary key default gen_random_uuid(),run_id uuid not null,owner_id uuid not null,
 version integer not null check(version>=1),origin text not null check(origin in('real','mock','trusted_control')),
 candidate_sha256 text not null check(candidate_sha256 ~ '^[0-9a-f]{64}$'),
 source_model_call uuid,admitted_at timestamptz,created_at timestamptz not null default now(),
 unique(run_id,version),foreign key(run_id,owner_id) references ss.runs(id,owner_id),
 foreign key(source_model_call,run_id,owner_id) references ss.model_calls(id,run_id,owner_id),
 check(origin<>'real' or source_model_call is not null));
create table ss.evaluations(
 id uuid primary key default gen_random_uuid(),candidate_id uuid not null references ss.candidates(id),
 suite_sha256 text not null check(suite_sha256 ~ '^[0-9a-f]{64}$'),total integer not null check(total>=0),
 passed integer not null check(passed>=0),failed integer not null check(failed>=0),
 skipped integer not null check(skipped>=0),indeterminate integer not null check(indeterminate>=0),
 result_sha256 text not null check(result_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz not null default now(),check(total=passed+failed+skipped+indeterminate),unique(candidate_id,suite_sha256));
do $$ declare t text; begin
foreach t in array array['targets','investigations','runs','run_events','jobs','approvals','model_calls','artifacts','observations','hypotheses','candidates','evaluations'] loop
 execute format('alter table ss.%I enable row level security',t);
end loop; end $$;
revoke all on all tables in schema ss from public,anon,authenticated;
revoke all on all sequences in schema ss from public,anon,authenticated;
grant select,insert,update,delete on all tables in schema ss to service_role;
revoke update,delete on ss.run_events from service_role;
grant usage,select on all sequences in schema ss to service_role;
