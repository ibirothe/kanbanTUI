import json
import os

from rich.console import Console
from rich.table import Table

from .models import AppConfig, Board, Task, TaskState, format_timestamp


SORT_CHOICES = ("default", "id", "created", "modified")


def _tasks_for_state(
    board: Board,
    state: TaskState,
    *,
    search: str | None = None,
    sort_by: str = "default",
) -> list[Task]:
    tasks = [task for task in board.active.values() if task.state is state]

    if search:
        needle = search.casefold()
        tasks = [task for task in tasks if needle in task.text.casefold()]

    if sort_by == "default":
        ordered = board.ordered_tasks(state)
        task_ids = {task.id for task in tasks}
        return [task for task in ordered if task.id in task_ids]
    if sort_by == "id":
        return sorted(tasks, key=lambda task: task.id)
    if sort_by == "created":
        return sorted(tasks, key=lambda task: (task.created_at, task.id), reverse=True)
    if sort_by == "modified":
        return sorted(tasks, key=lambda task: (task.modified_at, task.id), reverse=True)
    raise ValueError(f"unsupported sort: {sort_by}")


def visible_tasks(
    config: AppConfig,
    board: Board,
    *,
    state_filter: TaskState | None = None,
    search: str | None = None,
    sort_by: str = "default",
) -> list[Task]:
    states = (
        [state_filter]
        if state_filter is not None
        else [TaskState.TODO, TaskState.IN_PROGRESS, TaskState.DONE]
    )
    visible: list[Task] = []
    for state in states:
        tasks = _tasks_for_state(board, state, search=search, sort_by=sort_by)
        if state is TaskState.DONE:
            tasks = tasks[: config.limits.done]
        visible.extend(tasks)
    return visible


def split_items(board: Board):
    todos = [f"[{task.id}] {task.text}" for task in board.ordered_tasks(TaskState.TODO)]
    inprogs = [
        f"[{task.id}] {task.text}"
        for task in board.ordered_tasks(TaskState.IN_PROGRESS)
    ]
    dones = [f"[{task.id}] {task.text}" for task in board.ordered_tasks(TaskState.DONE)]
    return todos, inprogs, dones


def board_columns(config: AppConfig, board: Board):
    todos, inprogs, dones = split_items(board)
    return todos, inprogs, dones[: config.limits.done]


def _task_payload(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "state": task.state.value,
        "text": task.text,
        "created_at": format_timestamp(task.created_at),
        "modified_at": format_timestamp(task.modified_at),
    }


