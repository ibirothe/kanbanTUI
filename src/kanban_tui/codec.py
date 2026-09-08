"""Versioned YAML datastore codec isolated from the domain model."""

from dataclasses import dataclass
from typing import IO, Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from .idempotency import MAX_IMPORT_RECEIPTS, ImportReceipt
from .models import (
    Board,
    Task,
    TaskPriority,
    TaskState,
    format_timestamp,
    parse_timestamp,
)

DATASTORE_SCHEMA_VERSION = 2
SUPPORTED_DATASTORE_SCHEMA_VERSIONS = {1, DATASTORE_SCHEMA_VERSION}
UNDO_KEY = "_undo"
IMPORT_RECEIPTS_KEY = "_import_receipts"
_BOARD_KEYS = {"schema_version", "data", "deleted"}
_DATASTORE_KEYS = {*_BOARD_KEYS, UNDO_KEY, IMPORT_RECEIPTS_KEY}
_METADATA_KEYS = {"priority", "tags", "completed_at"}
_RECEIPT_KEYS = {
    "key_digest",
    "request_digest",
    "mode",
    "outcome",
    "id_mapping",
}


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys at every mapping level."""


def _construct_unique_mapping(
    loader: UniqueKeySafeLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class DatastoreDocument:
    board: Board
    previous: Board | None = None
    import_receipts: tuple[ImportReceipt, ...] = ()


def _require_mapping(raw: Any, context: str) -> dict[Any, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must contain a mapping")
    return raw


def _validate_keys(raw: dict[Any, Any], allowed: set[str], context: str) -> None:
    unknown = [key for key in raw if key not in allowed]
    if unknown:
        names = ", ".join(repr(key) for key in unknown)
        raise ValueError(f"{context} contains unknown fields: {names}")


def _validate_version(raw: dict[Any, Any], context: str) -> int | None:
    if "schema_version" not in raw:
        return None
    version = raw["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"{context} schema_version must be an integer")
    if version not in SUPPORTED_DATASTORE_SCHEMA_VERSIONS:
        raise ValueError(f"{context} uses unsupported schema_version {version}")
    return version


def _decode_task(task_id: Any, record: Any, *, deleted: bool) -> Task:
    collection = "deleted" if deleted else "active"
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
        raise ValueError(f"{collection} task ids must be positive integers")
    if not isinstance(record, list) or len(record) not in {4, 5, 6}:
        raise ValueError(
            f"task {task_id} has an invalid record; expected 4, 5, or 6 fields"
        )
    if not isinstance(record[1], str) or not record[1].strip():
        raise ValueError(f"task {task_id} must have non-empty text content")

    try:
        state = TaskState(record[0])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"task {task_id} has unsupported state {record[0]!r}") from exc
    allowed_states = (
        {TaskState.DELETED}
        if deleted
        else {TaskState.TODO, TaskState.IN_PROGRESS, TaskState.DONE}
    )
    if state not in allowed_states:
        raise ValueError(f"task {task_id} has invalid state {state.value!r}")

    try:
        modified_at = parse_timestamp(record[2])
        created_at = parse_timestamp(record[3])
    except ValueError as exc:
        raise ValueError(f"task {task_id} has an invalid timestamp: {exc}") from exc

    raw_position = task_id if len(record) == 4 else record[4]
    if isinstance(raw_position, bool):
        raise ValueError(f"task {task_id} has an invalid position")
    if isinstance(raw_position, int):
        position = raw_position
    elif isinstance(raw_position, str) and raw_position.strip().isdigit():
        position = int(raw_position.strip())
    else:
        raise ValueError(f"task {task_id} has an invalid position")
    if position < 1:
        raise ValueError(f"task {task_id} has an invalid position")
    priority: TaskPriority | None = None
    tags: tuple[str, ...] = ()
    completed_at = None
    if len(record) == 6:
        metadata = {} if record[5] is None else record[5]
        metadata = _require_mapping(metadata, f"task {task_id} metadata")
        _validate_keys(metadata, _METADATA_KEYS, f"task {task_id} metadata")
        raw_priority = metadata.get("priority")
        if raw_priority is not None:
            try:
                priority = TaskPriority(raw_priority)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"task {task_id} has an invalid priority") from exc
        raw_tags = metadata.get("tags", [])
        if not isinstance(raw_tags, list):
            raise ValueError(f"task {task_id} tags must be a list")
        tags = tuple(raw_tags)
        raw_completed_at = metadata.get("completed_at")
        if raw_completed_at is not None:
            try:
                completed_at = parse_timestamp(raw_completed_at)
            except ValueError as exc:
                raise ValueError(
                    f"task {task_id} has an invalid completion timestamp: {exc}"
                ) from exc

    try:
        return Task(
            id=task_id,
            state=state,
            text=record[1],
            modified_at=modified_at,
            created_at=created_at,
            position=position,
            priority=priority,
            tags=tags,
            completed_at=completed_at,
        )
    except ValueError as exc:
        raise ValueError(f"task {task_id} is invalid: {exc}") from exc


def _encode_task(task: Task) -> list[Any]:
    record: list[Any] = [
        task.state.value,
        task.text,
        format_timestamp(task.modified_at),
        format_timestamp(task.created_at),
        task.position,
    ]
    metadata: dict[str, object] = {}
    if task.priority is not None:
        metadata["priority"] = task.priority.value
    if task.tags:
        metadata["tags"] = list(task.tags)
    if task.completed_at is not None:
        metadata["completed_at"] = format_timestamp(task.completed_at)
    if metadata:
        record.append(metadata)
    return record


def decode_board(raw: Any, *, context: str = "datastore") -> Board:
    """Decode a current or unversioned legacy board mapping."""
    mapping = _require_mapping(raw, context)
    _validate_version(mapping, context)
    _validate_keys(mapping, _BOARD_KEYS, context)
    if "data" not in mapping or "deleted" not in mapping:
        raise ValueError(f"{context} must contain data and deleted mappings")
    if not isinstance(mapping["data"], dict) or not isinstance(
        mapping["deleted"], dict
    ):
        raise ValueError(f"{context} data and deleted must be mappings")

    active = {
        task_id: _decode_task(task_id, record, deleted=False)
        for task_id, record in mapping["data"].items()
    }
    deleted = {
        task_id: _decode_task(task_id, record, deleted=True)
        for task_id, record in mapping["deleted"].items()
    }
    return Board(active=active, deleted=deleted)


def encode_board(board: Board) -> dict[str, Any]:
    """Encode a board using the current explicit schema version."""
    return {
        "schema_version": DATASTORE_SCHEMA_VERSION,
        "data": {task_id: _encode_task(task) for task_id, task in board.active.items()},
        "deleted": {
            task_id: _encode_task(task) for task_id, task in board.deleted.items()
        },
    }


def _decode_import_receipt(raw: Any) -> ImportReceipt:
    mapping = _require_mapping(raw, "import receipt")
    _validate_keys(mapping, _RECEIPT_KEYS, "import receipt")
    if set(mapping) != _RECEIPT_KEYS:
        raise ValueError("import receipt must contain all required fields")

    outcome = mapping["outcome"]
    if outcome not in {"changed", "unchanged"}:
        raise ValueError("import receipt outcome must be changed or unchanged")
    raw_mapping = mapping["id_mapping"]
    if not isinstance(raw_mapping, list):
        raise ValueError("import receipt id_mapping must be a list")
    id_mapping: list[tuple[int, int]] = []
    for pair in raw_mapping:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) for value in pair
            )
        ):
            raise ValueError("import receipt ID mappings must be integer pairs")
        id_mapping.append((pair[0], pair[1]))
    try:
        return ImportReceipt(
            key_digest=mapping["key_digest"],
            request_digest=mapping["request_digest"],
            mode=mapping["mode"],
            changed=outcome == "changed",
            id_mapping=tuple(id_mapping),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid import receipt: {exc}") from exc


def _encode_import_receipt(receipt: ImportReceipt) -> dict[str, Any]:
    return {
        "key_digest": receipt.key_digest,
        "request_digest": receipt.request_digest,
        "mode": receipt.mode,
        "outcome": "changed" if receipt.changed else "unchanged",
        "id_mapping": [list(pair) for pair in receipt.id_mapping],
    }


def decode_datastore(raw: Any) -> DatastoreDocument:
    mapping = _require_mapping(raw, "datastore")
    version = _validate_version(mapping, "datastore")
    _validate_keys(mapping, _DATASTORE_KEYS, "datastore")
    if IMPORT_RECEIPTS_KEY in mapping and version != DATASTORE_SCHEMA_VERSION:
        raise ValueError(
            "datastore import receipts require "
            f"schema_version {DATASTORE_SCHEMA_VERSION}"
        )
    board = decode_board(
        {
            key: value
            for key, value in mapping.items()
            if key not in {UNDO_KEY, IMPORT_RECEIPTS_KEY}
        }
    )
    previous = (
        decode_board(mapping[UNDO_KEY], context="undo snapshot")
        if UNDO_KEY in mapping
        else None
    )
    raw_receipts = mapping.get(IMPORT_RECEIPTS_KEY, [])
    if not isinstance(raw_receipts, list):
        raise ValueError("datastore import receipts must be a list")
    if len(raw_receipts) > MAX_IMPORT_RECEIPTS:
        raise ValueError(
            f"datastore may contain at most {MAX_IMPORT_RECEIPTS} import receipts"
        )
    import_receipts = tuple(_decode_import_receipt(item) for item in raw_receipts)
    key_digests = [receipt.key_digest for receipt in import_receipts]
    if len(key_digests) != len(set(key_digests)):
        raise ValueError("datastore contains duplicate import receipt keys")
    return DatastoreDocument(
        board=board,
        previous=previous,
        import_receipts=import_receipts,
    )


def encode_datastore(
    board: Board,
    previous: Board | None = None,
    import_receipts: tuple[ImportReceipt, ...] = (),
) -> dict[str, Any]:
    if len(import_receipts) > MAX_IMPORT_RECEIPTS:
        raise ValueError(f"at most {MAX_IMPORT_RECEIPTS} import receipts are allowed")
    raw = encode_board(board)
    if previous is not None:
        raw[UNDO_KEY] = encode_board(previous)
    if import_receipts:
        raw[IMPORT_RECEIPTS_KEY] = [
            _encode_import_receipt(receipt) for receipt in import_receipts
        ]
    return raw


def load_datastore(stream: IO[str]) -> DatastoreDocument:
    """Parse YAML with duplicate-key protection, then decode its schema."""
    return decode_datastore(yaml.load(stream, Loader=UniqueKeySafeLoader))


def dump_datastore(
    stream: IO[str],
    board: Board,
    previous: Board | None = None,
    import_receipts: tuple[ImportReceipt, ...] = (),
) -> None:
    yaml.safe_dump(
        encode_datastore(board, previous, import_receipts),
        stream,
        default_flow_style=False,
        sort_keys=False,
    )
