"""Export a sanitized G3 evidence bundle for independent review.

Copies ONLY the sanitized run artifacts (report, broker artifact,
candidate bytes, input provenance) into a create-once export directory and
writes a sha256 manifest. Private model receipts (``*.private.json``) are
never copied; they are listed as excluded so the reviewer can confirm
nothing billable-sensitive crossed the boundary.

Usage:
    python scripts/export_g3_evidence.py <run-dir> <out-dir>

Exit 0 on success, 2 on usage or input errors. No model calls, no
credentials, no network.
"""
import hashlib
import json
import os
import shutil
import sys

SANITIZED_FILES = (
    "G3_report.json",
    "broker-artifact.v1.json",
    "candidate.v1.json",
    "G3_input_provenance.json",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def export_run(run_dir, out_dir):
    run = os.path.abspath(run_dir)
    out = os.path.abspath(out_dir)
    report_path = os.path.join(run, "G3_report.json")
    if not os.path.isfile(report_path):
        raise ValueError("run directory has no G3_report.json: " + run)
    try:
        os.makedirs(out, exist_ok=False)
    except FileExistsError:
        raise ValueError("export directory already exists: " + out)
    try:
        with open(report_path, "r", encoding="utf-8") as stream:
            report = json.load(stream)
    except (ValueError, OSError) as exc:
        raise ValueError("G3_report.json is not valid JSON") from exc
    files = {}
    for name in SANITIZED_FILES:
        source = os.path.join(run, name)
        if not os.path.isfile(source):
            continue
        shutil.copyfile(source, os.path.join(out, name))
        files[name] = sha256_file(os.path.join(out, name))
    excluded = sorted(
        name for name in os.listdir(run)
        if name.endswith(".private.json")
        and os.path.isfile(os.path.join(run, name)))
    manifest = {
        "kind": "G3_EVIDENCE_EXPORT_V1",
        "run_id": report.get("run_id", ""),
        "origin": report.get("origin", ""),
        "synthesis": report.get("synthesis", ""),
        "spec_digest": report.get("spec_digest", ""),
        "suite_digest": report.get("suite_digest", ""),
        "files": files,
        "excluded_private": excluded,
    }
    manifest_path = os.path.join(out, "export-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
    # Verify what was written before reporting success.
    for name, expected in files.items():
        actual = sha256_file(os.path.join(out, name))
        if actual != expected:
            raise ValueError("export integrity failure: " + name)
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest


def main(argv):
    if len(argv) != 3:
        print("usage: export_g3_evidence.py <run-dir> <out-dir>",
              file=sys.stderr)
        return 2
    try:
        manifest = export_run(argv[1], argv[2])
    except (ValueError, OSError) as exc:
        print("export refused: " + str(exc)[:200], file=sys.stderr)
        return 2
    print(json.dumps({"exported": sorted(manifest["files"]),
                      "excluded_private": manifest["excluded_private"],
                      "run_id": manifest["run_id"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
