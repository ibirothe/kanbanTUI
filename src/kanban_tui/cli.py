from pathlib import Path

import click
from click_default_group import DefaultGroup

from . import VERSION
from .config import (
    create_default_config,
    create_named_board,
    get_board_config_path,
    get_config_path,
    list_named_boards,
    read_config,
    set_config_value,
    validate_board_name,
)
from .models import TaskState
from .rendering import SORT_CHOICES, render_board, render_history
from .services import (
    OperationResult,
    add_tasks,
    delete_tasks,
    edit_task,
    move_tasks_to_state,
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
    if isinstance(config_path, Path):
        return config_path

    board_name = root_context.params.get("board_name")
    if isinstance(board_name, str):
        return get_board_config_path(board_name)
    return None


def _effective_config_path() -> Path:
    return get_config_path(_selected_config_path())


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


def _run_state_command(ids: tuple[str, ...], target_state: TaskState) -> None:
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = move_tasks_to_state(config, board, ids, target_state)
        write_data(config, board)
    _complete_operation(result, config)


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
@click.option(
    "--board",
    "board_name",
    default=None,
    metavar="NAME",
    help="Use a named board from $KANBAN_TUI_HOME/boards.",
)
def main(config_path, board_name):
    """kanbanTUI: terminal personal Kanban board."""
    if config_path is not None and board_name is not None:
        raise click.UsageError("--config and --board cannot be used together.")
    if board_name is not None:
        validate_board_name(board_name)


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


@main.group(name="board")
def board_commands():
    """Create and inspect named boards."""


@board_commands.command(name="create")
@click.argument("name")
def board_create(name):
    """Create a named board."""
    normalized = validate_board_name(name)
    created_path = create_named_board(normalized)
    click.echo(f"Created board '{normalized}' at {created_path}")


@board_commands.command(name="list")
def board_list():
    """List the default and named boards."""
    effective_path = _effective_config_path()
    default_path = get_config_path()
    entries: list[tuple[str, Path]] = []

    if default_path.exists() or effective_path == default_path:
        entries.append(("default", default_path))
    entries.extend(
        (name, get_board_config_path(name)) for name in list_named_boards()
    )

    if not entries:
        click.echo("No boards configured. Create one with: kanban-tui board create NAME")
        return

    for name, path in entries:
        marker = "*" if path == effective_path else " "
        click.echo(f"{marker} {name}\t{path}")


@main.group(name="config")
def config_commands():
    """Inspect and edit the selected configuration."""


@config_commands.command(name="path")
def config_path_command():
    """Print the selected configuration path."""
    click.echo(_effective_config_path())


@config_commands.command(name="show")
def config_show():
    """Show normalized configuration values."""
    path = _effective_config_path()
    config = _read_config()
    click.echo(f"path: {path}")
    click.echo(f"data_path: {config.data_path}")
    click.echo(
        "limits.todo: "
        + (str(config.limits.todo) if config.limits.todo is not None else "unlimited")
    )
    click.echo(
        "limits.wip: "
        + (str(config.limits.wip) if config.limits.wip is not None else "unlimited")
    )
    click.echo(f"limits.done: {config.limits.done}")
    click.echo(f"limits.taskname: {config.limits.taskname}")
    click.echo(f"repaint: {'true' if config.repaint else 'false'}")


@config_commands.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set one supported configuration value."""
    path = set_config_value(key, value, _selected_config_path())
    click.echo(f"Updated {key} in {path}")


@main.command()
@click.argument("task_words", nargs=-1, required=True)
def add(task_words):
    """Add one task to TODO."""
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
    """Archive tasks."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = delete_tasks(board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def restore(ids):
    """Restore archived tasks to TODO."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = restore_tasks(config, board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def start(ids):
    """Move tasks to IN PROGRESS."""
    _run_state_command(ids, TaskState.IN_PROGRESS)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def done(ids):
    """Complete tasks."""
    _run_state_command(ids, TaskState.DONE)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def todo(ids):
    """Move tasks to TODO."""
    _run_state_command(ids, TaskState.TODO)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def promote(ids):
    """Advance tasks by one state."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = promote_tasks(config, board, ids)
        write_data(config, board)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def regress(ids):
    """Move tasks back by one state."""
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
    """Reorder a TODO or IN PROGRESS task within its current column."""
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


def display(
    output_format: str = "table",
    *,
    state_filter: TaskState | None = None,
    search: str | None = None,
    sort_by: str = "default",
) -> None:
    config = _read_config()
    board = read_data(config, initialize_missing=False)
    render_board(
        config,
        board,
        VERSION,
        output_format,
        state_filter=state_filter,
        search=search,
        sort_by=sort_by,
    )


@main.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "plain", "json"], case_sensitive=False),
    default="table",
    show_default=True,
)
@click.option(
    "--state",
    "state_name",
    type=click.Choice(["todo", "inprogress", "done"], case_sensitive=False),
    default=None,
    help="Show only one task state.",
)
@click.option("--search", default=None, help="Show tasks whose text contains this value.")
@click.option(
    "--sort",
    "sort_by",
    type=click.Choice(SORT_CHOICES, case_sensitive=False),
    default="default",
    show_default=True,
)
def show(output_format, state_name, search, sort_by):
    """Show the board."""
    state_filter = TaskState(state_name.lower()) if state_name else None
    display(
        output_format.lower(),
        state_filter=state_filter,
        search=search,
        sort_by=sort_by.lower(),
    )


@main.command(name="tui")
def tui_command():
    """Open the interactive full-screen board."""
    config = _read_config()
    from .tui import run_tui

    run_tui(config)


@main.command()
def history():
    """Show archived task history."""
    config = _read_config()
    board = read_data(config, initialize_missing=False)
    render_history(board)
