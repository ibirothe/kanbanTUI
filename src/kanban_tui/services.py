from collections.abc import Callable, Iterable
from datetime import datetime

from .models import (
    Board,
    Task,
    TaskPriority,
    TaskState,
    normalize_tag,
)
from .policy import BoardPolicy, count_state
from .results import OperationCode, OperationItem, OperationResult, OperationStatus


def timestamp() -> datetime:
    return datetime.now().astimezone()


Clock = Callable[[], datetime]


def _now(clock: Clock | None) -> datetime:
    return (clock or timestamp)()


def _state_limit(policy: BoardPolicy, state: TaskState) -> int | None:
    return policy.state_limit(state)


def state_limit_reached(policy: BoardPolicy, board: Board, state: TaskState) -> bool:
    limit = _state_limit(policy, state)
    return limit is not None and limit <= count_state(board, state)


def wip_limit_reached(policy: BoardPolicy, board: Board) -> bool:
    return state_limit_reached(policy, board, TaskState.IN_PROGRESS)


def todo_limit_reached(policy: BoardPolicy, board: Board) -> bool:
    return state_limit_reached(policy, board, TaskState.TODO)


def _capacity_rejection(
    policy: BoardPolicy,
    board: Board,
    state: TaskState,
    *,
    task_id: int | None = None,
    text: str | None = None,
) -> OperationItem:
    limit = _state_limit(policy, state)
    count = count_state(board, state)
    return OperationItem(
        OperationCode.STATE_LIMIT_REACHED,
        OperationStatus.REJECTED,
        task_id=task_id,
        text=text,
        state=state,
        count=count,
        limit=limit,
    )


def _validate_task_text(
    policy: BoardPolicy, raw_text: str
) -> tuple[str | None, OperationItem | None]:
    text = raw_text.strip()
    if not text:
        return None, OperationItem(
            OperationCode.TEXT_EMPTY, OperationStatus.REJECTED, text=raw_text
        )
    if len(text) > policy.task_text_limit:
        return (
            None,
            OperationItem(
                OperationCode.TEXT_TOO_LONG,
                OperationStatus.REJECTED,
                text=text,
                count=len(text),
                limit=policy.task_text_limit,
            ),
        )
    return text, None


def _normalize_tags(
    tags: Iterable[object], *, task_id: int | None = None
) -> tuple[tuple[str, ...] | None, OperationItem | None]:
    normalized: set[str] = set()
    for raw_tag in tags:
        if not isinstance(raw_tag, str):
            return None, OperationItem(
                OperationCode.INVALID_TAG_TYPE,
                OperationStatus.REJECTED,
                task_id=task_id,
            )
        try:
            normalized.add(normalize_tag(raw_tag))
        except ValueError:
            return None, OperationItem(
                OperationCode.INVALID_TAG_FORMAT,
                OperationStatus.REJECTED,
                task_id=task_id,
                text=raw_tag,
            )
    return tuple(sorted(normalized)), None


def _parse_task_id(task_id: str) -> tuple[int | None, OperationItem | None]:
    try:
        numeric_id = int(task_id)
    except (TypeError, ValueError):
        return None, OperationItem(
            OperationCode.INVALID_TASK_ID,
            OperationStatus.REJECTED,
            raw_id=task_id,
        )
    if numeric_id < 1:
        return None, OperationItem(
            OperationCode.INVALID_TASK_ID,
            OperationStatus.REJECTED,
            raw_id=task_id,
        )
    return numeric_id, None


def _active_task(
    board: Board, task_id: str
) -> tuple[Task | None, OperationItem | None]:
    numeric_id, error = _parse_task_id(task_id)
    if error is not None:
        return None, error
    assert numeric_id is not None
    task = board.active.get(numeric_id)
    if task is None:
        return None, OperationItem(
            OperationCode.TASK_NOT_FOUND,
            OperationStatus.REJECTED,
            task_id=numeric_id,
        )
    return task, None


def _place_at_bottom(board: Board, task: Task, state: TaskState) -> None:
    task.position = board.next_position(state)
    task.state = state


def _transition_task(
    policy: BoardPolicy,
    board: Board,
    task: Task,
    target_state: TaskState,
    clock: Clock | None,
) -> OperationItem | None:
    if task.state is target_state:
        return OperationItem(
            OperationCode.TASK_ALREADY_IN_STATE,
            OperationStatus.UNCHANGED,
            task_id=task.id,
            state=target_state,
        )
    if state_limit_reached(policy, board, target_state):
        return _capacity_rejection(policy, board, target_state, task_id=task.id)

    previous_state = task.state
    now = _now(clock)
    if target_state in {TaskState.TODO, TaskState.IN_PROGRESS}:
        _place_at_bottom(board, task, target_state)
        if previous_state is TaskState.DONE:
            task.completed_at = None
    else:
        task.state = target_state
        task.completed_at = now

    if previous_state in {TaskState.TODO, TaskState.IN_PROGRESS}:
        board.normalize_positions(previous_state)
    task.modified_at = now
    return None


