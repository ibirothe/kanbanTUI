"""Presentation- and infrastructure-independent board policies."""

from dataclasses import dataclass

from .models import Board, TaskState


class PolicyViolation(ValueError):
    """A board violates a configured business policy."""

    def __init__(
        self,
        message: str,
        *,
        rule: str | None = None,
        limit: int | None = None,
        actual: int | None = None,
        task_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.rule = rule
        self.limit = limit
        self.actual = actual
        self.task_id = task_id


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
                f"({len(task.text)}/{policy.task_text_limit} characters).",
                rule="task_text_limit",
                limit=policy.task_text_limit,
                actual=len(task.text),
                task_id=task.id,
            )

    for state, label, rule in (
        (TaskState.TODO, "TODO", "todo_limit"),
        (TaskState.IN_PROGRESS, "WIP", "wip_limit"),
    ):
        limit = policy.state_limit(state)
        if limit is None:
            continue
        count = count_state(board, state)
        if count > limit:
            raise PolicyViolation(
                f"Imported board exceeds {label} limit ({count}/{limit}).",
                rule=rule,
                limit=limit,
                actual=count,
            )
