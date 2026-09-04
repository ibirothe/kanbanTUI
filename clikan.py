from collections import OrderedDict
from contextlib import contextmanager
import datetime
from importlib.metadata import PackageNotFoundError, version as package_version
import os
import tempfile

import click
from click_default_group import DefaultGroup
from rich.console import Console
from rich.table import Table
import yaml


def get_version():
    """Return the installed package version, falling back to VERSION."""
    try:
        return package_version("clikan")
    except PackageNotFoundError:
        version_path = os.path.join(os.path.dirname(__file__), "VERSION")
        try:
            with open(version_path, "r") as version_file:
                return version_file.read().strip()
        except OSError:
            return "unknown"


VERSION = get_version()


class PrefixGroup(DefaultGroup):
    """Click group that accepts a unique command prefix."""

    def get_command(self, ctx, cmd_name):
        command = click.Group.get_command(self, ctx, cmd_name)
        if command is not None:
            return command

        matches = [
            name
            for name in self.list_commands(ctx)
            if name.lower().startswith(cmd_name.lower())
        ]
        if not matches:
            return None
        if len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail("Too many matches: %s" % ", ".join(sorted(matches)))


def validate_config(config, config_path):
    """Validate and normalize the application configuration."""
    if not isinstance(config, dict):
        raise click.ClickException(
            "Config file %s must contain a YAML mapping." % config_path
        )

    clikan_data = config.get("clikan_data")
    if not isinstance(clikan_data, str) or not clikan_data.strip():
        raise click.ClickException(
            "Config file %s must define a non-empty clikan_data path."
            % config_path
        )

    limits = config.get("limits", {})
    if limits is None:
        limits = {}
    if not isinstance(limits, dict):
        raise click.ClickException(
            "Config file %s: limits must be a mapping." % config_path
        )

    for name in ("todo", "wip", "done", "taskname"):
        if name not in limits:
            continue
        value = limits[name]
        if isinstance(value, bool):
            raise click.ClickException(
                "Config file %s: limits.%s must be a non-negative integer."
                % (config_path, name)
            )
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise click.ClickException(
                "Config file %s: limits.%s must be a non-negative integer."
                % (config_path, name)
            )
        if value < 0:
            raise click.ClickException(
                "Config file %s: limits.%s must be a non-negative integer."
                % (config_path, name)
            )
        limits[name] = value

    repaint = config.get("repaint", False)
    if not isinstance(repaint, bool):
        raise click.ClickException(
            "Config file %s: repaint must be true or false." % config_path
        )

    limits.setdefault("taskname", 40)
    limits.setdefault("done", 10)
    config["limits"] = limits
    config["repaint"] = repaint
    return config


def validate_task_collection(tasks, collection_name, data_path, allowed_states):
    """Validate one task mapping in the datastore."""
    if not isinstance(tasks, dict):
        raise click.ClickException(
            "Datastore %s: %s must be a mapping."
            % (data_path, collection_name)
        )

    for task_id, item in tasks.items():
        if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id < 1:
            raise click.ClickException(
                "Datastore %s: task ids in %s must be positive integers."
                % (data_path, collection_name)
            )
        if not isinstance(item, list) or len(item) < 4:
            raise click.ClickException(
                "Datastore %s: task %s in %s has an invalid record."
                % (data_path, task_id, collection_name)
            )
        if item[0] not in allowed_states:
            raise click.ClickException(
                "Datastore %s: task %s in %s has unsupported state %r."
                % (data_path, task_id, collection_name, item[0])
            )
        if not isinstance(item[1], str):
            raise click.ClickException(
                "Datastore %s: task %s in %s must have text content."
                % (data_path, task_id, collection_name)
            )


