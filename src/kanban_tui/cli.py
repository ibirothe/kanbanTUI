from pathlib import Path

import click
from click_default_group import DefaultGroup

from . import VERSION
from .config import create_default_config, get_config_path, read_config
from .rendering import render_board, render_history
from .services import (
    OperationResult,
    add_tasks,
    delete_tasks,
    edit_task,
    promote_tasks,
    regress_tasks,
    reorder_task,
    restore_tasks,
)
from .storage import datastore_lock, read_data, write_data


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


def _selected_config_path() -> Path | None:
    root_context = click.get_current_context().find_root()
    config_path = root_context.params.get("config_path")
    return config_path if isinstance(config_path, Path) else None


def _read_config():
    return read_config(_selected_config_path())


def _echo_messages(messages: list[str]) -> None:
    for message in messages:
        click.echo(message)


def _complete_operation(result: OperationResult, config) -> None:
    _echo_messages(result.messages)
    if result.succeeded and config.repaint:
        display()
    if result.failed:
        raise click.exceptions.Exit(1)


@click.command(
    name="kanban-tui",
    cls=PrefixGroup,
    default="show",
    default_if_no_args=True,
)
@click.version_option(VERSION)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Use an explicit YAML configuration file.",
)
def main(config_path):
    """kanbanTUI: terminal personal Kanban board."""


@main.command()
def configure():
    """Create the selected configuration and default datastore path."""
    explicit_path = _selected_config_path()
    config_path = get_config_path(explicit_path)
    if config_path.exists() and not click.confirm(
        "Config file exists. Do you want to overwrite?"
    ):
        return

    created_path = create_default_config(explicit_path)
    click.echo(f"Creating {created_path}")


@main.command()
@click.argument("task_words", nargs=-1, required=True)
def add(task_words):
    """Add one task to todo."""
    config = _read_config()
    task_text = " ".join(task_words)
    with datastore_lock(config):
        board = read_data(config)
        result = add_tasks(config, board, [task_text])
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("task_id")
@click.argument("task_words", nargs=-1, required=True)
def edit(task_id, task_words):
    """Edit the text of an active task."""
    config = _read_config()
    task_text = " ".join(task_words)
    with datastore_lock(config):
        board = read_data(config)
        result = edit_task(config, board, task_id, task_text)
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def delete(ids):
    """Delete tasks."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = delete_tasks(board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def restore(ids):
    """Restore deleted tasks to todo."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = restore_tasks(config, board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def promote(ids):
    """Promote tasks."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = promote_tasks(config, board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def regress(ids):
    """Regress tasks."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = regress_tasks(config, board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("task_id")
@click.argument("target", type=click.Choice(["top", "bottom", "before", "after"]))
@click.argument("reference_id", required=False)
def move(task_id, target, reference_id):
    """Reorder a TODO or in-progress task within its current column."""
    if target in {"before", "after"} and reference_id is None:
        raise click.UsageError(f"{target} requires REFERENCE_ID")
    if target in {"top", "bottom"} and reference_id is not None:
        raise click.UsageError(f"{target} does not accept REFERENCE_ID")

    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = reorder_task(board, task_id, target, reference_id)
        write_data(config, board)
    _complete_operation(result, config)


def display(output_format: str = "table") -> None:
    config = _read_config()
    board = read_data(config, initialize_missing=False)
    render_board(config, board, VERSION, output_format)


@main.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "plain", "json"], case_sensitive=False),
    default="table",
    show_default=True,
)
def show(output_format):
    """Show the board."""
    display(output_format.lower())


@main.command()
def history():
    """Show deleted task history."""
    config = _read_config()
    board = read_data(config, initialize_missing=False)
    render_history(board)
