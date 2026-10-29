# Supabase authentication boundary — no paid service required

Supabase project: \`jpqcqqbzriizxhigvjki\` (Mumbai). The project is already
provisioned, but **Google provider OAuth is not enabled**. Set up the Google
client through Supabase Auth dashboard when owner-provided credentials exist.
Do not copy OAuth secrets or Supabase secret/service-role keys into Next.js.

## The implemented adapter

\`second_source.backend.auth.SupabaseIdentity(project_ref, publishable_key)\`
validates incoming access tokens against the fixed HTTPS
\`https://<project>.supabase.co/auth/v1/user\` endpoint. Supabase Auth verifies
the signature and expiry under the project's supported signing configuration. The adapter deliberately **never**
authorizes by decoding unsigned JWT claims, emails or user_metadata. Its
only result is the validated immutable user UUID, yielding the existing
\`Principal(owner_id)\`. Invalid or expired tokens, redirect attempts, malformed responses,
non-authenticated/anonymous users, oversized bodies and remote outages are
rejected. **Access tokens can remain usable after ordinary sign-out until
expiry; this endpoint alone does not guarantee immediate JWT revocation.**
For strict session invalidation, verify the returned session ID against
auth.sessions using a separately reviewed privileged server-side check.
See https://supabase.com/docs/guides/auth/sessions#how-to-ensure-an-access-token-jwt-cannot-be-used-after-a-user-signs-out .

Application integration:

\`\`\`python
from second_source.backend.api import create_app
from second_source.backend.auth import SupabaseIdentity
from second_source.backend.service import BackendService

identity = SupabaseIdentity(
    project_ref="jpqcqqbzriizxhigvjki",
    publishable_key="YOUR_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
)
app = create_app(BackendService("PRIVATE_DB.sqlite"), identity_resolver=identity)
\`\`\`

This initializes an **identity-enabled but still local SQLite** control plane;
it does *not* cloud-enable persistence, execution or storage. The
\`create_app(..., token_hashes={sha256: owner})\` local acceptance API remains
unchanged. Only one authority may be configured; mixed identity authorities
fail startup. The \`/v1/capabilities\` contract still truthfully advertises
mock-only mode and zero paid inference. Network calls are bounded to 4 seconds,
redirects are disallowed, response size is capped at 16 KiB, and remote
errors never leak token/provider response details. No user-info cache
is kept. Pre-auth global throttling and verification concurrency bounds are
implemented as in-process guardrails; they are NOT a distributed rate limit
across multiple Vercel instances. Before public multi-instance launch, add
provider-aware distributed throttling, transport telemetry, revocation
requirements and an explicit auth service-availability health signal.

## Key missing pieces

1. Google OAuth client ID/secret + exact allowed redirect URIs — needs the
   owner to configure in the provider dashboard.
2. A reviewed PostgreSQL storage adapter using the **existing live** private
   \`ss\` schema, with owner scope and durable transactions. Do not pretend
   the SQLite schema matches the pre-existing Supabase schema.
3. Deployment of the Python API/worker to an eligible free host. Render Free
   sleeps and is not a guaranteed always-on durable worker. No billing account
   or paid provider authorization is approved.
4. Strongly isolated execution for untrusted user-supplied code remains
   unavailable under current no-billing constraints. Only owned, bounded
   fixture execution is supported.

## Verification

\`pytest -q tests/test_backend_supabase_auth.py tests/test_backend_api.py\`

The authentication tests use fake transports and generate no network
requests, paid model calls or cloud writes.
