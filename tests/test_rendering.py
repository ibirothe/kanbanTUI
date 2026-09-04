import json
from datetime import datetime, timezone
from pathlib import Path

from kanban_tui.models import AppConfig, Board, Limits, Task, TaskState
from kanban_tui.rendering import (
    board_columns,
    column_label,
    format_json,
    format_plain,
    split_items,
)


def stamp(hour: int):
    return datetime(2026, 9, 4, hour, 0, tzinfo=timezone.utc)


def config(*, done_limit: int = 10, todo: int | None = None, wip: int | None = None):
    return AppConfig(
        data_path=Path("/tmp/unused"),
        limits=Limits(done=done_limit, todo=todo, wip=wip),
    )


def task(
    task_id: int,
    state: TaskState,
    text: str,
    hour: int,
    *,
    position: int = 0,
):
    return Task(task_id, state, text, stamp(hour), stamp(8), position=position)


def done(task_id: int, text: str, hour: int):
    return task(task_id, TaskState.DONE, text, hour)


def test_active_tasks_are_sorted_by_manual_position():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "second", 9, position=2),
            2: task(2, TaskState.TODO, "first", 9, position=1),
            3: task(3, TaskState.IN_PROGRESS, "doing second", 9, position=2),
            4: task(4, TaskState.IN_PROGRESS, "doing first", 9, position=1),
        }
    )

    todos, inprogs, _ = split_items(board)

    assert todos == ["[2] first", "[1] second"]
    assert inprogs == ["[4] doing first", "[3] doing second"]


def test_done_tasks_are_sorted_by_modified_time_newest_first():
    board = Board(
        active={
            1: done(1, "oldest", 9),
            2: done(2, "newest", 12),
            3: done(3, "middle", 10),
        }
    )

    _, _, dones = split_items(board)

    assert dones == ["[2] newest", "[3] middle", "[1] oldest"]


def test_done_limit_selects_newest_completed_tasks():
    board = Board(
        active={
            1: done(1, "oldest", 9),
            2: done(2, "newest", 12),
            3: done(3, "middle", 10),
        }
    )

    _, _, dones = board_columns(config(done_limit=2), board)

    assert dones == ["[2] newest", "[3] middle"]


def test_column_labels_show_capacity_full_and_filtered_counts():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "one", 9),
            2: task(2, TaskState.TODO, "two", 9),
            3: task(3, TaskState.IN_PROGRESS, "doing", 10),
            4: done(4, "done", 11),
            5: done(5, "done older", 10),
        }
    )
    cfg = config(todo=2, wip=3, done_limit=1)

    assert column_label(cfg, board, TaskState.TODO) == "TODO 2/2 FULL"
    assert column_label(cfg, board, TaskState.TODO, visible_count=1) == "TODO 2/2 FULL · 1 shown"
    assert column_label(cfg, board, TaskState.IN_PROGRESS) == "IN PROGRESS 1/3"
    assert column_label(cfg, board, TaskState.DONE, visible_count=1) == "DONE 1/2"


def test_json_output_is_structured_and_deterministic():
    board = Board(
        active={
            3: task(3, TaskState.TODO, "todo three", 9, position=2),
            1: task(1, TaskState.TODO, "todo one", 9, position=1),
            4: task(4, TaskState.IN_PROGRESS, "doing", 10),
            2: done(2, "done", 12),
        }
    )

    payload = json.loads(format_json(config(), board))

    assert [item["id"] for item in payload["tasks"]] == [1, 3, 4, 2]
    assert payload["tasks"][0] == {
        "id": 1,
        "state": "todo",
        "text": "todo one",
        "created_at": "2026-09-04T08:00:00+00:00",
        "modified_at": "2026-09-04T09:00:00+00:00",
    }


def test_search_is_case_insensitive_and_state_filter_composes():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "Fix Login", 9),
            2: task(2, TaskState.IN_PROGRESS, "login tests", 10),
            3: task(3, TaskState.TODO, "docs", 11),
        }
    )

    all_matches = json.loads(format_json(config(), board, search="LOGIN"))
    todo_matches = json.loads(
        format_json(
            config(),
            board,
            search="login",
            state_filter=TaskState.TODO,
        )
    )

    assert [item["id"] for item in all_matches["tasks"]] == [1, 2]
    assert [item["id"] for item in todo_matches["tasks"]] == [1]


def test_explicit_sort_can_override_manual_order_without_mutating_board():
    board = Board(
        active={
            8: task(8, TaskState.TODO, "manual first", 9, position=1),
            2: task(2, TaskState.TODO, "manual second", 10, position=2),
        }
    )

    manual = json.loads(format_json(config(), board))
    by_id = json.loads(format_json(config(), board, sort_by="id"))
    by_modified = json.loads(format_json(config(), board, sort_by="modified"))

    assert [item["id"] for item in manual["tasks"]] == [8, 2]
    assert [item["id"] for item in by_id["tasks"]] == [2, 8]
    assert [item["id"] for item in by_modified["tasks"]] == [2, 8]
    assert [task.id for task in board.ordered_tasks(TaskState.TODO)] == [8, 2]


def test_plain_output_is_stable_color_free_and_escapes_control_text():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "line\tbreak\nnext", 9),
        }
    )

    output = format_plain(config(), board)

    assert output.splitlines()[0] == "id\tstate\ttext\tcreated_at\tmodified_at"
    assert "1\ttodo\tline\\tbreak\\nnext\t" in output
    assert "\x1b[" not in output
