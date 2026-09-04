import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import click
import yaml

from .models import AppConfig, Board


LOCK_STALE_SECONDS = 300


def _read_owner_pid(owner_path: Path) -> int | None:
    try:
        return int(owner_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_is_running(pid: int) -> bool | None:
    if os.name != "posix":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _lock_is_stale(lock_path: Path, owner_path: Path) -> bool:
    owner_pid = _read_owner_pid(owner_path)
    if owner_pid is not None:
        running = _pid_is_running(owner_pid)
        if running is not None:
            return not running

    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False
    return age >= LOCK_STALE_SECONDS


def _remove_lock(lock_path: Path, owner_path: Path) -> bool:
    try:
        owner_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return False

    try:
        lock_path.rmdir()
    except OSError:
        return False
    return True


@contextmanager
def datastore_lock(config: AppConfig):
    data_path = config.clikan_data.resolve()
    lock_path = Path(f"{data_path}.lock")
    owner_path = lock_path / "owner"

    try:
        data_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_path.mkdir()
        except FileExistsError:
            if not _lock_is_stale(lock_path, owner_path) or not _remove_lock(
                lock_path, owner_path
            ):
                raise click.ClickException(
                    f"Datastore {data_path} is locked by another clikan process."
                )
            lock_path.mkdir()
    except click.ClickException:
        raise
    except OSError as exc:
        raise click.ClickException(f"Could not lock datastore {data_path}: {exc}")

    try:
        try:
            owner_path.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass
        yield
    finally:
        _remove_lock(lock_path, owner_path)


def read_data(config: AppConfig, *, initialize_missing: bool = True) -> Board:
    data_path = config.clikan_data
    try:
        with data_path.open("r", encoding="utf-8") as stream:
            try:
                raw = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    f"Datastore {data_path} contains invalid YAML: {exc}"
                )
    except FileNotFoundError:
        board = Board()
        if initialize_missing:
            click.echo("No data, initializing data file.")
            write_data(config, board)
        return board
    except OSError as exc:
        raise click.ClickException(f"Could not read datastore {data_path}: {exc}")

    try:
        return Board.from_mapping(raw)
    except ValueError as exc:
        raise click.ClickException(f"Datastore {data_path}: {exc}") from exc


def write_data(config: AppConfig, board: Board) -> None:
    data_path = config.clikan_data
    raw = board.to_mapping()
    directory = data_path.parent
    temp_path = None

    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".clikan-",
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
        raise click.ClickException(f"Could not write datastore {data_path}: {exc}")
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass
