from datetime import datetime, timezone

import pytest

from kanban_tui.codec import DATASTORE_SCHEMA_VERSION, decode_board, encode_board
from kanban_tui.models import Board, Task, TaskState, parse_timestamp

STAMP = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def test_legacy_timestamps_and_records_are_normalized():
    raw = {
        "data": {
            3: [
                "todo",
                "task",
                "2026-Sep-04 10:00:00",
                "2026-Sep-04 09:00:00",
            ]
        },
        "deleted": {},
    }

    board = decode_board(raw)
    serialized = encode_board(board)

    assert board.active[3].modified_at.tzinfo is not None
    assert board.active[3].created_at.tzinfo is not None
    assert board.active[3].position == 3
    assert parse_timestamp(serialized["data"][3][2]).tzinfo is not None
    assert "T" in serialized["data"][3][2]
    assert serialized["data"][3][4] == 3


def test_iso_timestamp_and_position_round_trip_is_stable():
    raw = {
        "schema_version": 1,
        "data": {
            1: [
                "todo",
                "task",
                "2026-09-04T10:00:00+00:00",
                "2026-09-04T09:00:00+00:00",
                4,
            ]
        },
        "deleted": {
            2: [
                "deleted",
                "old",
                "2026-09-04T10:00:00+00:00",
                "2026-09-04T09:00:00+00:00",
                2,
            ]
        },
    }

    board = decode_board(raw)

    assert board.active[1] == Task(
        id=1,
        state=TaskState.TODO,
        text="task",
        modified_at=STAMP,
        created_at=EARLIER,
        position=4,
    )
    assert board.deleted[2].state is TaskState.DELETED
    assert encode_board(board) == {
        **raw,
        "schema_version": DATASTORE_SCHEMA_VERSION,
    }


def test_active_manual_order_uses_position_then_id():
    board = Board(
        active={
            1: Task(1, TaskState.TODO, "one", STAMP, EARLIER, position=2),
            2: Task(2, TaskState.TODO, "two", STAMP, EARLIER, position=1),
            3: Task(3, TaskState.TODO, "three", STAMP, EARLIER, position=2),
        }
    )

    assert [task.id for task in board.ordered_tasks(TaskState.TODO)] == [2, 1, 3]


def test_invalid_task_state_is_rejected():
    with pytest.raises(ValueError, match="unsupported state"):
        decode_board(
            {
                "data": {
                    1: [
                        "unknown",
                        "task",
                        "2026-09-04T10:00:00+00:00",
                        "2026-09-04T09:00:00+00:00",
                    ]
                },
                "deleted": {},
            }
        )


def test_invalid_timestamp_is_rejected():
    with pytest.raises(ValueError, match="invalid timestamp"):
        decode_board(
            {
                "data": {1: ["todo", "task", "not-a-time", "also-not-a-time"]},
                "deleted": {},
            }
        )


def test_empty_task_text_is_rejected():
    with pytest.raises(ValueError, match="text cannot be empty"):
        Task(1, TaskState.TODO, "   ", STAMP, EARLIER)


def test_non_done_task_cannot_have_completion_timestamp():
    with pytest.raises(ValueError, match="cannot have a completion timestamp"):
        Task(
            1,
            TaskState.TODO,
            "task",
            STAMP,
            EARLIER,
            completed_at=STAMP,
        )


def test_invalid_position_is_rejected():
    with pytest.raises(ValueError, match="invalid position"):
        decode_board(
            {
                "data": {
                    1: [
                        "todo",
                        "task",
                        "2026-09-04T10:00:00+00:00",
                        "2026-09-04T09:00:00+00:00",
                        0,
                    ]
                },
                "deleted": {},
            }
        )


def test_fractional_position_is_rejected_instead_of_truncated():
    with pytest.raises(ValueError, match="invalid position"):
        decode_board(
            {
                "data": {
                    1: [
                        "todo",
                        "task",
                        "2026-09-04T10:00:00+00:00",
                        "2026-09-04T09:00:00+00:00",
                        1.5,
                    ]
                },
                "deleted": {},
            }
        )


def test_datastore_task_keys_must_be_positive_integers():
    with pytest.raises(ValueError, match="active task ids must be positive integers"):
        decode_board(
            {
                "data": {
                    "1": [
                        "todo",
                        "task",
                        "2026-09-04T10:00:00+00:00",
                        "2026-09-04T09:00:00+00:00",
                    ]
                },
                "deleted": {},
            }
        )


def test_board_key_must_match_task_id():
    with pytest.raises(ValueError, match="does not match task id"):
        Board(active={2: Task(1, TaskState.TODO, "task", STAMP, EARLIER)})


def test_next_task_id_includes_deleted_history():
    board = Board(
        active={1: Task(1, TaskState.TODO, "active", STAMP, EARLIER)},
        deleted={5: Task(5, TaskState.DELETED, "old", STAMP, EARLIER)},
    )

    assert board.next_task_id() == 6


def test_active_and_deleted_ids_cannot_overlap():
    raw = {
        "data": {
            1: [
                "todo",
                "active",
                "2026-09-04T10:00:00+00:00",
                "2026-09-04T09:00:00+00:00",
            ]
        },
        "deleted": {
            1: [
                "deleted",
                "old",
                "2026-09-04T10:00:00+00:00",
                "2026-09-04T09:00:00+00:00",
            ]
        },
    }

    with pytest.raises(ValueError, match="both active and deleted: 1"):
        decode_board(raw)
