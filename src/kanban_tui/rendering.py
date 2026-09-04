import json
import os

from rich.console import Console
from rich.table import Table

from .models import AppConfig, Board, Task, TaskState, format_timestamp


def _tasks_for_state(board: Board, state: TaskState) -> list[Task]:
    tasks = [task for task in board.active.values() if task.state is state]
    if state is TaskState.DONE:
        return sorted(
            tasks,
            key=lambda task: (task.modified_at, task.id),
            reverse=True,
        )
    return sorted(tasks, key=lambda task: task.id)


def visible_tasks(config: AppConfig, board: Board) -> list[Task]:
    todos = _tasks_for_state(board, TaskState.TODO)
    inprogs = _tasks_for_state(board, TaskState.IN_PROGRESS)
    dones = _tasks_for_state(board, TaskState.DONE)[: config.limits.done]
    return [*todos, *inprogs, *dones]


def split_items(board: Board):
    todos = [f"[{task.id}] {task.text}" for task in _tasks_for_state(board, TaskState.TODO)]
    inprogs = [
        f"[{task.id}] {task.text}"
        for task in _tasks_for_state(board, TaskState.IN_PROGRESS)
    ]
    dones = [f"[{task.id}] {task.text}" for task in _tasks_for_state(board, TaskState.DONE)]
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


def format_json(config: AppConfig, board: Board) -> str:
    payload = {"tasks": [_task_payload(task) for task in visible_tasks(config, board)]}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _escape_plain_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def format_plain(config: AppConfig, board: Board) -> str:
    lines = ["id\tstate\ttext\tcreated_at\tmodified_at"]
    for task in visible_tasks(config, board):
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


def render_board(
    config: AppConfig,
    board: Board,
    version: str,
    output_format: str = "table",
) -> None:
    if output_format == "json":
        print(format_json(config, board))
        return
    if output_format == "plain":
        print(format_plain(config, board))
        return
    if output_format != "table":
        raise ValueError(f"unsupported output format: {output_format}")

    todos, inprogs, dones = board_columns(config, board)
    table = Table(show_header=True, show_footer=True)
    table.add_column(
        "[bold yellow]todo[/bold yellow]", no_wrap=True, footer="clikan"
    )
    table.add_column("[bold green]in-progress[/bold green]", no_wrap=True)
    table.add_column(
        "[bold magenta]done[/bold magenta]",
        no_wrap=True,
        footer=f"v.{version}",
    )
    table.add_row("\n".join(todos), "\n".join(inprogs), "\n".join(dones))
    Console(no_color=bool(os.environ.get("NO_COLOR"))).print(table)


def render_history(board: Board) -> None:
    table = Table(show_header=True)
    table.add_column("id", justify="right")
    table.add_column("task")
    table.add_column("deleted / modified")
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
