"""Genuine model experiment for the Vikunja benchmark (Gemma dev provider).

What this measures — honestly delimited:
  Arms A/B/C are a PROMPT-CONDITION comparison over fixed observations
  (prior-only vs observations vs coverage-grounded prompting). They are
  NOT active experimentation: the model does not choose what to observe.
  Arm D is the active experiment-selection arm: the model first chooses
  probes from a menu (outcomes unseen), those probes are executed
  against a fresh reference, and only then does it synthesize. D uses
  2 model calls; A/B/C use 1. That budget difference is recorded, not
  hidden.

What the model generates vs what the interpreter supplies:
  The model authors ONLY a declarative candidate spec (routes, methods,
  statuses, validation rules, permission levels, response fields —
  see vikunja_candidate_server.py). The generic interpreter supplies
  the state machine, storage, auth plumbing, permission enforcement
  and HTTP serving. This is spec-level reconstruction, not autonomous
  full-software generation, and results must be described that way.

Independence controls:
  Every arm gets a FRESH Vikunja instance (new SQLite DB in a temp
  dir, own port) and a fresh candidate process. Tokens are issued per
  instance; the reference rate limiter starts clean per arm. Scores
  are admitted only when the spec validates AND the evaluator exits 0
  with a parseable held-out line; otherwise the arm records a failure
  class and no score.

Provenance: provider "gemma-test" / PIPELINE_SMOKE_NOT_META.
Development evidence only; never a Meta result. Live mode requires
GEMMA_API_KEY (rotated; never the exposed key) and --confirm-live.
Preflight makes zero model calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
OBS = ROOT / ".runs" / "vikunja-benchmark" / "public_observations.json"
OUT = ROOT / ".runs" / "vikunja-model"
MODEL = "gemma-4-26b-a4b-it"
API = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
VIKUNJA_BIN = Path(os.environ.get(
    "VIKUNJA_BIN", r"C:\tmp\vikunja-bench\bin\vikunja-v2.4.0-windows-4.0-amd64.exe"))

SPEC_SCHEMA = """Candidate spec JSON schema (vikunja_candidate_server.py):
{"users": {"alice": "bench_alice", "bob": "bench_bob"},
 "auth": {"login_error_status": int, "login_error_body": obj,
          "unauthenticated_status": int, "unauthenticated_body": obj,
          "forbidden_body": obj, "not_found_body": obj},
 "routes": [{"method": "PUT|GET|POST", "path": "/projects|/projects/{pid}/tasks|/tasks/{tid}|/projects/{pid}/users|/user",
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

# Arm D probe menu: descriptions only — outcomes are NOT shown before
# selection. Actions use vikunja_benchmark action tuples; {bob_id} is
# resolved by the executor (identity plumbing, not model knowledge).
PROBE_MENU = {
    "D1_share_write": ("Share project with write permission, then the "
                       "second user toggles a task done",
                       [("PUT", "/projects", {"title": "Menu Share"}, "alice"),
                        ("PUT", "/projects/{pid}/tasks", {"title": "M task"}, "alice"),
                        ("PUT", "/projects/{pid}/users",
                         {"username": "bench_bob", "permission": 1}, "alice"),
                        ("POST", "/tasks/{tid}", {"done": True}, "bob"),
                        ("GET", "/tasks/{tid}", None, "alice")]),
    "D2_assignees": ("Assign the second user to a task and list assignees",
                     [("PUT", "/projects", {"title": "Menu Assign"}, "alice"),
                      ("PUT", "/projects/{pid}/tasks", {"title": "M task"}, "alice"),
                      ("PUT", "/tasks/{tid}/assignees", {"user_id": "{bob_id}"}, "alice"),
                      ("GET", "/tasks/{tid}/assignees", None, "alice")]),
    "D3_labels": ("Create a label, attach it to a task, list tasks",
                  [("PUT", "/projects", {"title": "Menu Label"}, "alice"),
                   ("PUT", "/projects/{pid}/tasks", {"title": "M task"}, "alice"),
                   ("PUT", "/labels", {"title": "menu-label"}, "alice"),
                   ("PUT", "/tasks/{tid}/labels", {"label_id": "{label_id}"}, "alice"),
                   ("GET", "/projects/{pid}/tasks", None, "alice")]),
    "D4_filter_done": ("List only completed tasks after toggling one done",
                       [("PUT", "/projects", {"title": "Menu Filter"}, "alice"),
                        ("PUT", "/projects/{pid}/tasks", {"title": "M1"}, "alice"),
                        ("POST", "/tasks/{tid}", {"done": True}, "alice"),
                        ("GET", "/projects/{pid}/tasks?filter=done%20%3D%20true",
                         None, "alice")]),
    "D5_update_fields": ("Change a task title and priority after creation",
                         [("PUT", "/projects", {"title": "Menu Upd"}, "alice"),
                          ("PUT", "/projects/{pid}/tasks", {"title": "Old"}, "alice"),
                          ("POST", "/tasks/{tid}",
                           {"title": "New", "priority": 4}, "alice"),
                          ("GET", "/tasks/{tid}", None, "alice")]),
    "D6_delete_task": ("Delete a task and fetch it afterwards",
                       [("PUT", "/projects", {"title": "Menu Del"}, "alice"),
                        ("PUT", "/projects/{pid}/tasks", {"title": "M task"}, "alice"),
                        ("DELETE", "/tasks/{tid}", None, "alice"),
                        ("GET", "/tasks/{tid}", None, "alice")]),
    "D7_unshare": ("Share read access, revoke it, then the second user reads",
                   [("PUT", "/projects", {"title": "Menu Unshare"}, "alice"),
                    ("PUT", "/projects/{pid}/tasks", {"title": "M task"}, "alice"),
                    ("PUT", "/projects/{pid}/users",
                     {"username": "bench_bob", "permission": 0}, "alice"),
                    ("DELETE", "/projects/{pid}/users/{bob_name}", None, "alice"),
                    ("GET", "/projects/{pid}/tasks", None, "bob")]),
}

KINDS = {"create_project", "list_projects", "create_task", "list_tasks",
         "update_task", "get_task", "share_project", "get_user"}
PERMISSIONS = {"owner", "owner_or_read", "owner_or_write", "any_auth"}


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def file_digest(path: Path) -> str:
    return digest(path.read_text(encoding="utf-8", errors="replace"))


def provenance() -> dict:
    return {
        "provider": "gemma-test", "classification": "PIPELINE_SMOKE_NOT_META",
        "model": MODEL,
        "interpreter_sha256": file_digest(SCRIPTS / "vikunja_candidate_server.py"),
        "evaluator_sha256": file_digest(SCRIPTS / "vikunja_benchmark.py"),
        "held_out_sha256": file_digest(SCRIPTS / "vikunja_held_out.py"),
        "model_authorship": "declarative candidate spec only",
        "interpreter_supplies": "state machine, storage, auth plumbing, "
                                "permission enforcement, HTTP serving",
    }


def validate_spec(spec) -> list[str]:
    errors = []
    if not isinstance(spec, dict):
        return ["spec is not a JSON object"]
    users = spec.get("users")
    if not isinstance(users, dict) or "alice" not in users or "bob" not in users:
        errors.append("users must map alice and bob")
    routes = spec.get("routes")
    if not isinstance(routes, list) or not routes:
        errors.append("routes missing or empty")
        return errors
    for i, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f"route {i} not an object")
            continue
        if route.get("method") not in ("GET", "PUT", "POST", "DELETE"):
            errors.append(f"route {i}: bad method")
        if not str(route.get("path", "")).startswith("/"):
            errors.append(f"route {i}: bad path")
        if route.get("kind") not in KINDS:
            errors.append(f"route {i}: unknown kind {route.get('kind')}")
        status = route.get("status")
        if not isinstance(status, int) or not 100 <= status <= 599:
            errors.append(f"route {i}: bad status")
        if "permission" in route and route["permission"] not in PERMISSIONS:
            errors.append(f"route {i}: bad permission")
        for rule in route.get("validate", []):
            if rule.get("rule") != "nonempty" or not rule.get("field"):
                errors.append(f"route {i}: unsupported validate rule")
    return errors


DROP_KEYS = {"views", "background_information", "background_blur_hash"}


def compact_observations(observations: str) -> str:
    """Model-visible observations with UI-view payloads removed.

    Views are default frontend configuration, not contract behavior
    the bounded subsystem must reproduce field-for-field in prompts;
    dropping them cut Arm B/C/D prompts from ~17KB of raw JSON to a
    size the dev provider answers reliably. Statuses, error bodies,
    permissions and all entity fields are preserved verbatim.
    """
    try:
        data = json.loads(observations)
    except json.JSONDecodeError:
        return observations

    def strip(value):
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k == "views" and isinstance(v, list):
                    # Summarized: kind/title/position survive; the
                    # multi-KB default filter/bucket payload does not.
                    out[k] = [{kk: vv for kk, vv in item.items()
                               if kk in ("title", "view_kind", "position",
                                         "bucket_configuration_mode")}
                              for item in v if isinstance(item, dict)]
                elif k not in DROP_KEYS:
                    out[k] = strip(v)
            return out
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    return json.dumps(strip(data), indent=1)


JSON_FIRST = (
    "OUTPUT FORMAT (hard requirement): the FIRST character of your "
    "response MUST be '{' and the entire response MUST be that single "
    "JSON object. No analysis, no prose, no markdown fences, and no "
    "explanation before or after the JSON.")


def field_inventory_text(observations) -> str:
    """Generic field inventory for the prompt (observed data only).

    Delegates to scripts/field_inventory.py — the single generic
    extractor for any HTTP target (per method+route+status class:
    field names, value classes, one observed exemplar per field).
    No target-specific field names live here; swapping the
    observations for a different app's changes only the data.
    """
    if isinstance(observations, str):
        try:
            observations = json.loads(observations)
        except json.JSONDecodeError:
            return ""
    if not isinstance(observations, list) or not observations:
        return ""
    import field_inventory
    return field_inventory.inventory_prompt_block(observations)


def build_prompt(arm: str, observations: str, extra_obs: str = "") -> str:
    parts = [INTERFACE, SPEC_SCHEMA, ARMS.get(arm, ARMS["C_grounded"])]
    if arm != "A_prior":
        parts.append("OBSERVATIONS (public probes, authorized):\n"
                     + compact_observations(observations))
        inventory = field_inventory_text(observations)
        if inventory:
            parts.append(inventory)
    if extra_obs:
        parts.append("ADDITIONAL OBSERVATIONS (probes you selected):\n" + extra_obs)
        extra_inventory = field_inventory_text(extra_obs)
        if extra_inventory:
            parts.append(extra_inventory)
    parts.append(JSON_FIRST)
    return "\n\n".join(parts)


def build_selection_prompt(observations: str) -> str:
    menu = "\n".join(f"{k}: {v[0]}" for k, v in PROBE_MENU.items())
    return (INTERFACE + "\n\nYou may request up to 6 additional probes "
            "before reconstructing. You see descriptions only, not "
            "outcomes. Choose the probes that would most reduce your "
            "uncertainty about the contract.\n\nMENU:\n" + menu +
            "\n\nOBSERVATIONS SO FAR:\n" + compact_observations(observations) +
            '\n\nReturn ONLY JSON: {"probes": ["D1_share_write", ...]}'
            "\n\n" + JSON_FIRST)


def preflight() -> int:
    observations = OBS.read_text(encoding="utf-8") if OBS.exists() else ""
    report = {"kind": "VIKUNJA_MODEL_PREFLIGHT_V2", **provenance(),
              "calls_planned": {"A_prior": 1, "B_observations": 1,
                                "C_grounded": 1, "D_active": 2},
              "arm_semantics": "A/B/C prompt-condition comparison; "
                               "D active experiment-selection",
              "held_out_in_prompts": False,
              "observations_bytes": len(observations),
              "vikunja_binary_present": VIKUNJA_BIN.exists()}
    for arm in ARMS:
        prompt = build_prompt(arm, observations)
        report.setdefault("arms", {})[arm] = {
            "context_digest": digest(prompt), "prompt_chars": len(prompt)}
    sel = build_selection_prompt(observations)
    report["arms"]["D_active"] = {"selection_digest": digest(sel),
                                  "menu": sorted(PROBE_MENU)}
    key = os.environ.get("GEMMA_API_KEY")
    report["gemma_key_present"] = bool(key)
    report["live_ready"] = bool(key) and VIKUNJA_BIN.exists()
    if not key:
        report["blocker"] = ("GEMMA_API_KEY not set. Set the ROTATED key "
                             "locally; the previously exposed key must not "
                             "be reused. Zero model calls made.")
    print(json.dumps(report, indent=1))
    return 0


def call_gemma(prompt: str, api_key: str) -> str:
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "maxOutputTokens": 16000,
                                 "temperature": 0.2}}
    req = urllib.request.Request(
        API.format(m=MODEL), data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-goog-api-key", api_key)
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def parse_model_json(text: str):
    """Strict parse, then fence-strip, then embedded-object extraction.

    Extraction never invents fields: it only locates a COMPLETE JSON
    object the model emitted (Gemma characteristically analyses in
    prose first). The parse mode is recorded with every result, so an
    embedded_json admission is never disguised as strict compliance.
    Anything else is MODEL_OUTPUT_NOT_JSON, raw text preserved.
    """
    try:
        return json.loads(text), "strict"
    except json.JSONDecodeError:
        pass
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
        try:
            return json.loads(stripped), "fence_stripped"
        except json.JSONDecodeError:
            pass
    decoder = json.JSONDecoder()
    best = None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("routes"), list):
            best = obj  # keep the LAST complete spec-shaped object
    if best is not None:
        return best, "embedded_json"
    return None, "unparseable"


