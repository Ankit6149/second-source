"""Trusted fixture subprocess adapter. Takes fixed argv, never LLM-written shell."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from typing import Mapping, Sequence
from uuid import uuid4

from .contracts import Observation, SequenceResult


class CLIReferenceAdapter:
    def __init__(
        self,
        argv: Sequence[str],
        cwd: str | Path,
        *,
        timeout_seconds: float = 5.0,
        max_output_bytes: int = 128_000,
        env: Mapping[str, str] | None = None,
    ):
        if not argv or timeout_seconds <= 0 or max_output_bytes < 512:
            raise ValueError("Invalid fixed reference runtime configuration")
        self._argv = tuple(argv)
        self._cwd = Path(cwd).resolve(strict=True)
        self._timeout = timeout_seconds
        self._max_output = max_output_bytes
        self._env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8", **(env or {})}

    def execute_sequence(self, actions: Sequence[dict], *, sequence_id: str | None = None) -> SequenceResult:
        sequence_id = sequence_id or uuid4().hex
        # A fresh process is the reset boundary. State is retained within one sequence only.
        payload = "".join(json.dumps(a, separators=(",", ":"), ensure_ascii=False) + "\n" for a in actions)
        start = time.monotonic()
        try:
            result = subprocess.run(
                self._argv, input=payload, text=True, encoding="utf-8",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self._cwd,
                env=self._env, timeout=self._timeout, shell=False,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return SequenceResult(sequence_id=sequence_id, observations=(), status="timeout", stderr="Process timed out")
        elapsed_ms = max(0, round((time.monotonic() - start) * 1000))
        if len(result.stdout.encode()) > self._max_output or len(result.stderr.encode()) > self._max_output:
            return SequenceResult(sequence_id=sequence_id, observations=(), status="protocol_error", stderr="Output cap exceeded")
        lines = result.stdout.splitlines()
        if len(lines) != len(actions):
            return SequenceResult(sequence_id=sequence_id, observations=(), status="protocol_error", stderr=f"Expected {len(actions)} response lines, received {len(lines)}")
        out: list[Observation] = []
        try:
            for i, (action, line) in enumerate(zip(actions, lines)):
                obj = json.loads(line)
                if not isinstance(obj, dict) or "ok" not in obj or not isinstance(obj["ok"], bool):
                    raise ValueError("Fixture response must be an object with boolean ok")
                out.append(Observation(
                    observation_id=f"{sequence_id}:{i}", sequence_id=sequence_id,
                    action_index=i, input_action=action, output=obj,
                    exit_code=result.returncode, duration_ms=elapsed_ms,
                    status="ok" if obj["ok"] else "target_error",
                ))
        except (ValueError, TypeError):
            return SequenceResult(sequence_id=sequence_id, observations=(), status="protocol_error", stderr="Invalid reference JSON response")
        return SequenceResult(sequence_id=sequence_id, observations=tuple(out), status="ok", stderr="" if result.returncode == 0 else "Nonzero exit status")
