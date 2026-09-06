from datetime import datetime, timezone
from io import StringIO

import pytest
import yaml

from kanban_tui.codec import (
    DATASTORE_SCHEMA_VERSION,
    decode_board,
    decode_datastore,
    encode_board,
    encode_datastore,
    load_datastore,
)
from kanban_tui.models import Board, Task, TaskPriority, TaskState

STAMP = datetime(2026, 9, 6, 12, 0, 0, 123456, tzinfo=timezone.utc)
EARLIER = datetime(2026, 9, 6, 11, 0, tzinfo=timezone.utc)


def record(*, metadata=None):
    value = [
        "todo",
        "task",
        STAMP.isoformat(),
        EARLIER.isoformat(),
        1,
    ]
    if metadata is not None:
        value.append(metadata)
    return value


def test_current_board_has_stable_versioned_golden_round_trip():
    board = Board(
        active={
            1: Task(
                1,
                TaskState.TODO,
                "task",
                STAMP,
                EARLIER,
                priority=TaskPriority.HIGH,
                tags=("backend",),
            )
        }
    )
    expected = {
        "schema_version": DATASTORE_SCHEMA_VERSION,
        "data": {1: record(metadata={"priority": "high", "tags": ["backend"]})},
        "deleted": {},
    }

    assert encode_board(board) == expected
    assert decode_board(expected) == board


def test_unversioned_legacy_board_is_read_and_encoded_as_current_schema():
    legacy = {
        "data": {
            1: [
                "todo",
                "legacy",
                "2026-Sep-06 12:00:00",
                "2026-Sep-06 11:00:00",
            ]
        },
        "deleted": {},
    }

    board = decode_board(legacy)
    encoded = encode_board(board)

    assert board.active[1].position == 1
    assert encoded["schema_version"] == DATASTORE_SCHEMA_VERSION
    assert encoded["data"][1][0:2] == ["todo", "legacy"]
    assert encoded["data"][1][4] == 1


def test_legacy_undo_is_decoded_and_reencoded_with_versions():
    raw = {
        "data": {1: record()},
        "deleted": {},
        "_undo": {"data": {}, "deleted": {}},
    }

    document = decode_datastore(raw)
    encoded = encode_datastore(document.board, document.previous)

    assert document.previous == Board()
    assert encoded["schema_version"] == DATASTORE_SCHEMA_VERSION
    assert encoded["_undo"]["schema_version"] == DATASTORE_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            {"schema_version": 99, "data": {}, "deleted": {}},
            "unsupported schema_version 99",
        ),
        (
            {"schema_version": True, "data": {}, "deleted": {}},
            "schema_version must be an integer",
        ),
        (
            {"schema_version": 1, "data": {}, "deleted": {}, "future": {}},
            "unknown fields",
        ),
        (
            {
                "schema_version": 1,
                "data": {1: record(metadata={"due_date": "tomorrow"})},
                "deleted": {},
            },
            "metadata contains unknown fields",
        ),
        (
            {
                "schema_version": 1,
                "data": {1: [*record(metadata={}), "future-field"]},
                "deleted": {},
            },
            "invalid record",
        ),
    ],
)
def test_unknown_versions_and_fields_are_rejected(raw, message):
    with pytest.raises(ValueError, match=message):
        decode_datastore(raw)


@pytest.mark.parametrize(
    "source",
    [
        """schema_version: 1
data:
  1: [todo, first, '2026-09-06T12:00:00+00:00', '2026-09-06T11:00:00+00:00']
  1: [todo, second, '2026-09-06T12:00:00+00:00', '2026-09-06T11:00:00+00:00']
deleted: {}
""",
        """schema_version: 1
data:
  1:
    - todo
    - task
    - '2026-09-06T12:00:00+00:00'
    - '2026-09-06T11:00:00+00:00'
    - 1
    - priority: high
      priority: urgent
deleted: {}
""",
    ],
)
def test_duplicate_yaml_keys_are_rejected_at_every_mapping_level(source):
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        load_datastore(StringIO(source))
