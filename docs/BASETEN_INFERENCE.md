# Baseten Muse Spark Open — opt-in infrastructure adapter

**Status (30 October 2026):** Proposed code adapter only; **no key, live call, credit-balance check, real candidate, or runtime deployment is asserted.** Do not interpret the availability of Baseten hackathon credits as permission to spend them.

## Verified service contract

Meta's [hosted Baseten cookbook](https://github.com/meta-models/meta-oss-cookbook/blob/main/muse-spark/hosted/baseten.md) and [Baseten's Muse Spark Open catalog](https://www.baseten.co/library/muse-spark-open/) identify:

- Hosted provider: `baseten-muse-open` (Second Source receipt identity).
- Hosted Meta open-weight model: `meta-models/muse-spark-open`.
- Fixed HTTPS inference endpoint: `https://inference.baseten.co/v1/chat/completions`.
- Server-only bearer key: `BASETEN_API_KEY`, obtained from the Baseten dashboard. Never put it in git, model context, browser environment or client-side bundle.
- Published Standard prices checked on October 30: **$1.25 input / $4.25 output per 1M tokens** (subject to change). Credit entitlement/balance must be inspected privately, not inferred.
- Model **is not** the Meta-hosted `muse-spark-1.3` API and must never be recorded as `meta-direct`.

## Contract, zero-call integration

`BasetenMuseOpenProvider` implements the existing `ModelGateway` provider interface by subclassing `MetaProvider` so the **same** real-provider reservation/usage/uncertain spend/receipt rules apply. It is not auto-selected by the production API or G3 operator; existing `meta-direct` behavior is unchanged.

No network request happens on import or construction. A real call is sent **only** when the caller explicitly constructs a gateway with a positive per-run model-spend budget and actually invokes `gateway.generate` under a separately approved input/attempt policy. Illustrative wiring (**DO NOT EXECUTE until separately authorized**):

```python
import os
from second_source.baseten_provider import BasetenMuseOpenProvider
from second_source.model_gateway import ModelGateway
from second_source.budgets import RunBudget
from second_source.contracts import Budgets

# This creates NO billable request. Configure the actual key privately.
provider = BasetenMuseOpenProvider(os.environ["BASETEN_API_KEY"])
gateway = ModelGateway(
    provider, RunBudget(Budgets(max_estimated_model_spend_usd=0.02))
)
# No call here; a real dispatch requires the existing separate G3 approval
# mechanism and explicit user authorization. Do not call gateway.generate.
```

Budget is a **reservation estimate**, not a billing ceiling enforced by Baseten. A failed or ambiguous transport must remain uncertain; there are no hidden retries. The provider sends `model`, `messages`, `max_tokens`; the gateway inserts the public JSON schema into a system message and locally validates the response, without assuming the hosted API supports Meta-specific non-strict JSON-schema decoding. A schema refusal is not silently retried.

The model has no tool authority, run access or source-code privileges. Existing reference/gold separation, scope guard, sealed-suite integrity, reset policy and independent evaluator stay mandatory.

## Evidence and release gate

Run **key-free** tests:

```sh
python -m pytest tests/test_baseten_provider.py tests/test_g2_gateway.py -q
```

Before calling the hosted model in a genuine G3 experiment:
1. Review and approve an **exact** provider-specific model/endpoint/request digest, operator checkout, sealed suite identity, one-attempt count and maximum **application** spend, distinct from the consumed Meta direct allowances. No automatic fallback or interchangeable approvals.
2. Confirm credit availability, billing fallback/overage behavior, actual account rates and limits using Baseten's authenticated dashboard **without exposing keys**.
3. Independently review provider accounting and admissible schema on a hermetic suite; verify transport/response compatibility in a **separately approved minimal real probe**, if justified.
4. Wire provider selection through the existing `g3_verification` / guided-synthesis broker and preserve `provider` in the existing approvals, receipts, result and immutable witnesses. **Not implemented by this adapter.**
5. Preserve the original Meta direct G2/G3 archives and the sealed 25-case suite. Do not transfer a Meta approval to Baseten or report mock scores as real reconstruction.

No database migration, cloud deployment, credentials or paid inference was performed as part of this change.
