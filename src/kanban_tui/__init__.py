from typing import TYPE_CHECKING

if TYPE_CHECKING:
    VERSION: str


def get_version() -> str:
    """Return the repository version in source checkouts or installed metadata."""
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as package_version
    from pathlib import Path

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


def __getattr__(name: str) -> str:
    if name == "VERSION":
        return get_version()
    raise AttributeError(name)


__all__ = ["VERSION", "get_version"]
