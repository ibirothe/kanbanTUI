import json
from pathlib import Path

import click

from . import transfer_format as _transfer_format
from .atomic import atomic_text_writer
from .deprecations import warn_legacy_api
from .imports import merge_boards as _merge_boards
from .models import Board

__all__ = [  # noqa: F822 - deprecated names are resolved by __getattr__
    "EXPORT_FORMAT",
    "EXPORT_VERSION",
    "TransferFormatError",
    "board_from_export",
    "export_payload",
    "merge_boards",
    "read_export",
    "write_export",
]


def read_export(path: Path) -> Board:
    try:
        with path.open("r", encoding="utf-8") as infile:
            payload = json.load(infile)
    except UnicodeError as exc:
        raise click.ClickException(
            f"Import file {path} must use valid UTF-8 encoding."
        ) from exc
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"Import file {path} contains invalid JSON: {exc}"
        ) from exc
    except OSError as exc:
        raise click.ClickException(f"Could not read import file {path}: {exc}") from exc

    try:
        return _transfer_format.board_from_export(payload)
    except _transfer_format.TransferFormatError as exc:
        raise click.ClickException(f"Import file {path}: {exc}") from exc


def write_export(path: Path, board: Board, *, overwrite: bool = False) -> Path:
    path = path.expanduser().resolve()
    if path.exists() and not overwrite:
        raise click.ClickException(
            f"Export file {path} already exists. Use --force to overwrite it."
        )

    try:
        with atomic_text_writer(path) as outfile:
            json.dump(
                _transfer_format.export_payload(board),
                outfile,
                ensure_ascii=False,
                indent=2,
            )
            outfile.write("\n")
    except (OSError, ValueError) as exc:
        raise click.ClickException(
            f"Could not write export file {path}: {exc}"
        ) from exc

    return path


def __getattr__(name: str) -> object:
    compatibility_exports: dict[str, tuple[object, str]] = {
        "EXPORT_FORMAT": (
            _transfer_format.EXPORT_FORMAT,
            "kanban_tui.transfer_format.EXPORT_FORMAT",
        ),
        "EXPORT_VERSION": (
            _transfer_format.EXPORT_VERSION,
            "kanban_tui.transfer_format.EXPORT_VERSION",
        ),
        "TransferFormatError": (
            _transfer_format.TransferFormatError,
            "kanban_tui.transfer_format.TransferFormatError",
        ),
        "board_from_export": (
            _transfer_format.board_from_export,
            "kanban_tui.transfer_format.board_from_export()",
        ),
        "export_payload": (
            _transfer_format.export_payload,
            "kanban_tui.transfer_format.export_payload()",
        ),
        "merge_boards": (_merge_boards, "kanban_tui.imports.merge_boards()"),
    }
    if name in compatibility_exports:
        value, replacement = compatibility_exports[name]
        warn_legacy_api(f"kanban_tui.transfer.{name}", replacement, stacklevel=2)
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
