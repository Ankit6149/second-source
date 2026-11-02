"""Versioned HTTP candidate specification, strict loader, and interpreter.

A purely declarative JSON document describing one resource API surface.
Validation slots mirror the ledger DSL philosophy: the MODEL chooses
target-specific error-code strings, the RUNTIME fixes their meaning —
no guessing, no hidden mapping:

- POST /items: label/amount bounds, uniqueness folding, label_error,
  amount_error, duplicate_error slots, success status/body keys
- GET /items, GET /items/{id}, DELETE /items/{id}: success shapes and a
  not_found_error slot where lookups can fail
- unknown_route / method_not_allowed fallback blocks

No code, imports, shell, eval, subprocess, file paths, or network access —
the trusted interpreter below implements the fixed operation set.

Scope pins at load time: subsystem ``http_items`` with requirement
``REQ-HTTP-ITEMS`` (separate from the ledger scope; one candidate cannot
span subsystems). Unknown routes, methods, keys, or operations fail closed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse

from .candidate_spec import ERROR_CODE_RE
from .contracts import ScopeContract
from .http_target import HttpRequest, HttpResponse

HTTP_SPEC_VERSION = "1"
HTTP_SUBSYSTEM = "http_items"
HTTP_REQUIREMENT = "REQ-HTTP-ITEMS"
HTTP_ROUTES = ("POST /items", "GET /items", "GET /items/{id}",
               "DELETE /items/{id}")


class HttpCandidateError(ValueError):
    """A generated HTTP spec violates the trusted contract."""


def http_spec_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _code(value: Any, what: str) -> str:
    if type(value) is not str or not ERROR_CODE_RE.match(value):
        raise HttpCandidateError(f"bad error code for {what}")
    return value


def _status(value: Any, what: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise HttpCandidateError(f"bad status for {what}")
    return value


def _body_keys(value: Any, what: str) -> list:
    if (not isinstance(value, list) or not value
            or any(type(k) is not str or not k for k in value)):
        raise HttpCandidateError(f"bad body keys for {what}")
    return list(value)


def load_http_candidate(raw: bytes, scope: ScopeContract) -> tuple[dict, str]:
    """Validate a model-generated HTTP spec; return (spec, digest).

    Raises HttpCandidateError on any schema, semantic, or scope violation.
    """
    if len(raw) > 65536:
        raise HttpCandidateError("spec too large")
    try:
        spec = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HttpCandidateError("spec is not valid JSON") from exc
    if not isinstance(spec, dict):
        raise HttpCandidateError("spec must be an object")
    if spec.get("spec_version") != HTTP_SPEC_VERSION:
        raise HttpCandidateError("unsupported spec_version")
    if spec.get("subsystem") != HTTP_SUBSYSTEM:
        raise HttpCandidateError("subsystem must be http_items")
    requirements = spec.get("requirement_ids")
    if (not isinstance(requirements, list) or HTTP_REQUIREMENT not in requirements
            or not set(requirements) <= set(scope.implementation.requirements)):
        raise HttpCandidateError("requirement ids out of scope")
    if HTTP_SUBSYSTEM not in set(scope.implementation.allowed_subsystems):
        raise HttpCandidateError("subsystem out of scope")
    routes = spec.get("routes")
    if not isinstance(routes, dict) or set(routes) != set(HTTP_ROUTES):
        raise HttpCandidateError("routes must be exactly the public surface")
    _validate_post(routes["POST /items"])
    _validate_lookup(routes["GET /items/{id}"], "GET /items/{id}")
    _validate_lookup(routes["DELETE /items/{id}"], "DELETE /items/{id}")
    listing = routes["GET /items"]
    if not isinstance(listing, dict) or set(listing) != {
            "success_status", "success_body"}:
        raise HttpCandidateError("GET /items has unknown keys")
    _status(listing.get("success_status"), "GET /items.status", 200, 299)
    _body_keys(listing.get("success_body"), "GET /items.body")
    for key in ("unknown_route", "method_not_allowed"):
        block = spec.get(key)
        if (not isinstance(block, dict) or set(block) != {"status", "error"}
                or _status(block.get("status"), key, 400, 599) is None
                or _code(block.get("error"), key) is None):
            raise HttpCandidateError(f"bad {key}")
    if set(spec) - {"spec_version", "subsystem", "requirement_ids",
                     "routes", "unknown_route", "method_not_allowed"}:
        raise HttpCandidateError("unknown top-level keys")
    return spec, http_spec_digest(raw)


def _validate_post(route: Any) -> None:
    if not isinstance(route, dict) or set(route) != {
            "required_fields", "label", "amount", "unique_field",
            "unique_casefold", "label_error", "amount_error",
            "duplicate_error", "success_status", "success_body"}:
        raise HttpCandidateError("POST /items has unknown keys")
    if route.get("required_fields") != ["label", "amount"]:
        raise HttpCandidateError("POST required_fields are fixed")
    label, amount = route.get("label"), route.get("amount")
    if not isinstance(label, dict) or not isinstance(amount, dict):
        raise HttpCandidateError("POST needs label/amount bounds")
    for bound, low, text in (
            (label.get("min_length"), 1, "label.min_length"),
            (label.get("max_length"), 1, "label.max_length"),
            (amount.get("minimum"), 0, "amount.minimum"),
            (amount.get("maximum"), 0, "amount.maximum")):
        if type(bound) is not int or bound < low:
            raise HttpCandidateError(f"bad {text}")
    if label["max_length"] > 1024 or amount["maximum"] > 10 ** 9:
        raise HttpCandidateError("POST bounds exceed resource ceilings")
    if type(label.get("trim")) is not bool:
        raise HttpCandidateError("label.trim must be boolean")
    if route.get("unique_field") != "label":
        raise HttpCandidateError("unique_field is fixed to label")
    if type(route.get("unique_casefold")) is not bool:
        raise HttpCandidateError("unique_casefold must be boolean")
    _code(route.get("label_error"), "label_error")
    _code(route.get("amount_error"), "amount_error")
    _code(route.get("duplicate_error"), "duplicate_error")
    _status(route.get("success_status"), "POST.status", 200, 299)
    _body_keys(route.get("success_body"), "POST.body")


def _validate_lookup(route: Any, key: str) -> None:
    if not isinstance(route, dict) or set(route) != {
            "success_status", "success_body", "not_found_error"}:
        raise HttpCandidateError(f"{key} has unknown keys")
    _status(route.get("success_status"), key + ".status", 200, 299)
    _body_keys(route.get("success_body"), key + ".body")
    _code(route.get("not_found_error"), "not_found_error")


class HttpCandidateApp:
    """Trusted in-process interpreter for an admitted HTTP spec."""

    def __init__(self, spec: dict) -> None:
        self._spec = spec
        self._items: dict[str, dict] = {}
        self._next_id = 1

    def reset(self) -> None:
        self._items = {}
        self._next_id = 1

    def handle(self, request: HttpRequest) -> HttpResponse:
        # Routing mirrors the owned fixture exactly: exact surface keys
        # dispatch; any other method on a shaped path (/items or an
        # /items/{id} shape) is 405; shapeless paths are 404.
        path = urlparse(request.path).path.rstrip("/") or "/"
        key = f"{request.method} {path}"
        routes = self._spec["routes"]
        if key in routes:
            return self._dispatch(key, routes[key], request)
        matched_shape = path == "/items"
        for route_key, route in routes.items():
            route_method, _, route_path = route_key.partition(" ")
            if ("{" in route_path
                    and self._shapes_match(route_path, path)):
                matched_shape = True
                if route_method == request.method:
                    return self._dispatch(route_key, route, request)
        if matched_shape:
            return self._fallback("method_not_allowed")
        return self._fallback("unknown_route")

    @staticmethod
    def _shapes_match(template: str, concrete: str) -> bool:
        t_parts = template.split("/")
        c_parts = concrete.split("/")
        if len(t_parts) != len(c_parts):
            return False
        return all(tp.startswith("{") and tp.endswith("}") or tp == cp
                   for tp, cp in zip(t_parts, c_parts))

    def _fallback(self, key: str) -> HttpResponse:
        block = self._spec[key]
        return HttpResponse(status=block["status"],
                            body={"error": block["error"]})

    def _dispatch(self, key: str, route: dict,
                  request: HttpRequest) -> HttpResponse:
        if key == "POST /items":
            return self._create(route, request)
        if key == "GET /items":
            return HttpResponse(status=route["success_status"],
                                body={"items": list(self._items.values())})
        item_id = (urlparse(request.path).path.rstrip("/") or "/").rsplit("/", 1)[-1]
        item = self._items.get(item_id)
        if item is None:
            return HttpResponse(status=404,
                                body={"error": route["not_found_error"]})
        if key == "GET /items/{id}":
            return HttpResponse(status=route["success_status"],
                                body={k: item[k]
                                      for k in route["success_body"]})
        del self._items[item_id]
        return HttpResponse(status=route["success_status"],
                            body={"removed": item_id})

    def _create(self, route: dict, request: HttpRequest) -> HttpResponse:
        body = request.body
        if not isinstance(body, dict):
            return HttpResponse(
                status=400, body={"error": route["label_error"]})
        label, amount = body.get("label"), body.get("amount")
        bounds = route["label"]
        if not isinstance(label, str):
            return HttpResponse(
                status=400, body={"error": route["label_error"]})
        text = label.strip() if bounds["trim"] else label
        if (not text or not bounds["min_length"] <= len(text)
                <= bounds["max_length"]):
            return HttpResponse(
                status=400, body={"error": route["label_error"]})
        limits = route["amount"]
        if (type(amount) is not int
                or not limits["minimum"] <= amount <= limits["maximum"]):
            return HttpResponse(
                status=400, body={"error": route["amount_error"]})
        fold = (lambda v: v.casefold()) if route["unique_casefold"] else (lambda v: v)
        if fold(text) in (fold(v["label"]) for v in self._items.values()):
            return HttpResponse(status=409,
                                body={"error": route["duplicate_error"]})
        key = str(self._next_id)
        self._next_id += 1
        self._items[key] = {"id": key, "label": text, "amount": amount}
        return HttpResponse(status=route["success_status"], body={"id": key})
