# Hosted acceptance: owner decision packet

**Prepared for review; no live operation is authorized by this document.** The
target is a two-owner, zero-inference acceptance of one reviewed backend and an
isolated frontend preview. The existing landing production deployment remains
outside this change. Read-only metadata was inspected through the connected
Supabase integration; no credentials, backup contents or live mutations were
accessed or performed while preparing this packet.

On November 1, 2026, the connected service reported project
`jpqcqqbzriizxhigvjki` healthy in `ap-south-1` on the Free organization plan.
Its migration history listed only `20261028193413` and its twelve reported `ss`
tables had RLS enabled; read-only catalog checks found neither the `ss_runtime`
schema nor the `second_source_backend` role. The existing
`second-source-private` bucket was reported with `public=false`. These are
metadata observations, not proof of the policies' correctness, tenant isolation,
available quota, a usable backup or a tested restore. Recheck them immediately
before any approved change.

## Stage 1 decision — NO-GO for live migrations

The November 1 read-only review found RLS enabled on all twelve `ss` tables but
not forced, with no `ss` policies. `anon` and `authenticated` have no `ss`
schema usage or table SELECT/INSERT; the existing `service_role` has BYPASSRLS
and access, so server-side authorization and secret isolation remain essential.
The private Storage bucket exists, but no `storage.objects` policies were listed;
owner-scoped Storage behavior has not been proved. The proposed runtime RLS
policies trust one server role across owners and do **not** enforce tenant-level
separation independently of backend predicates.

No project-specific backup or restore drill has been verified. Supabase's
[Free-plan guidance](https://supabase.com/kb/faqs/platform/free-plan-backups)
says automatic daily backups are not provided on Free. Database backups also
do not preserve Storage object bytes or custom-role passwords. Do not export live
data, create a paid backup, add credentials or perform a restore without their
own explicit approval. A synthetic-only local PostgreSQL restore drill, if
available, demonstrates a technique but cannot establish recoverability of this
specific live project.

Two further conditions block DDL: the first proposed filename has an eight-digit
version (`20261029`), while the CLI convention uses fourteen digits and an
[upstream issue](https://github.com/supabase/cli/issues/4758) reports problems
displaying short migration versions; verify the exact ordering and history in a
disposable environment. Each migration has its own transaction: if the first
commits and the second fails, the first remains applied. Stop and inspect that
intermediate state; do not blindly retry or drop it. The second migration also
adds a unique constraint to existing `ss.runs`, an additive **schema change**
that must be specifically reviewed even though it does not intentionally alter
rows. Recheck live history, role grants and existing data before any approved DDL.

## Stable staging origin and CI limits

The existing separate preview project has the branch alias
`https://second-source-v08-product-previe-git-fef0b7-ankit6149s-projects.vercel.app`.
Read-only inspection on November 1 found it mapped to frontend commit `ab90636`
and protected by Vercel authentication (an unauthenticated request redirects to
Vercel SSO). It is a candidate stable hostname, **not yet an approved or
configured OAuth origin**. A branch alias follows deployments, so pin and verify
the exact reviewed deployment before hosted acceptance. Authorized test owners
must be able to pass the existing Vercel protection; a temporary share token is
not an OAuth origin. No protection, domain, OAuth or production setting has been
changed. See [Vercel preview environments](https://vercel.com/docs/deployments/environments).

The prepared `product/ci/frontend.yml` limits automatic quick checks to relevant
paths on one standard Linux runner. Full browser/worker acceptance is manually
dispatched; Windows and screenshot upload are opt-in, and explicit synthetic-only
PNG artifacts expire after two days. GitHub documents standard hosted runners as
free for public repositories; larger runners and artifact storage have separate
terms. At the listed standard rates, a 10-minute Linux quick-job ceiling would be
at most $0.06 of metered compute if this repository became private and its
included usage were exhausted; a manual 20-minute Linux job would be at most
$0.12, plus $0.20 for an opted-in 20-minute Windows job. These are ceilings,
not measured usage or a current bill. No workflow is installed or dispatched by
this proposal. See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and [runner prices](https://docs.github.com/en/billing/reference/actions-runner-pricing).

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
database, 1 GB storage and 5 GB egress; the organization is confirmed Free, but
its current usage, backup and restore readiness are unverified. No plan upgrade, payment method, paid
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