def start_reference(port: int):
    import vikunja_benchmark as vb
    workdir = Path(tempfile.mkdtemp(prefix=f"vikunja-arm-{port}-"))
    # Per-arm config file: explicit port + fresh SQLite DB, so an arm can
    # never silently talk to a shared long-running instance.
    (workdir / "config.yml").write_text(
        "service:\n"
        f"  interface: \":{port}\"\n"
        f"  publicurl: \"http://127.0.0.1:{port}/\"\n"
        "  secret: \"arm-local-secret\"\n"
        "  enableregistration: true\n"
        "database:\n"
        "  type: \"sqlite\"\n"
        f"  path: \"{(workdir / 'vikunja.db').as_posix()}\"\n"
        "files:\n"
        f"  basepath: \"{(workdir / 'files').as_posix()}\"\n",
        encoding="utf-8")
    proc = subprocess.Popen([str(VIKUNJA_BIN)], cwd=workdir,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            status, _ = vb.call("GET", "/info", base=base + "/api/v1")
            if status == 200:
                return proc, workdir, base
        except Exception:
            pass
        time.sleep(1)
    proc.terminate()
    raise RuntimeError("reference did not come up")


def stop_reference(proc, workdir):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    shutil.rmtree(workdir, ignore_errors=True)


def evaluate_spec(arm: str, spec, ref_base: str, cand_port: int) -> dict:
    record: dict = {}
    errors = validate_spec(spec)
    record["spec_digest"] = digest(json.dumps(spec, sort_keys=True))
    if errors:
        record.update(admitted=False, failure_class="SCHEMA_REJECTED",
                      schema_errors=errors)
        return record
    OUT.mkdir(parents=True, exist_ok=True)
    spec_path = OUT / f"spec_{arm}.json"
    spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPTS / "vikunja_candidate_server.py"),
         str(spec_path), str(cand_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "vikunja_benchmark.py"),
             "--mode", "evaluate",
             "--reference-url", ref_base,
             "--candidate-url", f"http://127.0.0.1:{cand_port}"],
            capture_output=True, text=True, timeout=900, cwd=ROOT)
        record["cases"] = [
            {"case": int(n), "passed": verdict == "PASS"}
            for n, verdict in re.findall(
                r"case (\d+): (PASS|FAIL)", result.stdout or "")]
        match = re.search(r"held-out: (\d+)/(\d+)", result.stdout or "")
        # Evaluator exit 1 = candidate failed cases (a valid measured
        # result); only an unparseable run or other exit is an error.
        if not match or result.returncode not in (0, 1):
            record.update(admitted=False, failure_class="EVALUATOR_ERROR",
                          evaluator_exit=result.returncode,
                          stderr_tail=(result.stderr or "")[-400:])
            return record
        record.update(admitted=True, failure_class=None,
                      passed=int(match.group(1)), total=int(match.group(2)),
                      spec_path=str(spec_path))
        return record
    finally:
        proc.terminate()


