"""Check local genuine-G3 record bindings without printing private model content.

No provider calls, credentials, sealed-case output, or broker-key access. Local
hash consistency and a replay are not a provider-signed attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

MAX_FILE_BYTES = 2_000_000


def _read(root: Path, name: str) -> bytes:
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe audit input")
    with path.open("rb") as source:
        raw = source.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Audit input too large")
    return raw


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def audit(root: Path, *, candidate: str, suite: str, request: str) -> dict:
    for value in (candidate, suite, request):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Expected hashes must be lowercase SHA-256")
    candidate_raw = _read(root, "candidate.v1.json")
    broker = json.loads(_read(root, "broker-artifact.v1.json"))
    dispatch = json.loads(_read(root, "generation-dispatch.v1.private.json"))
    result = json.loads(_read(root, "generation-result.v1.private.json"))
    report = json.loads(_read(root, "G3_report.json"))
    payload_raw = broker["payload"].encode("utf-8")
    payload = json.loads(payload_raw)
    origin, receipt, response, evaluation = payload["receipt"], result["receipt"], result["response"], report["evaluation_receipt"]
    def bare(value):
        return str(value).removeprefix("sha256:")
    common = ("response_id", "model", "provider", "real", "input_tokens", "output_tokens", "estimated_cost_usd", "uncertain_cost_usd")
    checks = {
        "candidate_identity": _digest(candidate_raw) == candidate == bare(report["spec_digest"]) == bare(broker["spec_digest"]) == bare(origin["candidate_digest"]) == bare(evaluation["candidate_digest"]),
        "candidate_payload": payload["spec"].encode("utf-8") == candidate_raw,
        "suite_identity": bare(report["suite_digest"]) == bare(evaluation["suite_digest"]) == suite,
        "request_identity": bare(dispatch["request_sha256"]) == bare(origin["request_digest"]) == request,
        "raw_response_hash": _digest(response["content_text"].encode("utf-8")) == bare(receipt["content_sha256"]),
        "raw_response_parses_to_record": json.loads(response["content_text"]) == response["parsed"],
        "parsed_response_hash": _digest(_encode(response["parsed"])) == bare(origin["model_output_digest"]),
        "broker_payload_hash": _digest(payload_raw) == bare(evaluation["artifact_digest"]),
        "origin_receipt_hash": _digest(_encode(origin)) == bare(evaluation["origin_receipt_digest"]),
        "origin_receipt_content": origin == evaluation["origin"],
        "receipt_fields": all(k in origin and k in receipt and k in response and origin[k] == receipt[k] == response[k] for k in common) and bool(origin["response_id"]) and report["response_id"] == origin["response_id"],
        "run_identity": dispatch["run_id"] == result["run_id"] == report["run_id"],
        "provider_label": report["provider"] == dispatch["provider"] == origin["provider"] == "meta-direct" and report["model"] == dispatch["model"] == origin["model"] == "muse-spark-1.3",
        "real_labels": report["real"] is True and dispatch["real"] is True and origin["real"] is True and report["origin"] == origin["origin"] == "real",
        "record_types": dispatch["event"] == "model_dispatch" and result["event"] == "model_result" and payload["kind"] == "CANDIDATE_ORIGIN" and report["stop_reason"] == "completed_real_run",
        "evaluation_consistency": report["evaluation"] == evaluation["evaluation"] and evaluation["g3_accepted"] is False,
    }
    return {"valid": all(checks.values()), "checks": checks, "candidate_sha256": candidate,
            "suite_sha256": suite, "request_sha256": request, "evaluation": report["evaluation"],
            "usage": {key: receipt[key] for key in ("input_tokens", "output_tokens", "estimated_cost_usd", "uncertain_cost_usd")},
            "provider_attested": False, "broker_signature_reverified": False,
            "limitations": "Local consistency only; provider signature and ephemeral broker HMAC were not verified."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--suite-sha256", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    try:
        result = audit(args.run_directory, candidate=args.candidate_sha256, suite=args.suite_sha256, request=args.request_sha256)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        print(json.dumps({"valid": False, "error": "Missing or invalid local audit input."}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
