import copy
import json
from pathlib import Path
from typing import Any

import click

from .atomic import atomic_text_writer
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


def _reject_unknown_fields(
    raw: dict[Any, Any], allowed: set[str], context: str
) -> None:
    unknown = [key for key in raw if key not in allowed]
    if unknown:
        names = ", ".join(repr(key) for key in unknown)
        raise ValueError(f"{context} contains unknown fields: {names}")


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
        raise ValueError("task entries must be objects")
    _reject_unknown_fields(raw, _TASK_KEYS, "task entry")

    task_id = raw.get("id")
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
        raise ValueError("task id must be a positive integer")

    text = raw.get("text")
    if not isinstance(text, str):
        raise ValueError(f"task {task_id} text must be a string")

    try:
        state = TaskState(raw.get("state"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"task {task_id} has an invalid state") from exc

    if archived and state is not TaskState.DELETED:
        raise ValueError(f"archived task {task_id} must have state deleted")
    if not archived and state is TaskState.DELETED:
        raise ValueError(f"active task {task_id} cannot have state deleted")

    position = raw.get("position", task_id)
    if isinstance(position, bool) or not isinstance(position, int) or position < 1:
        raise ValueError(f"task {task_id} position must be a positive integer")

    raw_priority = raw.get("priority")
    if raw_priority is not None:
        try:
            priority: TaskPriority | None = TaskPriority(raw_priority)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"task {task_id} has an invalid priority") from exc
    else:
        priority = None

    raw_tags = raw.get("tags", [])
    if not isinstance(raw_tags, list):
        raise ValueError(f"task {task_id} tags must be an array")

    try:
        created_at = parse_timestamp(raw.get("created_at"))
        modified_at = parse_timestamp(raw.get("modified_at"))
        raw_completed_at = raw.get("completed_at")
        completed_at = (
            parse_timestamp(raw_completed_at) if raw_completed_at is not None else None
        )
        task = Task(
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
        raise ValueError(
            f"task {task_id} has invalid metadata or timestamp: {exc}"
        ) from exc
    return task


def board_from_export(payload: Any) -> Board:
    if not isinstance(payload, dict):
        raise ValueError("export must contain a JSON object")
    _reject_unknown_fields(payload, _EXPORT_KEYS, "export")
    if payload.get("format") != EXPORT_FORMAT:
        raise ValueError(f"unsupported export format: {payload.get('format')!r}")
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("export version must be an integer")
    if version != EXPORT_VERSION:
        raise ValueError(f"unsupported export version: {version!r}")

    raw_active = payload.get("active")
    raw_archived = payload.get("archived")
    if not isinstance(raw_active, list) or not isinstance(raw_archived, list):
        raise ValueError("export must contain active and archived arrays")

    active_tasks = [_parse_task(raw, archived=False) for raw in raw_active]
    archived_tasks = [_parse_task(raw, archived=True) for raw in raw_archived]

    all_ids = [task.id for task in [*active_tasks, *archived_tasks]]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("export contains duplicate task IDs")

    board = Board(
        active={task.id: task for task in active_tasks},
        deleted={task.id: task for task in archived_tasks},
    )
    board.normalize_positions(TaskState.TODO)
    board.normalize_positions(TaskState.IN_PROGRESS)
    return board


def _remap_imported_ids(
    current: Board, imported: Board
) -> tuple[Board, dict[int, int]]:
    """Copy an imported board and remap only IDs that collide with current history."""
    incoming = copy.deepcopy(imported)
    current_ids = set(current.active) | set(current.deleted)
    imported_ids = set(incoming.active) | set(incoming.deleted)
    used_ids = current_ids | imported_ids
    next_id = max(used_ids, default=0) + 1
    remapped: dict[int, int] = {}

    for original_id in sorted(imported_ids):
        if original_id not in current_ids:
            continue
        while next_id in used_ids:
            next_id += 1
        remapped[original_id] = next_id
        used_ids.add(next_id)
        next_id += 1

    if not remapped:
        return incoming, remapped

    active: dict[int, Task] = {}
    for original_id, task in incoming.active.items():
        task.id = remapped.get(original_id, original_id)
        active[task.id] = task

    deleted: dict[int, Task] = {}
    for original_id, task in incoming.deleted.items():
        task.id = remapped.get(original_id, original_id)
        deleted[task.id] = task

    return Board(active=active, deleted=deleted), remapped


def merge_boards(current: Board, imported: Board) -> tuple[Board, dict[int, int]]:
    """Merge an independent board, remapping colliding imported task IDs."""
    merged = copy.deepcopy(current)
    incoming, remapped = _remap_imported_ids(current, imported)

    for state in (TaskState.TODO, TaskState.IN_PROGRESS):
        position = merged.next_position(state)
        for task in incoming.ordered_tasks(state):
            task.position = position
            position += 1
            merged.active[task.id] = task

    for task in incoming.ordered_tasks(TaskState.DONE):
        merged.active[task.id] = task
    merged.deleted.update(incoming.deleted)
    return merged, remapped


def read_export(path: Path) -> Board:
    try:
        with path.open("r", encoding="utf-8") as infile:
            payload = json.load(infile)
    except UnicodeError as exc:
        raise click.ClickException(
            f"Import file {path} must use valid UTF-8 encoding."
        ) from exc
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"Import file {path} contains invalid JSON: {exc}"
        ) from exc
    except OSError as exc:
        raise click.ClickException(f"Could not read import file {path}: {exc}") from exc

    try:
        return board_from_export(payload)
    except ValueError as exc:
        raise click.ClickException(f"Import file {path}: {exc}") from exc


def write_export(path: Path, board: Board, *, overwrite: bool = False) -> Path:
    path = path.expanduser().resolve()
    if path.exists() and not overwrite:
        raise click.ClickException(
            f"Export file {path} already exists. Use --force to overwrite it."
        )

    try:
        with atomic_text_writer(path) as outfile:
            json.dump(export_payload(board), outfile, ensure_ascii=False, indent=2)
            outfile.write("\n")
    except (OSError, ValueError) as exc:
        raise click.ClickException(
            f"Could not write export file {path}: {exc}"
        ) from exc

    return path
