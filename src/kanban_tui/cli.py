import os
from pathlib import Path

import click

from . import VERSION
from .application import BoardApplication, StoreError
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
from .http_api import ImportApi, create_server
from .imports import ImportMode
from .models import TaskPriority, TaskState, normalize_tag
from .operation_messages import format_operation
from .policy import PolicyViolation
from .rendering import SORT_CHOICES, render_board, render_history
from .resources import resolve_board_paths
from .results import OperationResult, OperationStatus
from .services import (
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
from .settings import AppConfig
from .storage import YamlBoardStore
from .themes import get_theme, theme_names
from .transfer import read_export, write_export


class ThemeParamType(click.ParamType):
    """Validate themes at invocation time, without filesystem work at import."""

    name = "theme"

    def convert(self, value, param, ctx):
        try:
            return get_theme(value).name
        except ValueError as exc:
            self.fail(str(exc), param, ctx)

    def shell_complete(self, ctx, param, incomplete):
        from click.shell_completion import CompletionItem

        return [
            CompletionItem(name)
            for name in theme_names()
            if name.casefold().startswith(incomplete.casefold())
        ]


class PrefixGroup(click.Group):
    """Click group that accepts a unique command prefix."""

    def get_command(self, ctx, cmd_name):
        command = super().get_command(ctx, cmd_name)
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
            return super().get_command(ctx, matches[0])
        ctx.fail("Too many matches: %s" % ", ".join(sorted(matches)))

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except StoreError as exc:
            raise click.ClickException(str(exc)) from exc


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


def _runtime() -> tuple[AppConfig, BoardApplication]:
    root = click.get_current_context().find_root()
    runtime = root.meta.get("kanban_tui.runtime")
    if runtime is None:
        config = _read_config()
        runtime = (config, BoardApplication(YamlBoardStore(config)))
        root.meta["kanban_tui.runtime"] = runtime
    return runtime


def _complete_board_name(ctx, param, incomplete):
    del ctx, param
    prefix = incomplete.casefold()
    return [name for name in list_named_boards() if name.casefold().startswith(prefix)]


def _echo_result(result: OperationResult) -> None:
    for item in result.items:
        click.echo(
            format_operation(item),
            err=item.status is OperationStatus.REJECTED,
        )


def _complete_operation(result: OperationResult, config) -> None:
    _echo_result(result)
    if result.changed and config.presentation.repaint:
        display()
    if result.rejected:
        raise click.exceptions.Exit(1)


def _run_state_command(ids: tuple[str, ...], target_state: TaskState) -> None:
    config, application = _runtime()
    _, result = application.mutate(
        lambda board: move_tasks_to_state(config.policy, board, ids, target_state),
    )
    _complete_operation(result, config)


def _validate_export_target(path: Path, config) -> Path:
    target = path.expanduser().resolve()
    try:
        paths = resolve_board_paths(config.data_path, _effective_config_path())
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if target in paths.protected:
        raise click.ClickException(
            f"Export target {target} is reserved for the selected board."
        )
    return target


@click.group(
    name="kanban-tui",
    cls=PrefixGroup,
    invoke_without_command=True,
    no_args_is_help=False,
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
    shell_complete=_complete_board_name,
    help="Use a named board.",
)
@click.pass_context
def main(ctx, config_path, board_name):
    """kanbanTUI: terminal personal Kanban board."""
    if config_path is not None and board_name is not None:
        raise click.UsageError("--config and --board cannot be used together.")
    if board_name is not None:
        validate_board_name(board_name)
    if ctx.invoked_subcommand is None:
        display()


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
        click.echo(
            "No boards configured. Create one with: kanban-tui board create NAME"
        )
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
    click.echo(f"theme: {config.presentation.theme}")
    click.echo(
        "limits.todo: "
        + (str(config.limits.todo) if config.limits.todo is not None else "unlimited")
    )
    click.echo(
        "limits.wip: "
        + (str(config.limits.wip) if config.limits.wip is not None else "unlimited")
    )
    click.echo(f"limits.done: {config.presentation.done_limit}")
    click.echo(f"limits.taskname: {config.limits.taskname}")
    click.echo(f"repaint: {'true' if config.presentation.repaint else 'false'}")


@config_commands.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set one supported configuration value."""
    path = set_config_value(key, value, _selected_config_path())
    click.echo(f"Updated {key} in {path}")


@main.group(name="theme")
def theme_commands():
    """Inspect and select the color theme for the selected board."""


@theme_commands.command(name="list")
def theme_list():
    """List available themes and mark the selected one."""
    current = _read_config().theme
    for name in theme_names():
        theme = get_theme(name)
        marker = "*" if name == current else " "
        click.echo(f"{marker} {name}\t{theme.description}")


@theme_commands.command(name="current")
def theme_current():
    """Print the selected theme name."""
    click.echo(_read_config().theme)


@theme_commands.command(name="set")
@click.argument("name", type=ThemeParamType())
def theme_set(name):
    """Persist an available theme for the selected board."""
    normalized = get_theme(name).name
    path = set_config_value("theme", normalized, _selected_config_path())
    click.echo(f"Theme set to {normalized} in {path}")


@main.command()
@click.argument("task_words", nargs=-1, required=True)
@click.option("--priority", type=click.Choice(["low", "normal", "high", "urgent"]))
@click.option("--tag", "tags", multiple=True, help="Add a tag; may be repeated.")
def add(task_words, priority, tags):
    """Add one task to TODO."""
    config, application = _runtime()
    task_text = " ".join(task_words)
    _, result = application.mutate(
        lambda board: add_tasks(
            config.policy, board, [task_text], priority=priority, tags=tags
        ),
    )
    _complete_operation(result, config)


@main.command()
@click.argument("task_id")
@click.argument("task_words", nargs=-1, required=True)
def edit(task_id, task_words):
    """Edit the text of an active task."""
    config, application = _runtime()
    task_text = " ".join(task_words)
    _, result = application.mutate(
        lambda board: edit_task(config.policy, board, task_id, task_text)
    )
    _complete_operation(result, config)


@main.command()
@click.argument("task_id")
@click.argument(
    "level",
    type=click.Choice(["low", "normal", "high", "urgent", "clear"]),
)
def priority(task_id, level):
    """Set or clear an active task priority."""
    config, application = _runtime()
    selected = None if level == "clear" else TaskPriority(level)
    _, result = application.mutate(
        lambda board: set_task_priority(board, task_id, selected)
    )
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
    config, application = _runtime()
    _, result = application.mutate(
        lambda board: update_task_tag(board, task_id, action, tag)
    )
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def delete(ids):
    """Archive tasks."""
    config, application = _runtime()
    _, result = application.mutate(lambda board: delete_tasks(board, ids))
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def restore(ids):
    """Restore archived tasks to TODO."""
    config, application = _runtime()
    _, result = application.mutate(
        lambda board: restore_tasks(config.policy, board, ids)
    )
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
    config, application = _runtime()
    _, result = application.mutate(
        lambda board: promote_tasks(config.policy, board, ids)
    )
    _complete_operation(result, config)


@main.command()
@click.argument("ids", nargs=-1, required=True)
def regress(ids):
    """Move tasks back by one state."""
    config, application = _runtime()
    _, result = application.mutate(
        lambda board: regress_tasks(config.policy, board, ids)
    )
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

    config, application = _runtime()
    _, result = application.mutate(
        lambda board: reorder_task(board, task_id, target, reference_id)
    )
    _complete_operation(result, config)


@main.command(name="export")
@click.argument("path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--force", is_flag=True, help="Overwrite an existing export file.")
def export_command(path, force):
    """Export the complete selected board as JSON."""
    config, application = _runtime()
    target = _validate_export_target(path, config)
    board = application.read()
    exported_path = write_export(target, board, overwrite=force)
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
    config, application = _runtime()
    try:
        _, result = application.import_board(
            config.policy,
            imported,
            ImportMode(mode.lower()),
            source=str(path.resolve()),
        )
    except PolicyViolation as exc:
        raise click.ClickException(str(exc)) from exc
    _echo_result(result)
    if not result.changed:
        return
    if config.presentation.repaint:
        display()


@main.command()
def undo():
    """Undo the last successful board mutation."""
    config, application = _runtime()
    application.undo()
    click.echo("Undid last board change.")
    if config.presentation.repaint:
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
    config, application = _runtime()
    board = application.read()
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
    config, application = _runtime()
    from .tui import run_tui

    params = click.get_current_context().find_root().params
    explicit = params.get("config_path")
    identity = str(params.get("board_name") or "default")
    if isinstance(explicit, Path):
        identity = f"config: {explicit.name}"
    run_tui(config, application=application, board_name=identity)


def _selected_board_identity() -> str:
    params = click.get_current_context().find_root().params
    explicit = params.get("config_path")
    if isinstance(explicit, Path):
        return f"config: {explicit.name}"
    return str(params.get("board_name") or "default")


@main.command(name="serve-api")
@click.option(
    "--port",
    type=click.IntRange(0, 65535),
    default=8765,
    show_default=True,
    help="Local TCP port; use 0 to let the OS select one.",
)
def api_command(port):
    """Serve the selected board's import API on IPv4 loopback.

    Requires KANBAN_TUI_API_TOKEN in the environment. The server never binds to
    an external interface.
    """
    token = os.environ.get("KANBAN_TUI_API_TOKEN")
    if token is None:
        raise click.ClickException(
            "Set KANBAN_TUI_API_TOKEN before starting the local API."
        )

    config, application = _runtime()
    try:
        api = ImportApi(application, config.policy, token=token)
        server = create_server(api, port=port)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except OSError as exc:
        raise click.ClickException(f"Could not bind local API: {exc}") from exc

    try:
        with server:
            bound_port = server.server_address[1]
            identity = _selected_board_identity()
            click.echo(
                f"Serving local API for {identity!r} on http://127.0.0.1:{bound_port}"
            )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    except OSError as exc:
        raise click.ClickException(f"Local API failed: {exc}") from exc
    click.echo("Local API stopped.")


@main.command()
def history():
    """Show archived task history."""
    config, application = _runtime()
    board = application.read()
    render_history(board, config)
