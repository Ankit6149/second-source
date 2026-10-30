"""Build an allowlisted static site; never copy operator state or the repository."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
ASSETS = ("dm-sans.ttf", "manrope.ttf", "DM-Sans-OFL.txt", "Manrope-OFL.txt")


def build():
    destination = ROOT / "dist"
    allowed = {"index.html", "styles.css", "release.css", "script.js", "console/index.html"}
    allowed.update("assets/" + name for name in ASSETS)
    if destination.exists():
        existing = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
        if existing - allowed:
            raise ValueError("Build directory contains unexpected files; review it before publishing.")
    destination.mkdir(exist_ok=True)
    for name in ("index.html", "styles.css", "release.css", "script.js"):
        shutil.copyfile(ROOT / name, destination / name)
    (destination / "console").mkdir(exist_ok=True)
    shutil.copyfile(ROOT.parent / "demo" / "index.html", destination / "console" / "index.html")
    (destination / "assets").mkdir(exist_ok=True)
    for name in ASSETS:
        shutil.copyfile(ROOT / "assets" / name, destination / "assets" / name)
    return destination


if __name__ == "__main__":
    print(build())
