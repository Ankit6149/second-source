"""Local investigation engine: the working backend behind the
workbench's live-engine panel.

Scope and honesty boundaries (enforced by construction):
- Binds to 127.0.0.1 only. Local operator tool, not a hosted service.
- Browser access is restricted to local origins: a page served from
  any non-local origin cannot call this engine (CORS + Origin guard).
- One target: Vikunja v2.4.0 `/api/v1` running as a disposable local
  reference (fresh database per investigation).
- Pipeline per investigation: start fresh reference -> replay the
  PUBLIC probe ladder losslessly -> deterministic evidence
  compilation (NON_AI) -> serve the compiled candidate -> public
  conformance comparison. No model is called (model synthesis stays
  in the recorded Gemma experiment); provenance is NON_AI.
- The held-out evaluator is never imported here: held-out scoring is
  evaluator-side CLI work and the engine says so in every record.

Run:  python scripts/investigation_engine.py [--port 8765]
API:  GET  /engine/v1/health
      GET  /engine/v1/targets
      POST /engine/v1/investigations {"target": "vikunja-v1"}
           (optional header: Idempotency-Key: <opaque, <=128 chars>)
      POST /engine/v1/investigations/{id}/cancel
      GET  /engine/v1/investigations/{id}
      GET  /engine/v1/investigations/{id}/candidate
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_compiler  # noqa: E402
import vikunja_benchmark as vb  # noqa: E402
import vikunja_hybrid_experiment as hybrid  # noqa: E402
import vikunja_model_experiment as mx  # noqa: E402

from fastapi import FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / ".runs" / "engine"
ENGINE_VERSION = "1.0.0"
TARGET_ID = "vikunja-v1"
MAX_BODY_BYTES = 16384
MAX_INVESTIGATIONS = 64
MAX_IDEMPOTENCY_KEY_LEN = 128
_LOCAL_ORIGIN = r"https?://(127\.0\.0\.1|localhost)(:\d+)?"
_LOCAL_ORIGIN_RE = re.compile(r"^" + _LOCAL_ORIGIN + r"$")
_INV_ID_RE = re.compile(r"^inv-[0-9a-f]{12}$")
_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_PORT_COUNTER = [3510]
_LOCK = threading.Lock()
_STATE_LOCK = threading.RLock()
INVESTIGATIONS: dict[str, dict] = {}
_IDEMPOTENCY: dict[str, str] = {}


class _Cancelled(Exception):
    pass


def _next_port() -> int:
    with _LOCK:
        _PORT_COUNTER[0] += 2
        return _PORT_COUNTER[0]


def _set(rec: dict, **fields) -> None:
    with _STATE_LOCK:
        rec.update(fields)


def _check_cancelled(rec: dict) -> None:
    event = rec.get("_cancel")
    if event is not None and event.is_set():
        raise _Cancelled()


def _prune_locked() -> None:
    """Bound temporary state; caller must hold _STATE_LOCK."""
    while len(INVESTIGATIONS) > MAX_INVESTIGATIONS:
        terminal = sorted(
            (r for r in INVESTIGATIONS.values()
             if r.get("status") in _TERMINAL),
            key=lambda r: r.get("created_at", 0))
        if not terminal:
            return
        victim = terminal[0]["id"]
        del INVESTIGATIONS[victim]
        for key in [k for k, v in _IDEMPOTENCY.items() if v == victim]:
            del _IDEMPOTENCY[key]
        try:
            (RUNS / f"{victim}.json").unlink(missing_ok=True)
        except OSError:
            pass


def prune_investigations() -> None:
    with _STATE_LOCK:
        _prune_locked()


def probe_reference(ref_base: str) -> list[dict]:
    """Replay the public ladder on a fresh reference, losslessly."""
    api = ref_base + "/api/v1"
    tokens = vb.fresh_tokens(api)
    observations = []
    status, info = vb.call("GET", "/info", base=api)
    observations.append({"action": "GET /info", "status": status,
                         "body": info})
    ids: dict[str, int] = {}
    for method, path, body, who in vb.PUBLIC_PROBES:
        p = path.format(pid=ids.get("pid", 0), tid=ids.get("tid", 0))
        status, out = vb.call(method, p, body, tokens.get(who), base=api)
        if isinstance(out, dict) and "id" in out:
            if p == "/projects":
                ids["pid"] = out["id"]
            elif "/tasks" in p:
                ids["tid"] = out["id"]
        observations.append({"action": f"{method} {path}", "as": who,
                             "request": body, "status": status,
                             "body": out})
    return observations


def run_investigation(inv_id: str) -> None:
    with _STATE_LOCK:
        rec = INVESTIGATIONS.get(inv_id)
    if rec is None:
        return
    proc = workdir = None
    try:
        _check_cancelled(rec)
        _set(rec, stage="starting_reference")
        ref_port = _next_port()
        proc, workdir, ref_base = mx.start_reference(ref_port)
        _check_cancelled(rec)
        _set(rec, stage="probing_reference")
        observations = probe_reference(ref_base)
        payload = json.dumps(observations, indent=1)
        obs_sha = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
        _set(rec, observations={"count": len(observations),
                                "sha256": obs_sha})
        _check_cancelled(rec)
        _set(rec, stage="compiling_evidence")
        spec = evidence_compiler.compile_spec(observations, obs_sha)
        _set(rec, compiled={
            "routes": [f"{r['method']} {r['path']}"
                       for r in spec.get("routes", [])],
            "provenance": "EVIDENCE_COMPILED",
            "label": "NON_AI"}, _spec=spec)
        _check_cancelled(rec)
        _set(rec, stage="checking_public_conformance")
        conf = hybrid.public_conformance(spec, ref_base, _next_port())
        _check_cancelled(rec)
        _set(rec, public_conformance={
            "passed": conf["public_passed"], "total": conf["public_total"],
            "divergences": [d["action"] for d in conf["divergences"]]},
            held_out={
                "status": "not_run_by_engine",
                "reason": "Held-out scoring is evaluator-side only "
                          "(scripts/vikunja_benchmark.py --mode evaluate); "
                          "the engine never imports the held-out cases."},
            model={"called": False,
                   "reason": "This engine runs the deterministic "
                             "NON_AI pipeline. Model-authored "
                             "results (GEMMA_TEST hybrid 3/6) are "
                             "recorded evidence, replayed in the "
                             "Lab, not generated here."},
            status="completed", stage="completed")
    except _Cancelled:
        _set(rec, status="cancelled", stage="cancelled")
    except Exception as exc:  # failure is a recorded state, not a crash
        _set(rec, status="failed", stage="failed",
             error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        if proc is not None:
            mx.stop_reference(proc, workdir)
        with _STATE_LOCK:
            stored = {k: copy.deepcopy(v) for k, v in rec.items()
                      if not k.startswith("_")}
            RUNS.mkdir(parents=True, exist_ok=True)
            (RUNS / f"{inv_id}.json").write_text(
                json.dumps(stored, indent=1), encoding="utf-8")
            _prune_locked()


def public_view(rec: dict) -> dict:
    with _STATE_LOCK:
        return {k: copy.deepcopy(v) for k, v in rec.items()
                if not k.startswith("_")}


class CreateInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=64)


def _valid_inv_id(inv_id: str) -> bool:
    return bool(_INV_ID_RE.match(inv_id))


app = FastAPI(title="Second Source local investigation engine",
              version=ENGINE_VERSION)
app.add_middleware(CORSMiddleware, allow_origin_regex=_LOCAL_ORIGIN,
                   allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "Idempotency-Key"])


@app.middleware("http")
async def _guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin is not None and not _LOCAL_ORIGIN_RE.match(origin):
        return JSONResponse({"detail": "origin not allowed"}, status_code=403)
    if request.method in {"POST", "PUT", "PATCH"}:
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() \
                and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "request body too large"},
                                status_code=413)
        if len(await request.body()) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "request body too large"},
                                status_code=413)
    return await call_next(request)


@app.get("/engine/v1/health")
def health():
    return {"ok": True, "engine": ENGINE_VERSION,
            "bind": "127.0.0.1", "model_calls": False}


@app.get("/engine/v1/targets")
def targets():
    binary = Path(r"C:\tmp\vikunja-bench\bin")
    available = binary.exists()
    return [{"id": TARGET_ID, "label": "Vikunja v2.4.0 (/api/v1)",
             "kind": "professional-http",
             "status": "available" if available else "reference-missing",
             "provenance": "NON_AI",
             "pipeline": ["probe", "compile", "public-conformance"]}]


@app.post("/engine/v1/investigations")
def create(body: CreateInvestigation,
           idempotency_key: str | None = Header(
               default=None, alias="Idempotency-Key")):
    if body.target != TARGET_ID:
        raise HTTPException(400, f"unknown target; only {TARGET_ID}")
    key = idempotency_key.strip() if idempotency_key else None
    if idempotency_key is not None and (
            not key or len(key) > MAX_IDEMPOTENCY_KEY_LEN):
        raise HTTPException(400, "invalid Idempotency-Key")
    with _STATE_LOCK:
        if key is not None and key in _IDEMPOTENCY:
            existing = INVESTIGATIONS.get(_IDEMPOTENCY[key])
            if existing is not None:
                return public_view(existing)
        inv_id = "inv-" + uuid.uuid4().hex[:12]
        rec = {"id": inv_id, "target": TARGET_ID, "status": "running",
               "stage": "queued", "created_at": int(time.time()),
               "provenance": "NON_AI", "cancel_requested": False,
               "_cancel": threading.Event()}
        INVESTIGATIONS[inv_id] = rec
        if key is not None:
            _IDEMPOTENCY[key] = inv_id
        _prune_locked()
    threading.Thread(target=run_investigation, args=(inv_id,),
                     daemon=True).start()
    return public_view(rec)


@app.post("/engine/v1/investigations/{inv_id}/cancel")
def cancel(inv_id: str):
    if not _valid_inv_id(inv_id):
        raise HTTPException(404, "investigation not found")
    with _STATE_LOCK:
        rec = INVESTIGATIONS.get(inv_id)
        if rec is None:
            stored = RUNS / f"{inv_id}.json"
            if stored.exists():
                return json.loads(stored.read_text(encoding="utf-8"))
            raise HTTPException(404, "investigation not found")
        if rec.get("status") not in _TERMINAL:
            event = rec.get("_cancel")
            if event is not None:
                event.set()
            rec["cancel_requested"] = True
        return public_view(rec)


@app.get("/engine/v1/investigations/{inv_id}")
def get_one(inv_id: str):
    if not _valid_inv_id(inv_id):
        raise HTTPException(404, "investigation not found")
    with _STATE_LOCK:
        rec = INVESTIGATIONS.get(inv_id)
        if rec is not None:
            return public_view(rec)
    stored = RUNS / f"{inv_id}.json"
    if stored.exists():
        return json.loads(stored.read_text(encoding="utf-8"))
    raise HTTPException(404, "investigation not found")


@app.get("/engine/v1/investigations/{inv_id}/candidate")
def candidate(inv_id: str):
    if not _valid_inv_id(inv_id):
        raise HTTPException(404, "investigation not found")
    with _STATE_LOCK:
        rec = INVESTIGATIONS.get(inv_id)
        spec = copy.deepcopy(rec.get("_spec")) if rec else None
    if spec is None:
        raise HTTPException(409, "candidate not available")
    return JSONResponse(spec, headers={
        "Content-Disposition": f'attachment; filename="{inv_id}-candidate.json"'})


def main() -> int:
    import uvicorn
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    print(f"engine on http://127.0.0.1:{port} (localhost only, NON_AI)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
