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


def _echo_messages(messages: list[str]) -> None:
    for message in messages:
        click.echo(message)


def _complete_operation(result: OperationResult, config) -> None:
    _echo_messages(result.messages)
    if result.succeeded and config.repaint:
        display()
    if result.failed:
        raise click.exceptions.Exit(1)


@click.version_option(VERSION)
@click.command(cls=PrefixGroup, default="show", default_if_no_args=True)
def clikan():
    """clikan: CLI personal kanban"""


@clikan.command()
def configure():
    """Create the default configuration in CLIKAN_HOME or HOME."""
    config_path = get_config_path()
    if config_path.exists() and not click.confirm(
        "Config file exists. Do you want to overwrite?"
    ):
        return

    created_path = create_default_config()
    click.echo(f"Creating {created_path}")


@clikan.command()
@click.argument("task_words", nargs=-1, required=True)
def add(task_words):
    """Add one task to todo."""
    config = read_config()
    task_text = " ".join(task_words)
    with datastore_lock(config):
        board = read_data(config)
        result = add_tasks(config, board, [task_text])
        write_data(config, board)
    _complete_operation(result, config)


@clikan.command()
@click.argument("task_id")
@click.argument("task_words", nargs=-1, required=True)
def edit(task_id, task_words):
    """Edit the text of an active task."""
    config = read_config()
    task_text = " ".join(task_words)
    with datastore_lock(config):
        board = read_data(config)
        result = edit_task(config, board, task_id, task_text)
        write_data(config, board)
    _complete_operation(result, config)


@clikan.command()
@click.argument("ids", nargs=-1, required=True)
def delete(ids):
    """Delete tasks."""
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = delete_tasks(board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@clikan.command()
@click.argument("ids", nargs=-1, required=True)
def restore(ids):
    """Restore deleted tasks to todo."""
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = restore_tasks(config, board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@clikan.command()
@click.argument("ids", nargs=-1, required=True)
def promote(ids):
    """Promote tasks."""
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = promote_tasks(config, board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@clikan.command()
@click.argument("ids", nargs=-1, required=True)
def regress(ids):
    """Regress tasks."""
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = regress_tasks(config, board, ids)
        write_data(config, board)
    _complete_operation(result, config)


def display():
    config = read_config()
    board = read_data(config, initialize_missing=False)
    render_board(config, board, VERSION)


@clikan.command()
def show():
    """Show the board."""
    display()


@clikan.command()
def history():
    """Show deleted task history."""
    config = read_config()
    board = read_data(config, initialize_missing=False)
    render_history(board)
