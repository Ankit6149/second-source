"""Verify a sanitized export offline without extracting its contents."""

import argparse
import json
from pathlib import Path

from second_source.backend.artifacts import verify_bundle
from second_source.backend.contracts import BackendError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Downloaded sanitized ZIP")
    parser.add_argument("--sha256", help="Optional independently obtained SHA-256 witness")
    args = parser.parse_args()
    try:
        # Bound the read itself, not only the downstream ZIP verification.
        with args.bundle.open("rb") as source:
            raw = source.read(8_000_001)
        result = verify_bundle(raw, expected_sha256=args.sha256)
    except (OSError, BackendError):
        print(json.dumps({"valid": False, "error": "Cannot verify bundle"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
