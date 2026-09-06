"""Application transaction boundaries shared by terminal adapters."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

from .models import AppConfig, Board, Task, TaskPriority, TaskState
from .services import OperationResult
from .storage import datastore_lock, read_data, undo_last_change, write_data


@dataclass(frozen=True)
class TaskExpectation:
    """Detached comparison of the complete task state represented on disk."""

    task_id: int
    archived: bool
    state: TaskState
    text: str
    modified_at: datetime
    created_at: datetime
    position: int
    priority: TaskPriority | None
    tags: tuple[str, ...]
    completed_at: datetime | None

    @classmethod
    def capture(cls, task: Task) -> "TaskExpectation":
        return cls(
            task.id,
            task.state is TaskState.DELETED,
            task.state,
            task.text,
            task.modified_at,
            task.created_at,
            task.position,
            task.priority,
            task.tags,
            task.completed_at,
        )

    def matches(self, board: Board) -> bool:
        tasks = board.deleted if self.archived else board.active
        task = tasks.get(self.task_id)
        return task is not None and self == self.capture(task)


class TaskConflict(Exception):
    """A snapshot-dependent command no longer matches the current task."""

    def __init__(self, board: Board, task_id: int) -> None:
        self.board = board
        self.task_id = task_id
        super().__init__(
            f"Conflict: task #{task_id} changed or is no longer available."
        )


def mutate_board(
    config: AppConfig,
    operation: Callable[[Board], OperationResult],
    *,
    expected_tasks: tuple[TaskExpectation, ...] = (),
) -> tuple[Board, OperationResult]:
    with datastore_lock(config):
        board = read_data(config)
        for expected in expected_tasks:
            if not expected.matches(board):
                raise TaskConflict(board, expected.task_id)
        previous = deepcopy(board)
        result = operation(board)
        if result.succeeded and board != previous:
            write_data(config, board, previous=previous)
        else:
            board = previous
    return board, result


def undo_board(config: AppConfig) -> Board:
    with datastore_lock(config):
        return undo_last_change(config)
