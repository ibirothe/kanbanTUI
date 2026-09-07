from datetime import datetime, timezone

from kanban_tui.codec import decode_board, encode_board
from kanban_tui.models import (
    Board,
    Task,
    TaskPriority,
    TaskState,
    format_timestamp,
    parse_timestamp,
)
from kanban_tui.services import (
    add_tasks,
    edit_task,
    move_tasks_to_state,
    reorder_task,
    set_task_priority,
    set_task_tags,
)
from kanban_tui.transactions import mutate_board, undo_board
from kanban_tui.transfer import board_from_export, export_payload

T09 = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
T10 = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
T11 = datetime(2026, 9, 4, 11, 0, tzinfo=timezone.utc)
T12 = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
T10_EARLY = T10.replace(microsecond=100_000)
T10_LATE = T10.replace(microsecond=900_000)


def test_legacy_done_record_uses_modified_time_as_completion_fallback():
    raw = {
        "data": {
            1: [
                "done",
                "legacy completed task",
                T10.isoformat(),
                T09.isoformat(),
                1,
            ]
        },
        "deleted": {},
    }

    board = decode_board(raw)

    assert board.active[1].completed_at == T10
    serialized = encode_board(board)["data"][1]
    assert serialized[5]["completed_at"] == T10.isoformat()


def test_timestamp_format_preserves_subseconds_without_inventing_them():
    assert format_timestamp(T10_LATE) == "2026-09-04T10:00:00.900000+00:00"
    legacy_seconds = parse_timestamp("2026-09-04T10:00:00+00:00")
    assert format_timestamp(legacy_seconds) == "2026-09-04T10:00:00+00:00"


def test_done_order_survives_mapping_and_export_round_trips_within_one_second():
    board = Board(
        active={
            1: Task(1, TaskState.DONE, "later", T10_LATE, T09, completed_at=T10_LATE),
            2: Task(
                2, TaskState.DONE, "earlier", T10_EARLY, T09, completed_at=T10_EARLY
            ),
        }
    )

    mapped = decode_board(encode_board(board))
    exported = board_from_export(export_payload(board))

    assert [task.id for task in board.ordered_tasks(TaskState.DONE)] == [1, 2]
    assert [task.id for task in mapped.ordered_tasks(TaskState.DONE)] == [1, 2]
    assert [task.id for task in exported.ordered_tasks(TaskState.DONE)] == [1, 2]
    assert mapped.active[1].completed_at == T10_LATE
    assert exported.active[2].completed_at == T10_EARLY


def test_done_ties_use_descending_task_id():
    board = Board(
        active={
            1: Task(1, TaskState.DONE, "one", T10, T09, completed_at=T10),
            2: Task(2, TaskState.DONE, "two", T10, T09, completed_at=T10),
        }
    )

    assert [task.id for task in board.ordered_tasks(TaskState.DONE)] == [2, 1]


def test_done_order_survives_later_text_priority_and_tag_changes(
    write_config, monkeypatch
):
    config = write_config()
    first = Task(1, TaskState.DONE, "first", T09, T09, completed_at=T09)
    second = Task(2, TaskState.DONE, "second", T10, T09, completed_at=T10)
    board = Board(active={1: first, 2: second})

    monkeypatch.setattr("kanban_tui.services.timestamp", lambda: T12)
    assert edit_task(config.policy, board, "1", "first edited").ok
    assert set_task_priority(board, "1", TaskPriority.URGENT).ok
    assert set_task_tags(board, "1", ["changed"]).ok

    assert board.active[1].modified_at == T12
    assert board.active[1].completed_at == T09
    assert [task.id for task in board.ordered_tasks(TaskState.DONE)] == [2, 1]


def test_leaving_and_reentering_done_refreshes_completion_time(write_config):
    config = write_config()
    board = Board(
        active={1: Task(1, TaskState.DONE, "task", T10, T09, completed_at=T10)}
    )
    assert move_tasks_to_state(
        config.policy, board, ["1"], TaskState.TODO, clock=lambda: T11
    ).ok
    assert board.active[1].completed_at is None

    assert move_tasks_to_state(
        config.policy, board, ["1"], TaskState.DONE, clock=lambda: T12
    ).ok
    assert board.active[1].completed_at == T12


def test_undo_restores_precise_done_order(write_config):
    config = write_config()
    mutate_board(
        config,
        lambda board: add_tasks(
            config.policy, board, ["later", "earlier"], clock=lambda: T09
        ),
    )
    mutate_board(
        config,
        lambda board: move_tasks_to_state(
            config.policy, board, ["2"], TaskState.DONE, clock=lambda: T10_EARLY
        ),
    )
    mutate_board(
        config,
        lambda board: move_tasks_to_state(
            config.policy, board, ["1"], TaskState.DONE, clock=lambda: T10_LATE
        ),
    )
    mutate_board(
        config,
        lambda board: set_task_priority(
            board, "1", TaskPriority.HIGH, clock=lambda: T11
        ),
    )

    restored = undo_board(config)

    assert [task.id for task in restored.ordered_tasks(TaskState.DONE)] == [1, 2]
    assert restored.active[1].completed_at == T10_LATE
    assert restored.active[2].completed_at == T10_EARLY


def test_transfer_round_trip_preserves_completion_time():
    board = Board(
        active={1: Task(1, TaskState.DONE, "done", T11, T09, completed_at=T10)}
    )

    restored = board_from_export(export_payload(board))

    assert restored.active[1].completed_at == T10
    assert restored.active[1].modified_at == T11


def test_relative_noop_reorders_do_not_touch_modified_time():
    first = Task(1, TaskState.TODO, "first", T09, T09, position=1)
    second = Task(2, TaskState.TODO, "second", T10, T09, position=2)
    third = Task(3, TaskState.TODO, "third", T11, T09, position=3)
    board = Board(active={1: first, 2: second, 3: third})

    before = reorder_task(board, "1", "before", "2")
    after = reorder_task(board, "3", "after", "2")
    bottom = reorder_task(board, "3", "bottom")

    assert before.failed == 1
    assert after.failed == 1
    assert bottom.failed == 1
    assert first.modified_at == T09
    assert second.modified_at == T10
    assert third.modified_at == T11
    assert [task.id for task in board.ordered_tasks(TaskState.TODO)] == [1, 2, 3]