def add_tasks(
    policy: BoardPolicy,
    board: Board,
    tasks: Iterable[str],
    *,
    priority: TaskPriority | str | None = None,
    tags: Iterable[str] = (),
    clock: Clock | None = None,
) -> OperationResult:
    result = OperationResult()

    try:
        normalized_priority = TaskPriority(priority) if priority is not None else None
    except ValueError:
        result.reject(OperationCode.INVALID_PRIORITY, text=str(priority))
        return result
    normalized_tags, tag_error = _normalize_tags(tags)
    if tag_error is not None:
        result.items.append(tag_error)
        return result
    assert normalized_tags is not None

    for raw_text in tasks:
        text, error = _validate_task_text(policy, raw_text)
        if error is not None:
            result.items.append(error)
            continue
        assert text is not None

        if todo_limit_reached(policy, board):
            result.items.append(
                _capacity_rejection(policy, board, TaskState.TODO, text=text)
            )
            continue

        task_id = board.next_task_id()
        now = _now(clock)
        board.active[task_id] = Task(
            id=task_id,
            state=TaskState.TODO,
            text=text,
            modified_at=now,
            created_at=now,
            position=board.next_position(TaskState.TODO),
            priority=normalized_priority,
            tags=normalized_tags,
        )
        result.change(OperationCode.TASK_ADDED, task_id=task_id, text=text)

    return result


def edit_task(
    policy: BoardPolicy,
    board: Board,
    task_id: str,
    raw_text: str,
    *,
    clock: Clock | None = None,
) -> OperationResult:
    result = OperationResult()
    numeric_id, error = _parse_task_id(task_id)
    if error is not None:
        result.items.append(error)
        return result
    assert numeric_id is not None

    if numeric_id in board.deleted:
        result.reject(OperationCode.ARCHIVED_TASK_NOT_EDITABLE, task_id=numeric_id)
        return result

    task = board.active.get(numeric_id)
    if task is None:
        result.reject(OperationCode.TASK_NOT_FOUND, task_id=numeric_id)
        return result

    text, error = _validate_task_text(policy, raw_text)
    if error is not None:
        result.items.append(error)
        return result
    assert text is not None

    if task.text == text:
        result.no_change(OperationCode.TASK_UNCHANGED, task_id=numeric_id)
        return result

    task.text = text
    task.modified_at = _now(clock)
    result.change(OperationCode.TASK_UPDATED, task_id=numeric_id, text=text)
    return result


