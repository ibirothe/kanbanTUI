from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


LEGACY_TIMESTAMP_FORMAT = "%Y-%b-%d %H:%M:%S"


def parse_timestamp(value: Any) -> datetime:
    """Parse current ISO timestamps and the older timestamp format."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            try:
                parsed = datetime.strptime(value, LEGACY_TIMESTAMP_FORMAT)
            except ValueError as exc:
                raise ValueError(f"invalid timestamp {value!r}") from exc
    else:
        raise ValueError(f"invalid timestamp {value!r}")

    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def format_timestamp(value: datetime) -> str:
    """Serialize a timestamp as timezone-aware ISO 8601 to second precision."""
    if value.tzinfo is None:
        value = value.astimezone()
    return value.isoformat(timespec="seconds")


class TaskState(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "inprogress"
    DONE = "done"
    DELETED = "deleted"


@dataclass
class Task:
    id: int
    state: TaskState
    text: str
    modified_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        self.modified_at = parse_timestamp(self.modified_at)
        self.created_at = parse_timestamp(self.created_at)

    @classmethod
    def from_record(cls, task_id: int, record: Any, *, deleted: bool = False) -> "Task":
        if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id < 1:
            raise ValueError("task ids must be positive integers")
        if not isinstance(record, list) or len(record) < 4:
            raise ValueError(f"task {task_id} has an invalid record")
        if not isinstance(record[1], str):
            raise ValueError(f"task {task_id} must have text content")

        try:
            state = TaskState(record[0])
        except ValueError as exc:
            raise ValueError(
                f"task {task_id} has unsupported state {record[0]!r}"
            ) from exc

        allowed = (
            {TaskState.DELETED}
            if deleted
            else {
                TaskState.TODO,
                TaskState.IN_PROGRESS,
                TaskState.DONE,
            }
        )
        if state not in allowed:
            raise ValueError(f"task {task_id} has invalid state {state.value!r}")

        try:
            modified_at = parse_timestamp(record[2])
            created_at = parse_timestamp(record[3])
        except ValueError as exc:
            raise ValueError(f"task {task_id} has an invalid timestamp: {exc}") from exc

        return cls(
            id=task_id,
            state=state,
            text=record[1],
            modified_at=modified_at,
            created_at=created_at,
        )

    def to_record(self) -> list[str]:
        return [
            self.state.value,
            self.text,
            format_timestamp(self.modified_at),
            format_timestamp(self.created_at),
        ]


@dataclass
class Limits:
    todo: int | None = None
    wip: int | None = None
    done: int = 10
    taskname: int = 40

    @classmethod
    def from_mapping(cls, raw: Any) -> "Limits":
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("limits must be a mapping")

        values: dict[str, int | None] = {
            "todo": None,
            "wip": None,
            "done": 10,
            "taskname": 40,
        }
        for name in values:
            if name not in raw:
                continue
            value = raw[name]
            if isinstance(value, bool):
                raise ValueError(f"limits.{name} must be a non-negative integer")
            try:
                normalized = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"limits.{name} must be a non-negative integer"
                ) from exc
            if normalized < 0:
                raise ValueError(f"limits.{name} must be a non-negative integer")
            values[name] = normalized

        return cls(**values)


@dataclass
class AppConfig:
    data_path: Path
    limits: Limits = field(default_factory=Limits)
    repaint: bool = False


@dataclass
class Board:
    active: dict[int, Task] = field(default_factory=dict)
    deleted: dict[int, Task] = field(default_factory=dict)

    def __post_init__(self) -> None:
        overlapping_ids = set(self.active).intersection(self.deleted)
        if overlapping_ids:
            ids = ", ".join(str(task_id) for task_id in sorted(overlapping_ids))
            raise ValueError(f"task ids cannot be both active and deleted: {ids}")

    def next_task_id(self) -> int:
        """Return the next ID without reusing IDs from deleted history."""
        return max((*self.active, *self.deleted), default=0) + 1

    @classmethod
    def from_mapping(cls, raw: Any) -> "Board":
        if not isinstance(raw, dict):
            raise ValueError("must contain a YAML mapping")
        if "data" not in raw or "deleted" not in raw:
            raise ValueError("must contain data and deleted mappings")
        if not isinstance(raw["data"], dict) or not isinstance(raw["deleted"], dict):
            raise ValueError("data and deleted must be mappings")

        active = {
            task_id: Task.from_record(task_id, record)
            for task_id, record in raw["data"].items()
        }
        deleted = {
            task_id: Task.from_record(task_id, record, deleted=True)
            for task_id, record in raw["deleted"].items()
        }
        return cls(active=active, deleted=deleted)

    def to_mapping(self) -> dict[str, dict[int, list[str]]]:
        return {
            "data": {
                task_id: task.to_record() for task_id, task in self.active.items()
            },
            "deleted": {
                task_id: task.to_record() for task_id, task in self.deleted.items()
            },
        }
