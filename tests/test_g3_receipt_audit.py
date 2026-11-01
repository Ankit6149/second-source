"""The offline receipt audit rejects altered bindings and never emits content."""
import hashlib
import json
from pathlib import Path
import runpy

audit = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/audit_g3_receipt.py"))["audit"]
encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
digest = lambda raw: hashlib.sha256(raw).hexdigest()


def test_genuine_receipt_audit_checks_bindings_and_redacts_content(tmp_path):
    candidate = b'{"synthetic":true}'
    candidate_hash, suite, request = digest(candidate), "b" * 64, "c" * 64
    parsed = {"content": "PRIVATE_TEST_SENTINEL"}
    content = encode(parsed).decode()
    common = {"response_id": "synthetic", "model": "muse-spark-1.3", "provider": "meta-direct", "real": True,
              "input_tokens": 1, "output_tokens": 2, "estimated_cost_usd": 0, "uncertain_cost_usd": 0}
    origin = {**common, "origin": "real", "candidate_digest": "sha256:" + candidate_hash,
              "request_digest": "sha256:" + request, "model_output_digest": "sha256:" + digest(encode(parsed))}
    payload = {"kind": "CANDIDATE_ORIGIN", "spec": candidate.decode(), "receipt": origin}
    payload_raw = encode(payload)
    evaluation = {"passed": 1, "failed": 0, "indeterminate": 0, "total": 1, "failure_categories": {}}
    embedded = {"candidate_digest": "sha256:" + candidate_hash, "suite_digest": "sha256:" + suite,
                "artifact_digest": "sha256:" + digest(payload_raw), "origin_receipt_digest": "sha256:" + digest(encode(origin)),
                "origin": origin, "evaluation": evaluation, "g3_accepted": False}
    records = {
        "broker-artifact.v1.json": {"payload": payload_raw.decode(), "spec_digest": "sha256:" + candidate_hash},
        "generation-dispatch.v1.private.json": {"event": "model_dispatch", "run_id": "synthetic", "real": True,
                                                 "provider": "meta-direct", "model": "muse-spark-1.3", "request_sha256": request},
        "generation-result.v1.private.json": {"event": "model_result", "run_id": "synthetic",
          "receipt": {**common, "content_sha256": digest(content.encode())}, "response": {**common, "content_text": content, "parsed": parsed}},
        "G3_report.json": {"run_id": "synthetic", "response_id": "synthetic", "real": True, "origin": "real", "provider": "meta-direct",
          "model": "muse-spark-1.3", "spec_digest": "sha256:" + candidate_hash, "suite_digest": "sha256:" + suite,
          "stop_reason": "completed_real_run", "evaluation": evaluation, "evaluation_receipt": embedded},
    }
    (tmp_path / "candidate.v1.json").write_bytes(candidate)
    for name, value in records.items():
        (tmp_path / name).write_bytes(encode(value))
    result = audit(tmp_path, candidate=candidate_hash, suite=suite, request=request)
    assert result["valid"] and not result["provider_attested"] and not result["broker_signature_reverified"]
    assert "PRIVATE_TEST_SENTINEL" not in json.dumps(result)
    (tmp_path / "candidate.v1.json").write_bytes(b'{"synthetic":false}')
    assert not audit(tmp_path, candidate=candidate_hash, suite=suite, request=request)["valid"]

