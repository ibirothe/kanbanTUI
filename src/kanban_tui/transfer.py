import json
from pathlib import Path

import click

from .atomic import atomic_text_writer
from .imports import merge_boards as merge_boards
from .models import Board
from .transfer_format import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    TransferFormatError,
    board_from_export,
    export_payload,
)

__all__ = [
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
        return board_from_export(payload)
    except TransferFormatError as exc:
        raise click.ClickException(f"Import file {path}: {exc}") from exc


def write_export(path: Path, board: Board, *, overwrite: bool = False) -> Path:
    path = path.expanduser().resolve()
    if path.exists() and not overwrite:
        raise click.ClickException(
            f"Export file {path} already exists. Use --force to overwrite it."
        )

    try:
        with atomic_text_writer(path) as outfile:
            json.dump(export_payload(board), outfile, ensure_ascii=False, indent=2)
            outfile.write("\n")
    except (OSError, ValueError) as exc:
        raise click.ClickException(
            f"Could not write export file {path}: {exc}"
        ) from exc

    return path
