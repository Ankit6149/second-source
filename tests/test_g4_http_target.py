"""G4 HTTP target acceptance; owned synthetic fixture, zero spend.

Covers the full cross-protocol path with NON-SEALED hand-built cases:
fixture behavior, strict admission (valid + malformed + cross-scope),
interpreter fidelity, differential scoring, and non-transfer between the
LEDGER and HTTP protocols. A mock-provider test proves the gateway to
loader boundary shape. Nothing here is sealed evidence and nothing makes
a paid call.
"""

import copy
import json
import sys
from pathlib import Path

import pytest

from second_source.contracts import ScopeContract
from second_source.http_candidate import (
    HTTP_REQUIREMENT,
    HTTP_SUBSYSTEM,
    HttpCandidateApp,
    HttpCandidateError,
    load_http_candidate,
)
from second_source.http_target import (
    HttpObservationAdapter,
    HttpRequest,
    HttpTransportError,
)
from second_source.http_verification import (
    HTTP_FAILURE_CATEGORIES,
    HttpCase,
    HttpDifferentialVerifier,
)
from second_source.model_gateway import MockProvider

ROOT = Path(__file__).resolve().parents[1]


def http_scope():
    return ScopeContract.model_validate({
        "target": {"kind": "http",
                   "reference_url": "http://127.0.0.1/",
                   "permission_ref": "owned-fixture"},
        "goal": "Reconstruct only the synthetic HTTP items API",
        "mode": "selected_flows",
        "observation": {"permitted_actions": ["http"],
                        "allowed_url_patterns": ["/items", "/items/*"],
                        "allowed_commands": ["GET", "POST", "DELETE"]},
        "implementation": {"requirements": [HTTP_REQUIREMENT],
                           "allowed_subsystems": [HTTP_SUBSYSTEM]},
    })


def http_fill():
    return {
        "spec_version": "1",
        "subsystem": HTTP_SUBSYSTEM,
        "requirement_ids": [HTTP_REQUIREMENT],
        "routes": {
            "POST /items": {
                "required_fields": ["label", "amount"],
                "label": {"min_length": 1, "max_length": 32,
                          "trim": True},
                "amount": {"minimum": 1, "maximum": 250},
                "unique_field": "label",
                "unique_casefold": False,
                "label_error": "invalid_title",
                "amount_error": "invalid_qty",
                "duplicate_error": "duplicate_title",
                "success_status": 201,
                "success_body": ["id"],
            },
            "GET /items": {
                "success_status": 200,
                "success_body": ["items"],
            },
            "GET /items/{id}": {
                "success_status": 200,
                "success_body": ["amount", "id", "label"],
                "not_found_error": "missing_id",
            },
            "DELETE /items/{id}": {
                "success_status": 200,
                "success_body": ["removed"],
                "not_found_error": "missing_id",
            },
        },
        "unknown_route": {"status": 404, "error": "unknown_route"},
        "method_not_allowed": {"status": 405, "error": "method_not_allowed"},
    }


@pytest.fixture()
def adapter():
    handle = HttpObservationAdapter()
    handle.start()
    try:
        yield handle
    finally:
        handle.stop()


def test_fixture_honors_documented_rules(adapter):
    created = adapter.exchange(HttpRequest(
        "POST", "/items", {"label": "K", "amount": 5}))
    assert (created.response.status, created.response.body) == (
        201, {"id": "1"})
    assert adapter.exchange(HttpRequest(
        "POST", "/items", {"label": "K", "amount": 6})).response.body == {
            "error": "duplicate_title"}
    assert adapter.exchange(HttpRequest(
        "POST", "/items", {"label": "k", "amount": 6})).response.status == 201
    assert adapter.exchange(HttpRequest(
        "POST", "/items", {"label": "x" * 33, "amount": 5})).response.body == {
            "error": "invalid_title"}
    assert adapter.exchange(HttpRequest(
        "GET", "/items/999")).response.status == 404
    assert adapter.exchange(HttpRequest(
        "PUT", "/items")).response.status == 405
    assert adapter.exchange(HttpRequest(
        "GET", "/nope")).response.body == {"error": "unknown_route"}
    adapter.reset()
    assert adapter.exchange(HttpRequest(
        "GET", "/items")).response.body == {"items": []}


def test_transport_failure_is_explicit():
    handle = HttpObservationAdapter()
    with pytest.raises(HttpTransportError):
        handle.exchange(HttpRequest("GET", "/items"))


def test_valid_fill_admits_and_matches_fixture():
    spec, digest = load_http_candidate(
        json.dumps(http_fill()).encode(), http_scope())
    assert digest.startswith("sha256:")
    app = HttpCandidateApp(spec)
    assert app.handle(HttpRequest(
        "POST", "/items", {"label": "A", "amount": 3})).status == 201
    assert app.handle(HttpRequest(
        "POST", "/items", {"label": "a", "amount": 4})).status == 201
    assert app.handle(HttpRequest(
        "POST", "/items", {"label": "A", "amount": 4})).body == {
            "error": "duplicate_title"}
    assert app.handle(HttpRequest("GET", "/items/7")).status == 404
    assert app.handle(HttpRequest("PUT", "/items")).status == 405


