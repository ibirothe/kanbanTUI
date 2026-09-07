import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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
    """Serialize a timestamp as timezone-aware ISO 8601 without losing precision."""
    if value.tzinfo is None:
        value = value.astimezone()
    return value.isoformat(timespec="auto")


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

        if (
            isinstance(self.position, int)
            and not isinstance(self.position, bool)
            and self.position == 0
        ):
            self.position = self.id
        else:
            self.position = _strict_integer(
                self.position,
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


@dataclass
class Board:
    active: dict[int, Task] = field(default_factory=dict)
    deleted: dict[int, Task] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for collection_name, collection in (
            ("active", self.active),
            ("deleted", self.deleted),
        ):
            for task_id, task in collection.items():
                if (
                    isinstance(task_id, bool)
                    or not isinstance(task_id, int)
                    or task_id < 1
                ):
                    raise ValueError(
                        f"{collection_name} task ids must be positive integers"
                    )
                if task.id != task_id:
                    raise ValueError(
                        f"{collection_name} task key {task_id} does not match task id {task.id}"
                    )
                if collection_name == "active" and task.state is TaskState.DELETED:
                    raise ValueError("active tasks cannot have deleted state")
                if collection_name == "deleted" and task.state is not TaskState.DELETED:
                    raise ValueError("deleted tasks must have deleted state")

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
                (task.position for task in self.active.values() if task.state is state),
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
