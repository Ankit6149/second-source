"""Provider-neutral visual scan: segment app/website screenshots and summarize motion physics.

Two independent stages:

1. Regions (needs a configured vision backend, server-side only):
   - Any segmentation/vision service works, including Meta SAM
     (Segment Anything). The service contract is provider-neutral:
     POST PNG bytes to <endpoint>/segment, receive JSON
     {"regions": [{"label": str, "x": int, "y": int,
     "w": int, "h": int, "score": float}]}.
   - Configure with SECOND_SOURCE_VISION_ENDPOINT (server environment
     only; never in the browser). An optional
     SECOND_SOURCE_VISION_API_KEY travels only on that TLS call.
   - Unconfigured -> available=false with a reason. Regions stay
     unmeasured, never zero or invented.

2. Motion/physics (always local, NON_AI, no model involved):
   - scan_motion() reads one browser-slice capture directory
     (observations.json, inferred.json, verdict.json) and summarizes
     the fitted spring physics plus held-out trajectory error.

CLI:
  python scripts/vision_scan.py --capabilities
  python scripts/vision_scan.py --motion browser-slice-v2
  python scripts/vision_scan.py --image shot.png [--backend sam|auto]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISION_ENDPOINT_ENV = "SECOND_SOURCE_VISION_ENDPOINT"
VISION_KEY_ENV = "SECOND_SOURCE_VISION_API_KEY"
MAX_IMAGE_BYTES = 8_000_000
REQUEST_TIMEOUT_S = 25
MAX_REGIONS = 200


def _redacted_host(endpoint: str) -> str:
    try:
        return urllib.parse.urlsplit(endpoint).hostname or "unparseable"
    except Exception:
        return "unparseable"


def capabilities() -> dict:
    """What this host can do; never includes credentials."""
    endpoint = os.environ.get(VISION_ENDPOINT_ENV, "").strip()
    return {
        "regions": "sam-or-compatible-service" if endpoint else "unconfigured",
        "regions_endpoint_host": _redacted_host(endpoint) if endpoint else None,
        "motion_physics": "local-non-ai",
        "note": "Any PNG->regions vision service (SAM or other) may back "
                "region scans; motion physics is dependency-free and local.",
    }


def _valid_endpoint(endpoint: str) -> str:
    parts = urllib.parse.urlsplit(endpoint.strip().rstrip("/"))
    if parts.scheme not in ("https", "http"):
        raise ValueError("vision endpoint must be http(s)")
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("refusing non-TLS vision endpoint outside loopback")
    if not parts.hostname:
        raise ValueError("vision endpoint has no host")
    return endpoint.strip().rstrip("/")


def scan_image(path: str | Path, *, backend: str = "auto",
               timeout_s: int = REQUEST_TIMEOUT_S) -> dict:
    """Segment one PNG screenshot into labeled regions.

    backend: "auto" (use the configured service) or "sam" (same service,
    requested explicitly as SAM-compatible). There is no local fallback
    segmenter: without a configured service the scan is unavailable.
    """
    if backend not in ("auto", "sam"):
        raise ValueError(f"unknown vision backend {backend!r}")
    image = Path(path)
    if not image.is_file():
        raise FileNotFoundError(f"image not found: {image}")
    raw = image.read_bytes()
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds 8MB scan limit")
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("only PNG screenshots are accepted")
    endpoint = os.environ.get(VISION_ENDPOINT_ENV, "").strip()
    if not endpoint:
        return {"available": False, "backend": "none",
                "reason": f"{VISION_ENDPOINT_ENV} is not configured; "
                          "region scan unmeasured (no fallback invented).",
                "regions": None}
    try:
        base = _valid_endpoint(endpoint)
    except ValueError as exc:
        return {"available": False, "backend": "none",
                "reason": f"invalid vision endpoint: {exc}", "regions": None}
    req = urllib.request.Request(base + "/segment", data=raw, method="POST",
                                 headers={"Content-Type": "image/png"})
    key = os.environ.get(VISION_KEY_ENV, "")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"available": False, "backend": backend,
                "reason": f"vision service HTTP {exc.code}", "regions": None}
    except Exception as exc:
        return {"available": False, "backend": backend,
                "reason": f"vision service unreachable: {type(exc).__name__}",
                "regions": None}
    regions = payload.get("regions") if isinstance(payload, dict) else None
    if not isinstance(regions, list) or len(regions) > MAX_REGIONS:
        return {"available": False, "backend": backend,
                "reason": "vision service returned a malformed region list",
                "regions": None}
    cleaned = []
    for item in regions:
        if not isinstance(item, dict):
            return {"available": False, "backend": backend,
                    "reason": "vision service returned a malformed region",
                    "regions": None}
        try:
            label = str(item["label"])[:80]
            box = [int(item[k]) for k in ("x", "y", "w", "h")]
            score = float(item.get("score", 1.0))
        except (KeyError, TypeError, ValueError):
            return {"available": False, "backend": backend,
                    "reason": "vision service returned a malformed region",
                    "regions": None}
        if any(v < 0 for v in box) or not 0.0 <= score <= 1.0:
            return {"available": False, "backend": backend,
                    "reason": "vision service returned an out-of-range region",
                    "regions": None}
        cleaned.append({"label": label, "x": box[0], "y": box[1],
                        "w": box[2], "h": box[3], "score": score})
    return {"available": True, "backend": "vision-service",
            "endpoint_host": _redacted_host(base),
            "regions": cleaned, "region_count": len(cleaned)}


def scan_motion(capture_dir: str | Path) -> dict:
    """Summarize fitted UI motion physics from a browser-slice capture.

    Dependency-free and NON_AI: reads only the capture artifacts
    (observations.json, inferred.json, verdict.json) the repo already
    produces. Missing files -> explicit unmeasured fields, never zeros.
    """
    root = Path(capture_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"capture directory not found: {root}")

    def _load(name: str):
        path = root / name
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    obs = _load("observations.json")
    inferred = _load("inferred.json") or {}
    verdict = _load("verdict.json") or {}
    samples = None
    if isinstance(obs, dict):
        track = obs.get("trajectory") or obs.get("samples")
        samples = len(track) if isinstance(track, list) else None
    elif isinstance(obs, list):
        samples = len(obs)
    spring = inferred.get("spring") if isinstance(inferred, dict) else None
    physics = None
    if isinstance(spring, dict):
        try:
            physics = {"stiffness": float(spring["stiffness"]),
                       "damping": float(spring["damping"]),
                       "fit_rmse_px": float(spring["fitRmsePx"]),
                       "release_x_px": float(spring.get("releaseX", 0.0))}
        except (KeyError, TypeError, ValueError):
            physics = None
    traj = verdict.get("trajectory") if isinstance(verdict, dict) else None
    held_out = None
    if isinstance(traj, dict):
        try:
            held_out = {"rmse_px": float(traj["rmseCandidatePx"]),
                        "threshold_px": float(traj["thresholdPx"]),
                        "pass": bool(traj["pass"])}
        except (KeyError, TypeError, ValueError):
            held_out = None
    return {"available": True, "provenance": "NON_AI",
            "capture": root.name,
            "observation_samples": samples,
            "spring_physics": physics,
            "held_out_trajectory": held_out,
            "verdict_pass": verdict.get("pass") if isinstance(verdict, dict) else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visual scan: regions + motion physics.")
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--motion", default=None,
                        help="browser-slice capture directory to summarize")
    parser.add_argument("--image", default=None, help="PNG screenshot to segment")
    parser.add_argument("--backend", default="auto", choices=["auto", "sam"])
    args = parser.parse_args(argv)
    if args.capabilities:
        print(json.dumps(capabilities(), indent=1))
        return 0
    if args.motion:
        print(json.dumps(scan_motion(args.motion), indent=1))
        return 0
    if args.image:
        try:
            result = scan_image(args.image, backend=args.backend)
        except (FileNotFoundError, ValueError) as exc:
            print(f"BLOCKED: {exc}")
            return 2
        print(json.dumps(result, indent=1))
        return 0 if result.get("available") else 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
