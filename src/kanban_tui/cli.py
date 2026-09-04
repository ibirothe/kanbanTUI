import click
from click_default_group import DefaultGroup

from . import VERSION
from .config import create_default_config, get_config_path, read_config
from .rendering import render_board
from .services import add_tasks, delete_tasks, promote_tasks, regress_tasks
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


def _echo_messages(messages):
    for message in messages:
        click.echo(message)


def _repaint_if_enabled(config):
    if config.repaint:
        display()


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
@click.argument("tasks", nargs=-1)
def add(tasks):
    """Add tasks in todo."""
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
        messages = add_tasks(config, board, tasks)
        write_data(config, board)
    _echo_messages(messages)
    _repaint_if_enabled(config)


@clikan.command()
@click.argument("ids", nargs=-1)
def delete(ids):
    """Delete tasks."""
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
        messages = delete_tasks(board, ids)
        write_data(config, board)
    _echo_messages(messages)
    _repaint_if_enabled(config)


@clikan.command()
@click.argument("ids", nargs=-1)
def promote(ids):
    """Promote tasks."""
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
        messages = promote_tasks(config, board, ids)
        write_data(config, board)
    _echo_messages(messages)
    _repaint_if_enabled(config)


@clikan.command()
@click.argument("ids", nargs=-1)
def regress(ids):
    """Regress tasks."""
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
        messages = regress_tasks(config, board, ids)
        write_data(config, board)
    _echo_messages(messages)
    _repaint_if_enabled(config)


def display():
    config = read_config()
    with datastore_lock(config):
        board = read_data(config)
    render_board(config, board, VERSION)


@clikan.command()
def show():
    """Show the board."""
    display()
