"""Local investigation engine: the working backend behind the
workbench's live-engine panel.

Scope and honesty boundaries (enforced by construction):
- Binds to 127.0.0.1 only. Local operator tool, not a hosted service.
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
      GET  /engine/v1/investigations/{id}
      GET  /engine/v1/investigations/{id}/candidate
"""
from __future__ import annotations

import hashlib
import json
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

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / ".runs" / "engine"
ENGINE_VERSION = "1.0.0"
TARGET_ID = "vikunja-v1"
_PORT_COUNTER = [3510]
_LOCK = threading.Lock()
INVESTIGATIONS: dict[str, dict] = {}


def _next_port() -> int:
    with _LOCK:
        _PORT_COUNTER[0] += 2
        return _PORT_COUNTER[0]


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
    rec = INVESTIGATIONS[inv_id]
    proc = workdir = None
    try:
        rec["stage"] = "starting_reference"
        ref_port = _next_port()
        proc, workdir, ref_base = mx.start_reference(ref_port)
        rec["stage"] = "probing_reference"
        observations = probe_reference(ref_base)
        payload = json.dumps(observations, indent=1)
        obs_sha = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
        rec["observations"] = {"count": len(observations), "sha256": obs_sha}
        rec["stage"] = "compiling_evidence"
        spec = evidence_compiler.compile_spec(observations, obs_sha)
        rec["compiled"] = {
            "routes": [f"{r['method']} {r['path']}"
                       for r in spec.get("routes", [])],
            "provenance": "EVIDENCE_COMPILED",
            "label": "NON_AI"}
        rec["_spec"] = spec
        rec["stage"] = "checking_public_conformance"
        conf = hybrid.public_conformance(spec, ref_base, _next_port())
        rec["public_conformance"] = {
            "passed": conf["public_passed"], "total": conf["public_total"],
            "divergences": [d["action"] for d in conf["divergences"]]}
        rec["held_out"] = {
            "status": "not_run_by_engine",
            "reason": "Held-out scoring is evaluator-side only "
                      "(scripts/vikunja_benchmark.py --mode evaluate); "
                      "the engine never imports the held-out cases."}
        rec["model"] = {"called": False,
                        "reason": "This engine runs the deterministic "
                                  "NON_AI pipeline. Model-authored "
                                  "results (GEMMA_TEST hybrid 3/6) are "
                                  "recorded evidence, replayed in the "
                                  "Lab, not generated here."}
        rec["status"] = "completed"
        rec["stage"] = "completed"
    except Exception as exc:  # failure is a recorded state, not a crash
        rec["status"] = "failed"
        rec["stage"] = "failed"
        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if proc is not None:
            mx.stop_reference(proc, workdir)
        RUNS.mkdir(parents=True, exist_ok=True)
        stored = {k: v for k, v in rec.items() if not k.startswith("_")}
        (RUNS / f"{inv_id}.json").write_text(
            json.dumps(stored, indent=1), encoding="utf-8")


def public_view(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("_")}


app = FastAPI(title="Second Source local investigation engine",
              version=ENGINE_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


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
def create(body: dict):
    if body.get("target") != TARGET_ID:
        raise HTTPException(400, f"unknown target; only {TARGET_ID}")
    inv_id = "inv-" + uuid.uuid4().hex[:12]
    INVESTIGATIONS[inv_id] = {
        "id": inv_id, "target": TARGET_ID, "status": "running",
        "stage": "queued", "created_at": int(time.time()),
        "provenance": "NON_AI"}
    threading.Thread(target=run_investigation, args=(inv_id,),
                     daemon=True).start()
    return public_view(INVESTIGATIONS[inv_id])


@app.get("/engine/v1/investigations/{inv_id}")
def get_one(inv_id: str):
    rec = INVESTIGATIONS.get(inv_id)
    if rec is None:
        stored = RUNS / f"{inv_id}.json"
        if stored.exists():
            return json.loads(stored.read_text(encoding="utf-8"))
        raise HTTPException(404, "investigation not found")
    return public_view(rec)


@app.get("/engine/v1/investigations/{inv_id}/candidate")
def candidate(inv_id: str):
    rec = INVESTIGATIONS.get(inv_id)
    spec = rec.get("_spec") if rec else None
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
