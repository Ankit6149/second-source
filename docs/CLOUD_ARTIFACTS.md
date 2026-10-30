# Private cloud artifacts

`backend.cloud_artifacts` implements a dependency-injected adapter for the existing
`second-source-private` bucket on `jpqcqqbzriizxhigvjki`. Construction performs no
network access or credential lookup. Current acceptance uses synthetic bytes,
local service rows and fake HTTP only. Live connectivity, bucket policy, cloud
durability and deployment remain unverified. This work creates no bucket or policy.

Bind the adapter to a verified principal on the server:

```python
storage = SupabaseArtifactStore(transport, authorize_run=service.get_run)
owned = storage.for_owner(principal)
reference = owned.publish_report(run_id, existing_engine_report)
raw = owned.read(run_id, reference)
bundle = owned.export_bundle(investigation, run, events)
```

The existing `ArtifactReference`, `sanitized_report`, `ArtifactStore.export_bundle`
and `verify_bundle` contracts are reused. The public report path currently accepts
only the existing zero-cost mock origin. Genuine model reports require the
separately reviewed engine contract; this adapter cannot relabel them as mock.
Every operation calls the injected owner/run authorization check before transport.
API integration must bind the authenticated principal per request. It must never
accept an owner ID supplied in an HTTP body as identity.

Object keys contain domain-separated owner and run hashes, an explicit report or
private classification and an allowlisted filename. They contain no plaintext
owner/run identifiers, input paths or model content. Hashes are namespace bindings,
not authorization or encryption. Supabase project/bucket are fixed, and no listing,
delete, public URL or signed URL API is implemented.

Uploads use immutable `POST` with `x-upsert: false`. Success and duplicate conflict
both require authenticated read-back with exact size, SHA-256 and byte equality.
HTTP 409 and recognized duplicate 400 responses allow idempotent same-byte
publication; different bytes fail closed. There are at most two HTTP operations
per publish and no automatic transport retry. An outage after dispatch can leave
an uploaded object with an unknown client outcome; a deliberate repeated publish
can verify identical bytes without replacing them.

The adapter caps each artifact at 2,000,000 bytes, upload acknowledgements at
16,384 bytes, and each request timeout at a configured 0.1–30 seconds. The explicit
`SupabaseHTTPTransport(access_token=..., api_key=...)` uses fixed-host HTTPS,
normal certificate verification, bounded reads and no redirects. It injects
credentials only in server-side headers. Transport errors, headers and response
bodies are excluded from diagnostic messages. Service keys bypass Storage RLS;
server owner/run checks remain mandatory, and keys must never reach browser code.
No credentials were accessed or created for this implementation.

Trusted worker code can use `storage.for_worker(principal).retain_private(...)`
with raw bytes and an externally supplied SHA-256. Only these filenames from the
existing immutable engine contract are accepted:

- `candidate.v1.json`
- `broker-artifact.v1.json`
- `generation-dispatch.v1.private.json`
- `generation-result.v1.private.json`
- `G3_report.json`
- `G3_input_provenance.json`

Private references use the existing artifact reference type with a `private:`
classification. Public `read` rejects them. Owner-bound public stores expose no
private read/retention methods. This allowlist classifies bytes supplied by trusted
worker code; it does not independently establish model provenance. No arbitrary
filesystem reader is provided. Sealed suites, credentials, environment files,
logs and unknown filenames are rejected. Original sensitive bytes never enter
sanitized reports or the existing proof ZIP. Private retention is not proof that
the trusted worker has been connected to this adapter.

The implementation follows [standard uploads](https://supabase.com/docs/guides/storage/uploads/standard-uploads),
[private downloads](https://supabase.com/docs/guides/storage/serving/downloads),
and [Storage access control](https://supabase.com/docs/guides/storage/security/access-control).
The documentation describes duplicate 400 responses; legacy duplicate 409 is
also handled by exact read-back. The [October 12 TLS notice](https://supabase.com/changelog/cbc-tls-ciphers-deprecated)
announces removal of obsolete CBC TLS 1.2 suites starting November 10; this adapter
uses the platform's current default TLS context. These references were checked on
October 30, 2026; they are protocol guidance, not evidence of live project access.

Run hermetic acceptance with `python -m pytest tests/test_backend_cloud_artifacts.py`.
