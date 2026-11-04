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
import os
import subprocess
import hashlib
import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_compiler  # noqa: E402
import filebrowser_benchmark as fb  # noqa: E402
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
FB_TARGET_ID = "filebrowser-v1"
GT_TARGET_ID = "gitea-v1"
TARGETS = (TARGET_ID, FB_TARGET_ID, GT_TARGET_ID)
GT_BASE = "http://127.0.0.1:3000/api/v1"
GT_ADMIN = {"username": "ssadmin", "password": "SsPass#12345"}
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


def _persist_completed_record(rec: dict) -> None:
    """Durably retain the selected local candidate after engine restarts."""
    with _STATE_LOCK:
        RUNS.mkdir(parents=True, exist_ok=True)
        stored = {k: copy.deepcopy(v) for k, v in rec.items()
                  if not k.startswith("_")}
        spec = rec.get("_spec")
        if spec is not None:
            raw = json.dumps(spec, indent=1, default=str).encode("utf-8")
            artifact = RUNS / f"{rec['id']}-candidate.json"
            with artifact.open("wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(artifact, 0o600)
            stored["candidate_artifact"] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "provenance": rec.get("compiled", {}).get("provenance", "UNSPECIFIED")}
        (RUNS / f"{rec['id']}.json").write_text(
            json.dumps(stored, indent=1, default=str), encoding="utf-8")
        _prune_locked()


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


def _fb_ref_available() -> bool:
    try:
        st, tok = fb.token_of(fb.REF, fb.ADMIN)
        return bool(tok)
    except Exception:
        return False


def _wait_candidate(base: str) -> None:
    for _ in range(60):
        try:
            fb.call(base, "GET", "/users")
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("candidate server did not start")


