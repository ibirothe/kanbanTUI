from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

import click
import yaml


def validate_task_collection(tasks, collection_name, data_path, allowed_states):
    if not isinstance(tasks, dict):
        raise click.ClickException(
            f"Datastore {data_path}: {collection_name} must be a mapping."
        )

    for task_id, item in tasks.items():
        if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id < 1:
            raise click.ClickException(
                f"Datastore {data_path}: task ids in {collection_name} must be positive integers."
            )
        if not isinstance(item, list) or len(item) < 4:
            raise click.ClickException(
                f"Datastore {data_path}: task {task_id} in {collection_name} has an invalid record."
            )
        if item[0] not in allowed_states:
            raise click.ClickException(
                f"Datastore {data_path}: task {task_id} in {collection_name} has unsupported state {item[0]!r}."
            )
        if not isinstance(item[1], str):
            raise click.ClickException(
                f"Datastore {data_path}: task {task_id} in {collection_name} must have text content."
            )


def validate_data(data, data_path):
    if not isinstance(data, dict):
        raise click.ClickException(
            f"Datastore {data_path} must contain a YAML mapping."
        )
    if "data" not in data or "deleted" not in data:
        raise click.ClickException(
            f"Datastore {data_path} must contain data and deleted mappings."
        )

    validate_task_collection(
        data["data"], "data", data_path, {"todo", "inprogress", "done"}
    )
    validate_task_collection(
        data["deleted"], "deleted", data_path, {"deleted"}
    )
    return data


@contextmanager
def datastore_lock(config):
    data_path = Path(config["clikan_data"]).expanduser().resolve()
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


def read_data(config):
    data_path = Path(config["clikan_data"]).expanduser()
    try:
        with data_path.open("r", encoding="utf-8") as stream:
            try:
                data = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    f"Datastore {data_path} contains invalid YAML: {exc}"
                )
    except FileNotFoundError:
        click.echo("No data, initializing data file.")
        data = {"data": {}, "deleted": {}}
        write_data(config, data)
        return data
    except OSError as exc:
        raise click.ClickException(f"Could not read datastore {data_path}: {exc}")

    return validate_data(data, data_path)


def write_data(config, data):
    data_path = Path(config["clikan_data"]).expanduser()
    validate_data(data, data_path)

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
            yaml.safe_dump(data, outfile, default_flow_style=False)
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
