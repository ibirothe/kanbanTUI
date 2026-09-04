from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from .models import AppConfig, Board, Task, TaskState


@dataclass
class OperationResult:
    messages: list[str] = field(default_factory=list)
    succeeded: int = 0
    failed: int = 0

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def success(self, message: str) -> None:
        self.succeeded += 1
        self.messages.append(message)

    def failure(self, message: str) -> None:
        self.failed += 1
        self.messages.append(message)


def timestamp() -> datetime:
    return datetime.now().astimezone()


def _count_state(board: Board, state: TaskState) -> int:
    return sum(1 for task in board.active.values() if task.state is state)


def _state_limit(config: AppConfig, state: TaskState) -> int | None:
    if state is TaskState.TODO:
        return config.limits.todo
    if state is TaskState.IN_PROGRESS:
        return config.limits.wip
    return None


def state_limit_reached(config: AppConfig, board: Board, state: TaskState) -> bool:
    limit = _state_limit(config, state)
    return limit is not None and limit <= _count_state(board, state)


def wip_limit_reached(config: AppConfig, board: Board) -> bool:
    return state_limit_reached(config, board, TaskState.IN_PROGRESS)


def todo_limit_reached(config: AppConfig, board: Board) -> bool:
    return state_limit_reached(config, board, TaskState.TODO)


def _validate_task_text(config: AppConfig, raw_text: str) -> tuple[str | None, str | None]:
    text = raw_text.strip()
    if not text:
        return None, "Task text cannot be empty."
    if len(text) > config.limits.taskname:
        return (
            None,
            "Task must be at most %s chars, Brevity counts: %s"
            % (config.limits.taskname, text),
        )
    return text, None


def _parse_task_id(task_id: str) -> tuple[int | None, str | None]:
    try:
        return int(task_id), None
    except (TypeError, ValueError):
        return None, "Invalid task id"


def _place_at_bottom(board: Board, task: Task, state: TaskState) -> None:
    task.position = board.next_position(state)
    task.state = state


def add_tasks(
    config: AppConfig, board: Board, tasks: Iterable[str]
) -> OperationResult:
    result = OperationResult()

    for raw_text in tasks:
        text, error = _validate_task_text(config, raw_text)
        if error is not None:
            result.failure(error)
            continue
        assert text is not None

        if todo_limit_reached(config, board):
            result.failure("No new todos, limit reached already.")
            continue

        task_id = board.next_task_id()
        now = timestamp()
        board.active[task_id] = Task(
            id=task_id,
            state=TaskState.TODO,
            text=text,
            modified_at=now,
            created_at=now,
            position=board.next_position(TaskState.TODO),
        )
        result.success("Creating new task w/ id: %d -> %s" % (task_id, text))

    return result


def edit_task(
    config: AppConfig, board: Board, task_id: str, raw_text: str
) -> OperationResult:
    result = OperationResult()
    numeric_id, error = _parse_task_id(task_id)
    if error is not None:
        result.failure(error)
        return result
    assert numeric_id is not None

    if numeric_id in board.deleted:
        result.failure("Can not edit deleted task %d." % numeric_id)
        return result

    task = board.active.get(numeric_id)
    if task is None:
        result.failure("No existing task with that id: %d" % numeric_id)
        return result

    text, error = _validate_task_text(config, raw_text)
    if error is not None:
        result.failure(error)
        return result
    assert text is not None

    task.text = text
    task.modified_at = timestamp()
    result.success("Updated task %d -> %s" % (numeric_id, text))
    return result


def delete_tasks(board: Board, ids: Iterable[str]) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        numeric_id, error = _parse_task_id(task_id)
        if error is not None:
            result.failure(error)
            continue
        assert numeric_id is not None

        task = board.active.get(numeric_id)
        if task is None:
            result.failure("No existing task with that id: %d" % numeric_id)
            continue

        previous_state = task.state
        task.state = TaskState.DELETED
        task.modified_at = timestamp()
        board.deleted[numeric_id] = task
        board.active.pop(numeric_id)
        board.normalize_positions(previous_state)
        result.success("Removed task %d." % numeric_id)

    return result


