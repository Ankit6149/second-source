"""Per-investigation reports and runnable candidate exports.

Owns only report/export concerns. Input is the caller's *actual* investigation
data: this module never invents observations, scores, or provenance. A section
supplied without an explicit epistemic claim is rendered as ``UNKNOWN``; a
missing section is a single ``UNKNOWN`` claim with no evidence. Every
``OBSERVED``/``INFERRED``/``CONTRADICTED`` claim must link to an evidence ID
present in the caller-supplied registry, so a rendered status is always
traceable. Secret-shaped fields are redacted (reusing ``evidence.redact``)
before anything is rendered or bundled.

Report sections, in order: summary, request+scope, reference/env,
observations, architecture, behaviors, rules, data models, validation, auth,
state, UI, methodology, AI hypotheses/decisions, candidate architecture,
file inventory, choices, tests, fidelity, mismatches, assumptions/unknowns,
security, reproduction, next steps.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evidence import redact
from .g2_persistence import canonical

__all__ = [
    "STATUSES", "SECTIONS", "ReportError", "build_report", "render_markdown",
    "render_html", "build_manifest", "export_report_bundle",
    "verify_report_bundle", "build_file_inventory", "build_candidate_bundle",
    "verify_candidate_bundle", "extract_and_run_candidate", "write_report_files",
]

STATUSES = ("OBSERVED", "INFERRED", "ASSUMED", "UNKNOWN", "CONTRADICTED")
_EVIDENCE_REQUIRED = {"OBSERVED", "INFERRED", "CONTRADICTED"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAX_FILE = 5_000_000
_MAX_TOTAL = 20_000_000
_MAX_FILES = 500
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

# (section_id, title) — order is the report order required by the contract.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("summary", "Summary"),
    ("request_scope", "Request and scope"),
    ("reference_env", "Reference and environment"),
    ("observations", "Observations"),
    ("architecture", "Architecture"),
    ("behaviors", "Behaviors"),
    ("rules", "Rules"),
    ("data_models", "Data models"),
    ("validation", "Validation"),
    ("auth", "Authentication and authorization"),
    ("state", "State"),
    ("ui", "User interface"),
    ("methodology", "Methodology"),
    ("ai_hypotheses_decisions", "AI hypotheses and decisions"),
    ("candidate_architecture", "Candidate architecture"),
    ("file_inventory", "File inventory"),
    ("choices", "Choices"),
    ("tests", "Tests"),
    ("fidelity", "Fidelity"),
    ("mismatches", "Mismatches"),
    ("assumptions_unknowns", "Assumptions and unknowns"),
    ("security", "Security"),
    ("reproduction", "Reproduction"),
    ("next_steps", "Next steps"),
)
SECTION_IDS = tuple(s for s, _ in SECTIONS)


class ReportError(ValueError):
    """Report/candidate input fails closed; message carries no secret data."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _claim(raw: Any, registry: Mapping[str, Any]) -> dict:
    if not isinstance(raw, Mapping) or set(raw) - {"text", "status", "evidence_ids"}:
        raise ReportError("Claim must be {text, status, evidence_ids}")
    text, status = raw.get("text"), raw.get("status")
    ids = raw.get("evidence_ids", [])
    if not isinstance(text, str) or not text.strip():
        raise ReportError("Claim text is required")
    if status not in STATUSES:
        raise ReportError(f"Claim status must be one of {STATUSES}")
    if not isinstance(ids, (list, tuple)) or any(not isinstance(i, str) for i in ids):
        raise ReportError("Claim evidence_ids must be a list of strings")
    ids = sorted(set(ids))
    missing = [i for i in ids if i not in registry]
    if missing:
        raise ReportError(f"Claim links unknown evidence IDs: {missing}")
    if status in _EVIDENCE_REQUIRED and not ids:
        raise ReportError(f"{status} claim requires at least one evidence ID")
    return {"text": text.strip(), "status": status, "evidence_ids": ids}


def _check_counts(data: Any, section: str) -> None:
    if isinstance(data, Mapping) and {"passed", "failed", "indeterminate", "total"} <= set(data):
        vals = [data[k] for k in ("passed", "failed", "indeterminate", "total")]
        if any(type(v) is not int or v < 0 for v in vals) or sum(vals[:3]) != vals[3]:
            raise ReportError(f"{section} counts must be non-negative and sum to total")


