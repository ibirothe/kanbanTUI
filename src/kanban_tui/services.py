from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from .models import (
    AppConfig,
    Board,
    Task,
    TaskPriority,
    TaskState,
    normalize_tag,
)


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


def _state_name(state: TaskState) -> str:
    if state is TaskState.IN_PROGRESS:
        return "IN PROGRESS"
    return state.value.upper()


def _capacity_error(config: AppConfig, board: Board, state: TaskState) -> str:
    limit = _state_limit(config, state)
    count = _count_state(board, state)
    label = "WIP" if state is TaskState.IN_PROGRESS else "TODO"
    return f"Error: {label} limit reached ({count}/{limit})."


def _validate_task_text(config: AppConfig, raw_text: str) -> tuple[str | None, str | None]:
    text = raw_text.strip()
    if not text:
        return None, "Error: task text cannot be empty."
    if len(text) > config.limits.taskname:
        return (
            None,
            f"Error: task text exceeds limit ({len(text)}/{config.limits.taskname} characters).",
        )
    return text, None


def _parse_task_id(task_id: str) -> tuple[int | None, str | None]:
    try:
        return int(task_id), None
    except (TypeError, ValueError):
        return None, f"Error: invalid task ID {task_id!r}."


def _active_task(board: Board, task_id: str) -> tuple[Task | None, str | None]:
    numeric_id, error = _parse_task_id(task_id)
    if error is not None:
        return None, error
    assert numeric_id is not None
    task = board.active.get(numeric_id)
    if task is None:
        return None, f"Error: task #{numeric_id} does not exist."
    return task, None


def _place_at_bottom(board: Board, task: Task, state: TaskState) -> None:
    task.position = board.next_position(state)
    task.state = state


def _transition_task(
    config: AppConfig,
    board: Board,
    task: Task,
    target_state: TaskState,
) -> str | None:
    if task.state is target_state:
        return f"Error: task #{task.id} is already {_state_name(target_state)}."
    if state_limit_reached(config, board, target_state):
        return _capacity_error(config, board, target_state)

    previous_state = task.state
    if target_state in {TaskState.TODO, TaskState.IN_PROGRESS}:
        _place_at_bottom(board, task, target_state)
    else:
        task.state = target_state

    if previous_state in {TaskState.TODO, TaskState.IN_PROGRESS}:
        board.normalize_positions(previous_state)
    task.modified_at = timestamp()
    return None


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
            result.failure(_capacity_error(config, board, TaskState.TODO))
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
        result.success(f"Added #{task_id}: {text}")

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
        result.failure(f"Error: archived task #{numeric_id} cannot be edited.")
        return result

    task = board.active.get(numeric_id)
    if task is None:
        result.failure(f"Error: task #{numeric_id} does not exist.")
        return result

    text, error = _validate_task_text(config, raw_text)
    if error is not None:
        result.failure(error)
        return result
    assert text is not None

    task.text = text
    task.modified_at = timestamp()
    result.success(f"Updated #{numeric_id}: {text}")
    return result


def delete_tasks(board: Board, ids: Iterable[str]) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        task, error = _active_task(board, task_id)
        if error is not None:
            result.failure(error)
            continue
        assert task is not None

        previous_state = task.state
        task.state = TaskState.DELETED
        task.modified_at = timestamp()
        board.deleted[task.id] = task
        board.active.pop(task.id)
        board.normalize_positions(previous_state)
        result.success(f"Archived #{task.id}.")

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
            result.failure(f"Error: task #{numeric_id} is already active.")
            continue

        task = board.deleted.get(numeric_id)
        if task is None:
            result.failure(f"Error: archived task #{numeric_id} does not exist.")
            continue

        if todo_limit_reached(config, board):
            result.failure(_capacity_error(config, board, TaskState.TODO))
            continue

        _place_at_bottom(board, task, TaskState.TODO)
        task.modified_at = timestamp()
        board.active[numeric_id] = task
        board.deleted.pop(numeric_id)
        result.success(f"Restored #{numeric_id} to TODO.")

    return result


def move_tasks_to_state(
    config: AppConfig,
    board: Board,
    ids: Iterable[str],
    target_state: TaskState,
) -> OperationResult:
    """Move active tasks directly to an explicit target state."""
    result = OperationResult()
    for task_id in ids:
        task, error = _active_task(board, task_id)
        if error is not None:
            result.failure(error)
            continue
        assert task is not None

        error = _transition_task(config, board, task, target_state)
        if error is not None:
            result.failure(error)
            continue

        if target_state is TaskState.IN_PROGRESS:
            result.success(f"Started #{task.id}.")
        elif target_state is TaskState.DONE:
            result.success(f"Completed #{task.id}.")
        else:
            result.success(f"Moved #{task.id} to TODO.")
    return result