def execute_menu_probes(selected, ref_base):
    """Execute model-selected probes step by step against the reference.

    Ids resolve as each sequence unfolds ({pid}/{tid} from responses,
    {bob_id}/{label_id} as typed ints) — including in paths (D7).
    """
    import vikunja_benchmark as vb
    base = ref_base + "/api/v1"
    tokens = vb.fresh_tokens(base)
    _, bob_user = vb.call("GET", "/user", None, tokens["bob"], base=base)
    ids = {"bob_id": bob_user.get("id") if isinstance(bob_user, dict) else 0,
           "label_id": 0, "pid": 0, "tid": 0}
    observations = []
    for probe_id in selected:
        if probe_id not in PROBE_MENU:
            continue
        ids["pid"] = ids["tid"] = 0
        for method, path_tpl, body, who in PROBE_MENU[probe_id][1]:
            path = (path_tpl.replace("{bob_id}", str(ids["bob_id"]))
                    .replace("{bob_name}", "bench_bob")
                    .format(pid=ids["pid"], tid=ids["tid"]))
            if body:
                body = {k: (ids["bob_id"] if v == "{bob_id}"
                            else ids["label_id"] if v == "{label_id}" else v)
                        for k, v in body.items()}
            status, out = vb.call(method, path, body, tokens.get(who), base=base)
            if isinstance(out, dict) and "id" in out:
                segments = [s for s in path_tpl.split("/") if s]
                if segments == ["projects"]:
                    ids["pid"] = out["id"]
                elif "tasks" in segments and method in ("PUT", "POST"):
                    ids["tid"] = out["id"]
                elif segments == ["labels"]:
                    ids["label_id"] = out["id"]
            observations.append({"probe": probe_id,
                                 "action": f"{method} {path_tpl}", "as": who,
                                 "status": status, "body": out})
    return observations