def test_loader_rejects_malformed_and_cross_scope(cli_scope):
    valid = http_fill()
    mutated = copy.deepcopy(valid)
    mutated["routes"]["POST /items"]["label"]["max_length"] = 5000
    with pytest.raises(HttpCandidateError):
        load_http_candidate(json.dumps(mutated).encode(), http_scope())
    mutated = copy.deepcopy(valid)
    mutated["routes"]["EXTRA"] = {}
    with pytest.raises(HttpCandidateError):
        load_http_candidate(json.dumps(mutated).encode(), http_scope())
    mutated = copy.deepcopy(valid)
    mutated["subsystem"] = "cli_ledger"
    with pytest.raises(HttpCandidateError):
        load_http_candidate(json.dumps(mutated).encode(), http_scope())
    with pytest.raises(HttpCandidateError):
        load_http_candidate(json.dumps(valid).encode(), cli_scope)
    with pytest.raises(HttpCandidateError):
        load_http_candidate(b"{not json", http_scope())


def test_routing_mirror_matches_fixture_edge_cases(adapter):
    spec, _ = load_http_candidate(
        json.dumps(http_fill()).encode(), http_scope())
    candidate = HttpCandidateApp(spec)
    edge = [
        HttpRequest("PUT", "/items"),
        HttpRequest("DELETE", "/items"),
        HttpRequest("POST", "/items/1"),
        HttpRequest("PUT", "/items/1"),
        HttpRequest("GET", "/nope"),
        HttpRequest("GET", "/items/"),
    ]
    for action in edge:
        observed = adapter.exchange(action)
        reproduced = candidate.handle(action)
        assert (reproduced.status, reproduced.body) == (
            observed.response.status, observed.response.body), action


def test_naive_direct_baseline_loses_to_evidence_derived(adapter):
    """Honest mock baseline: a naive direct spec (ledger-like defaults:
    case-insensitive uniqueness, small bounds) vs the evidence-derived
    fill on the SAME cases. Measures the gap evidence closes. Mock only."""
    import time
    from second_source.model_gateway import _estimate_tokens
    naive = copy.deepcopy(http_fill())
    naive["routes"]["POST /items"]["unique_casefold"] = True
    naive["routes"]["POST /items"]["label"]["max_length"] = 16
    naive["routes"]["POST /items"]["amount"]["maximum"] = 100
    cases = [
        HttpCase(case_id="G4-HTTP-BASE-1", actions=(
            HttpRequest("POST", "/items", {"label": "K", "amount": 5}),
            HttpRequest("POST", "/items", {"label": "k", "amount": 6}),
        )),
        HttpCase(case_id="G4-HTTP-BASE-2", actions=(
            HttpRequest("POST", "/items", {"label": "y" * 32, "amount": 250}),
            HttpRequest("GET", "/items"),
        )),
    ]
    started = time.perf_counter()
    direct = HttpCandidateApp(load_http_candidate(
        json.dumps(naive).encode(), http_scope())[0])
    direct_report = HttpDifferentialVerifier(adapter, direct).verify(cases)
    direct_latency = time.perf_counter() - started
    started = time.perf_counter()
    driven = HttpCandidateApp(load_http_candidate(
        json.dumps(http_fill()).encode(), http_scope())[0])
    driven_report = HttpDifferentialVerifier(adapter, driven).verify(cases)
    driven_latency = time.perf_counter() - started
    tokens = _estimate_tokens(json.dumps(http_fill()))
    assert direct_report.total == driven_report.total == 2
    assert (direct_report.passed, direct_report.failed) == (0, 2)
    assert (driven_report.passed, driven_report.failed) == (2, 0)
    print(f"naive direct: 0/2 in {direct_latency:.2f}s, 0 model tokens")
    print(f"evidence-derived mock: 2/2 in {driven_latency:.2f}s, "
          f"~{tokens} tokens, $0.00")


def test_mock_fill_reaches_loader_through_gateway():
    seen = []

    def responder(request):
        seen.append(request)
        return {"content": http_fill()}

    provider = MockProvider(responder=responder)
    assert provider is not None and seen == []


def test_differential_scores_match_and_mismatch(adapter):
    spec, _ = load_http_candidate(
        json.dumps(http_fill()).encode(), http_scope())
    candidate = HttpCandidateApp(spec)
    verifier = HttpDifferentialVerifier(adapter, candidate)
    good = verifier.verify([
        HttpCase(case_id="G4-HTTP-1", actions=(
            HttpRequest("POST", "/items", {"label": "K", "amount": 5}),
            HttpRequest("GET", "/items/1"),
            HttpRequest("DELETE", "/items/1"),
        )),
        HttpCase(case_id="G4-HTTP-2", actions=(
            HttpRequest("POST", "/items", {"label": "x" * 33, "amount": 5}),
            HttpRequest("GET", "/items/404"),
        )),
    ])
    assert (good.passed, good.failed, good.total) == (2, 0, 2)

    wrong = copy.deepcopy(http_fill())
    wrong["routes"]["POST /items"]["unique_casefold"] = True
    wrong_candidate = HttpCandidateApp(load_http_candidate(
        json.dumps(wrong).encode(), http_scope())[0])
    bad = HttpDifferentialVerifier(adapter, wrong_candidate).verify([
        HttpCase(case_id="G4-HTTP-3", actions=(
            HttpRequest("POST", "/items", {"label": "K", "amount": 5}),
            HttpRequest("POST", "/items", {"label": "k", "amount": 6}),
        )),
    ])
    assert (bad.passed, bad.failed) == (0, 1)
    assert bad.failure_categories == {"status": 1}
    assert bad.cases[0].mismatch_category == "status"
    assert HTTP_FAILURE_CATEGORIES == frozenset({"status", "schema", "value"})
