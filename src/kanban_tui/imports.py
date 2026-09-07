"""Pure board-import composition independent of JSON and terminal adapters."""

import copy
from enum import Enum

from .models import Board, Task, TaskState


class ImportMode(str, Enum):
    MERGE = "merge"
    REPLACE = "replace"


def _remap_imported_ids(
    current: Board, imported: Board
) -> tuple[Board, dict[int, int]]:
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
