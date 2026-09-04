import datetime
from collections.abc import Iterable
from dataclasses import dataclass, field

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


def timestamp() -> str:
    return "{:%Y-%b-%d %H:%M:%S}".format(datetime.datetime.now())


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
        )
        result.success("Creating new task w/ id: %d -> %s" % (task_id, text))

    return result


def edit_task(
    config: AppConfig, board: Board, task_id: str, raw_text: str
) -> OperationResult:
    result = OperationResult()
    try:
        numeric_id = int(task_id)
    except (TypeError, ValueError):
        result.failure("Invalid task id")
        return result

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
        try:
            numeric_id = int(task_id)
        except (TypeError, ValueError):
            result.failure("Invalid task id")
            continue

        task = board.active.get(numeric_id)
        if task is None:
            result.failure("No existing task with that id: %d" % numeric_id)
            continue

        task.state = TaskState.DELETED
        task.modified_at = timestamp()
        board.deleted[numeric_id] = task
        board.active.pop(numeric_id)
        result.success("Removed task %d." % numeric_id)

    return result


def restore_tasks(
    config: AppConfig, board: Board, ids: Iterable[str]
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        try:
            numeric_id = int(task_id)
        except (TypeError, ValueError):
            result.failure("Invalid task id")
            continue

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

        task.state = TaskState.TODO
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
        try:
            numeric_id = int(task_id)
        except (TypeError, ValueError):
            result.failure("Invalid task id")
            continue

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
                task.state = TaskState.IN_PROGRESS
                task.modified_at = timestamp()
                result.success("Promoting task %s to in-progress." % task_id)
        elif task.state is TaskState.IN_PROGRESS:
            task.state = TaskState.DONE
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
        try:
            numeric_id = int(task_id)
        except (TypeError, ValueError):
            result.failure("Invalid task id")
            continue

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
                task.state = TaskState.IN_PROGRESS
                task.modified_at = timestamp()
                result.success("Regressing task %s to in-progress." % task_id)
        elif task.state is TaskState.IN_PROGRESS:
            if todo_limit_reached(config, board):
                result.failure(
                    "Can not regress, todo limit of %s reached."
                    % config.limits.todo
                )
            else:
                task.state = TaskState.TODO
                task.modified_at = timestamp()
                result.success("Regressing task %s to todo." % task_id)
        else:
            result.failure("Already in todo, can not regress %s" % task_id)

    return result
