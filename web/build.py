"""Build an allowlisted static site; never copy operator state or the repository."""
from pathlib import Path
import argparse
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
ASSETS = ("dm-sans.ttf", "manrope.ttf", "DM-Sans-OFL.txt", "Manrope-OFL.txt")


def app_asset(name):
    return bool(re.fullmatch(r"app/(?:index\.html|assets/[A-Za-z0-9_-]+\.(?:css|js)|fonts/[A-Za-z0-9_-]+\.(?:ttf|txt))", name))


def build(include_app=False):
    destination = ROOT / "dist"
    if destination.is_symlink() or any((destination / name).is_symlink() for name in ("app", "app/assets", "app/fonts")):
        raise ValueError("Build output may not contain linked directories.")
    allowed = {"index.html", "landing.css", "styles.css", "release.css", "script.js", "research.css", "reports/index.html", "experiments/index.html", "console/index.html", "evidence/index.html", "lab/index.html", "challenge/index.html", "handoff/index.html", "architecture/index.html"}
    REDIRECTS = ("console", "handoff")
    STUB = "<!doctype html><meta charset=\"utf-8\"><title>Second Source</title><meta http-equiv=\"refresh\" content=\"0; url=/app/\"><link rel=\"canonical\" href=\"/app/\"><p>This page has moved into the app. <a href=\"/app/\">Open Second Source</a>.</p><script>location.replace('/app/')</script>"
    allowed.update("assets/" + name for name in ASSETS)
    if destination.exists():
        existing = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
        if any(name not in allowed and not app_asset(name) for name in existing):
            raise ValueError("Build directory contains unexpected files; review it before publishing.")
        for name in existing:
            if app_asset(name):
                path = destination / name
                if path.is_symlink():
                    raise ValueError("Generated application output may not be a symlink.")
                path.unlink()
    destination.mkdir(exist_ok=True)
    for name in ("index.html", "landing.css", "styles.css", "release.css", "script.js", "research.css"):
        shutil.copyfile(ROOT / name, destination / name)
    for route in ("reports", "experiments", "challenge", "architecture"):
        (destination / route).mkdir(exist_ok=True)
        shutil.copyfile(ROOT / route / "index.html", destination / route / "index.html")
    for route, target in (("evidence", "/reports/"),
                          ("lab", "/experiments/"), ("console", "/app/"), ("handoff", "/app/")):
        (destination / route).mkdir(exist_ok=True)
        (destination / route / "index.html").write_text(
            '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='
            + target + '"><link rel="canonical" href="' + target
            + '"><p>This page moved. <a href="' + target + '">Continue to current page</a></p>',
            encoding="utf-8"
        )
    (destination / "assets").mkdir(exist_ok=True)
    for name in ASSETS:
        shutil.copyfile(ROOT / "assets" / name, destination / "assets" / name)
    if include_app:
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("Node.js and npm are required to build the workspace.")
        with tempfile.TemporaryDirectory(prefix="second-source-app-build-") as directory:
            generated = Path(directory)
            subprocess.run([npm, "run", "build", "--", "--base=/app/", "--outDir", str(generated), "--emptyOutDir"],
                           cwd=ROOT.parent / "product", check=True)
            files = [path for path in generated.rglob("*") if path.is_file()]
            names = {"app/" + path.relative_to(generated).as_posix() for path in files}
            if "app/index.html" not in names or any(not app_asset(name) for name in names):
                raise ValueError("Application build contains unexpected files.")
            for path in files:
                if path.is_symlink() or path.stat().st_size > 10_000_000:
                    raise ValueError("Application build contains an unsafe file.")
                target = destination / "app" / path.relative_to(generated)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-app", action="store_true", help="Build the product workspace into /app/.")
    print(build(include_app=parser.parse_args().with_app))
