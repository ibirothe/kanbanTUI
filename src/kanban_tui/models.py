import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


LEGACY_TIMESTAMP_FORMAT = "%Y-%b-%d %H:%M:%S"
TAG_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
INTEGER_PATTERN = re.compile(r"[0-9]+")


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


def normalize_tag(value: str) -> str:
    """Normalize and validate one lightweight task tag."""
    if not isinstance(value, str):
        raise ValueError("tags must be strings")
    normalized = value.strip().casefold()
    if not TAG_PATTERN.fullmatch(normalized):
        raise ValueError(
            "tags must be 1-32 lowercase letters/numbers and may contain - or _"
        )
    return normalized


def _strict_integer(value: Any, *, minimum: int, error: str) -> int:
    if isinstance(value, bool):
        raise ValueError(error)
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and INTEGER_PATTERN.fullmatch(value.strip()):
        parsed = int(value.strip())
    else:
        raise ValueError(error)
    if parsed < minimum:
        raise ValueError(error)
    return parsed


class TaskState(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "inprogress"
    DONE = "done"
    DELETED = "deleted"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Task:
    id: int
    state: TaskState
    text: str
    modified_at: datetime
    created_at: datetime
    position: int = 0
    priority: TaskPriority | None = None
    tags: tuple[str, ...] = ()
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        self.id = _strict_integer(
            self.id,
            minimum=1,
            error="task id must be a positive integer",
        )
        if not isinstance(self.state, TaskState):
            try:
                self.state = TaskState(self.state)
            except (TypeError, ValueError) as exc:
                raise ValueError("task state is invalid") from exc
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("task text cannot be empty")

        self.modified_at = parse_timestamp(self.modified_at)
        self.created_at = parse_timestamp(self.created_at)
        if self.completed_at is not None:
            self.completed_at = parse_timestamp(self.completed_at)
        elif self.state is TaskState.DONE:
            # Legacy records used modified_at as the completion timestamp.
            self.completed_at = self.modified_at

        if (
            self.state in {TaskState.TODO, TaskState.IN_PROGRESS}
            and self.completed_at is not None
        ):
            raise ValueError(
                "TODO and IN PROGRESS tasks cannot have a completion timestamp"
            )

        self.position = _strict_integer(
            self.position if self.position != 0 else self.id,
            minimum=1,
            error="task position must be a positive integer",
        )

        if self.priority is not None and not isinstance(self.priority, TaskPriority):
            try:
                self.priority = TaskPriority(self.priority)
            except (TypeError, ValueError) as exc:
                raise ValueError("task priority is invalid") from exc

        if isinstance(self.tags, str):
            raise ValueError("task tags must be a collection of strings")
        self.tags = tuple(sorted({normalize_tag(tag) for tag in self.tags}))

    @classmethod
    def from_record(cls, task_id: int, record: Any, *, deleted: bool = False) -> "Task":
        try:
            normalized_id = _strict_integer(
                task_id,
                minimum=1,
                error="task ids must be positive integers",
            )
        except ValueError as exc:
            raise ValueError("task ids must be positive integers") from exc
        if not isinstance(record, list) or len(record) < 4:
            raise ValueError(f"task {normalized_id} has an invalid record")
        if not isinstance(record[1], str) or not record[1].strip():
            raise ValueError(f"task {normalized_id} must have non-empty text content")

        try:
            state = TaskState(record[0])
        except ValueError as exc:
            raise ValueError(
                f"task {normalized_id} has unsupported state {record[0]!r}"
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
            raise ValueError(f"task {normalized_id} has invalid state {state.value!r}")

        try:
            modified_at = parse_timestamp(record[2])
            created_at = parse_timestamp(record[3])
        except ValueError as exc:
            raise ValueError(
                f"task {normalized_id} has an invalid timestamp: {exc}"
            ) from exc

        position = normalized_id
        if len(record) >= 5:
            try:
                position = _strict_integer(
                    record[4],
                    minimum=1,
                    error=f"task {normalized_id} has an invalid position",
                )
            except ValueError as exc:
                raise ValueError(
                    f"task {normalized_id} has an invalid position"
                ) from exc

        priority: TaskPriority | None = None
        tags: tuple[str, ...] = ()
        completed_at: datetime | None = None
        if len(record) >= 6:
            metadata = record[5]
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict):
                raise ValueError(f"task {normalized_id} metadata must be a mapping")

            raw_priority = metadata.get("priority")
            if raw_priority is not None:
                try:
                    priority = TaskPriority(raw_priority)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"task {normalized_id} has an invalid priority"
                    ) from exc

            raw_tags = metadata.get("tags", [])
            if not isinstance(raw_tags, list):
                raise ValueError(f"task {normalized_id} tags must be a list")
            try:
                tags = tuple(sorted({normalize_tag(tag) for tag in raw_tags}))
            except ValueError as exc:
                raise ValueError(
                    f"task {normalized_id} has invalid tags: {exc}"
                ) from exc

            raw_completed_at = metadata.get("completed_at")
            if raw_completed_at is not None:
                try:
                    completed_at = parse_timestamp(raw_completed_at)
                except ValueError as exc:
                    raise ValueError(
                        f"task {normalized_id} has an invalid completion timestamp: {exc}"
                    ) from exc

        return cls(
            id=normalized_id,
            state=state,
            text=record[1],
            modified_at=modified_at,
            created_at=created_at,
            position=position,
            priority=priority,
            tags=tags,
            completed_at=completed_at,
        )

    def to_record(self) -> list[Any]:
        record: list[Any] = [
            self.state.value,
            self.text,
            format_timestamp(self.modified_at),
            format_timestamp(self.created_at),
            self.position,
        ]
        metadata: dict[str, object] = {}
        if self.priority is not None:
            metadata["priority"] = self.priority.value
        if self.tags:
            metadata["tags"] = list(self.tags)
        if self.completed_at is not None:
            metadata["completed_at"] = format_timestamp(self.completed_at)
        if metadata:
            record.append(metadata)
        return record


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
            try:
                values[name] = _strict_integer(
                    raw[name],
                    minimum=0,
                    error=f"limits.{name} must be a non-negative integer",
                )
            except ValueError as exc:
                raise ValueError(
                    f"limits.{name} must be a non-negative integer"
                ) from exc

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

    def next_position(self, state: TaskState) -> int:
        """Return the next position at the bottom of an active state."""
        return (
            max(
                (
                    task.position
                    for task in self.active.values()
                    if task.state is state
                ),
                default=0,
            )
            + 1
        )

    def ordered_tasks(self, state: TaskState) -> list[Task]:
        """Return tasks in manual order, except DONE which is completion ordered."""
        tasks = [task for task in self.active.values() if task.state is state]
        if state is TaskState.DONE:
            return sorted(
                tasks,
                key=lambda task: (task.completed_at or task.modified_at, task.id),
                reverse=True,
            )
        return sorted(tasks, key=lambda task: (task.position, task.id))

    def normalize_positions(self, state: TaskState) -> None:
        """Compact manual positions for one active state."""
        if state is TaskState.DONE:
            return
        for position, task in enumerate(self.ordered_tasks(state), start=1):
            task.position = position

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

    def to_mapping(self) -> dict[str, dict[int, list[Any]]]:
        return {
            "data": {
                task_id: task.to_record() for task_id, task in self.active.items()
            },
            "deleted": {
                task_id: task.to_record() for task_id, task in self.deleted.items()
            },
        }