def delete_tasks(
    board: Board, ids: Iterable[str], *, clock: Clock | None = None
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        task, error = _active_task(board, task_id)
        if error is not None:
            result.items.append(error)
            continue
        assert task is not None

        previous_state = task.state
        task.state = TaskState.DELETED
        task.modified_at = _now(clock)
        board.deleted[task.id] = task
        board.active.pop(task.id)
        board.normalize_positions(previous_state)
        result.change(OperationCode.TASK_ARCHIVED, task_id=task.id)

    return result


def restore_tasks(
    policy: BoardPolicy,
    board: Board,
    ids: Iterable[str],
    *,
    clock: Clock | None = None,
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        numeric_id, error = _parse_task_id(task_id)
        if error is not None:
            result.items.append(error)
            continue
        assert numeric_id is not None

        if numeric_id in board.active:
            result.no_change(OperationCode.TASK_ALREADY_ACTIVE, task_id=numeric_id)
            continue

        task = board.deleted.get(numeric_id)
        if task is None:
            result.reject(OperationCode.ARCHIVED_TASK_NOT_FOUND, task_id=numeric_id)
            continue

        if todo_limit_reached(policy, board):
            result.items.append(
                _capacity_rejection(policy, board, TaskState.TODO, task_id=numeric_id)
            )
            continue

        _place_at_bottom(board, task, TaskState.TODO)
        task.completed_at = None
        task.modified_at = _now(clock)
        board.active[numeric_id] = task
        board.deleted.pop(numeric_id)
        result.change(OperationCode.TASK_RESTORED, task_id=numeric_id)

    return result


def move_tasks_to_state(
    policy: BoardPolicy,
    board: Board,
    ids: Iterable[str],
    target_state: TaskState,
    *,
    clock: Clock | None = None,
) -> OperationResult:
    """Move active tasks directly to an explicit target state."""
    result = OperationResult()
    for task_id in ids:
        task, error = _active_task(board, task_id)
        if error is not None:
            result.items.append(error)
            continue
        assert task is not None

        error = _transition_task(policy, board, task, target_state, clock)
        if error is not None:
            result.items.append(error)
            continue

        if target_state is TaskState.IN_PROGRESS:
            result.change(OperationCode.TASK_STARTED, task_id=task.id)
        elif target_state is TaskState.DONE:
            result.change(OperationCode.TASK_COMPLETED, task_id=task.id)
        else:
            result.change(
                OperationCode.TASK_MOVED, task_id=task.id, state=TaskState.TODO
            )
    return result


def promote_tasks(
    policy: BoardPolicy,
    board: Board,
    ids: Iterable[str],
    *,
    clock: Clock | None = None,
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        task, error = _active_task(board, task_id)
        if error is not None:
            result.items.append(error)
            continue
        assert task is not None

        if task.state is TaskState.TODO:
            target_state = TaskState.IN_PROGRESS
            success_code = OperationCode.TASK_STARTED
        elif task.state is TaskState.IN_PROGRESS:
            target_state = TaskState.DONE
            success_code = OperationCode.TASK_COMPLETED
        else:
            result.no_change(
                OperationCode.TASK_ALREADY_IN_STATE,
                task_id=task.id,
                state=TaskState.DONE,
            )
            continue

        error = _transition_task(policy, board, task, target_state, clock)
        if error is not None:
            result.items.append(error)
        else:
            result.change(success_code, task_id=task.id)

    return result


def regress_tasks(
    policy: BoardPolicy,
    board: Board,
    ids: Iterable[str],
    *,
    clock: Clock | None = None,
) -> OperationResult:
    result = OperationResult()
    for task_id in ids:
        task, error = _active_task(board, task_id)
        if error is not None:
            result.items.append(error)
            continue
        assert task is not None

        if task.state is TaskState.DONE:
            target_state = TaskState.IN_PROGRESS
        elif task.state is TaskState.IN_PROGRESS:
            target_state = TaskState.TODO
        else:
            result.no_change(
                OperationCode.TASK_ALREADY_IN_STATE,
                task_id=task.id,
                state=TaskState.TODO,
            )
            continue

        error = _transition_task(policy, board, task, target_state, clock)
        if error is not None:
            result.items.append(error)
        else:
            result.change(OperationCode.TASK_MOVED, task_id=task.id, state=target_state)

    return result


def reorder_task(
    board: Board,
    task_id: str,
    target: str,
    reference_id: str | None = None,
    *,
    clock: Clock | None = None,
) -> OperationResult:
    """Reorder one TODO or IN PROGRESS task within its current state."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.items.append(error)
        return result
    assert task is not None

    if task.state is TaskState.DONE:
        result.reject(OperationCode.DONE_ORDER_FIXED, task_id=task.id)
        return result

    current_order = board.ordered_tasks(task.state)
    current_index = next(
        index
        for index, candidate in enumerate(current_order)
        if candidate.id == task.id
    )
    result_reference_id: int | None = None

    if target == "top":
        if current_index == 0:
            result.no_change(
                OperationCode.TASK_ALREADY_AT_POSITION,
                task_id=task.id,
                target=target,
            )
            return result
        insert_at = 0
    elif target == "bottom":
        if current_index == len(current_order) - 1:
            result.no_change(
                OperationCode.TASK_ALREADY_AT_POSITION,
                task_id=task.id,
                target=target,
            )
            return result
        insert_at = len(current_order) - 1
    elif target in {"before", "after"}:
        if reference_id is None:
            result.reject(OperationCode.REFERENCE_REQUIRED, target=target)
            return result
        reference, reference_error = _active_task(board, reference_id)
        if reference_error is not None:
            result.items.append(reference_error)
            return result
        assert reference is not None
        if reference.id == task.id:
            result.reject(OperationCode.SELF_REFERENCE, task_id=task.id)
            return result
        if reference.state is not task.state:
            result.reject(
                OperationCode.REFERENCE_DIFFERENT_STATE,
                task_id=task.id,
                reference_id=reference.id,
            )
            return result

        reference_current_index = next(
            index
            for index, candidate in enumerate(current_order)
            if candidate.id == reference.id
        )
        if target == "before" and current_index + 1 == reference_current_index:
            result.no_change(
                OperationCode.TASK_ALREADY_RELATIVE,
                task_id=task.id,
                target=target,
                reference_id=reference.id,
            )
            return result
        if target == "after" and reference_current_index + 1 == current_index:
            result.no_change(
                OperationCode.TASK_ALREADY_RELATIVE,
                task_id=task.id,
                target=target,
                reference_id=reference.id,
            )
            return result

        ordered_without_task = [
            candidate for candidate in current_order if candidate.id != task.id
        ]
        reference_index = next(
            index
            for index, candidate in enumerate(ordered_without_task)
            if candidate.id == reference.id
        )
        insert_at = reference_index if target == "before" else reference_index + 1
        result_reference_id = reference.id
    else:
        result.reject(OperationCode.INVALID_POSITION, target=target)
        return result

    ordered = [candidate for candidate in current_order if candidate.id != task.id]
    ordered.insert(insert_at, task)
    for position, candidate in enumerate(ordered, start=1):
        candidate.position = position
    task.modified_at = _now(clock)
    result.change(
        OperationCode.TASK_REORDERED,
        task_id=task.id,
        target=target,
        reference_id=result_reference_id,
    )
    return result


def reorder_task_relative(
    board: Board,
    task_id: str,
    delta: int,
    *,
    clock: Clock | None = None,
) -> OperationResult:
    """Choose the adjacent task from the current transaction's board."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.items.append(error)
        return result
    assert task is not None
    if delta not in {-1, 1}:
        result.reject(OperationCode.INVALID_DELTA, task_id=task.id)
        return result
    if task.state is TaskState.DONE:
        result.reject(OperationCode.DONE_ORDER_FIXED, task_id=task.id)
        return result
    ordered = board.ordered_tasks(task.state)
    index = next(i for i, candidate in enumerate(ordered) if candidate.id == task.id)
    neighbor_index = index + delta
    if not 0 <= neighbor_index < len(ordered):
        result.no_change(OperationCode.COLUMN_EDGE, task_id=task.id)
        return result
    return reorder_task(
        board,
        task_id,
        "before" if delta < 0 else "after",
        str(ordered[neighbor_index].id),
        clock=clock,
    )


def set_task_priority(
    board: Board,
    task_id: str,
    priority: TaskPriority | str | None,
    *,
    clock: Clock | None = None,
) -> OperationResult:
    """Set or clear one active task priority without changing manual order."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.items.append(error)
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
            result.reject(OperationCode.INVALID_PRIORITY, text=str(priority))
            return result

    if task.priority is normalized:
        result.no_change(
            OperationCode.PRIORITY_UNCHANGED,
            task_id=task.id,
            priority=normalized,
        )
        return result

    task.priority = normalized
    task.modified_at = _now(clock)
    if normalized is None:
        result.change(OperationCode.PRIORITY_CLEARED, task_id=task.id)
    else:
        result.change(OperationCode.PRIORITY_SET, task_id=task.id, priority=normalized)
    return result


def set_task_tags(
    board: Board,
    task_id: str,
    tags: Iterable[str],
    *,
    clock: Clock | None = None,
) -> OperationResult:
    """Replace the complete tag set for one active task."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.items.append(error)
        return result
    assert task is not None

    normalized, tag_error = _normalize_tags(tags, task_id=task.id)
    if tag_error is not None:
        result.items.append(tag_error)
        return result
    assert normalized is not None

    if task.tags == normalized:
        result.no_change(OperationCode.TAGS_UNCHANGED, task_id=task.id)
        return result

    task.tags = normalized
    task.modified_at = _now(clock)
    if normalized:
        result.change(OperationCode.TAGS_SET, task_id=task.id, tags=normalized)
    else:
        result.change(OperationCode.TAGS_CLEARED, task_id=task.id)
    return result


def update_task_tag(
    board: Board,
    task_id: str,
    action: str,
    raw_tag: str | None = None,
    *,
    clock: Clock | None = None,
) -> OperationResult:
    """Add, remove, or clear tags for one active task."""
    result = OperationResult()
    task, error = _active_task(board, task_id)
    if error is not None:
        result.items.append(error)
        return result
    assert task is not None

    if action == "clear":
        return set_task_tags(board, task_id, [], clock=clock)
    if raw_tag is None:
        result.reject(OperationCode.TAG_REQUIRED, task_id=task.id, action=action)
        return result

    normalized, tag_error = _normalize_tags([raw_tag], task_id=task.id)
    if tag_error is not None:
        result.items.append(tag_error)
        return result
    assert normalized is not None
    tag = normalized[0]

    tags = set(task.tags)
    if action == "add":
        if tag in tags:
            result.no_change(OperationCode.TAG_PRESENT, task_id=task.id, text=tag)
            return result
        tags.add(tag)
    elif action == "remove":
        if tag not in tags:
            result.no_change(OperationCode.TAG_MISSING, task_id=task.id, text=tag)
            return result
        tags.remove(tag)
    else:
        result.reject(OperationCode.INVALID_TAG_ACTION, task_id=task.id, action=action)
        return result

    task.tags = tuple(sorted(tags))
    task.modified_at = _now(clock)
    result.change(
        OperationCode.TAG_ADDED if action == "add" else OperationCode.TAG_REMOVED,
        task_id=task.id,
        text=tag,
    )
    return result
