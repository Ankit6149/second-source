# Hosted acceptance: owner decision packet

**Prepared for review; no live operation is authorized by this document.** The
target is a two-owner, zero-inference acceptance of one reviewed backend and an
isolated frontend preview. The existing landing production deployment remains
outside this change. No credentials, migration history, backup or live resources
were accessed while preparing this packet.

## Proposed operations, each requiring explicit approval

1. **Preflight and recovery:** inspect the existing Supabase project
   `jpqcqqbzriizxhigvjki`, its applied migration history, current `ss` schema,
   Auth/Storage configuration and free-plan eligibility. Establish that an
   owner-controlled backup exists and demonstrate an appropriate restore path
   before DDL. Stop if backup/restore or free-tier eligibility cannot be verified.
   Never reapply the existing `20261028193413` evidence baseline.
2. **Runtime database:** after a separate migration approval, apply only
   `supabase/migrations/20261029_backend_runtime_schema.sql` and
   `supabase/migrations/20261030180237_runtime_private_role_and_bindings.sql`, in
   that order, after independent review against the actual migration history.
   Verify preserved `ss` data/policies, runtime RLS, role grants, tenant isolation,
   optimistic revisions, job claims and artifact bindings. The server-only
   `second_source_backend` role is non-owner, `NOBYPASSRLS` and has no password
   in the migration; provision its credential privately, with verified TLS.
3. **Identity and storage:** after approval, configure only the approved Google
   OAuth callback and exact preview redirect origin, preserving existing settings.
   Verify or configure the `second-source-private` bucket as private. Keep the
   Storage server credential on the backend; never put it in frontend variables,
   chat, Git, logs or the browser. Verify expiry, ownership and object integrity.
4. **Backend preview:** after approval and account eligibility checks, provision
   one Render Free service from the reviewed `render.yaml`, with auto-deploy off,
   real inference and mock execution disabled, no sandbox and no other worker.
   Set `SECOND_SOURCE_CORS_ORIGINS` to the exact approved preview HTTPS origin.
   Verify readiness, cold start, permissions and authenticated refusal paths.
   Railway remains an inactive alternative.
5. **Preview connection:** after approval, configure the isolated frontend preview
   with `VITE_API_ORIGIN`, the fixed Supabase project URL and its **publishable**
   key only. The OAuth redirect is the preview origin plus application pathname;
   no service-role, database, Storage or model secret belongs in the frontend.
6. **Bounded acceptance:** only after separate approval, enable
   `SECOND_SOURCE_ENABLE_MOCK_EXECUTION=true` for the single service. With two
   owner-controlled test identities verify login, scope, authorization, queue,
   NON_AI execution, progress, independent evaluation, report, integrity export,
   restart recovery, other-owner denial, cancellation, corrupt-object refusal,
   lost acknowledgements and uncertain-operation quarantine. Disable execution
   immediately on unexpected cost, security failure or unclear execution state.

## Cost and limits

The intended incremental plan cost is **$0**, not a verified account-specific
invoice or guarantee. [Render Free](https://render.com/docs/free) includes 750
instance hours per workspace per month; it sleeps after 15 idle minutes, can take
about a minute to wake, and has an ephemeral filesystem. Render states that a
workspace with a payment method can incur bandwidth or build-minute overages;
without a payment method it suspends services or builds on exhaustion. Confirm
account status and included usage before provisioning, without disclosing private
balances. [Supabase Free pricing](https://supabase.com/pricing) lists 500 MB
database, 1 GB storage and 5 GB egress; its actual organization, current usage,
backup and project state are unverified. No plan upgrade, payment method, paid
worker, inference, sandbox or promotional credit use is included.

## Stop and rollback

Stop new runs, disable mock execution, preserve evidence and quarantine uncertain
work. Revert OAuth/origin and preview configuration to their recorded prior values
and restore the prior compatible backend build or stop the new service. A failed
transactional migration rolls back before commit; after commit do not drop or
rewind `ss`, `ss_runtime`, events or private objects. Any restore or destructive
reversal requires an independently reviewed recovery plan and separate approval.
The complete operational constraints are in `CLOUD_BACKEND_OPERATIONS.md` and
`POSTGRES_BACKEND.md`.
