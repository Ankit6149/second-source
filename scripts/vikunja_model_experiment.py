"""Genuine model experiment for the Vikunja benchmark (Gemma dev provider).

Arms (comparable budgets: identical observation exposure within B/C,
exactly ONE synthesis call per arm, same spec schema, same evaluator):
  A prior-only        -- interface summary + spec schema, no observations
  B observations      -- public probe observations + spec schema
  C coverage-grounded -- observations + claim-state discipline
                         (claim only what observations show; mark the
                         rest unknown rather than guessing)

The model authors a candidate SPEC (see vikunja_candidate_server.py).
The spec is executed by the generic interpreter and scored by the
independent held-out evaluator. Held-out sequences are never included
in any prompt. Provenance: provider "gemma-test" /
PIPELINE_SMOKE_NOT_META. This is development evidence, not a Meta
hackathon result, and never a substitute for the gated Muse run.

Live mode requires GEMMA_API_KEY in the environment (rotated key; the
previously exposed key must not be reused) and --confirm-live.
Preflight mode makes zero network calls to any model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / ".runs" / "vikunja-benchmark" / "public_observations.json"
OUT = ROOT / ".runs" / "vikunja-model"
MODEL = "gemma-4-26b-a4b-it"
API = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

SPEC_SCHEMA = """Candidate spec JSON schema (vikunja_candidate_server.py):
{"users": {"alice": "bench_alice", "bob": "bench_bob"},
 "auth": {"login_error_status": int, "login_error_body": obj,
          "unauthenticated_status": int, "unauthenticated_body": obj,
          "forbidden_body": obj, "not_found_body": obj},
 "routes": [{"method": "PUT|GET|POST", "path": "/projects|/projects/{pid}/tasks|/tasks/{tid}|/projects/{pid}/users|/projects|/user",
             "kind": "create_project|list_projects|create_task|list_tasks|update_task|get_task|share_project|get_user",
             "auth": true, "status": int,
             "permission": "owner|owner_or_read|owner_or_write|any_auth",
             "validate": [{"field": "title", "rule": "nonempty", "status": int, "error_body": obj}],
             "fields": {extra response fields; tokens <creator>, <auto_id>,
                        <entity_id>, <target>, <permission>, <index>, <identifier>},
             "fields_override": bool, "forbidden_body": obj}]}
Return ONLY the JSON spec."""

INTERFACE = """Target: a self-hosted task-management web app, REST API under
/api/v1, token auth (Bearer). Domain: users own projects; projects contain
tasks; tasks can be done/undone; projects can be shared with other users
with permission levels. You are reconstructing the externally observable
contract of a bounded subsystem: auth errors, project create/list, task
create/list/get/update (done transitions), project sharing, cross-user
permissions, validation errors."""

ARMS = {
    "A_prior": "Use only the interface summary and your engineering priors. "
               "Do not invent observation claims.",
    "B_observations": "Use the observations below as your only evidence of "
                      "actual behavior; priors may fill gaps.",
    "C_grounded": "Use the observations below. Claim ONLY behavior the "
                  "observations show. For anything unobserved, choose the "
                  "most conservative contract and never contradict an "
                  "observation. Distinguish observed from assumed in your "
                  "choices: exact statuses, exact error bodies, exact fields.",
}


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def build_prompt(arm: str, observations: str) -> str:
    parts = [INTERFACE, SPEC_SCHEMA, ARMS[arm]]
    if arm != "A_prior":
        parts.append("OBSERVATIONS (public probes, authorized):\n" + observations)
    return "\n\n".join(parts)


def preflight() -> int:
    observations = OBS.read_text(encoding="utf-8") if OBS.exists() else ""
    report = {"kind": "VIKUNJA_MODEL_PREFLIGHT_V1", "provider": "gemma-test",
              "classification": "PIPELINE_SMOKE_NOT_META",
              "model": MODEL, "calls_planned": {a: 1 for a in ARMS},
              "held_out_in_prompts": False,
              "observations_bytes": len(observations)}
    for arm in ARMS:
        prompt = build_prompt(arm, observations)
        report.setdefault("arms", {})[arm] = {
            "context_digest": digest(prompt), "prompt_chars": len(prompt)}
    key = os.environ.get("GEMMA_API_KEY")
    report["gemma_key_present"] = bool(key)
    report["live_ready"] = bool(key)
    if not key:
        report["blocker"] = ("GEMMA_API_KEY not set. Set the ROTATED key "
                             "locally; the previously exposed key must not "
                             "be reused. Zero model calls made.")
    print(json.dumps(report, indent=1))
    return 0


def call_gemma(prompt: str, api_key: str) -> str:
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "maxOutputTokens": 8000,
                                 "temperature": 0.2}}
    req = urllib.request.Request(
        API.format(m=MODEL), data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-goog-api-key", api_key)
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode())
    return data["candidates"][0]["content"]["parts"][0]["text"]


def run_arm(arm: str, observations: str, api_key: str, port: int) -> dict:
    prompt = build_prompt(arm, observations)
    record = {"arm": arm, "context_digest": digest(prompt)}
    text = call_gemma(prompt, api_key)
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        record.update(ok=False, failure="model output not JSON")
        return record
    OUT.mkdir(parents=True, exist_ok=True)
    spec_path = OUT / f"spec_{arm}.json"
    spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/vikunja_candidate_server.py"),
         str(spec_path), str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/vikunja_benchmark.py"),
             "--mode", "evaluate", "--candidate-url", f"http://127.0.0.1:{port}"],
            capture_output=True, text=True, timeout=600, cwd=ROOT)
        tail = result.stdout.strip().splitlines()[-1] if result.stdout else ""
        record.update(ok=True, evaluation=tail, spec_path=str(spec_path))
    finally:
        proc.terminate()
    return record


def live() -> int:
    api_key = os.environ.get("GEMMA_API_KEY")
    if not api_key:
        print("BLOCKED: GEMMA_API_KEY not set (rotated key required). "
              "Zero model calls made.")
        return 2
    observations = OBS.read_text(encoding="utf-8")
    results = {}
    for i, arm in enumerate(ARMS):
        results[arm] = run_arm(arm, observations, api_key, 3580 + i)
        print(json.dumps(results[arm]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gemma_arms_result.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["preflight", "live"], default="preflight")
    ap.add_argument("--confirm-live", action="store_true")
    args = ap.parse_args()
    if args.mode == "live":
        if not args.confirm_live:
            print("Live mode requires --confirm-live. Zero calls made.")
            return 2
        return live()
    return preflight()


if __name__ == "__main__":
    raise SystemExit(main())
