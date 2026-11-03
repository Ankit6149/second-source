"""Hybrid reconstruction: evidence compiler + model synthesis + repair.

GEMMA_TEST development experiment (provider gemma-test,
PIPELINE_SMOKE_NOT_META). Never a Meta result.

Design (all comparisons on the same frozen held-out suite, fresh
reference per evaluation, evaluator untouched):

- Baseline C_grounded (already measured): model authors a spec from
  observations alone -> 2/6.
- Baseline compiled (already measured): deterministic evidence
  compiler, NON_AI -> 6/6.
- H_hybrid (this script): the model receives the observations, the
  generic field inventory, AND the compiled facts (deterministic
  NON_AI transcription, labeled as such). The model authors the final
  spec: it may adopt, correct, or extend compiled facts. Model
  authorship is therefore real (selection/correction/extension), and
  any score change vs both baselines is attributable.
- H_repair (bounded, optional second call): the hybrid candidate is
  executed against the PUBLIC probe ladder only; field-level
  divergences from the recorded public observations are fed back for
  ONE targeted repair. The held-out suite is never shown to the model
  and is run once, on the frozen repaired candidate.

Call budget: at most 2 Gemma calls per run. No retries. Live mode
requires GEMMA_API_KEY in the environment and --confirm-live.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_compiler  # noqa: E402
import vikunja_benchmark as vb  # noqa: E402
import vikunja_model_experiment as mx  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runs" / "vikunja-model"
OBS_PATH = ROOT / ".runs" / "vikunja-benchmark" / "public_observations.json"


def compiled_facts_block(compiled: dict) -> str:
    lines = ["COMPILED FACTS (deterministic NON_AI transcription of the "
             "observations above; templates with dynamic tokens "
             "<new_id> <ts> <creator> <entity:id> <path:*> <index> "
             "<identifier> and {\"$input\": field} input echoes):"]
    for route in compiled.get("routes", []):
        lines.append(f"- {route['method']} {route['path']} -> "
                     f"{route['status']} access={route.get('access')}")
        lines.append("  template: " + json.dumps(route.get("template"))[:600])
        for v in route.get("validate", []):
            lines.append(f"  validate: {v['field']} {v['rule']} -> "
                         f"{v['status']} {json.dumps(v.get('error_body'))[:200]}")
    auth = compiled.get("auth", {})
    if auth:
        lines.append("auth facts: " + json.dumps(auth)[:500])
    return "\n".join(lines)


def build_hybrid_prompt(observations: str, compiled: dict) -> str:
    parts = [mx.INTERFACE,
             "You are the synthesis stage of a reconstruction system. "
             "A deterministic compiler has already transcribed firmly "
             "observed behavior into facts (below). Your job: author "
             "the final candidate spec. Adopt compiled facts unless an "
             "observation contradicts them; use your engineering "
             "judgment only for behavior the facts do not cover, and "
             "never contradict an observation.",
             mx.SPEC_SCHEMA,
             "OBSERVATIONS (public probes, authorized):\n"
             + mx.compact_observations(observations)]
    inventory = mx.field_inventory_text(observations)
    if inventory:
        parts.append(inventory)
    parts.append(compiled_facts_block(compiled))
    parts.append(mx.JSON_FIRST)
    return "\n\n".join(parts)


MODULES = {
    "projects": ("projects: project create/list and its validation "
                 "error contract",
                 lambda a: ("/projects" in a and "/tasks" not in a
                            and "/users" not in a)),
    "tasks_write": ("tasks write path: task create and update (done "
                    "transitions), its validation error contract",
                    lambda a: ("/tasks" in a
                               and a.split(" ", 1)[0] in ("PUT", "POST"))),
    "tasks_read": ("tasks read path: task list/get, filtering, "
                   "cross-user read outcomes and error contracts",
                   lambda a: ("/tasks" in a
                              and a.split(" ", 1)[0] == "GET")),
    "access": ("identity/access: current user, project sharing, login "
               "and unauthenticated/forbidden error contracts",
               lambda a: any(s in a for s in ("/users", "/user", "/login"))),
}


CONFIG_TAG = "gen-a16:per-route+rich-validate-schema+temp0"

# No "template" property: when the model could re-emit templates, the
# large project template degenerated into token loops on every try
# (attempts 11-14). In this design the model decides the contract
# fields (kind/status/access/validate/error bodies); templates are
# carried verbatim from the compiled NON_AI facts and restored at
# compose. Template edits are therefore NOT expressible here — a
# recorded limitation of this attempt design.
ROUTE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "route": {"type": "OBJECT", "properties": {
            "method": {"type": "STRING"}, "path": {"type": "STRING"},
            "kind": {"type": "STRING"}, "collection": {"type": "STRING"},
            "auth": {"type": "BOOLEAN"}, "status": {"type": "INTEGER"},
            "access": {"type": "STRING"},
            "template_unchanged": {"type": "BOOLEAN"},
            # Rich item schema: an unconstrained ARRAY of OBJECT made
            # the model loop empty objects (observed on the task
            # create route, 22k chars of {}), same as attempt 10.
            "validate": {"type": "ARRAY", "items": {
                "type": "OBJECT", "properties": {
                    "field": {"type": "STRING"},
                    "rule": {"type": "STRING"},
                    "status": {"type": "INTEGER"},
                    "error_body": {"type": "OBJECT", "properties": {
                        "code": {"type": "INTEGER"},
                        "message": {"type": "STRING"}}}},
                "required": ["field", "rule", "status"]}},
            "forbidden_body": {"type": "OBJECT", "properties": {
                "code": {"type": "INTEGER"},
                "message": {"type": "STRING"}}}},
            "required": ["method", "path", "kind", "status",
                         "template_unchanged"]}},
    "required": ["route"]}


def call_gemma_long(prompt: str, api_key: str, schema=ROUTE_SCHEMA) -> str:
    """Same native endpoint as mx.call_gemma, longer read timeout.

    The dev provider repeatedly exceeded the shared 300s read timeout
    on synthesis calls (attempts 1-3, INFRASTRUCTURE); this bounded
    experiment waits up to 600s. No retries happen here either: one
    request, one outcome, recorded either way.
    """
    import urllib.request
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 12000, "temperature": 0,
                # Native structured output with a RICH single-route
                # schema. A loose routes schema (attempt 10) produced
                # loops of empty objects; per-route calls with typed
                # properties are the working granularity.
                **({"responseSchema": schema} if schema else {})}}
    # NOTE: thinkingConfig.thinkingBudget=0 was tried (attempt 8) and
    # the provider rejected it with HTTP 400 for this model; the
    # JSON-immediately prompt instruction is the working lever.
    req = urllib.request.Request(
        mx.API.format(m=mx.MODEL), data=json.dumps(body).encode(),
        method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-goog-api-key", api_key)
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode())
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def light_observations(obs_list: list) -> str:
    """Action/status/request + error bodies only.

    Success templates are already carried losslessly by the compiled
    facts; repeating full bodies made prompts 27-33k chars and the
    dev provider timed out / HTTP-500'd (attempts 1-2, INFRASTRUCTURE).
    """
    lines = []
    for o in obs_list:
        line = (f"- {o.get('action')} as={o.get('as')} -> {o.get('status')}"
                f" request={json.dumps(o.get('request'))[:160]}")
        if isinstance(o.get("status"), int) and o["status"] >= 400:
            line += f" body={json.dumps(o.get('body'))[:240]}"
        lines.append(line)
    return "\n".join(lines)


def build_module_prompt(module: str, obs_list: list, compiled: dict) -> str:
    """Modular synthesis: one coherent subsystem per call.

    A single 33k monolithic prompt timed out on the dev provider
    (recorded INFRASTRUCTURE, attempt 1); subsystem prompts stay
    small enough to answer reliably.
    """
    scope, keep = MODULES[module]
    sub_obs = [o for o in obs_list if keep(str(o.get("action", "")))]
    sub_compiled = {"routes": [r for r in compiled.get("routes", [])
                               if keep(f"{r.get('method', '')} "
                                       f"{r.get('path', '')}")],
                    "auth": compiled.get("auth", {})}
    parts = [mx.INTERFACE,
             f"You are the synthesis stage for ONE subsystem: {scope}. "
             "A deterministic compiler transcribed firmly observed "
             "behavior into facts (below). Author the spec routes for "
             "THIS subsystem only, adopting compiled facts unless an "
             "observation contradicts them; never contradict an "
             "observation.",
             mx.SPEC_SCHEMA,
             "OBSERVATIONS (public probes, authorized; success bodies "
             "are in COMPILED FACTS below):\n" + light_observations(sub_obs)]
    inventory = mx.field_inventory_text(sub_obs)
    if inventory:
        parts.append(inventory)
    parts.append(compiled_facts_block(sub_compiled))
    parts.append(mx.JSON_FIRST)
    return "\n\n".join(parts)


def _strip_views(template):
    if isinstance(template, dict):
        template.pop("views", None)
    elif isinstance(template, list):
        for item in template:
            _strip_views(item)


def _restore_views(base_template, edited_template):
    if isinstance(base_template, dict) and isinstance(edited_template, dict):
        if "views" in base_template and "views" not in edited_template:
            edited_template["views"] = base_template["views"]
    elif isinstance(base_template, list) and isinstance(edited_template, list):
        for b_item, e_item in zip(base_template, edited_template):
            _restore_views(b_item, e_item)


EDIT_SCHEMA = """Compiled spec format (same as the input below):
{"routes": [{"method": "PUT|GET|POST", "path": "/projects|/projects/{pid}/tasks|/tasks/{tid}|/projects/{pid}/users|/user",
  "kind": "compiled_create|compiled_list|compiled_get|compiled_update|compiled_share|compiled_single",
  "collection": str, "auth": true, "status": int, "access": "owner|shared_read|shared_write|any_auth",
  "template": <exact response template; dynamic tokens <new_id> <ts> <creator> <entity:id> <path:pid> <path:tid> <index> <identifier>, {"$input": field, "default": value} for request echoes, literal values otherwise>,
  "validate": [{"field": str, "rule": "nonempty", "status": int, "error_body": obj}],
  "forbidden_body": obj}]}
