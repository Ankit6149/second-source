# Second Source — no-billing release audit (29 October 2026)

**Scope:** read-only GitHub and Supabase inspection of current state plus static review of the open PR #13 and PR #14 diffs. **Verdict: NO-GO for full product / genuine G3 acceptance.** This document is supplemental to [the delivery board](G3_DELIVERY_BOARD.md), not an execution authorization.

## Verified source and engineering state

- Latest observed GitHub `main` is [`d7bd7cf551f2abe7280619bdaf334f5713f92ab3`](https://github.com/Ankit6149/second-source/commit/d7bd7cf551f2abe7280619bdaf334f5713f92ab3) (merged PR #12 — recovered already-applied Supabase schema and disposable PG acceptance). The older `1ba89054` reference is an ancestor, not latest HEAD.
- The [521-Linux/522-Windows green run](https://github.com/Ankit6149/second-source/actions/runs/40849690763) is source-specific evidence from the previous published main, **not automatically proof of tests at `d7bd7cf`**. Check the latest exact-main CI separately.
- [PR #13 — Supabase identity](https://github.com/Ankit6149/second-source/pull/13) and [PR #14 — PostgreSQL persistence](https://github.com/Ankit6149/second-source/pull/14) were **open** during review. Do not duplicate their implementation or presume acceptance.
- Genuine G3: two attempts were consumed; **no admitted Muse-generated candidate, no scored genuine candidate**. Root rejection field is unknown; prior model receipt estimates are not confirmed billing.
- Trusted positive 25/25, scripted mock 22/25 and sensitivity negative controls 2/2/1 are **NON_AI**. No authorized paid retries, repair, credentials or new inference.

## Read-only Supabase confirmation

Project `jpqcqqbzriizxhigvjki` in `ap-south-1` reported **ACTIVE_HEALTHY**.

- Twelve tables exist in the private `ss` schema; **all have RLS enabled**.
- None of these twelve tables grants direct SELECT to `anon` or `authenticated`. The advisor's 12 “RLS enabled no policy” INFO notices are **not a confirmed exposure** in this private server-only schema. Do not add open `authenticated` policies in response.
- The `second-source-private` bucket is **not public**; object limit 10 MiB; allowed JSON/ZIP/text/octet-stream MIME types.
- Advisor flagged 14 missing covering indexes on foreign keys; do workload-informed review rather than blindly applying indexes. [Supabase RLS notice](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy) · [FK index notice](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys).
- No changes to live tables, grants, policies, buckets, auth providers, secrets, production API or billing occurred. This is **not** proof of working Google OAuth, production API/worker, client authentication, or durable live cloud integration.

## Targeted code review: pending pull requests

### PR #13 — fail-closed identity handling

In `src/second_source/backend/auth.py`, the remote-user check currently rejects `value.get("is_anonymous") is True`, but accepts **missing / non-boolean** `is_anonymous`. Because the intended boundary excludes anonymous sessions, require explicit `value.get("is_anonymous") is False` (or document a specific supported API compatibility exception); test absence and incorrect types. Continue binding owner ID only after authoritative HTTPS `/auth/v1/user` validation. This is a **review finding, not a claim of exploitability**.

Google provider configuration, real PKCE redirects, refresh/revocation, live session and cross-owner tests remain unverified.

### PR #14 — TLS and principal

In `src/second_source/backend/postgres.py`, the DSN accepts `sslmode=require` and `sslmode=verify-ca` as well as `verify-full`. Requiring TLS **without verifying the expected hostname** is a weaker remote-peer identity guarantee than the stated production goal. Prefer `sslmode=verify-full` with the correct trust store; test refusal of weaker modes. In the current constructor, a direct `postgres` admin account is accepted. Production must instead use a least-privilege runtime principal and explicit permissions, with a separate reviewed operational setup. Do not deploy or apply the additive `ss_runtime` migration yet.

The native disposable PG test checks valuable offline behavior, **not** live hosted transaction authority, Google sign-in, artifact storage, worker survival, or hosted production acceptance.

## Truthful release gates

| Release condition | Current state |
|---|---|
| Verified G2 hypotheses + model-selected experiment | Previous genuine receipts available (local operator evidence) |
| Genuine G3 generated candidate admitted | **Blocked / unproven** |
| Genuine sealed behavioral score | **Blocked / unproven** |
| Bounded repair measurable on unchanged suite | **Unverified / not authorized** |
| SQLite mock-only API/worker/exports | Previously accepted NON_AI |
| Supabase OAuth + authenticated production API | **Unverified; PR #13 open** |
| Hosted PostgreSQL runtime/storage | **Unverified; PR #14 open** |
| Public landing/design atlas | Visual prototypes, not evidence of backend capability |
| 180-second demo video and organizer submission receipt | **Unverified** |

### Next actions (zero-cost first)

1. Review/fix PR #13 anonymous-field fail-closed boundary; run exact-head tests/independent review.
2. Review/fix PR #14 hostname verification and least-privilege runtime plan; test disposable PG/CI, no cloud migration.
3. Check exact latest main CI and maintain the canonical delivery board with SHA-specific acceptance evidence.
4. Perform no-call G3 preflight only with authentic operator-local inputs, preserving immutable pinned scope/suite; do not reopen consumed attempts.
5. Continue visual QA on separate landing preview without presenting mock results as real.
6. Only after distinct owner authorization may a genuinely new paid model attempt, live credential operation, production deployment, or merge occur. Otherwise submit honestly scoped G2 + NON_AI evidence.

**No-billing / no-production-write boundary:** This audit does not permit provider calls, paid resources, database DDL, credentials, public data exports, automatic merges, or production promotion.