def format_json(
    config: AppConfig,
    board: Board,
    *,
    state_filter: TaskState | None = None,
    search: str | None = None,
    sort_by: str = "default",
) -> str:
    payload = {
        "tasks": [
            _task_payload(task)
            for task in visible_tasks(
                config,
                board,
                state_filter=state_filter,
                search=search,
                sort_by=sort_by,
            )
        ]
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _escape_plain_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def format_plain(
    config: AppConfig,
    board: Board,
    *,
    state_filter: TaskState | None = None,
    search: str | None = None,
    sort_by: str = "default",
) -> str:
    lines = ["id\tstate\ttext\tcreated_at\tmodified_at"]
    for task in visible_tasks(
        config,
        board,
        state_filter=state_filter,
        search=search,
        sort_by=sort_by,
    ):
        lines.append(
            "\t".join(
                [
                    str(task.id),
                    task.state.value,
                    _escape_plain_text(task.text),
                    format_timestamp(task.created_at),
                    format_timestamp(task.modified_at),
                ]
            )
        )
    return "\n".join(lines)


def column_label(
    config: AppConfig,
    board: Board,
    state: TaskState,
    *,
    visible_count: int | None = None,
) -> str:
    total = sum(1 for task in board.active.values() if task.state is state)
    shown = total if visible_count is None else visible_count

    if state is TaskState.TODO:
        limit = config.limits.todo
        label = "TODO"
    elif state is TaskState.IN_PROGRESS:
        limit = config.limits.wip
        label = "IN PROGRESS"
    else:
        limit = None
        label = "DONE"

    if state is TaskState.DONE:
        base = f"{label} {shown}/{total}" if shown != total else f"{label} {total}"
    elif limit is None:
        base = f"{label} {total}"
    else:
        base = f"{label} {total}/{limit}"
        if total >= limit:
            base += " FULL"

    if state is not TaskState.DONE and shown != total:
        base += f" · {shown} shown"
    return base


def _table_tasks(
    config: AppConfig,
    board: Board,
    *,
    search: str | None = None,
    sort_by: str = "default",
) -> dict[TaskState, list[Task]]:
    return {
        state: _tasks_for_state(board, state, search=search, sort_by=sort_by)[
            : config.limits.done if state is TaskState.DONE else None
        ]
        for state in [TaskState.TODO, TaskState.IN_PROGRESS, TaskState.DONE]
    }


def render_board(
    config: AppConfig,
    board: Board,
    version: str,
    output_format: str = "table",
    *,
    state_filter: TaskState | None = None,
    search: str | None = None,
    sort_by: str = "default",
) -> None:
    if output_format == "json":
        print(
            format_json(
                config,
                board,
                state_filter=state_filter,
                search=search,
                sort_by=sort_by,
            )
        )
        return
    if output_format == "plain":
        print(
            format_plain(
                config,
                board,
                state_filter=state_filter,
                search=search,
                sort_by=sort_by,
            )
        )
        return
    if output_format != "table":
        raise ValueError(f"unsupported output format: {output_format}")

    console = Console(no_color=bool(os.environ.get("NO_COLOR")))
    filtered = state_filter is not None or bool(search)

    if state_filter is not None:
        tasks = _tasks_for_state(board, state_filter, search=search, sort_by=sort_by)
        if state_filter is TaskState.DONE:
            tasks = tasks[: config.limits.done]
        if not tasks:
            console.print("No matching tasks.")
            return
        table = Table(show_header=True, show_footer=True)
        table.add_column(
            column_label(config, board, state_filter, visible_count=len(tasks)),
            overflow="fold",
            footer=f"kanbanTUI v.{version}",
        )
        for task in tasks:
            table.add_row(f"[{task.id}] {task.text}")
        console.print(table)
        return

    columns = _table_tasks(config, board, search=search, sort_by=sort_by)
    if not any(columns.values()):
        if filtered:
            console.print("No matching tasks.")
        else:
            console.print("No tasks yet. Add one with: kanban-tui add <task>")
        return

    table = Table(show_header=True, show_footer=True, expand=True)
    table.add_column(
        f"[bold yellow]{column_label(config, board, TaskState.TODO, visible_count=len(columns[TaskState.TODO]))}[/bold yellow]",
        overflow="fold",
        footer="kanbanTUI",
    )
    table.add_column(
        f"[bold green]{column_label(config, board, TaskState.IN_PROGRESS, visible_count=len(columns[TaskState.IN_PROGRESS]))}[/bold green]",
        overflow="fold",
    )
    table.add_column(
        f"[bold magenta]{column_label(config, board, TaskState.DONE, visible_count=len(columns[TaskState.DONE]))}[/bold magenta]",
        overflow="fold",
        footer=f"v.{version}",
    )

    max_rows = max(len(tasks) for tasks in columns.values())
    for index in range(max_rows):
        row = []
        for state in [TaskState.TODO, TaskState.IN_PROGRESS, TaskState.DONE]:
            tasks = columns[state]
            row.append(f"[{tasks[index].id}] {tasks[index].text}" if index < len(tasks) else "")
        table.add_row(*row)
    console.print(table)


def render_history(board: Board) -> None:
    table = Table(show_header=True)
    table.add_column("id", justify="right")
    table.add_column("task")
    table.add_column("archived / modified")
    table.add_column("created")

    deleted_tasks = sorted(
        board.deleted.values(),
        key=lambda task: (task.modified_at, task.id),
        reverse=True,
    )
    for task in deleted_tasks:
        table.add_row(
            str(task.id),
            task.text,
            format_timestamp(task.modified_at),
            format_timestamp(task.created_at),
        )

    Console(no_color=bool(os.environ.get("NO_COLOR"))).print(table)