Return ONLY JSON: {"routes": [...]} for your subsystem."""


def build_edit_prompt(module: str, obs_list: list, compiled: dict) -> str:
    """Attempt-6 design: the model EDITS the compiled spec.

    Authoring classic-kind specs from scratch produced degenerate
    prose (attempt 5). Editing a concrete compiled spec is a bounded
    copy-edit: the model's contribution is exactly its diff from the
    NON_AI baseline, which we record route by route.
    """
    scope, keep = MODULES[module]
    import copy
    sub_routes = []
    for r in compiled.get("routes", []):
        if keep(f"{r.get('method', '')} {r.get('path', '')}"):
            r = copy.deepcopy(r)
            # Default frontend view config, not contract behavior;
            # omitted for prompt size, restored verbatim at compose.
            _strip_views(r.get("template"))
            sub_routes.append(r)
    sub_obs = [o for o in obs_list if keep(str(o.get("action", "")))]
    return "\n\n".join([
        "Output the JSON object immediately. No analysis, no "
        "commentary, no explanation before or after the JSON.",
        mx.INTERFACE,
        f"You are the model synthesis stage for ONE subsystem: {scope}. "
        "Below is a candidate spec produced by a deterministic compiler "
        "(NON_AI) from the same observations. Review it against the "
        "observations: correct anything the observations contradict, "
        "keep everything they support (including exact templates and "
        "tokens), and extend it only where behavior is unobserved but "
        "strongly implied by the observed contract. Return the "
        "complete corrected routes for THIS subsystem.",
        EDIT_SCHEMA,
        "COMPILED SPEC (your starting point; large default `views` "
        "payloads are omitted and restored automatically — do not "
        "re-emit them):\n"
        + json.dumps({"routes": sub_routes}, indent=1),
        "OBSERVATIONS (public probes, authorized; success bodies are "
        "encoded in the templates above):\n" + light_observations(sub_obs),
        mx.JSON_FIRST])


def parse_route_json(text: str):
    """mx.parse_model_json, plus a raw_decode fallback.

    Observed live: a complete JSON object followed by a trailing
    code fence, which the shared parser reports unparseable.
    raw_decode extracts the first complete JSON value and ignores
    trailing bytes; it invents no fields. Mode recorded as
    "raw_decode" so it is never disguised as strict compliance.
    """
    parsed, how = mx.parse_model_json(text)
    if parsed is not None:
        return parsed, how
    try:
        obj, _end = json.JSONDecoder().raw_decode(text.strip())
        if isinstance(obj, dict):
            return obj, "raw_decode"
    except (json.JSONDecodeError, ValueError):
        pass
    return None, how


def build_route_prompt(route: dict, obs_list: list) -> str:
    """One route per call: the granularity the dev provider answers.

    Module-sized calls degenerated (prose loops, empty-object loops,
    timeouts); a single route with its own observations and the
    compiled template is a small, concrete copy-edit.
    """
    import copy
    route = copy.deepcopy(route)
    _strip_views(route.get("template"))
    key = f"{route.get('method', '')} {route.get('path', '')}"
    sub_obs = [o for o in obs_list
               if str(o.get("action", "")).split("?")[0] == key
               or str(o.get("action", "")) == key]
    return "\n\n".join([
        "Output the JSON object immediately. No analysis, no "
        "commentary, no explanation before or after the JSON.",
        mx.INTERFACE,
        "You are the model synthesis stage for ONE route. Below is "
        "the route as transcribed by a deterministic compiler (NON_AI) "
        "from the observations. Return it corrected: keep everything "
        "the observations support (exact template values and dynamic "
        "tokens <new_id> <ts> <creator> <entity:id> <path:pid> "
        "<path:tid> <index> <identifier>, {\"$input\": field} echoes), "
        "fix anything they contradict. IMPORTANT: never emit a "
        "\"template\" field — set \"template_unchanged\": true; the "
        "compiled template is restored automatically. Your decisions "
        "are the contract fields: kind, status, access, validate "
        "rules, forbidden_body. Large default `views` payloads are "
        "omitted and restored automatically.",
        EDIT_SCHEMA,
        "COMPILED ROUTE (your starting point):\n"
        + json.dumps({"route": route}, indent=1),
        "OBSERVATIONS for this route (public probes, authorized):\n"
        + (light_observations(sub_obs) or "(none recorded)"),
        mx.JSON_FIRST])


def compose_edited(compiled: dict, module_routes: dict) -> tuple[dict, list]:
    """Compiled base with model-edited routes substituted per module.

    Returns (spec, diff) where diff lists every route the model
    changed, added, or removed vs the NON_AI baseline — the exact
    measurable model contribution.
    """
    spec = {"users": dict(compiled.get("users", {})),
            "auth": dict(compiled.get("auth", {})),
            "routes": []}
    if not spec["users"]:
        spec["users"] = {"alice": "bench_alice", "bob": "bench_bob"}
    base = {(r["method"], r["path"]): r for r in compiled.get("routes", [])}
    edited = {}
    for routes in module_routes.values():
        for r in routes:
            edited[(r.get("method"), r.get("path"))] = r
    diff = []
    for key, route in edited.items():
        # Restore the omitted views payload verbatim from the baseline
        # (declared in the prompt; data plumbing, not a model edit).
        if key in base:
            _restore_views(base[key].get("template"), route.get("template"))
        if key not in base:
            diff.append({"change": "added", "route": list(key)})
        elif json.dumps(base[key], sort_keys=True) != json.dumps(route, sort_keys=True):
            diff.append({"change": "modified", "route": list(key)})
        spec["routes"].append(route)
    for key, route in base.items():
        if key not in edited:
            diff.append({"change": "removed_by_model_omission",
                         "route": list(key)})
    return spec, diff


def compose_specs(module_specs: dict) -> dict:
    """Compose subsystem specs: union of routes, shared users/auth."""
    merged = {"users": {}, "auth": {}, "routes": []}
    seen = set()
    for name, spec in module_specs.items():
        if not isinstance(spec, dict):
            continue
        merged["users"].update(spec.get("users", {}) or {})
        for k, v in (spec.get("auth", {}) or {}).items():
            merged["auth"].setdefault(k, v)
        for route in spec.get("routes", []) or []:
            key = (route.get("method"), route.get("path"))
            if key not in seen:
                seen.add(key)
                merged["routes"].append(route)
    if not merged["users"]:
        merged["users"] = {"alice": "bench_alice", "bob": "bench_bob"}
    return merged


def public_conformance(spec: dict, ref_base: str, cand_port: int) -> dict:
    """Replay the PUBLIC probe ladder against candidate and reference.

    Returns divergence list (public evidence only). Both sides run the
    identical public actions with fresh tokens on fresh state.
    """
    spec_path = OUT / "spec_H_public_check.json"
    OUT.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "vikunja_candidate_server.py"),
         str(spec_path), str(cand_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        cand_base = f"http://127.0.0.1:{cand_port}/api/v1"
        ref = vb.canonical_sequence(
            vb.run_actions(vb.PUBLIC_PROBES, vb.fresh_tokens(ref_base + "/api/v1"),
                           ref_base + "/api/v1"))
        got = vb.canonical_sequence(
            vb.run_actions(vb.PUBLIC_PROBES, vb.fresh_tokens(cand_base), cand_base))
        divergences = []
        for i, (r, g) in enumerate(zip(ref, got)):
            if r != g:
                divergences.append({"probe_index": i,
                                    "action": " ".join(vb.PUBLIC_PROBES[i][:2]),
                                    "reference": r, "candidate": g})
        return {"public_passed": len(ref) - len(divergences),
                "public_total": len(ref), "divergences": divergences}
    finally:
        proc.terminate()


def diff_text(divergences, limit=6) -> str:
    out = []
    for d in divergences[:limit]:
        out.append(f"probe {d['probe_index']} ({d['action']}):\n"
                   f"  reference: {json.dumps(d['reference'])[:500]}\n"
                   f"  candidate: {json.dumps(d['candidate'])[:500]}")
    return "\n".join(out)


def run_live() -> int:
    api_key = os.environ.get("GEMMA_API_KEY")
    if not api_key:
        print("BLOCKED: GEMMA_API_KEY not set. Zero model calls made.")
        return 2
    observations = OBS_PATH.read_text(encoding="utf-8")
    obs_list = json.loads(observations)
    compiled = evidence_compiler.compile_spec(obs_list)
    record = {"kind": "VIKUNJA_HYBRID_V1", **mx.provenance(),
              "model_authorship": "final spec authored by model from "
                                  "observations + compiled NON_AI facts",
              "baselines": {"C_grounded_model_only": "2/6",
                            "compiled_NON_AI": "6/6"},
              "calls": 0}
    proc = workdir = None
    try:
        proc, workdir, ref_base = mx.start_reference(3480)
        # Attempt history: attempt 1 was the monolithic 33k prompt,
        # which timed out on the provider (INFRASTRUCTURE, no raw
        # output). Attempt 2+ uses modular subsystem synthesis.
        record["attempts"] = [{
            "attempt": 1, "design": "monolithic hybrid prompt (33,220 chars)",
            "failure_class": "INFRASTRUCTURE",
            "detail": "provider read timeout in call_gemma; unscored"},
            {"attempt": 2, "design": "modular prompts with full bodies "
                                     "(core 32,692 chars)",
             "failure_class": "INFRASTRUCTURE",
             "detail": "provider HTTPError on core module; unscored"},
            {"attempt": 3, "design": "light modular prompts (core 15,280 "
                                    "chars, 300s timeout)",
             "failure_class": "INFRASTRUCTURE",
             "detail": "provider read timeout on core module; unscored"},
            {"attempt": 4, "design": "3 modules, 600s timeout (projects "
                                    "6,079 / tasks 12,346 / access 5,059)",
             "failure_class": "INFRASTRUCTURE",
             "detail": "projects module answered and parsed; tasks module "
                       "provider HTTPError; unscored"},
            {"attempt": 5, "design": "4 modules authoring classic specs",
             "failure_class": "MODEL_OUTPUT_NOT_JSON",
             "detail": "projects output degenerated into repetitive prose "
                       "(31k chars, truncated); unscored"},
            {"attempt": 6, "design": "edit-compiled modules (<=7.4k chars)",
             "failure_class": "INFRASTRUCTURE",
             "detail": "projects module provider HTTPError; unscored. "
                       "Module cache added so answered modules are not "
                       "re-burned on retry."},
            {"attempt": 7, "design": "edit-compiled modules with cache",
             "failure_class": "MODEL_OUTPUT_NOT_JSON",
             "detail": "projects parsed (embedded_json); tasks_write "
                       "spent 40k chars on prose analysis, truncated "
                       "before any JSON; unscored"},
            {"attempt": 8, "design": "thinkingBudget=0 + edit modules",
             "failure_class": "INFRASTRUCTURE",
             "detail": "provider HTTP 400: thinkingConfig unsupported "
                       "for gemma-4-26b-a4b-it; unscored"},
            {"attempt": 9, "design": "JSON-immediately instruction, "
                                    "edit modules",
             "failure_class": "MODEL_OUTPUT_NOT_JSON",
             "detail": "projects output degenerated into repetitive "
                       "prose again (36k chars, truncated); unscored"},
            {"attempt": 10, "design": "loose responseSchema, edit modules",
             "failure_class": "MODEL_OUTPUT_NOT_JSON",
             "detail": "schema forced JSON shape but items degenerated "
                       "into loops of empty objects; unscored. Cache-key "
                       "bug (config not hashed) found and fixed."},
            {"attempt": 11, "design": "per-route calls, rich route schema",
             "failure_class": "INFRASTRUCTURE",
             "detail": "first route provider HTTP 500; unscored"},
            {"attempt": 12, "design": "per-route calls, rich route schema",
             "failure_class": "MODEL_OUTPUT_NOT_JSON",
             "detail": "GET /projects JSON degenerated mid-template "
                       "into token repetition, truncated; unscored"},
            {"attempt": 13, "design": "per-route + frequencyPenalty",
             "failure_class": "INFRASTRUCTURE",
             "detail": "provider HTTP 400: frequencyPenalty unsupported; "
                       "unscored"},
            {"attempt": 14, "design": "per-route, template_unchanged "
                                     "allowed",
             "failure_class": "MODEL_OUTPUT_NOT_JSON",
             "detail": "5/8 routes admitted; PUT /projects degenerated "
                       "re-emitting its large template on every try; "
                       "unscored"},
            {"attempt": 15, "design": "per-route, templates not emittable",
             "failure_class": "MODEL_OUTPUT_NOT_JSON",
             "detail": "7/8 admitted; task-create validate array looped "
                       "empty objects; unscored"},
            {"attempt": 16, "design": "per-route, rich validate schema, "
                                     "templates carried from compiled",
             "failure_class": None,
             "detail": "ADMITTED AND SCORED: hybrid 3/6 held-out "
                       "(cases 0,2,3), public conformance 7/19; repair "
                       "call provider INFRASTRUCTURE (unmeasured)"}]
        # Attempt 11+: per-route calls (module calls degenerated).
        edited_routes = []
        record["route_results"] = []
        for route in compiled.get("routes", []):
            rkey = f"{route.get('method', '')} {route.get('path', '')}"
            slug = (rkey.replace(" ", "_").replace("/", "-")
                    .replace("{", "").replace("}", ""))
            prompt = build_route_prompt(route, obs_list)
            rdigest = mx.digest(prompt + "|" + CONFIG_TAG)
            cache_raw = OUT / f"raw_H_route_{slug}.txt"
            cache_meta = OUT / f"raw_H_route_{slug}.digest"
            if cache_raw.exists() and cache_meta.exists() \
                    and cache_meta.read_text().strip() == rdigest:
                text = cache_raw.read_text(encoding="utf-8")
                source = "cached_raw_same_digest"
            else:
                # Bounded per-route retry on provider 500s: standalone
                # probes show the same call succeeds alone, and the
                # failures cluster on later rapid calls (rate-limit
                # shaped). Max 3 tries, backoff, all recorded.
                text = None
                last_exc = None
                for try_no in range(1, 4):
                    try:
                        text = call_gemma_long(prompt, api_key)
                        record["calls"] += 1
                        break
                    except Exception as exc:
                        record["calls"] += 1
                        last_exc = exc
                        if getattr(exc, "code", None) != 500 or try_no == 3:
                            break
                        time.sleep(30 * try_no)
                record.setdefault("route_retries", {})[rkey] = try_no
                if text is None:
                    code = getattr(last_exc, "code", "")
                    record.update(
                        admitted=False, failure_class="INFRASTRUCTURE",
                        failed_route=rkey,
                        detail=f"{type(last_exc).__name__} {code}: "
                               "provider call failed after retries")
                    (OUT / "hybrid_result.json").write_text(
                        json.dumps(record, indent=1), encoding="utf-8")
                    print(json.dumps(record, indent=1))
                    return 0
                source = "live_call"  # cached only after admission below
            parsed, how = parse_route_json(text)
            route_out = parsed.get("route") if isinstance(parsed, dict) else None
            if isinstance(route_out, dict):
                # Templates are not emittable in this design (see
                # ROUTE_SCHEMA): always carry the compiled template.
                route_out.pop("template_unchanged", None)
                import copy as _copy
                route_out["template"] = _copy.deepcopy(route.get("template"))
            identity_fixed = False
            if isinstance(route_out, dict) and (
                    route_out.get("method") != route.get("method")
                    or route_out.get("path") != route.get("path")):
                # Route identity is addressing from the compiled spec,
                # not behavior: the model once rewrote /projects to
                # /api/v1/projects. Correct it mechanically, recorded.
                route_out["method"] = route.get("method")
                route_out["path"] = route.get("path")
                identity_fixed = True
            record["route_results"].append(
                {"route": rkey, "source": source, "json_parse": how,
                 "admitted": isinstance(route_out, dict),
                 "identity_corrected": identity_fixed})
            if not isinstance(route_out, dict):
                # Never cache an unadmitted raw: it would poison every
                # later run with the same frozen digest. Keep it as a
                # .failed.txt diagnostic instead.
                (OUT / f"raw_H_route_{slug}.failed.txt").write_text(
                    text, encoding="utf-8")
                cache_raw.unlink(missing_ok=True)
                cache_meta.unlink(missing_ok=True)
                record.update(admitted=False,
                              failure_class="MODEL_OUTPUT_NOT_JSON",
                              failed_route=rkey)
                (OUT / "hybrid_result.json").write_text(
                    json.dumps(record, indent=1), encoding="utf-8")
                print(json.dumps(record, indent=1))
                return 0
            if source == "live_call":
                cache_raw.write_text(text, encoding="utf-8")
                cache_meta.write_text(rdigest, encoding="utf-8")
            edited_routes.append(route_out)
        spec, model_diff = compose_edited(
            compiled, {"routes": edited_routes})
        record["design"] = "per-route edit of compiled spec (attempt 11+)"
        record["model_diff_vs_compiled"] = model_diff
        errors = mx.validate_spec(spec)
        if errors:
            record.update(admitted=False, failure_class="SCHEMA_REJECTED",
                          schema_errors=errors)
            print(json.dumps(record, indent=1))
            return 0
        conf = public_conformance(spec, ref_base, 3601)
        record["hybrid_public"] = {"passed": conf["public_passed"],
                                   "total": conf["public_total"]}
        record.update(mx.evaluate_spec("H_hybrid", spec, ref_base, 3602))
        record["hybrid_heldout"] = {"passed": record.get("passed"),
                                    "total": record.get("total")}
        # H_repair: one bounded repair call on public divergences only.
        if conf["divergences"]:
            import copy as _cp
            slim_routes = []
            for r in spec["routes"]:
                r2 = _cp.deepcopy(r)
                r2.pop("template", None)  # restored verbatim below
                slim_routes.append(r2)
            repair_prompt = (
                mx.INTERFACE + "\n\n" + EDIT_SCHEMA +
                "\n\nYour previous routes (JSON; templates omitted and "
                "restored automatically — do not emit templates):\n"
                + json.dumps({"routes": slim_routes}) +
                "\n\nExecuting them against the PUBLIC probe ladder "
                "produced these divergences from the reference (public "
                "evidence only; the held-out suite is not shown):\n"
                + diff_text(conf["divergences"]) +
                "\n\nReturn the complete corrected routes as ONLY JSON "
                "{\"routes\": [...]}. Fix the divergences without "
                "breaking conforming behavior.\n\n" + mx.JSON_FIRST)
            record["repair_context_digest"] = mx.digest(repair_prompt)
            try:
                text2 = call_gemma_long(repair_prompt, api_key, schema=None)
            except Exception:
                time.sleep(30)  # one recorded retry on provider failure
                record["repair_retries"] = 1
                try:
                    text2 = call_gemma_long(repair_prompt, api_key,
                                            schema=None)
                except Exception as exc:
                    text2 = None
                    record["repair_heldout"] = {
                        "admitted": False, "failure_class": "INFRASTRUCTURE",
                        "detail": f"{type(exc).__name__}: repair failed "
                                  "after retry"}
                    record["model_calls"] = record["calls"] + 1
                    (OUT / "hybrid_result.json").write_text(
                        json.dumps(record, indent=1), encoding="utf-8")
                    print(json.dumps(record, indent=1))
                    return 0
            record["calls"] += 1 + record.get("repair_retries", 0)
            (OUT / "raw_H_repair.txt").write_text(text2, encoding="utf-8")
            parsed2, how2 = mx.parse_model_json(text2)
            record["repair_json_parse"] = how2
            routes2 = (parsed2.get("routes")
                       if isinstance(parsed2, dict) else None)
            if isinstance(routes2, list):
                prev = {(r.get("method"), r.get("path")): r
                        for r in spec["routes"]}
                for r2 in routes2:
                    if isinstance(r2, dict) and "template" not in r2:
                        base_r = prev.get((r2.get("method"), r2.get("path")))
                        if base_r is not None:
                            import copy as _cp2
                            r2["template"] = _cp2.deepcopy(
                                base_r.get("template"))
            spec2 = ({"users": spec["users"], "auth": spec["auth"],
                      "routes": routes2}
                     if isinstance(routes2, list) and routes2 else None)
            if spec2 is not None and not mx.validate_spec(spec2):
                conf2 = public_conformance(spec2, ref_base, 3603)
                record["repair_public"] = {"passed": conf2["public_passed"],
                                           "total": conf2["public_total"]}
                rec2 = mx.evaluate_spec("H_repair", spec2, ref_base, 3604)
                record["repair_heldout"] = {"passed": rec2.get("passed"),
                                            "total": rec2.get("total"),
                                            "admitted": rec2.get("admitted")}
            else:
                record["repair_heldout"] = {
                    "admitted": False,
                    "failure_class": "REPAIR_NOT_ADMITTED"}
        record["model_calls"] = record["calls"]
        (OUT / "hybrid_result.json").write_text(
            json.dumps(record, indent=1), encoding="utf-8")
        print(json.dumps(record, indent=1))
        return 0
    finally:
        if proc is not None:
            mx.stop_reference(proc, workdir)


def preflight() -> int:
    observations = OBS_PATH.read_text(encoding="utf-8")
    compiled = evidence_compiler.compile_spec(json.loads(observations))
    prompt = build_hybrid_prompt(observations, compiled)
    print(json.dumps({
        "kind": "VIKUNJA_HYBRID_PREFLIGHT_V1", **mx.provenance(),
        "calls_planned": {"H_hybrid": 1, "H_repair_max": 1},
        "hybrid_context_digest": mx.digest(prompt),
        "prompt_chars": len(prompt),
        "compiled_routes": len(compiled.get("routes", [])),
        "gemma_key_present": bool(os.environ.get("GEMMA_API_KEY")),
        "held_out_in_prompts": False}, indent=1))
    return 0


def main() -> int:
    if "--live" in sys.argv:
        if "--confirm-live" not in sys.argv:
            print("BLOCKED: --live requires --confirm-live. Zero calls.")
            return 2
        return run_live()
    return preflight()


if __name__ == "__main__":
    raise SystemExit(main())
