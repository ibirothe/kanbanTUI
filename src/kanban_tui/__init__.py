from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path


def get_version() -> str:
    """Return installed distribution version, falling back to VERSION."""
    try:
        return package_version("clikan")
    except PackageNotFoundError:
        version_file = Path(__file__).resolve().parents[2] / "VERSION"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            return "unknown"


VERSION = get_version()

__all__ = ["VERSION", "get_version"]