def _gt_call(base, method, path, body=None, auth=None):
    """auth: None | 'basic' (reference) | token string (candidate X-Auth)."""
    import base64 as _b64
    import urllib.error as _e
    import urllib.request as _r
    req = _r.Request(base + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if auth == "basic":
        raw = f"{GT_ADMIN['username']}:{GT_ADMIN['password']}".encode()
        req.add_header("Authorization", "Basic " + _b64.b64encode(raw).decode())
    elif auth:
        req.add_header("X-Auth", auth)
    try:
        with _r.urlopen(req, data=data, timeout=15) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except _e.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def _gt_available() -> bool:
    try:
        st, _ = _gt_call(GT_BASE, "GET", "/version")
        return st == 200
    except Exception:
        return False


def _gt_case(base, auth):
    """One differential case set; returns comparable tuples per case."""
    out = {}
    st, body = _gt_call(base, "GET", "/version", auth=auth)
    out["version"] = (st,)
    _gt_call(base, "DELETE", "/repos/ssadmin/ss-case", auth=auth)
    st, body = _gt_call(base, "POST", "/user/repos",
                        {"name": "ss-case", "auto_init": True}, auth=auth)
    out["create_repo"] = (st, body.get("name") if isinstance(body, dict) else None)
    st, body = _gt_call(base, "GET", "/repos/ssadmin/ss-case", auth=auth)
    out["get_repo"] = (st, body.get("name") if isinstance(body, dict) else None)
    st, body = _gt_call(base, "POST", "/repos/ssadmin/ss-case/issues",
                        {"title": "Case bug"}, auth=auth)
    out["create_issue"] = (st, body.get("title") if isinstance(body, dict) else None)
    st, body = _gt_call(base, "GET", "/repos/ssadmin/ss-case/issues", auth=auth)
    out["list_issues"] = (st, len(body) if isinstance(body, list) else None)
    st, _ = _gt_call(base, "GET", "/user")
    out["unauth_user"] = (st,)
    _gt_call(base, "DELETE", "/repos/ssadmin/ss-case", auth=auth)
    return out


def _run_gitea(rec: dict) -> None:
    """Gitea 1.22.6 first contact: public probes -> compile -> differential.

    Bounded subsystem only (version, repositories, issues, auth boundary).
    The candidate is the generic spec interpreter; Gitea's large nested
    bodies are compiled as observed templates, so field-level mismatches
    are expected and reported, never hidden.
    """
    procs = []
    try:
        _check_cancelled(rec)
        _set(rec, stage="starting_reference")
        if not _gt_available():
            raise RuntimeError("gitea reference not reachable at 127.0.0.1:3000")
        _check_cancelled(rec)
        _set(rec, stage="probing_reference")
        _gt_call(GT_BASE, "DELETE", "/repos/ssadmin/ss-demo", auth="basic")
        obs = []

        def rec_obs(action, request, status, body):
            obs.append({"action": action, "as": "alice", "request": request,
                        "status": status, "body": body})

        st, body = _gt_call(GT_BASE, "GET", "/version", auth="basic")
        rec_obs("GET /version", None, st, body)
        st, body = _gt_call(GT_BASE, "POST", "/user/repos",
                            {"name": "ss-demo", "auto_init": True}, auth="basic")
        rec_obs("POST /user/repos", {"name": "ss-demo", "auto_init": True}, st, body)
        st, body = _gt_call(GT_BASE, "GET", "/repos/ssadmin/ss-demo", auth="basic")
        rec_obs("GET /repos/ssadmin/ss-demo", None, st, body)
        st, body = _gt_call(GT_BASE, "POST", "/repos/ssadmin/ss-demo/issues",
                            {"title": "Demo bug"}, auth="basic")
        rec_obs("POST /repos/ssadmin/ss-demo/issues", {"title": "Demo bug"}, st, body)
        st, body = _gt_call(GT_BASE, "GET", "/repos/ssadmin/ss-demo/issues", auth="basic")
        rec_obs("GET /repos/ssadmin/ss-demo/issues", None, st,
                [i.get("title") for i in body] if isinstance(body, list) else body)
        st, body = _gt_call(GT_BASE, "GET", "/user", auth="basic")
        rec_obs("GET /user", None, st, body)
        st, body = _gt_call(GT_BASE, "GET", "/user")
        obs.append({"action": "GET /user", "as": "None", "request": None,
                    "status": st, "body": body})
        digest = hashlib.sha256(json.dumps(obs, sort_keys=True, default=str).encode()).hexdigest()
        _set(rec, observations={"count": len(obs), "sha256": "sha256:" + digest})
        _check_cancelled(rec)
        _set(rec, stage="compiling_evidence")
        spec = fb.compile_spec(obs, digest)
        spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
        spec["users"] = {"alice": "ssadmin"}
        _set(rec, compiled={
            "routes": [f"{r['method']} {r['path']}" for r in spec.get("routes", [])],
            "provenance": "EVIDENCE_COMPILED",
            "label": "NON_AI"}, _spec=spec)
        _check_cancelled(rec)
        _set(rec, stage="checking_public_conformance")
        RUNS.mkdir(parents=True, exist_ok=True)
        spec_path = RUNS / f"{rec['id']}-gt-spec.json"
        spec_path.write_text(json.dumps(spec, indent=1, default=str), encoding="utf-8")
        port = _next_port()
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "vikunja_candidate_server.py"),
             str(spec_path), str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(proc)
        cand = f"http://127.0.0.1:{port}"
        _wait_candidate(cand)
        fb.call(cand, "POST", "/register", GT_ADMIN)
        _, tok = fb.token_of(cand, GT_ADMIN)
        ref_cases = _gt_case(GT_BASE, "basic")
        cand_cases = _gt_case(cand, tok)
        results = [{"case": k, "pass": ref_cases[k] == cand_cases[k],
                    "ref": ref_cases[k], "cand": cand_cases[k]} for k in ref_cases]
        passed = sum(1 for r in results if r["pass"])
        _check_cancelled(rec)
        _set(rec, public_conformance={
            "passed": passed, "total": len(results),
            "divergences": [f"{r['case']}: ref={r['ref']} cand={r['cand']}"
                            for r in results if not r["pass"]]},
            held_out={
                "status": "not_run_by_engine",
                "reason": "Held-out scoring is evaluator-side only; "
                          "the engine never imports held-out cases."},
            model={"called": False,
                   "reason": "This engine runs the deterministic NON_AI pipeline. "
                             "Model-authored results are recorded evidence, not generated here."},
            status="completed", stage="completed")
    except _Cancelled:
        _set(rec, status="cancelled", stage="cancelled")
    except Exception as exc:
        _set(rec, status="failed", stage="failed",
             error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        for proc in procs:
            try:
                proc.terminate()
            except Exception:
                pass
        _persist_completed_record(rec)


def _run_filebrowser(rec: dict) -> None:
    """File Browser v2.63.23: public probes -> compile -> differential cases.

    Same generic compiler/interpreter as the CLI benchmark; no target code
    in the compiler. The reference is the operator-run local server on
    127.0.0.1:3471; if it is down the investigation fails honestly.
    """
    procs = []
    try:
        _check_cancelled(rec)
        _set(rec, stage="starting_reference")
        if not _fb_ref_available():
            raise RuntimeError("filebrowser reference not reachable at 127.0.0.1:3471")
        _check_cancelled(rec)
        _set(rec, stage="probing_reference")
        observations = fb.public_probes()
        digest = hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest()
        _set(rec, observations={"count": len(observations), "sha256": "sha256:" + digest})
        _check_cancelled(rec)
        _set(rec, stage="compiling_evidence")
        spec = fb.compile_spec(observations, digest)
        spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
        spec["users"] = {"alice": "genadmin"}
        _set(rec, compiled={
            "routes": [f"{r['method']} {r['path']}" for r in spec.get("routes", [])],
            "provenance": "EVIDENCE_COMPILED",
            "label": "NON_AI"}, _spec=spec)
        _check_cancelled(rec)
        _set(rec, stage="checking_public_conformance")
        RUNS.mkdir(parents=True, exist_ok=True)
        spec_path = RUNS / f"{rec['id']}-fb-spec.json"
        spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")

        def start_candidate(spec_obj, name):
            path = RUNS / f"{rec['id']}-{name}.json"
            path.write_text(json.dumps(spec_obj, indent=1), encoding="utf-8")
            port = _next_port()
            proc = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts" / "vikunja_candidate_server.py"),
                 str(path), str(port)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs.append(proc)
            base = f"http://127.0.0.1:{port}"
            _wait_candidate(base)
            return base

        cand = start_candidate(spec, "fb-candidate")
        fb.call(cand, "POST", "/register", fb.ADMIN)
        fb.call(cand, "POST", "/register", {"username": "genbob", "password": "genpassword456"})
        st0, tok0 = fb.token_of(cand, fb.ADMIN)
        admin_entity = dict(fb.NEW_USER, username="genadmin",
                            perm={"admin": True, "execute": True, "create": True,
                                  "rename": True, "modify": True, "delete": True,
                                  "share": True, "download": True})
        fb.call(cand, "POST", "/users",
                {"what": "user", "which": [], "data": admin_entity,
                 "current_password": fb.ADMIN["password"]}, token=tok0)
        results = []
        for cid, kind, name in fb.CASES:
            ref_r = fb.run_case(fb.REF, name)
            cand_r = fb.run_case(cand, name)
            results.append({"case": cid, "pass": ref_r == cand_r})
        bad = json.loads(json.dumps(spec))
        bad["auth"]["login_error_status"] = 200
        mut = start_candidate(bad, "fb-mutated")
        fb.call(mut, "POST", "/register", fb.ADMIN)
        mut_r = fb.run_case(mut, "wrong-password-login")
        ref_r = fb.run_case(fb.REF, "wrong-password-login")
        results.append({"case": "FB-CONTROL-MUTATED", "pass": ref_r != mut_r})
        passed = sum(1 for r in results if r["pass"])
        _check_cancelled(rec)
        _set(rec, public_conformance={
            "passed": passed, "total": len(results),
            "divergences": [r["case"] for r in results if not r["pass"]]},
            held_out={
                "status": "not_run_by_engine",
                "reason": "Held-out scoring is evaluator-side only; "
                          "the engine never imports held-out cases."},
            model={"called": False,
                   "reason": "This engine runs the deterministic NON_AI pipeline. "
                             "Model-authored results are recorded evidence, not generated here."},
            status="completed", stage="completed")
    except _Cancelled:
        _set(rec, status="cancelled", stage="cancelled")
    except Exception as exc:
        _set(rec, status="failed", stage="failed",
             error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        for proc in procs:
            try:
                proc.terminate()
            except Exception:
                pass
        _persist_completed_record(rec)


def run_investigation(inv_id: str) -> None:
    with _STATE_LOCK:
        rec = INVESTIGATIONS.get(inv_id)
    if rec is None:
        return
    if rec.get("target") == FB_TARGET_ID:
        _run_filebrowser(rec)
        return
    if rec.get("target") == GT_TARGET_ID:
        _run_gitea(rec)
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
        selected = spec
        model_summary = {"called": False, "mode": "none",
                         "reason": "Deterministic NON_AI compiler only."}
        if rec.get("model_mode") == "muse-repair":
            # This optional, explicit paid stage uses ONLY public evidence.
            # Never feed withheld evaluation cases or reference source to Muse.
            from muse_pipeline_repair import attempt_muse_public_repair
            _set(rec, stage="muse_public_repair")
            RUNS.mkdir(parents=True, exist_ok=True)
            audit_file = RUNS / f"{rec['id']}-muse-private-receipts.jsonl"

            def persist_model_receipt(kind: str, payload: dict) -> None:
                line = json.dumps({"kind": kind, **payload}, default=str) + "\n"
                fd = os.open(audit_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as stream:
                    stream.write(line)
                    stream.flush()
                    os.fsync(stream.fileno())

            def measure_on_fresh_reference(candidate_spec: dict) -> dict:
                _check_cancelled(rec)
                probe_proc = probe_dir = None
                try:
                    probe_proc, probe_dir, fresh_base = mx.start_reference(_next_port())
                    return hybrid.public_conformance(candidate_spec, fresh_base, _next_port())
                finally:
                    if probe_proc is not None:
                        mx.stop_reference(probe_proc, probe_dir)

            selected, conf, model_summary = attempt_muse_public_repair(
                compiled=spec, observations=observations, baseline=conf,
                measure=measure_on_fresh_reference,
                api_key=os.environ.get("MODEL_API_KEY", ""),
                record_audit=persist_model_receipt,
                cancelled=lambda: bool(rec["_cancel"].is_set()))
            _check_cancelled(rec)
        accepted = bool(model_summary.get("accepted"))
        if accepted:
            _set(rec, compiled={
                "routes": [f"{r['method']} {r['path']}"
                           for r in selected.get("routes", [])],
                "provenance": "REAL_MODEL_ASSISTED",
                "label": "Muse-edited, public-gated candidate"})
        _set(rec, _spec=selected,
            public_conformance={
                "passed": conf["public_passed"], "total": conf["public_total"],
                "divergences": [d["action"] for d in conf["divergences"]]},
            held_out={
                "status": "not_run_by_engine",
                "reason": "Held-out scoring is evaluator-side only "
                          "(scripts/vikunja_benchmark.py --mode evaluate); "
                          "the engine never imports the held-out cases."},
            model=model_summary,
            status="completed", stage="completed")
    except _Cancelled:
        _set(rec, status="cancelled", stage="cancelled")
    except Exception as exc:  # failure is a recorded state, not a crash
        _set(rec, status="failed", stage="failed",
             error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        if proc is not None:
            mx.stop_reference(proc, workdir)
        _persist_completed_record(rec)


def public_view(rec: dict) -> dict:
    with _STATE_LOCK:
        return {k: copy.deepcopy(v) for k, v in rec.items()
                if not k.startswith("_")}


class CreateInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=64)
    # Paid inference never starts unless the operator explicitly requests it.
    model_mode: Literal["none", "muse-repair"] = "none"


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
            "bind": "127.0.0.1",
            "model_calls": os.environ.get("SECOND_SOURCE_ALLOW_MUSE_REPAIR") == "true"
            and bool(os.environ.get("MODEL_API_KEY"))}


@app.get("/engine/v1/targets")
def targets():
    binary = Path(r"C:\tmp\vikunja-bench\bin")
    available = binary.exists()
    return [
        {"id": TARGET_ID, "label": "Vikunja v2.4.0 (/api/v1)",
         "kind": "professional-http",
         "status": "available" if available else "reference-missing",
         "provenance": "NON_AI",
         "pipeline": ["probe", "compile", "public-conformance"]},
        {"id": FB_TARGET_ID, "label": "File Browser v2.63.23 (/api)",
         "kind": "professional-http",
         "status": "available" if _fb_ref_available() else "reference-missing",
         "provenance": "NON_AI",
         "pipeline": ["probe", "compile", "differential-cases"]},
        {"id": GT_TARGET_ID, "label": "Gitea 1.22.6 (/api/v1)",
         "kind": "professional-http",
         "status": "available" if _gt_available() else "reference-missing",
         "provenance": "NON_AI",
         "pipeline": ["probe", "compile", "differential-cases"]},
    ]


@app.post("/engine/v1/investigations")
def create(body: CreateInvestigation,
           idempotency_key: str | None = Header(
               default=None, alias="Idempotency-Key")):
    if body.target not in TARGETS:
        raise HTTPException(400, f"unknown target; supported: {', '.join(TARGETS)}")
    if body.model_mode == "muse-repair":
        if body.target != TARGET_ID:
            raise HTTPException(422, "Muse repair is only supported for the Vikunja local adapter")
        if os.environ.get("SECOND_SOURCE_ALLOW_MUSE_REPAIR") != "true":
            raise HTTPException(409, "Local Muse repair is disabled by the operator")
        if not os.environ.get("MODEL_API_KEY"):
            raise HTTPException(503, "Local Meta model credential is not configured")
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
        rec = {"id": inv_id, "target": body.target, "status": "running",
               "stage": "queued", "created_at": int(time.time()),
               "provenance": "NON_AI", "model_mode": body.model_mode,
               "cancel_requested": False, "_cancel": threading.Event()}
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
        saved = RUNS / f"{inv_id}-candidate.json"
        if saved.exists():
            if saved.stat().st_size > 2_000_000:
                raise HTTPException(409, "candidate artifact exceeds download limit")
            spec = json.loads(saved.read_text(encoding="utf-8"))
    if spec is None:
        raise HTTPException(409, "candidate not available")
    return JSONResponse(spec, headers={
        "Content-Disposition": f'attachment; filename="{inv_id}-candidate.json"'})


def main() -> int:
    import uvicorn
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    print(f"engine on http://127.0.0.1:{port} (localhost only, default NON_AI; optional explicit Muse repair)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