def promote_tasks(
    config: AppConfig, board: Board, ids: Iterable[str]
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        task, error = _active_task(board, task_id)
        if error is not None:
            result.failure(error)
            continue
        assert task is not None

        if task.state is TaskState.TODO:
            target_state = TaskState.IN_PROGRESS
            success_message = f"Started #{task.id}."
        elif task.state is TaskState.IN_PROGRESS:
            target_state = TaskState.DONE
            success_message = f"Completed #{task.id}."
        else:
            result.failure(f"Error: task #{task.id} is already DONE.")
            continue

        error = _transition_task(config, board, task, target_state)
        if error is not None:
            result.failure(error)
        else:
            result.success(success_message)

    return result


def regress_tasks(
    config: AppConfig, board: Board, ids: Iterable[str]
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        task, error = _active_task(board, task_id)
        if error is not None:
            result.failure(error)
            continue
        assert task is not None

        if task.state is TaskState.DONE:
            target_state = TaskState.IN_PROGRESS
            success_message = f"Moved #{task.id} to IN PROGRESS."
        elif task.state is TaskState.IN_PROGRESS:
            target_state = TaskState.TODO
            success_message = f"Moved #{task.id} to TODO."
        else:
            result.failure(f"Error: task #{task.id} is already TODO.")
            continue

        error = _transition_task(config, board, task, target_state)
        if error is not None:
            result.failure(error)
        else:
            result.success(success_message)

    return result


def reorder_task(
    board: Board,
    task_id: str,
    target: str,
    reference_id: str | None = None,
) -> OperationResult:
    """Reorder one TODO or IN PROGRESS task within its current state."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.failure(error)
        return result
    assert task is not None

    if task.state is TaskState.DONE:
        result.failure("Error: completed tasks are ordered by completion time.")
        return result

    ordered = [
        candidate
        for candidate in board.ordered_tasks(task.state)
        if candidate.id != task.id
    ]

    if target == "top":
        insert_at = 0
        success_message = f"Moved #{task.id} to top."
    elif target == "bottom":
        insert_at = len(ordered)
        success_message = f"Moved #{task.id} to bottom."
    elif target in {"before", "after"}:
        if reference_id is None:
            result.failure(f"Error: {target} requires a reference task ID.")
            return result
        reference, reference_error = _active_task(board, reference_id)
        if reference_error is not None:
            result.failure(reference_error)
            return result
        assert reference is not None
        if reference.id == task.id:
            result.failure("Error: a task cannot be positioned relative to itself.")
            return result
        if reference.state is not task.state:
            result.failure("Error: reference task must be in the same column.")
            return result
        reference_index = next(
            index for index, candidate in enumerate(ordered) if candidate.id == reference.id
        )
        insert_at = reference_index if target == "before" else reference_index + 1
        success_message = f"Moved #{task.id} {target} #{reference.id}."
    else:
        result.failure("Error: position must be top, bottom, before, or after.")
        return result

    ordered.insert(insert_at, task)
    for position, candidate in enumerate(ordered, start=1):
        candidate.position = position
    task.modified_at = timestamp()
    result.success(success_message)
    return result


def set_task_priority(
    board: Board,
    task_id: str,
    priority: TaskPriority | str | None,
) -> OperationResult:
    """Set or clear one active task priority without changing manual order."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.failure(error)
        return result
    assert task is not None

    normalized: TaskPriority | None
    if priority is None:
        normalized = None
    elif isinstance(priority, TaskPriority):
        normalized = priority
    else:
        try:
            normalized = TaskPriority(priority)
        except ValueError:
            result.failure(f"Error: invalid priority {priority!r}.")
            return result

    if task.priority is normalized:
        label = normalized.value if normalized is not None else "none"
        result.failure(f"Error: task #{task.id} priority is already {label}.")
        return result

    task.priority = normalized
    task.modified_at = timestamp()
    if normalized is None:
        result.success(f"Cleared priority for #{task.id}.")
    else:
        result.success(f"Set #{task.id} priority to {normalized.value}.")
    return result


def set_task_tags(board: Board, task_id: str, tags: Iterable[str]) -> OperationResult:
    """Replace the complete tag set for one active task."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.failure(error)
        return result
    assert task is not None

    try:
        normalized = tuple(sorted({normalize_tag(tag) for tag in tags}))
    except ValueError as exc:
        result.failure(f"Error: {exc}.")
        return result

    if task.tags == normalized:
        result.failure(f"Error: task #{task.id} tags are unchanged.")
        return result

    task.tags = normalized
    task.modified_at = timestamp()
    if normalized:
        result.success(f"Set #{task.id} tags: {', '.join(normalized)}.")
    else:
        result.success(f"Cleared tags for #{task.id}.")
    return result


def update_task_tag(
    board: Board,
    task_id: str,
    action: str,
    raw_tag: str | None = None,
) -> OperationResult:
    """Add, remove, or clear tags for one active task."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.failure(error)
        return result
    assert task is not None

    if action == "clear":
        return set_task_tags(board, task_id, [])
    if raw_tag is None:
        result.failure(f"Error: tag {action} requires a tag value.")
        return result

    try:
        tag = normalize_tag(raw_tag)
    except ValueError as exc:
        result.failure(f"Error: {exc}.")
        return result

    tags = set(task.tags)
    if action == "add":
        if tag in tags:
            result.failure(f"Error: task #{task.id} already has tag #{tag}.")
            return result
        tags.add(tag)
    elif action == "remove":
        if tag not in tags:
            result.failure(f"Error: task #{task.id} does not have tag #{tag}.")
            return result
        tags.remove(tag)
    else:
        result.failure("Error: tag action must be add, remove, or clear.")
        return result

    task.tags = tuple(sorted(tags))
    task.modified_at = timestamp()
    verb = "Added" if action == "add" else "Removed"
    result.success(f"{verb} tag #{tag} {'to' if action == 'add' else 'from'} #{task.id}.")
    return result
