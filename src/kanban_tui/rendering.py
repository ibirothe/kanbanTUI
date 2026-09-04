from rich.console import Console
from rich.table import Table

from .models import AppConfig, Board, TaskState


def split_items(board: Board):
    todos = []
    inprogs = []
    dones = []

    for task_id, task in board.active.items():
        label = f"[{task_id}] {task.text}"
        if task.state is TaskState.TODO:
            todos.append(label)
        elif task.state is TaskState.IN_PROGRESS:
            inprogs.append(label)
        else:
            dones.insert(0, label)

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

    for task_id in sorted(board.deleted, reverse=True):
        task = board.deleted[task_id]
        table.add_row(
            str(task_id),
            task.text,
            task.modified_at,
            task.created_at,
        )

    Console().print(table)
