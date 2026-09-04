from rich.console import Console
from rich.table import Table

from .models import AppConfig, Board, TaskState, format_timestamp


def split_items(board: Board):
    todos = [
        f"[{task.id}] {task.text}"
        for task in sorted(board.active.values(), key=lambda item: item.id)
        if task.state is TaskState.TODO
    ]
    inprogs = [
        f"[{task.id}] {task.text}"
        for task in sorted(board.active.values(), key=lambda item: item.id)
        if task.state is TaskState.IN_PROGRESS
    ]
    done_tasks = sorted(
        (
            task
            for task in board.active.values()
            if task.state is TaskState.DONE
        ),
        key=lambda task: (task.modified_at, task.id),
        reverse=True,
    )
    dones = [f"[{task.id}] {task.text}" for task in done_tasks]
    return todos, inprogs, dones


def render_board(config: AppConfig, board: Board, version: str) -> None:
    todos, inprogs, dones = split_items(board)
    dones = dones[: config.limits.done]

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
    Console().print(table)


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

    Console().print(table)