def restore_tasks(
    config: AppConfig, board: Board, ids: Iterable[str]
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        numeric_id, error = _parse_task_id(task_id)
        if error is not None:
            result.failure(error)
            continue
        assert numeric_id is not None

        if numeric_id in board.active:
            result.failure("Task id %d is already active." % numeric_id)
            continue

        task = board.deleted.get(numeric_id)
        if task is None:
            result.failure("No deleted task with that id: %d" % numeric_id)
            continue

        if todo_limit_reached(config, board):
            result.failure(
                "Can not restore, todo limit of %s reached." % config.limits.todo
            )
            continue

        _place_at_bottom(board, task, TaskState.TODO)
        task.modified_at = timestamp()
        board.active[numeric_id] = task
        board.deleted.pop(numeric_id)
        result.success("Restored task %d to todo." % numeric_id)

    return result


def promote_tasks(
    config: AppConfig, board: Board, ids: Iterable[str]
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        numeric_id, error = _parse_task_id(task_id)
        if error is not None:
            result.failure(error)
            continue
        assert numeric_id is not None

        task = board.active.get(numeric_id)
        if task is None:
            result.failure("No existing task with that id: %s" % task_id)
        elif task.state is TaskState.TODO:
            if wip_limit_reached(config, board):
                result.failure(
                    "Can not promote, in-progress limit of %s reached."
                    % config.limits.wip
                )
            else:
                _place_at_bottom(board, task, TaskState.IN_PROGRESS)
                board.normalize_positions(TaskState.TODO)
                task.modified_at = timestamp()
                result.success("Promoting task %s to in-progress." % task_id)
        elif task.state is TaskState.IN_PROGRESS:
            task.state = TaskState.DONE
            board.normalize_positions(TaskState.IN_PROGRESS)
            task.modified_at = timestamp()
            result.success("Promoting task %s to done." % task_id)
        else:
            result.failure("Can not promote %s, already done." % task_id)

    return result


def regress_tasks(
    config: AppConfig, board: Board, ids: Iterable[str]
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        numeric_id, error = _parse_task_id(task_id)
        if error is not None:
            result.failure(error)
            continue
        assert numeric_id is not None

        task = board.active.get(numeric_id)
        if task is None:
            result.failure("No existing task with id: %s" % task_id)
        elif task.state is TaskState.DONE:
            if wip_limit_reached(config, board):
                result.failure(
                    "Can not regress, in-progress limit of %s reached."
                    % config.limits.wip
                )
            else:
                _place_at_bottom(board, task, TaskState.IN_PROGRESS)
                task.modified_at = timestamp()
                result.success("Regressing task %s to in-progress." % task_id)
        elif task.state is TaskState.IN_PROGRESS:
            if todo_limit_reached(config, board):
                result.failure(
                    "Can not regress, todo limit of %s reached."
                    % config.limits.todo
                )
            else:
                _place_at_bottom(board, task, TaskState.TODO)
                board.normalize_positions(TaskState.IN_PROGRESS)
                task.modified_at = timestamp()
                result.success("Regressing task %s to todo." % task_id)
        else:
            result.failure("Already in todo, can not regress %s" % task_id)

    return result


def reorder_task(
    board: Board,
    task_id: str,
    target: str,
    reference_id: str | None = None,
) -> OperationResult:
    """Reorder one TODO or IN PROGRESS task within its current state."""
    result = OperationResult()
    numeric_id, error = _parse_task_id(task_id)
    if error is not None:
        result.failure(error)
        return result
    assert numeric_id is not None

    task = board.active.get(numeric_id)
    if task is None:
        result.failure("No existing task with that id: %d" % numeric_id)
        return result
    if task.state is TaskState.DONE:
        result.failure("Completed tasks are ordered by completion time.")
        return result

    ordered = board.ordered_tasks(task.state)
    ordered = [candidate for candidate in ordered if candidate.id != numeric_id]

    if target == "top":
        insert_at = 0
    elif target == "bottom":
        insert_at = len(ordered)
    elif target in {"before", "after"}:
        if reference_id is None:
            result.failure(f"{target} requires a reference task id.")
            return result
        reference_numeric_id, reference_error = _parse_task_id(reference_id)
        if reference_error is not None:
            result.failure(reference_error)
            return result
        assert reference_numeric_id is not None
        reference = board.active.get(reference_numeric_id)
        if reference is None:
            result.failure("No existing task with that id: %d" % reference_numeric_id)
            return result
        if reference.id == task.id:
            result.failure("A task cannot be positioned relative to itself.")
            return result
        if reference.state is not task.state:
            result.failure("Reference task must be in the same column.")
            return result
        reference_index = next(
            index for index, candidate in enumerate(ordered) if candidate.id == reference.id
        )
        insert_at = reference_index if target == "before" else reference_index + 1
    else:
        result.failure("Position must be top, bottom, before, or after.")
        return result

    ordered.insert(insert_at, task)
    for position, candidate in enumerate(ordered, start=1):
        candidate.position = position
    task.modified_at = timestamp()
    result.success("Moved task %d %s." % (numeric_id, target))
    return result
