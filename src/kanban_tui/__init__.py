from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path


def get_version() -> str:
    """Return the repository version in source checkouts or installed metadata."""
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    if version_file.is_file():
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    try:
        return package_version("kanbanTUI")
    except PackageNotFoundError:
        return "unknown"


VERSION = get_version()

__all__ = ["VERSION", "get_version"]
