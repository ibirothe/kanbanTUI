import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import click

from .models import (
    AppConfig,
    Board,
    Task,
    TaskPriority,
    TaskState,
    format_timestamp,
    parse_timestamp,
)


EXPORT_FORMAT = "kanbanTUI-board"
EXPORT_VERSION = 1


def _task_payload(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "state": task.state.value,
        "text": task.text,
        "created_at": format_timestamp(task.created_at),
        "modified_at": format_timestamp(task.modified_at),
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
        task = Task(
            id=task_id,
            state=state,
            text=text,
            created_at=created_at,
            modified_at=modified_at,
            position=position,
            priority=priority,
            tags=tuple(raw_tags),
        )
    except ValueError as exc:
        raise ValueError(f"task {task_id} has invalid metadata or timestamp: {exc}") from exc
    return task


def board_from_export(payload: Any) -> Board:
    if not isinstance(payload, dict):
        raise ValueError("export must contain a JSON object")
    if payload.get("format") != EXPORT_FORMAT:
        raise ValueError(f"unsupported export format: {payload.get('format')!r}")
    if payload.get("version") != EXPORT_VERSION:
        raise ValueError(f"unsupported export version: {payload.get('version')!r}")

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


def validate_board_capacity(config: AppConfig, board: Board) -> None:
    for state, limit, label in (
        (TaskState.TODO, config.limits.todo, "TODO"),
        (TaskState.IN_PROGRESS, config.limits.wip, "WIP"),
    ):
        if limit is None:
            continue
        count = sum(1 for task in board.active.values() if task.state is state)
        if count > limit:
            raise click.ClickException(
                f"Imported board exceeds {label} limit ({count}/{limit})."
            )


def _remap_imported_ids(current: Board, imported: Board) -> tuple[Board, dict[int, int]]:
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
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Import file {path} contains invalid JSON: {exc}") from exc
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

    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as outfile:
            temporary_path = Path(outfile.name)
            json.dump(export_payload(board), outfile, ensure_ascii=False, indent=2)
            outfile.write("\n")
            outfile.flush()
            os.fsync(outfile.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise click.ClickException(f"Could not write export file {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return path
