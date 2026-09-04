from datetime import datetime, timezone

import pytest

from kanban_tui.models import Board, Task, TaskState, parse_timestamp


STAMP = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def test_legacy_timestamps_are_parsed_and_normalized_to_iso():
    raw = {
        "data": {
            1: [
                "todo",
                "task",
                "2026-Sep-04 10:00:00",
                "2026-Sep-04 09:00:00",
            ]
        },
        "deleted": {},
    }

    board = Board.from_mapping(raw)
    serialized = board.to_mapping()

    assert board.active[1].modified_at.tzinfo is not None
    assert board.active[1].created_at.tzinfo is not None
    assert parse_timestamp(serialized["data"][1][2]).tzinfo is not None
    assert "T" in serialized["data"][1][2]


def test_iso_timestamp_round_trip_is_stable():
    raw = {
        "data": {
            1: [
                "todo",
                "task",
                "2026-09-04T10:00:00+00:00",
                "2026-09-04T09:00:00+00:00",
            ]
        },
        "deleted": {
            2: [
                "deleted",
                "old",
                "2026-09-04T10:00:00+00:00",
                "2026-09-04T09:00:00+00:00",
            ]
        },
    }

    board = Board.from_mapping(raw)

    assert board.active[1] == Task(
        id=1,
        state=TaskState.TODO,
        text="task",
        modified_at=STAMP,
        created_at=EARLIER,
    )
    assert board.deleted[2].state is TaskState.DELETED
    assert board.to_mapping() == raw


def test_invalid_task_state_is_rejected():
    with pytest.raises(ValueError, match="unsupported state"):
        Board.from_mapping(
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
        Board.from_mapping(
            {
                "data": {1: ["todo", "task", "not-a-time", "also-not-a-time"]},
                "deleted": {},
            }
        )


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
        Board.from_mapping(raw)
