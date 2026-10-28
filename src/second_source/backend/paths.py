"""Local storage path checks shared by database and immutable artifact boundaries."""
from pathlib import Path
import stat

from .contracts import BackendError


def reject_links(path: Path) -> None:
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BackendError("UNSAFE_STORAGE", "Storage path is unsafe", 503)


def safe_directory(path: Path) -> Path:
    reject_links(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    reject_links(path)
    if not path.is_dir():
        raise BackendError("UNSAFE_STORAGE", "Storage path is unsafe", 503)
    return path.resolve()


def checked_regular_file(path: Path) -> None:
    reject_links(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise BackendError("UNSAFE_STORAGE", "Storage file is unsafe", 503)
