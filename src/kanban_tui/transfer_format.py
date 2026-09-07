"""Transport-neutral codec for the versioned board transfer payload."""

from typing import Any

from .models import (
    Board,
    Task,
    TaskPriority,
    TaskState,
    format_timestamp,
    parse_timestamp,
)

EXPORT_FORMAT = "kanbanTUI-board"
EXPORT_VERSION = 1
_EXPORT_KEYS = {"format", "version", "active", "archived"}
_TASK_KEYS = {
    "id",
    "state",
    "text",
    "created_at",
    "modified_at",
    "completed_at",
    "position",
    "priority",
    "tags",
}


class TransferFormatError(ValueError):
    """A payload does not satisfy the public board transfer contract."""


def _reject_unknown_fields(
    raw: dict[Any, Any], allowed: set[str], context: str
) -> None:
    unknown = [key for key in raw if key not in allowed]
    if unknown:
        names = ", ".join(repr(key) for key in unknown)
        raise TransferFormatError(f"{context} contains unknown fields: {names}")


def _task_payload(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "state": task.state.value,
        "text": task.text,
        "created_at": format_timestamp(task.created_at),
        "modified_at": format_timestamp(task.modified_at),
        "completed_at": (
            format_timestamp(task.completed_at)
            if task.completed_at is not None
            else None
        ),
        "position": task.position,
        "priority": task.priority.value if task.priority is not None else None,
        "tags": list(task.tags),
    }


def export_payload(board: Board) -> dict[str, object]:
    """Encode a complete board into the public transfer payload."""
    active = [
        *board.ordered_tasks(TaskState.TODO),
        *board.ordered_tasks(TaskState.IN_PROGRESS),
        *board.ordered_tasks(TaskState.DONE),
    ]
    archived = sorted(board.deleted.values(), key=lambda task: task.id)
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "active": [_task_payload(task) for task in active],
        "archived": [_task_payload(task) for task in archived],
    }


def _parse_task(raw: Any, *, archived: bool) -> Task:
    if not isinstance(raw, dict):
        raise TransferFormatError("task entries must be objects")
    _reject_unknown_fields(raw, _TASK_KEYS, "task entry")

    task_id = raw.get("id")
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
        raise TransferFormatError("task id must be a positive integer")

    text = raw.get("text")
    if not isinstance(text, str):
        raise TransferFormatError(f"task {task_id} text must be a string")

    try:
        state = TaskState(raw.get("state"))
    except (TypeError, ValueError) as exc:
        raise TransferFormatError(f"task {task_id} has an invalid state") from exc

    if archived and state is not TaskState.DELETED:
        raise TransferFormatError(f"archived task {task_id} must have state deleted")
    if not archived and state is TaskState.DELETED:
        raise TransferFormatError(f"active task {task_id} cannot have state deleted")

    position = raw.get("position", task_id)
    if isinstance(position, bool) or not isinstance(position, int) or position < 1:
        raise TransferFormatError(f"task {task_id} position must be a positive integer")

    raw_priority = raw.get("priority")
    if raw_priority is not None:
        try:
            priority: TaskPriority | None = TaskPriority(raw_priority)
        except (TypeError, ValueError) as exc:
            raise TransferFormatError(
                f"task {task_id} has an invalid priority"
            ) from exc
    else:
        priority = None

    raw_tags = raw.get("tags", [])
    if not isinstance(raw_tags, list):
        raise TransferFormatError(f"task {task_id} tags must be an array")

    try:
        created_at = parse_timestamp(raw.get("created_at"))
        modified_at = parse_timestamp(raw.get("modified_at"))
        raw_completed_at = raw.get("completed_at")
        completed_at = (
            parse_timestamp(raw_completed_at) if raw_completed_at is not None else None
        )
        return Task(
            id=task_id,
            state=state,
            text=text,
            created_at=created_at,
            modified_at=modified_at,
            position=position,
            priority=priority,
            tags=tuple(raw_tags),
            completed_at=completed_at,
        )
    except ValueError as exc:
        raise TransferFormatError(
            f"task {task_id} has invalid metadata or timestamp: {exc}"
        ) from exc


def board_from_export(payload: Any) -> Board:
    """Decode and validate a public transfer payload into a board."""
    if not isinstance(payload, dict):
        raise TransferFormatError("export must contain a JSON object")
    _reject_unknown_fields(payload, _EXPORT_KEYS, "export")
    if payload.get("format") != EXPORT_FORMAT:
        raise TransferFormatError(
            f"unsupported export format: {payload.get('format')!r}"
        )
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise TransferFormatError("export version must be an integer")
    if version != EXPORT_VERSION:
        raise TransferFormatError(f"unsupported export version: {version!r}")

    raw_active = payload.get("active")
    raw_archived = payload.get("archived")
    if not isinstance(raw_active, list) or not isinstance(raw_archived, list):
        raise TransferFormatError("export must contain active and archived arrays")

    active_tasks = [_parse_task(raw, archived=False) for raw in raw_active]
    archived_tasks = [_parse_task(raw, archived=True) for raw in raw_archived]

    all_ids = [task.id for task in [*active_tasks, *archived_tasks]]
    if len(all_ids) != len(set(all_ids)):
        raise TransferFormatError("export contains duplicate task IDs")

    board = Board(
        active={task.id: task for task in active_tasks},
        deleted={task.id: task for task in archived_tasks},
    )
    board.normalize_positions(TaskState.TODO)
    board.normalize_positions(TaskState.IN_PROGRESS)
    return board
