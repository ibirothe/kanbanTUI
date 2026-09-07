"""Presentation- and infrastructure-independent board policies."""

from dataclasses import dataclass

from .models import Board, TaskState


class PolicyViolation(ValueError):
    """A board violates a configured business policy."""


@dataclass(frozen=True)
class BoardPolicy:
    """Business limits required by task mutations and imports."""

    todo_limit: int | None = None
    wip_limit: int | None = None
    task_text_limit: int = 40

    def state_limit(self, state: TaskState) -> int | None:
        if state is TaskState.TODO:
            return self.todo_limit
        if state is TaskState.IN_PROGRESS:
            return self.wip_limit
        return None


def count_state(board: Board, state: TaskState) -> int:
    return sum(1 for task in board.active.values() if task.state is state)


def state_limit_reached(policy: BoardPolicy, board: Board, state: TaskState) -> bool:
    limit = policy.state_limit(state)
    return limit is not None and limit <= count_state(board, state)


def validate_imported_board(policy: BoardPolicy, board: Board) -> None:
    """Enforce the same text and capacity policy used by task services."""
    for task in [*board.active.values(), *board.deleted.values()]:
        if len(task.text) > policy.task_text_limit:
            raise PolicyViolation(
                "Imported task "
                f"#{task.id} text exceeds limit "
                f"({len(task.text)}/{policy.task_text_limit} characters)."
            )

    for state, label in (
        (TaskState.TODO, "TODO"),
        (TaskState.IN_PROGRESS, "WIP"),
    ):
        limit = policy.state_limit(state)
        if limit is None:
            continue
        count = count_state(board, state)
        if count > limit:
            raise PolicyViolation(
                f"Imported board exceeds {label} limit ({count}/{limit})."
            )
