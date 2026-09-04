from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

import click
import yaml

from .models import AppConfig, Board


@contextmanager
def datastore_lock(config: AppConfig):
    data_path = config.clikan_data.resolve()
    lock_path = Path(f"{data_path}.lock")
    owner_path = lock_path / "owner"

    try:
        lock_path.mkdir()
    except FileExistsError:
        raise click.ClickException(
            f"Datastore {data_path} is locked by another clikan process. "
            f"If no clikan process is active, remove {lock_path}."
        )
    except OSError as exc:
        raise click.ClickException(f"Could not lock datastore {data_path}: {exc}")

    try:
        try:
            owner_path.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass
        yield
    finally:
        try:
            owner_path.unlink()
        except OSError:
            pass
        try:
            lock_path.rmdir()
        except OSError:
            pass


def read_data(config: AppConfig) -> Board:
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
        click.echo("No data, initializing data file.")
        board = Board()
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
    directory = data_path.resolve().parent
    temp_path = None

    try:
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