def run_arm(arm: str, observations: str, api_key: str,
            ref_port: int, cand_port: int) -> dict:
    record = {"arm": arm, **provenance()}
    proc = workdir = None
    try:
        proc, workdir, ref_base = start_reference(ref_port)
        record["reference"] = "fresh Vikunja instance, new SQLite DB"
        extra_obs = ""
        calls = 0
        if arm == "D_active":
            sel_prompt = build_selection_prompt(observations)
            record["selection_digest"] = digest(sel_prompt)
            raw = call_gemma(sel_prompt, api_key)
            calls += 1
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "raw_D_selection.txt").write_text(raw, encoding="utf-8")
            parsed, _ = parse_model_json(raw)
            selected = (parsed.get("probes", [])[:6]
                        if isinstance(parsed, dict) else [])
            record["selected_probes"] = selected
            found = execute_menu_probes(selected, ref_base)
            record["probe_observations"] = len(found)
            extra_obs = json.dumps(found, indent=1)
            prompt_arm = "C_grounded"
        else:
            prompt_arm = arm
        prompt = build_prompt(prompt_arm, observations, extra_obs)
        record["context_digest"] = digest(prompt)
        text = call_gemma(prompt, api_key)
        calls += 1
        record["model_calls"] = calls
        OUT.mkdir(parents=True, exist_ok=True)
        raw_path = OUT / f"raw_{arm}.txt"
        raw_path.write_text(text, encoding="utf-8")
        record["raw_output"] = str(raw_path)
        spec, how = parse_model_json(text)
        record["json_parse"] = how
        if spec is None:
            record.update(admitted=False, failure_class="MODEL_OUTPUT_NOT_JSON")
            return record
        record.update(evaluate_spec(arm, spec, ref_base, cand_port))
        return record
    except Exception as exc:  # infrastructure failure, recorded honestly
        record.update(admitted=False, failure_class="INFRASTRUCTURE",
                      error=f"{type(exc).__name__}: {exc}")
        return record
    finally:
        if proc is not None:
            stop_reference(proc, workdir)


ALL_ARMS = ["A_prior", "B_observations", "C_grounded", "D_active"]


def live(arms=None) -> int:
    api_key = os.environ.get("GEMMA_API_KEY")
    if not api_key:
        print("BLOCKED: GEMMA_API_KEY not set (rotated key required). "
              "Zero model calls made.")
        return 2
    if not VIKUNJA_BIN.exists():
        print(f"BLOCKED: Vikunja binary missing at {VIKUNJA_BIN}. "
              "Zero model calls made.")
        return 2
    arms = list(arms) if arms else ALL_ARMS
    unknown = [a for a in arms if a not in ALL_ARMS]
    if unknown:
        print(f"BLOCKED: unknown arms {unknown}. Zero model calls made.")
        return 2
    observations = OBS.read_text(encoding="utf-8")
    results = {}
    for i, arm in enumerate(arms):
        results[arm] = run_arm(arm, observations, api_key, 3460 + i, 3580 + i)
        print(json.dumps(results[arm]))
    OUT.mkdir(parents=True, exist_ok=True)
    # A subset rerun never overwrites the full-run record.
    name = ("gemma_arms_result.json" if arms == ALL_ARMS
            else "gemma_arms_result_rerun.json")
    (OUT / name).write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["preflight", "live"], default="preflight")
    ap.add_argument("--confirm-live", action="store_true")
    ap.add_argument("--arms", default="",
                    help="comma-separated subset of arms to run live "
                         "(default: all arms)")
    args = ap.parse_args()
    if args.mode == "live":
        if not args.confirm_live:
            print("Live mode requires --confirm-live. Zero calls made.")
            return 2
        arms = [a.strip() for a in args.arms.split(",") if a.strip()] or None
        return live(arms)
    return preflight()


if __name__ == "__main__":
    raise SystemExit(main())