def validate_data(data, data_path):
    """Validate the persisted board document before command logic uses it."""
    if not isinstance(data, dict):
        raise click.ClickException(
            "Datastore %s must contain a YAML mapping." % data_path
        )

    if "data" not in data or "deleted" not in data:
        raise click.ClickException(
            "Datastore %s must contain data and deleted mappings." % data_path
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
    """Serialize access to one datastore using an atomic lock directory."""
    data_path = os.path.abspath(config["clikan_data"])
    lock_path = data_path + ".lock"
    owner_path = os.path.join(lock_path, "owner")

    try:
        os.mkdir(lock_path)
    except FileExistsError:
        raise click.ClickException(
            "Datastore %s is locked by another clikan process. "
            "If no clikan process is active, remove %s."
            % (data_path, lock_path)
        )
    except OSError as exc:
        raise click.ClickException(
            "Could not lock datastore %s: %s" % (data_path, exc)
        )

    try:
        try:
            with open(owner_path, "w") as owner_file:
                owner_file.write(str(os.getpid()))
        except OSError:
            pass
        yield
    finally:
        try:
            os.unlink(owner_path)
        except OSError:
            pass
        try:
            os.rmdir(lock_path)
        except OSError:
            pass


def wip_limit_reached(config, data):
    """Return True when another transition into WIP would exceed its limit."""
    if "wip" not in config["limits"]:
        return False

    wip_count = sum(
        1 for item in data["data"].values() if item[0] == "inprogress"
    )
    return config["limits"]["wip"] <= wip_count


@click.version_option(VERSION)
@click.command(cls=PrefixGroup, default="show", default_if_no_args=True)
def clikan():
    """clikan: CLI personal kanban"""


@clikan.command()
def configure():
    """Place default config file in CLIKAN_HOME or HOME."""
    home = get_clikan_home()
    data_path = os.path.join(home, ".clikan.dat")
    config_path = os.path.join(home, ".clikan.yaml")
    if os.path.exists(config_path) and not click.confirm(
        "Config file exists. Do you want to overwrite?"
    ):
        return
    try:
        with open(config_path, "w") as outfile:
            yaml.safe_dump(
                {"clikan_data": data_path}, outfile, default_flow_style=False
            )
    except OSError as exc:
        raise click.ClickException(
            "Could not write config file %s: %s" % (config_path, exc)
        )
    click.echo("Creating %s" % config_path)


@clikan.command()
@click.argument("tasks", nargs=-1)
def add(tasks):
    """Add tasks in todo."""
    config = read_config_yaml()
    taskname_length = config["limits"]["taskname"]

    with datastore_lock(config):
        data = read_data(config)
        for task in tasks:
            if len(task) > taskname_length:
                click.echo(
                    "Task must be at most %s chars, Brevity counts: %s"
                    % (taskname_length, task)
                )
                continue

            todos, _, _ = split_items(config, data)
            if (
                "todo" in config["limits"]
                and config["limits"]["todo"] <= len(todos)
            ):
                click.echo("No new todos, limit reached already.")
                continue

            ordered = OrderedDict(sorted(data["data"].items()))
            new_id = next(reversed(ordered)) + 1 if ordered else 1
            entry = ["todo", task, timestamp(), timestamp()]
            data["data"].update({new_id: entry})
            click.echo("Creating new task w/ id: %d -> %s" % (new_id, task))

        write_data(config, data)

    if config["repaint"]:
        display()


@clikan.command()
@click.argument("ids", nargs=-1)
def delete(ids):
    """Delete task."""
    config = read_config_yaml()

    with datastore_lock(config):
        data = read_data(config)
        for task_id in ids:
            try:
                numeric_id = int(task_id)
                item = data["data"].get(numeric_id)
                if item is None:
                    click.echo("No existing task with that id: %d" % numeric_id)
                else:
                    item[0] = "deleted"
                    item[2] = timestamp()
                    data["deleted"].update({numeric_id: item})
                    data["data"].pop(numeric_id)
                    click.echo("Removed task %d." % numeric_id)
            except ValueError:
                click.echo("Invalid task id")

        write_data(config, data)

    if config["repaint"]:
        display()


@clikan.command()
@click.argument("ids", nargs=-1)
def promote(ids):
    """Promote task."""
    config = read_config_yaml()

    with datastore_lock(config):
        data = read_data(config)
        for task_id in ids:
            try:
                numeric_id = int(task_id)
                item = data["data"].get(numeric_id)
                if item is None:
                    click.echo("No existing task with that id: %s" % task_id)
                elif item[0] == "todo":
                    if wip_limit_reached(config, data):
                        click.echo(
                            "Can not promote, in-progress limit of %s reached."
                            % config["limits"]["wip"]
                        )
                    else:
                        click.echo(
                            "Promoting task %s to in-progress." % task_id
                        )
                        data["data"][numeric_id] = [
                            "inprogress",
                            item[1],
                            timestamp(),
                            item[3],
                        ]
                elif item[0] == "inprogress":
                    click.echo("Promoting task %s to done." % task_id)
                    data["data"][numeric_id] = [
                        "done",
                        item[1],
                        timestamp(),
                        item[3],
                    ]
                else:
                    click.echo("Can not promote %s, already done." % task_id)
            except ValueError:
                click.echo("Invalid task id")

        write_data(config, data)

    if config["repaint"]:
        display()


@clikan.command()
@click.argument("ids", nargs=-1)
def regress(ids):
    """Regress task."""
    config = read_config_yaml()

    with datastore_lock(config):
        data = read_data(config)
        for task_id in ids:
            try:
                numeric_id = int(task_id)
                item = data["data"].get(numeric_id)
                if item is None:
                    click.echo("No existing task with id: %s" % task_id)
                elif item[0] == "done":
                    if wip_limit_reached(config, data):
                        click.echo(
                            "Can not regress, in-progress limit of %s reached."
                            % config["limits"]["wip"]
                        )
                    else:
                        click.echo(
                            "Regressing task %s to in-progress." % task_id
                        )
                        data["data"][numeric_id] = [
                            "inprogress",
                            item[1],
                            timestamp(),
                            item[3],
                        ]
                elif item[0] == "inprogress":
                    click.echo("Regressing task %s to todo." % task_id)
                    data["data"][numeric_id] = [
                        "todo",
                        item[1],
                        timestamp(),
                        item[3],
                    ]
                else:
                    click.echo("Already in todo, can not regress %s" % task_id)
            except ValueError:
                click.echo("Invalid task id")

        write_data(config, data)

    if config["repaint"]:
        display()


def display():
    """Show tasks in clikan."""
    config = read_config_yaml()

    with datastore_lock(config):
        data = read_data(config)
        todos, inprogs, dones = split_items(config, data)
        dones = dones[0 : config["limits"]["done"]]

    table = Table(show_header=True, show_footer=True)
    table.add_column(
        "[bold yellow]todo[/bold yellow]", no_wrap=True, footer="clikan"
    )
    table.add_column("[bold green]in-progress[/bold green]", no_wrap=True)
    table.add_column(
        "[bold magenta]done[/bold magenta]",
        no_wrap=True,
        footer="v.{}".format(VERSION),
    )
    table.add_row("\n".join(todos), "\n".join(inprogs), "\n".join(dones))
    Console().print(table)


@clikan.command()
def show():
    """Show the board."""
    display()


def read_data(config):
    """Read the existing data from the configured datasource."""
    data_path = config["clikan_data"]
    try:
        with open(data_path, "r") as stream:
            try:
                data = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    "Datastore %s contains invalid YAML: %s"
                    % (data_path, exc)
                )
    except FileNotFoundError:
        click.echo("No data, initializing data file.")
        data = {"data": {}, "deleted": {}}
        write_data(config, data)
        return data
    except OSError as exc:
        raise click.ClickException(
            "Could not read datastore %s: %s" % (data_path, exc)
        )

    return validate_data(data, data_path)


