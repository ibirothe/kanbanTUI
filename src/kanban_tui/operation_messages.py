"""English terminal presentation for typed operation outcomes."""

from .models import TaskState
from .results import OperationCode, OperationItem, OperationResult


def _state_name(state: TaskState | None) -> str:
    if state is TaskState.IN_PROGRESS:
        return "IN PROGRESS"
    return state.value.upper() if state is not None else ""


def format_operation(item: OperationItem) -> str:
    code = item.code
    task_id = item.task_id
    if code is OperationCode.TASK_ADDED:
        return f"Added #{task_id}: {item.text}"
    if code is OperationCode.TASK_UPDATED:
        return f"Updated #{task_id}: {item.text}"
    if code is OperationCode.TASK_UNCHANGED:
        return f"Task #{task_id} is unchanged."
    if code is OperationCode.TASK_ARCHIVED:
        return f"Archived #{task_id}."
    if code is OperationCode.TASK_RESTORED:
        return f"Restored #{task_id} to TODO."
    if code is OperationCode.TASK_STARTED:
        return f"Started #{task_id}."
    if code is OperationCode.TASK_COMPLETED:
        return f"Completed #{task_id}."
    if code is OperationCode.TASK_MOVED:
        return f"Moved #{task_id} to {_state_name(item.state)}."
    if code is OperationCode.TASK_REORDERED:
        if item.reference_id is None:
            return f"Moved #{task_id} to {item.target}."
        return f"Moved #{task_id} {item.target} #{item.reference_id}."
    if code is OperationCode.PRIORITY_SET:
        assert item.priority is not None
        return f"Set #{task_id} priority to {item.priority.value}."
    if code is OperationCode.PRIORITY_CLEARED:
        return f"Cleared priority for #{task_id}."
    if code is OperationCode.TAGS_SET:
        return f"Set #{task_id} tags: {', '.join(item.tags)}."
    if code is OperationCode.TAGS_CLEARED:
        return f"Cleared tags for #{task_id}."
    if code is OperationCode.TAG_ADDED:
        return f"Added tag #{item.text} to #{task_id}."
    if code is OperationCode.TAG_REMOVED:
        return f"Removed tag #{item.text} from #{task_id}."
    if code is OperationCode.IMPORT_COMPLETED:
        return f"Imported board from {item.text} ({item.action})."
    if code is OperationCode.IMPORT_UNCHANGED:
        return "Import produced no board changes."
    if code is OperationCode.IDS_REMAPPED:
        return f"Remapped task IDs: {item.text}"

    if code is OperationCode.TEXT_EMPTY:
        return "Error: task text cannot be empty."
    if code is OperationCode.TEXT_TOO_LONG:
        return f"Error: task text exceeds limit ({item.count}/{item.limit} characters)."
    if code is OperationCode.INVALID_TASK_ID:
        return f"Error: invalid task ID {item.raw_id!r}."
    if code is OperationCode.TASK_NOT_FOUND:
        return f"Error: task #{task_id} does not exist."
    if code is OperationCode.ARCHIVED_TASK_NOT_EDITABLE:
        return f"Error: archived task #{task_id} cannot be edited."
    if code is OperationCode.TASK_ALREADY_ACTIVE:
        return f"Task #{task_id} is already active."
    if code is OperationCode.ARCHIVED_TASK_NOT_FOUND:
        return f"Error: archived task #{task_id} does not exist."
    if code is OperationCode.STATE_LIMIT_REACHED:
        label = "WIP" if item.state is TaskState.IN_PROGRESS else "TODO"
        return f"Error: {label} limit reached ({item.count}/{item.limit})."
    if code is OperationCode.TASK_ALREADY_IN_STATE:
        return f"Task #{task_id} is already {_state_name(item.state)}."
    if code is OperationCode.DONE_ORDER_FIXED:
        return "Error: completed tasks are ordered by completion time."
    if code is OperationCode.TASK_ALREADY_AT_POSITION:
        return f"Task #{task_id} is already at {item.target}."
    if code is OperationCode.REFERENCE_REQUIRED:
        return f"Error: {item.target} requires a reference task ID."
    if code is OperationCode.SELF_REFERENCE:
        return "Error: a task cannot be positioned relative to itself."
    if code is OperationCode.REFERENCE_DIFFERENT_STATE:
        return "Error: reference task must be in the same column."
    if code is OperationCode.TASK_ALREADY_RELATIVE:
        return f"Task #{task_id} is already {item.target} #{item.reference_id}."
    if code is OperationCode.INVALID_POSITION:
        return "Error: position must be top, bottom, before, or after."
    if code is OperationCode.INVALID_DELTA:
        return "Error: relative position must be -1 or 1."
    if code is OperationCode.COLUMN_EDGE:
        return "Task is already at the edge of the column."
    if code is OperationCode.INVALID_PRIORITY:
        return f"Error: invalid priority {item.text!r}."
    if code is OperationCode.PRIORITY_UNCHANGED:
        label = item.priority.value if item.priority is not None else "none"
        return f"Task #{task_id} priority is already {label}."
    if code is OperationCode.INVALID_TAG_TYPE:
        return "Error: tags must be strings."
    if code is OperationCode.INVALID_TAG_FORMAT:
        return (
            "Error: tags must be 1-32 lowercase letters/numbers and may contain - or _."
        )
    if code is OperationCode.TAGS_UNCHANGED:
        return f"Task #{task_id} tags are unchanged."
    if code is OperationCode.TAG_REQUIRED:
        return f"Error: tag {item.action} requires a tag value."
    if code is OperationCode.TAG_PRESENT:
        return f"Task #{task_id} already has tag #{item.text}."
    if code is OperationCode.TAG_MISSING:
        return f"Task #{task_id} does not have tag #{item.text}."
    if code is OperationCode.INVALID_TAG_ACTION:
        return "Error: tag action must be add, remove, or clear."
    raise ValueError(f"Unsupported operation code: {code}")


def format_result(result: OperationResult) -> list[str]:
    return [format_operation(item) for item in result.items]


def format_task_conflict(task_id: int) -> str:
    return f"Conflict: task #{task_id} changed or is no longer available."
