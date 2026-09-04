import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO

import click
import yaml

from .models import AppConfig, Board


UNDO_KEY = "_undo"


class _LockUnavailable(Exception):
    """Raised when another process currently owns the datastore lock."""


def _ensure_lock_byte(lock_file: BinaryIO) -> None:
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    lock_file.seek(0)


def _acquire_file_lock(lock_file: BinaryIO) -> None:
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise _LockUnavailable from exc
        return

    import fcntl

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise _LockUnavailable from exc


def _release_file_lock(lock_file: BinaryIO) -> None:
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return

    import fcntl

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def datastore_lock(config: AppConfig):
    """Hold one OS-backed exclusive writer lock for a datastore transaction."""
    data_path = config.data_path.resolve()
    lock_path = Path(f"{data_path}.lock")
    lock_file: BinaryIO | None = None

    try:
        data_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a+b")
        _ensure_lock_byte(lock_file)
        _acquire_file_lock(lock_file)
    except _LockUnavailable as exc:
        if lock_file is not None:
            lock_file.close()
        raise click.ClickException(
            f"Datastore {data_path} is locked by another kanban-tui process."
        ) from exc
    except OSError as exc:
        if lock_file is not None:
            lock_file.close()
        raise click.ClickException(f"Could not lock datastore {data_path}: {exc}") from exc

    try:
        yield
    finally:
        assert lock_file is not None
        _release_file_lock(lock_file)
        lock_file.close()


def _read_raw_data(data_path: Path) -> Any:
    try:
        with data_path.open("r", encoding="utf-8") as stream:
            try:
                return yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    f"Datastore {data_path} contains invalid YAML: {exc}"
                ) from exc
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise click.ClickException(f"Could not read datastore {data_path}: {exc}") from exc


def _atomic_write_mapping(data_path: Path, raw: dict[str, Any]) -> None:
    directory = data_path.parent
    temp_path: Path | None = None

    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".kanban-tui-",
            suffix=".tmp",
            delete=False,
        ) as outfile:
            temp_path = Path(outfile.name)
            yaml.safe_dump(raw, outfile, default_flow_style=False)
            outfile.flush()
            os.fsync(outfile.fileno())

        os.replace(temp_path, data_path)
        temp_path = None
    except (OSError, yaml.YAMLError) as exc:
        raise click.ClickException(f"Could not write datastore {data_path}: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def read_data(config: AppConfig, *, initialize_missing: bool = False) -> Board:
    """Read the datastore without creating files or emitting user-facing output."""
    data_path = config.data_path
    try:
        raw = _read_raw_data(data_path)
    except FileNotFoundError:
        return Board()

    try:
        return Board.from_mapping(raw)
    except ValueError as exc:
        raise click.ClickException(f"Datastore {data_path}: {exc}") from exc


def write_data(
    config: AppConfig,
    board: Board,
    *,
    snapshot_previous: bool = False,
) -> None:
    raw: dict[str, Any] = board.to_mapping()
    if snapshot_previous:
        previous = read_data(config, initialize_missing=False)
        raw[UNDO_KEY] = previous.to_mapping()
    _atomic_write_mapping(config.data_path, raw)


def undo_last_change(config: AppConfig) -> Board:
    data_path = config.data_path
    try:
        raw = _read_raw_data(data_path)
    except FileNotFoundError as exc:
        raise click.ClickException("Nothing to undo.") from exc

    if not isinstance(raw, dict) or UNDO_KEY not in raw:
        raise click.ClickException("Nothing to undo.")

    try:
        previous = Board.from_mapping(raw[UNDO_KEY])
    except ValueError as exc:
        raise click.ClickException(f"Undo snapshot is invalid: {exc}") from exc

    _atomic_write_mapping(data_path, previous.to_mapping())
    return previous