def write_data(config, data):
    """Atomically replace the datastore with validated YAML data."""
    data_path = config["clikan_data"]
    validate_data(data, data_path)

    directory = os.path.dirname(os.path.abspath(data_path))
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
            temp_path = outfile.name
            yaml.safe_dump(data, outfile, default_flow_style=False)
            outfile.flush()
            os.fsync(outfile.fileno())

        os.replace(temp_path, data_path)
        temp_path = None
    except (OSError, yaml.YAMLError) as exc:
        raise click.ClickException(
            "Could not write datastore %s: %s" % (data_path, exc)
        )
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def get_clikan_home():
    home = os.environ.get("CLIKAN_HOME")
    return home if home else os.path.expanduser("~")


def read_config_yaml():
    """Read and validate the app config from ~/.clikan.yaml."""
    home = get_clikan_home()
    config_path = os.path.join(home, ".clikan.yaml")
    try:
        with open(config_path, "r") as stream:
            try:
                config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    "Config file %s contains invalid YAML: %s"
                    % (config_path, exc)
                )
    except OSError as exc:
        raise click.ClickException(
            "Could not read config file %s: %s" % (config_path, exc)
        )

    return validate_config(config, config_path)


def split_items(config, data):
    todos = []
    inprogs = []
    dones = []

    for key, value in data["data"].items():
        if value[0] == "todo":
            todos.append("[%d] %s" % (key, value[1]))
        elif value[0] == "inprogress":
            inprogs.append("[%d] %s" % (key, value[1]))
        else:
            dones.insert(0, "[%d] %s" % (key, value[1]))

    return todos, inprogs, dones


def timestamp():
    return "{:%Y-%b-%d %H:%M:%S}".format(datetime.datetime.now())
