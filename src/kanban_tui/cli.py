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
from .models import TaskPriority, TaskState, normalize_tag
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
    set_task_priority,
    update_task_tag,
)
from .storage import datastore_lock, read_data, undo_last_change, write_data
from .transfer import (
    merge_boards,
    read_export,
    validate_board_capacity,
    write_export,
)


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


def _persist_operation(config, board, result: OperationResult) -> None:
    if result.succeeded:
        write_data(config, board, snapshot_previous=True)


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
        _persist_operation(config, board, result)
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

    if default_path.exists():
        entries.append(("default", default_path))
    entries.extend((name, get_board_config_path(name)) for name in list_named_boards())

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
        _persist_operation(config, board, result)
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
        _persist_operation(config, board, result)
    _complete_operation(result, config)


@main.command()
@click.argument("task_id")
@click.argument(
    "level",
    type=click.Choice(["low", "normal", "high", "urgent", "clear"]),
)
def priority(task_id, level):
    """Set or clear an active task priority."""
    config = _read_config()
    selected = None if level == "clear" else TaskPriority(level)
    with datastore_lock(config):
        board = read_data(config)
        result = set_task_priority(board, task_id, selected)
        _persist_operation(config, board, result)
    _complete_operation(result, config)


@main.group(name="tag")
def tag_commands():
    """Add, remove, or clear active task tags."""


@tag_commands.command(name="add")
@click.argument("task_id")
@click.argument("tag")
def tag_add(task_id, tag):
    """Add one tag to a task."""
    _run_tag_command(task_id, "add", tag)


@tag_commands.command(name="remove")
@click.argument("task_id")
@click.argument("tag")
def tag_remove(task_id, tag):
    """Remove one tag from a task."""
    _run_tag_command(task_id, "remove", tag)


@tag_commands.command(name="clear")
@click.argument("task_id")
def tag_clear(task_id):
    """Clear all tags from a task."""
    _run_tag_command(task_id, "clear")


def _run_tag_command(task_id: str, action: str, tag: str | None = None) -> None:
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = update_task_tag(board, task_id, action, tag)
        _persist_operation(config, board, result)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def delete(ids):
    """Archive tasks."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = delete_tasks(board, ids)
        _persist_operation(config, board, result)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def restore(ids):
    """Restore archived tasks to TODO."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = restore_tasks(config, board, ids)
        _persist_operation(config, board, result)
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
        _persist_operation(config, board, result)
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def regress(ids):
    """Move tasks back by one state."""
    config = _read_config()
    with datastore_lock(config):
        board = read_data(config)
        result = regress_tasks(config, board, ids)
        _persist_operation(config, board, result)
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
        _persist_operation(config, board, result)
    _complete_operation(result, config)


@main.command(name="export")
@click.argument("path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--force", is_flag=True, help="Overwrite an existing export file.")
def export_command(path, force):
    """Export the complete selected board as JSON."""
    config = _read_config()
    board = read_data(config, initialize_missing=False)
    exported_path = write_export(path, board, overwrite=force)
    click.echo(f"Exported board to {exported_path}")


@main.command(name="import")
@click.argument(
    "path",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
)
@click.option(
    "--mode",
    type=click.Choice(["merge", "replace"], case_sensitive=False),
    default="merge",
    show_default=True,
)
def import_command(path, mode):
    """Import a complete board export."""
    imported = read_export(path)
    config = _read_config()

    with datastore_lock(config):
        current = read_data(config, initialize_missing=False)
        target = imported if mode.lower() == "replace" else merge_boards(current, imported)
        validate_board_capacity(config, target)
        write_data(config, target, snapshot_previous=True)

    click.echo(f"Imported board from {path.resolve()} ({mode.lower()}).")
    if config.repaint:
        display()


@main.command()
def undo():
    """Undo the last successful board mutation."""
    config = _read_config()
    with datastore_lock(config):
        undo_last_change(config)
    click.echo("Undid last board change.")
    if config.repaint:
        display()


def display(
    output_format: str = "table",
    *,
    state_filter: TaskState | None = None,
    search: str | None = None,
    sort_by: str = "default",
    priority_filter: TaskPriority | None = None,
    unprioritized_only: bool = False,
    tag_filter: str | None = None,
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
        priority_filter=priority_filter,
        unprioritized_only=unprioritized_only,
        tag_filter=tag_filter,
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
@click.option("--search", default=None, help="Search task text, tags, or priority.")
@click.option(
    "--sort",
    "sort_by",
    type=click.Choice(SORT_CHOICES, case_sensitive=False),
    default="default",
    show_default=True,
)
@click.option(
    "--priority",
    "priority_name",
    type=click.Choice(["low", "normal", "high", "urgent", "none"]),
    default=None,
    help="Filter by priority, or use none for unprioritized tasks.",
)
@click.option("--tag", "tag_name", default=None, help="Filter by exact tag.")
def show(output_format, state_name, search, sort_by, priority_name, tag_name):
    """Show the board."""
    state_filter = TaskState(state_name.lower()) if state_name else None
    priority_filter = (
        TaskPriority(priority_name)
        if priority_name is not None and priority_name != "none"
        else None
    )
    unprioritized_only = priority_name == "none"
    tag_filter = None
    if tag_name is not None:
        try:
            tag_filter = normalize_tag(tag_name)
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="--tag") from exc

    display(
        output_format.lower(),
        state_filter=state_filter,
        search=search,
        sort_by=sort_by.lower(),
        priority_filter=priority_filter,
        unprioritized_only=unprioritized_only,
        tag_filter=tag_filter,
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
