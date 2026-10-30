"""Opt-in Baseten inference transport for Meta's Muse Spark Open.

This is a hosted Meta *open-weight* model, not Meta's first-party Model API.
The provider plugs into the existing ModelGateway and its budget/receipt
controls. Importing or constructing it never issues a request.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.request

from .budgets import estimate_cost_usd
from .model_gateway import (
    GatewayError, MetaProvider, ModelRequest, ModelResponse,
    ProviderResponseError,
)

BASETEN_ENDPOINT = "https://inference.baseten.co/v1/chat/completions"
BASETEN_MODEL = "meta-models/muse-spark-open"
# Published per 1M tokens; always check live rates before a paid run.
BASETEN_STANDARD_RATES = (1.25, 4.25)
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_REQUEST_BYTES = 256_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class BasetenMuseOpenProvider(MetaProvider):
    """Real provider whose identity remains distinct from meta-direct.

    Subclassing MetaProvider intentionally reuses ModelGateway's existing
    real-provider budgeting. The endpoint/model are fixed: never accept a
    user-supplied URL, another model, or a localhost exception.
    """

    provider_name = "baseten-muse-open"

    def __init__(self, api_key: str, *, timeout_s: float = 60.0,
                 rates: tuple[float, float] = BASETEN_STANDARD_RATES):
        if not isinstance(api_key, str) or not api_key.strip():
            raise GatewayError("Baseten key must be configured server-side")
        if (type(timeout_s) not in (int, float)
                or not math.isfinite(timeout_s) or not 1 <= timeout_s <= 120):
            raise GatewayError("Invalid Baseten timeout")
        if (not isinstance(rates, tuple) or len(rates) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                       for v in rates)):
            raise GatewayError("Explicit positive Baseten pricing is required")
        self._api_key = api_key
        self._timeout_s = float(timeout_s)
        self._rates = tuple(float(v) for v in rates)
        self._model = BASETEN_MODEL

    @property
    def model(self) -> str:
        return self._model

    @property
    def rates(self) -> tuple[float, float]:
        return self._rates

    def complete(self, request: ModelRequest) -> ModelResponse:
        # ModelGateway injects the schema into a system prompt before billing.
        # Do not assume Baseten implements Meta's provider-specific JSON-schema
        # response_format; strictly validate the returned JSON locally.
        payload = {
            "model": BASETEN_MODEL,
            "messages": [dict(message) for message in request.messages],
            "max_tokens": request.max_output_tokens,
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise GatewayError("Baseten request exceeds allowed input size")
        http_request = urllib.request.Request(
            BASETEN_ENDPOINT, data=body,
            headers={"Authorization": "Bearer " + self._api_key,
                     "Content-Type": "application/json",
                     "Accept": "application/json"},
            method="POST",
        )
        # urllib opener validates TLS using the system trust store.
        opener = urllib.request.build_opener(_NoRedirect())
        started = time.monotonic()
        try:
            with opener.open(http_request, timeout=self._timeout_s) as response:
                if response.status != 200 or response.geturl() != BASETEN_ENDPOINT:
                    raise GatewayError("Baseten returned unexpected HTTP response")
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            # No response bodies/reason strings: provider errors can echo secrets.
            raise GatewayError(f"Baseten HTTP error {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise GatewayError("Baseten transport failed or timed out") from None
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise GatewayError("Baseten response exceeded size limit")
        latency_ms = max(0, round((time.monotonic() - started) * 1000))
        try:
            doc = json.loads(raw)
            info = doc["choices"][0]
            content = info["message"]["content"]
            response_id = doc.get("id", "")
            usage = doc["usage"]
            in_tokens = usage["prompt_tokens"]
            out_tokens = usage["completion_tokens"]
            if (not isinstance(response_id, str) or len(response_id) > 128
                    or type(in_tokens) is not int or type(out_tokens) is not int
                    or not 0 <= in_tokens <= 100_000_000
                    or not 0 <= out_tokens <= 100_000_000):
                raise ValueError
            raw_reason = info.get("finish_reason")
            finish_reason = raw_reason if raw_reason in (
                "stop", "length", "content_filter", "tool_calls") else "other"
            if not isinstance(content, str):
                content = ""
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise GatewayError("Baseten response missing valid choice or usage") from None
        details = usage.get("completion_tokens_details") or {}
        reasoning_tokens = details.get("reasoning_tokens", 0)
        if type(reasoning_tokens) is not int or reasoning_tokens < 0:
            reasoning_tokens = 0
        metadata = dict(
            response_id=response_id, finish_reason=finish_reason,
            input_tokens=in_tokens, output_tokens=out_tokens,
            reasoning_tokens=reasoning_tokens, content_chars=len(content),
            content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )
        if not content.strip():
            raise ProviderResponseError(
                "EMPTY_MODEL_RESPONSE", "Baseten returned empty model content", **metadata)
        try:
            parsed = self._validate_parsed(content, request)
        except GatewayError as exc:
            code = "MODEL_JSON_INVALID" if "not JSON" in str(exc) else "MODEL_SCHEMA_INVALID"
            raise ProviderResponseError(code, "Baseten output failed local validation", **metadata) from None
        return ModelResponse(
            provider=self.provider_name, real=True, model=self._model,
            response_id=response_id, content_text=content, parsed=parsed,
            latency_ms=latency_ms, input_tokens=in_tokens, output_tokens=out_tokens,
            estimated_cost_usd=estimate_cost_usd(in_tokens, out_tokens, self._rates),
            prompt_version=request.prompt_version,
        )