def build_report(data: Mapping[str, Any]) -> dict:
    """Build the canonical report dict from actual investigation data.

    ``data`` keys: ``investigation_id`` (required), ``title``, ``generated_at``
    (caller-supplied; never fabricated here), ``evidence`` mapping of
    evidence ID -> {kind, source, sha256?, detail?}, plus one key per section
    ID. A section value is either ``{"claims": [...], "data": <actual data>}``,
    a bare list of claims, or any raw value stored verbatim (redacted) as
    section data with status left ``UNKNOWN`` until the caller asserts one.
    """
    if not isinstance(data, Mapping):
        raise ReportError("Report data must be a mapping")
    inv = data.get("investigation_id")
    if not isinstance(inv, str) or not _ID.fullmatch(inv):
        raise ReportError("investigation_id is required (alphanumeric id)")
    registry_in = data.get("evidence", {})
    if not isinstance(registry_in, Mapping):
        raise ReportError("evidence must be a mapping of id -> record")
    registry: dict[str, Any] = {}
    for eid, record in registry_in.items():
        if not isinstance(eid, str) or not _ID.fullmatch(eid) or not isinstance(record, Mapping):
            raise ReportError(f"Invalid evidence record: {eid!r}")
        registry[eid] = redact(json.loads(json.dumps(record, default=str)))
    sections = []
    for sid, title in SECTIONS:
        raw = data.get(sid)
        claims_in: Any = []
        payload: Any = None
        if isinstance(raw, Mapping) and ("claims" in raw or "data" in raw):
            claims_in, payload = raw.get("claims", []), raw.get("data")
        elif isinstance(raw, (list, tuple)):
            claims_in = raw
        elif raw is not None:
            payload = raw
        if not isinstance(claims_in, (list, tuple)):
            raise ReportError(f"Section {sid} claims must be a list")
        claims = [_claim(c, registry) for c in claims_in]
        payload = redact(payload) if payload is not None else None
        _check_counts(payload, sid)
        if payload is None and not claims:
            claims = [{"text": f"No data provided for {title.lower()}.", "status": "UNKNOWN", "evidence_ids": []}]
        elif payload is not None and not claims:
            claims = [{"text": f"Data provided for {title.lower()} without an asserted epistemic status.",
                       "status": "UNKNOWN", "evidence_ids": []}]
        sections.append({"id": sid, "title": title, "claims": claims, "data": payload})
    body = {
        "schema_version": "1", "kind": "PER_INVESTIGATION_REPORT",
        "investigation_id": inv,
        "title": redact(data["title"]) if isinstance(data.get("title"), str) else None,
        "generated_at": data.get("generated_at") if isinstance(data.get("generated_at"), str) else None,
        "evidence": registry, "sections": sections,
        "claim_counts": {s: sum(1 for sec in sections for c in sec["claims"] if c["status"] == s) for s in STATUSES},
    }
    body["report_id"] = _sha(canonical(body))
    return body


def _report_bytes(report: Mapping[str, Any]) -> bytes:
    return canonical(dict(report))


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [f"# Investigation report: {report.get('title') or report['investigation_id']}", "",
             f"- Report ID: `{report['report_id']}`", f"- Investigation: `{report['investigation_id']}`",
             f"- Generated at: {report.get('generated_at') or 'UNKNOWN'}", ""]
    for sec in report["sections"]:
        lines += [f"## {sec['title']}", ""]
        for c in sec["claims"]:
            ev = ", ".join(f"`{e}`" for e in c["evidence_ids"]) or "none"
            lines.append(f"- **{c['status']}** — {c['text']} (evidence: {ev})")
        if sec.get("data") is not None:
            lines += ["", "```json", json.dumps(sec["data"], indent=2, sort_keys=True, ensure_ascii=False), "```"]
        lines.append("")
    if report.get("evidence"):
        lines += ["## Evidence registry", ""]
        for eid in sorted(report["evidence"]):
            lines.append(f"- `{eid}`: {json.dumps(report['evidence'][eid], sort_keys=True, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def render_html(report: Mapping[str, Any]) -> str:
    esc = html.escape
    parts = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
             f"<title>Investigation {esc(str(report['investigation_id']))}</title>",
             "<style>body{font-family:system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}"
             ".st{font-weight:700}.UNKNOWN{color:#8a6d00}.CONTRADICTED{color:#b00020}"
             ".OBSERVED{color:#146c2e}pre{background:#f4f4f4;padding:1rem;overflow:auto}</style></head><body>",
             f"<h1>Investigation report: {esc(str(report.get('title') or report['investigation_id']))}</h1>",
             f"<p>Report ID: <code>{esc(report['report_id'])}</code></p>"]
    for sec in report["sections"]:
        parts.append(f"<h2>{esc(sec['title'])}</h2><ul>")
        for c in sec["claims"]:
            ev = ", ".join(esc(e) for e in c["evidence_ids"]) or "none"
            parts.append(f"<li><span class=\"st {c['status']}\">{c['status']}</span> — {esc(c['text'])} (evidence: {ev})</li>")
        parts.append("</ul>")
        if sec.get("data") is not None:
            parts.append(f"<pre>{esc(json.dumps(sec['data'], indent=2, sort_keys=True, ensure_ascii=False))}</pre>")
    parts.append("<h2>Evidence registry</h2><ul>")
    for eid in sorted(report.get("evidence", {})):
        parts.append(f"<li><code>{esc(eid)}</code>: {esc(json.dumps(report['evidence'][eid], sort_keys=True, ensure_ascii=False))}</li>")
    parts.append("</ul></body></html>")
    return "".join(parts) + "\n"


