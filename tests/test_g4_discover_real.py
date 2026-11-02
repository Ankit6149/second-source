"""Genuine G4 HTTP discovery mode: fail-closed gates + hermetic fake-provider run.

No network, no real credentials: the MetaProvider class is replaced with a
fake that delegates to the deterministic mock planner responder, so the
discovery loop, persistence, and preflight binding are exercised exactly as
the genuine path runs them. The fake is labeled in test code only; production
code constructs the real MetaProvider.
"""
import json
from pathlib import Path

import pytest

from second_source import g4_http_reconstruct as g4
from second_source.hypotheses import validate_batch
from second_source.model_gateway import MetaProvider, MockProvider


class FakeMetaProvider(MetaProvider):
    """Hermetic MetaProvider stand-in (test-only, never shipped as real)."""

    def __init__(self, api_key: str) -> None:
        self._mock = MockProvider(responder=g4._build_mock_planner_responder())
        self._model = "muse-spark-1.3"
        self._rates = (1.25, 4.25)

    def complete(self, request):
        response = self._mock.complete(request)
        return response.model_copy(
            update={
                "provider": "meta-direct",
                "real": True,
                "model": "muse-spark-1.3",
                "response_id": "fake-meta-" + request.stage,
            }
        )


def _args(run_dir: Path, *extra: str) -> list[str]:
    return [
        "--mode", "discover-real",
        "--max-usd", "0.50",
        "--run-dir", str(run_dir),
        *extra,
    ]


def test_discover_real_blocked_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("SECOND_SOURCE_MAX_RUN_USD", raising=False)
    run_dir = tmp_path / "blocked-no-creds"
    assert g4.main(_args(run_dir, "--confirm-real-run")) == 2
    assert not run_dir.exists()


def test_discover_real_blocked_without_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.50")
    run_dir = tmp_path / "blocked-no-confirm"
    assert g4.main(_args(run_dir)) == 2
    assert not run_dir.exists()


def test_discover_real_blocked_over_hard_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.50")
    run_dir = tmp_path / "blocked-over-cap"
    args = _args(run_dir, "--confirm-real-run")
    args[args.index("0.50")] = "0.51"
    assert g4.main(args) == 2
    assert not run_dir.exists()


def test_discover_real_blocked_when_env_cap_lower(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.10")
    run_dir = tmp_path / "blocked-env-cap"
    assert g4.main(_args(run_dir, "--confirm-real-run")) == 2
    assert not run_dir.exists()


def test_fake_discovery_persists_inputs_that_preflight_accepts(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MODEL_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.50")
    monkeypatch.setattr(g4, "MetaProvider", FakeMetaProvider)

    run_dir = tmp_path / "discover"
    assert g4.main(_args(run_dir, "--confirm-real-run")) == 0

    summary = json.loads(
        (run_dir / "G4_discovery_summary.json").read_text(encoding="utf-8")
    )
    assert summary["origin"] == "real"
    assert summary["real"] is True
    assert summary["stop_reason"] == "discovery_complete"
    assert summary["model_receipts"], "genuine path must record call receipts"
    digests = summary["observation_digests"]
    assert len(digests) >= 15

    batch = json.loads(
        (run_dir / "hypotheses.original.json").read_text(encoding="utf-8")
    )
    validate_batch(batch, frozenset(digests))

    # The persisted inputs must bind through the existing zero-call preflight.
    preflight_dir = tmp_path / "preflight"
    seal_dir = tmp_path / "seal"
    rc = g4.main(
        [
            "--mode", "preflight",
            "--max-usd", "0.50",
            "--ledger-dir", str(run_dir / "evidence"),
            "--hypotheses-file", str(run_dir / "hypotheses.original.json"),
            "--observation-digests", ",".join(digests),
            "--seal-dir", str(seal_dir),
            "--run-dir", str(preflight_dir),
        ]
    )
    assert rc == 0
    receipt = json.loads(
        (preflight_dir / "G4_preflight.json").read_text(encoding="utf-8")
    )
    assert receipt["provider_calls"] == 0
    assert receipt["stop_reason"] == "preflight_ready"
    assert receipt["approved_context_digest"].startswith("sha256:")
