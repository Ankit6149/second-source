"""Append-only, hash-addressed raw observation store and sanitized model views."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .contracts import Observation


def publish_once(path: Path, raw: bytes) -> Path:
    """Publish complete, fsynced bytes without replacing an existing artifact.

    Shared by G2 journals and G3 reports. Same-filesystem hard-link publication
    prevents partial final files and makes concurrent publication exclusive.
    Directory metadata power-loss durability remains filesystem-dependent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".", suffix=".staging"
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staging, path)
        return path
    finally:
        try:
            os.unlink(staging)
        except OSError:
            pass

_SECRET_FIELD = re.compile(r"(?:authorization|cookie|api[_-]?key|password|secret|access[_-]?token|refresh[_-]?token|otp|session)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+")


def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if _SECRET_FIELD.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(x) for x in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(r"\1[REDACTED]", value)
    return value


class EvidenceLedger:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValueError("Ledger root cannot be a symlink")

    def store(self, observation: Observation) -> dict[str, str]:
        raw = observation.model_dump(mode="json")
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        path = self.root / (digest + ".json")
        if path.exists():
            if path.read_bytes() != canonical:
                raise ValueError("Content address corrupted")
        else:
            # Exclusive create, no overwrite. Caller controls trusted filesystem root.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(canonical)
                out.flush()
                os.fsync(out.fileno())
        return {"observation_id": observation.observation_id, "sha256": digest, "artifact": path.name}

    def inspect(self, digest: str) -> Observation:
        if not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Invalid artifact digest")
        content = (self.root / (digest + ".json")).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Tampered artifact")
        return Observation.model_validate_json(content)

    def model_view(self, digest: str) -> dict:
        """Return sanitized evidence rather than handing the raw artifact to the model."""
        return redact(self.inspect(digest).model_dump(mode="json"))