def build_manifest(report: Mapping[str, Any], files: Mapping[str, bytes]) -> dict:
    return {"schema_version": "1", "kind": "REPORT_MANIFEST",
            "report_id": report["report_id"], "investigation_id": report["investigation_id"],
            "claim_counts": report.get("claim_counts", {}),
            "evidence_ids": sorted(report.get("evidence", {})),
            "files": {n: {"sha256": _sha(b), "size_bytes": len(b)} for n, b in sorted(files.items())}}


def _zip(files: Mapping[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for name in sorted(files):
            z.writestr(zipfile.ZipInfo(name, date_time=_ZIP_DATE), files[name])
    return out.getvalue()


def export_report_bundle(report: Mapping[str, Any]) -> bytes:
    """Deterministic ZIP: report.json + report.md + report.html + manifest.json."""
    files = {"report.json": _report_bytes(report),
             "report.md": render_markdown(report).encode(),
             "report.html": render_html(report).encode()}
    files["manifest.json"] = canonical(build_manifest(report, files))
    return _zip(files)


def verify_report_bundle(raw: bytes) -> dict:
    if len(raw) > _MAX_TOTAL:
        raise ReportError("Report bundle too large")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sorted(z.namelist()) != ["manifest.json", "report.html", "report.json", "report.md"]:
                raise ReportError("Report bundle file set is invalid")
            manifest = json.loads(z.read("manifest.json"))
            report = json.loads(z.read("report.json"))
            files = {n: z.read(n) for n in ("report.json", "report.md", "report.html")}
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        raise ReportError("Report bundle is unreadable") from exc
    expected = build_manifest(report, files)
    if manifest != expected or report.get("kind") != "PER_INVESTIGATION_REPORT":
        raise ReportError("Report bundle manifest does not match contents")
    # Rebuilding must reproduce the report ID exactly (no silent mutation).
    if build_report({**_as_input(report)})["report_id"] != report["report_id"]:
        raise ReportError("Report bundle report_id does not recompute")
    return {"valid": True, "report_id": report["report_id"], "bundle_sha256": _sha(raw), "file_count": 4}


def _as_input(report: Mapping[str, Any]) -> dict:
    data: dict[str, Any] = {"investigation_id": report["investigation_id"], "title": report.get("title"),
                            "generated_at": report.get("generated_at"), "evidence": report.get("evidence", {})}
    for sec in report["sections"]:
        # UNKNOWN placeholder claims round-trip as explicit claims.
        data[sec["id"]] = {"claims": sec["claims"], "data": sec.get("data")}
    return data


def write_report_files(report: Mapping[str, Any], out_dir: str | Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bundle = export_report_bundle(report)
    files = {"report.json": _report_bytes(report), "report.md": render_markdown(report).encode(),
             "report.html": render_html(report).encode()}
    files["manifest.json"] = canonical(build_manifest(report, {k: v for k, v in files.items()}))
    for name, raw in files.items():
        (out / name).write_bytes(raw)
    (out / "report-bundle.zip").write_bytes(bundle)
    return {"directory": str(out), "bundle_sha256": _sha(bundle), "files": sorted(files) + ["report-bundle.zip"]}


def build_file_inventory(root: str | Path, paths: Sequence[str] | None = None) -> list[dict]:
    """Hash actual files under ``root``; missing paths fail closed."""
    base = Path(root).resolve()
    rels: list[Path] = []
    if paths is None:
        rels = sorted(p for p in base.rglob("*") if p.is_file() and not p.is_symlink())
    else:
        rels = [base / p for p in paths]
    inventory = []
    for path in rels:
        resolved = path.resolve()
        if base not in resolved.parents and resolved != base or not resolved.is_file():
            raise ReportError(f"Inventory path escapes root or is missing: {path}")
        raw = resolved.read_bytes()
        inventory.append({"path": resolved.relative_to(base).as_posix(), "size_bytes": len(raw), "sha256": _sha(raw)})
    return inventory


_EXCLUDE_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
_EXCLUDE_NAMES = {".env", "candidate-manifest.json"}


def _candidate_files(base: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base)
        if any(part in _EXCLUDE_DIRS for part in rel.parts) or rel.name in _EXCLUDE_NAMES \
                or rel.name.startswith(".env") or path.suffix in (".pyc", ".pyo", ".zip") or path.is_symlink():
            continue
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if len(raw) > _MAX_FILE:
            raise ReportError(f"Candidate file too large: {rel.as_posix()}")
        files[rel.as_posix()] = raw
        if len(files) > _MAX_FILES or sum(len(v) for v in files.values()) > _MAX_TOTAL:
            raise ReportError("Candidate bundle exceeds size/file limits")
    names = {n.lower() for n in files}
    if "readme.md" not in names:
        raise ReportError("Candidate requires README.md")
    if "pyproject.toml" not in names and "requirements.txt" not in names:
        raise ReportError("Candidate requires pyproject.toml or requirements.txt (dependency declaration)")
    if not any(n.endswith(".py") for n in files):
        raise ReportError("Candidate requires at least one Python source file")
    return files


def build_candidate_bundle(source_dir: str | Path) -> bytes:
    """ZIP (code + dependency declaration + README + hash manifest) that runs standalone."""
    base = Path(source_dir).resolve()
    if not base.is_dir() or base.is_symlink():
        raise ReportError("Candidate source directory is missing or unsafe")
    files = _candidate_files(base)
    manifest = {"schema_version": "1", "kind": "CANDIDATE_BUNDLE",
                "files": {n: {"sha256": _sha(b), "size_bytes": len(b)} for n, b in sorted(files.items())}}
    files["candidate-manifest.json"] = canonical(manifest)
    return _zip(files)


def verify_candidate_bundle(raw: bytes) -> dict:
    if len(raw) > _MAX_TOTAL + _MAX_FILE:
        raise ReportError("Candidate bundle too large")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            names = z.namelist()
            if "candidate-manifest.json" not in names or len(names) != len(set(names)):
                raise ReportError("Candidate bundle manifest missing or names duplicated")
            for info in infos:
                p = Path(info.filename)
                if p.is_absolute() or ".." in p.parts or info.is_dir():
                    if info.is_dir():
                        continue
                    raise ReportError("Candidate bundle contains unsafe path")
            manifest = json.loads(z.read("candidate-manifest.json"))
            files = {n: z.read(n) for n in names if n != "candidate-manifest.json"}
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        raise ReportError("Candidate bundle is unreadable") from exc
    expected = {"schema_version": "1", "kind": "CANDIDATE_BUNDLE",
                "files": {n: {"sha256": _sha(b), "size_bytes": len(b)} for n, b in sorted(files.items())}}
    if manifest != expected:
        raise ReportError("Candidate bundle manifest does not match contents")
    lower = {n.lower() for n in files}
    if "readme.md" not in lower or not ({"pyproject.toml", "requirements.txt"} & lower) \
            or not any(n.endswith(".py") for n in files):
        raise ReportError("Candidate bundle lacks README, dependency declaration, or code")
    return {"valid": True, "bundle_sha256": _sha(raw), "file_count": len(files), "files": sorted(files)}


def extract_and_run_candidate(raw: bytes, command: Sequence[str], *, timeout: int = 30) -> dict:
    """Extract to a fresh temp dir (zip-slip/symlink safe) and execute ``command``.

    ``{python}`` in any argument is replaced with the current interpreter.
    This is the clean-environment check: nothing is imported from the
    caller's working tree; the extracted directory is the subprocess cwd.
    """
    verify_candidate_bundle(raw)
    if not command:
        raise ReportError("Candidate run command is required")
    argv = [a.replace("{python}", sys.executable) for a in command]
    with tempfile.TemporaryDirectory(prefix="candidate-verify-") as tmp:
        dest = Path(tmp) / "candidate"
        dest.mkdir()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                target = (dest / info.filename).resolve()
                if dest.resolve() not in target.parents:
                    raise ReportError("Candidate bundle contains unsafe path")
                # Reject symlink entries (unix mode file-type bits).
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ReportError("Candidate bundle contains a symlink")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info.filename))
        proc = subprocess.run(argv, cwd=dest, capture_output=True, text=True,
                              timeout=timeout, env={"PATH": "", "PYTHONNOUSERSITE": "1",
                                                    "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
        return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:],
                "command": argv, "file_count": verify_candidate_bundle(raw)["file_count"]}
