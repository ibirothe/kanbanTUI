"""Typed application results shared by domain services and adapters."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict, Unpack

from .models import TaskPriority, TaskState


class OperationStatus(str, Enum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    REJECTED = "rejected"


class OperationCode(str, Enum):
    TASK_ADDED = "task_added"
    TASK_UPDATED = "task_updated"
    TASK_UNCHANGED = "task_unchanged"
    TASK_ARCHIVED = "task_archived"
    TASK_RESTORED = "task_restored"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_MOVED = "task_moved"
    TASK_REORDERED = "task_reordered"
    PRIORITY_SET = "priority_set"
    PRIORITY_CLEARED = "priority_cleared"
    TAGS_SET = "tags_set"
    TAGS_CLEARED = "tags_cleared"
    TAG_ADDED = "tag_added"
    TAG_REMOVED = "tag_removed"
    IMPORT_COMPLETED = "import_completed"
    IMPORT_UNCHANGED = "import_unchanged"
    IDS_REMAPPED = "ids_remapped"

    TEXT_EMPTY = "text_empty"
    TEXT_TOO_LONG = "text_too_long"
    INVALID_TASK_ID = "invalid_task_id"
    TASK_NOT_FOUND = "task_not_found"
    ARCHIVED_TASK_NOT_EDITABLE = "archived_task_not_editable"
    TASK_ALREADY_ACTIVE = "task_already_active"
    ARCHIVED_TASK_NOT_FOUND = "archived_task_not_found"
    STATE_LIMIT_REACHED = "state_limit_reached"
    TASK_ALREADY_IN_STATE = "task_already_in_state"
    DONE_ORDER_FIXED = "done_order_fixed"
    TASK_ALREADY_AT_POSITION = "task_already_at_position"
    REFERENCE_REQUIRED = "reference_required"
    SELF_REFERENCE = "self_reference"
    REFERENCE_DIFFERENT_STATE = "reference_different_state"
    TASK_ALREADY_RELATIVE = "task_already_relative"
    INVALID_POSITION = "invalid_position"
    INVALID_DELTA = "invalid_delta"
    COLUMN_EDGE = "column_edge"
    INVALID_PRIORITY = "invalid_priority"
    PRIORITY_UNCHANGED = "priority_unchanged"
    INVALID_TAG_TYPE = "invalid_tag_type"
    INVALID_TAG_FORMAT = "invalid_tag_format"
    TAGS_UNCHANGED = "tags_unchanged"
    TAG_REQUIRED = "tag_required"
    TAG_PRESENT = "tag_present"
    TAG_MISSING = "tag_missing"
    INVALID_TAG_ACTION = "invalid_tag_action"
    TASK_CONFLICT = "task_conflict"


@dataclass(frozen=True)
class OperationItem:
    code: OperationCode
    status: OperationStatus
    task_id: int | None = None
    raw_id: str | None = None
    text: str | None = None
    state: TaskState | None = None
    limit: int | None = None
    count: int | None = None
    target: str | None = None
    reference_id: int | None = None
    priority: TaskPriority | None = None
    tags: tuple[str, ...] = ()
    action: str | None = None
    id_mapping: tuple[tuple[int, int], ...] = ()


class OperationValues(TypedDict, total=False):
    task_id: int | None
    raw_id: str | None
    text: str | None
    state: TaskState | None
    limit: int | None
    count: int | None
    target: str | None
    reference_id: int | None
    priority: TaskPriority | None
    tags: tuple[str, ...]
    action: str | None
    id_mapping: tuple[tuple[int, int], ...]


@dataclass
class OperationResult:
    items: list[OperationItem] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return sum(item.status is OperationStatus.CHANGED for item in self.items)

    @property
    def unchanged(self) -> int:
        return sum(item.status is OperationStatus.UNCHANGED for item in self.items)

    @property
    def rejected(self) -> int:
        return sum(item.status is OperationStatus.REJECTED for item in self.items)

    @property
    def succeeded(self) -> int:
        """Compatibility count for accepted changed and unchanged outcomes."""
        return self.changed + self.unchanged

    @property
    def failed(self) -> int:
        """Compatibility count for rejected outcomes."""
        return self.rejected

    @property
    def ok(self) -> bool:
        return self.rejected == 0

    def add(
        self,
        code: OperationCode,
        status: OperationStatus,
        **values: Unpack[OperationValues],
    ) -> None:
        self.items.append(OperationItem(code, status, **values))

    def change(self, code: OperationCode, **values: Unpack[OperationValues]) -> None:
        self.add(code, OperationStatus.CHANGED, **values)

    def no_change(self, code: OperationCode, **values: Unpack[OperationValues]) -> None:
        self.add(code, OperationStatus.UNCHANGED, **values)

    def reject(self, code: OperationCode, **values: Unpack[OperationValues]) -> None:
        self.add(code, OperationStatus.REJECTED, **values)
