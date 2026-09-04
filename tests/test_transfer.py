import json
from datetime import datetime, timezone

import click
import pytest

from kanban_tui.cli import main
from kanban_tui.models import Board, Task, TaskState
from kanban_tui.services import add_tasks, delete_tasks, move_tasks_to_state
from kanban_tui.storage import datastore_lock, read_data, write_data
from kanban_tui.transfer import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    board_from_export,
    export_payload,
    merge_boards,
    read_export,
    validate_board_capacity,
    write_export,
)


STAMP = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def task(task_id, state, text, *, position=1):
    return Task(task_id, state, text, STAMP, EARLIER, position=position)


def test_export_payload_contains_complete_board_not_display_subset():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "todo", position=2),
            2: task(2, TaskState.IN_PROGRESS, "doing", position=1),
            3: task(3, TaskState.DONE, "done", position=3),
        },
        deleted={4: task(4, TaskState.DELETED, "archived", position=4)},
    )

    payload = export_payload(board)

    assert payload["format"] == EXPORT_FORMAT
    assert payload["version"] == EXPORT_VERSION
    assert {item["id"] for item in payload["active"]} == {1, 2, 3}
    assert [item["id"] for item in payload["archived"]] == [4]
    assert all("created_at" in item and "modified_at" in item for item in payload["active"])
    assert all("position" in item for item in [*payload["active"], *payload["archived"]])


def test_export_round_trip_preserves_ids_states_text_and_timestamps():
    board = Board(
        active={
            5: task(5, TaskState.TODO, "five", position=2),
            2: task(2, TaskState.TODO, "two", position=1),
            8: task(8, TaskState.DONE, "eight", position=8),
        },
        deleted={11: task(11, TaskState.DELETED, "old", position=11)},
    )

    restored = board_from_export(export_payload(board))

    assert set(restored.active) == {2, 5, 8}
    assert set(restored.deleted) == {11}
    assert [task.id for task in restored.ordered_tasks(TaskState.TODO)] == [2, 5]
    assert restored.active[5].text == "five"
    assert restored.active[5].created_at == EARLIER
    assert restored.deleted[11].state is TaskState.DELETED


def test_invalid_export_format_and_duplicate_ids_are_rejected():
    with pytest.raises(ValueError, match="unsupported export format"):
        board_from_export({"format": "other", "version": 1, "active": [], "archived": []})

    payload = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "active": [
            {
                "id": 1,
                "state": "todo",
                "text": "one",
                "created_at": EARLIER.isoformat(),
                "modified_at": STAMP.isoformat(),
                "position": 1,
            }
        ],
        "archived": [
            {
                "id": 1,
                "state": "deleted",
                "text": "old",
                "created_at": EARLIER.isoformat(),
                "modified_at": STAMP.isoformat(),
                "position": 1,
            }
        ],
    }
    with pytest.raises(ValueError, match="duplicate task IDs"):
        board_from_export(payload)


def test_merge_appends_ordered_tasks_and_rejects_id_conflicts():
    current = Board(active={1: task(1, TaskState.TODO, "one", position=1)})
    imported = Board(
        active={
            2: task(2, TaskState.TODO, "two", position=1),
            3: task(3, TaskState.IN_PROGRESS, "three", position=1),
        }
    )

    merged = merge_boards(current, imported)

    assert [task.id for task in merged.ordered_tasks(TaskState.TODO)] == [1, 2]
    assert [task.id for task in merged.ordered_tasks(TaskState.IN_PROGRESS)] == [3]

    with pytest.raises(click.ClickException, match="task ID conflicts: 1"):
        merge_boards(current, Board(active={1: task(1, TaskState.TODO, "duplicate")}))


def test_import_capacity_is_validated_before_write(write_config):
    config = write_config(limits={"todo": 1})
    imported = Board(
        active={
            1: task(1, TaskState.TODO, "one", position=1),
            2: task(2, TaskState.TODO, "two", position=2),
        }
    )

    with pytest.raises(click.ClickException, match="exceeds TODO limit"):
        validate_board_capacity(config, imported)


def test_write_export_requires_force_for_existing_file(tmp_path):
    path = tmp_path / "board.json"
    board = Board(active={1: task(1, TaskState.TODO, "one")})

    write_export(path, board)
    with pytest.raises(click.ClickException, match="already exists"):
        write_export(path, board)

    write_export(path, board, overwrite=True)
    assert read_export(path).active[1].text == "one"


def test_cli_export_import_replace_and_undo(runner, write_config, tmp_path):
    config = write_config()
    runner.invoke(main, ["add", "original"])
    export_path = tmp_path / "board.json"

    export_result = runner.invoke(main, ["export", str(export_path)])
    runner.invoke(main, ["edit", "1", "changed"])
    import_result = runner.invoke(
        main,
        ["import", str(export_path), "--mode", "replace"],
    )

    assert export_result.exit_code == 0
    assert import_result.exit_code == 0
    assert read_data(config, initialize_missing=False).active[1].text == "original"

    undo_result = runner.invoke(main, ["undo"])
    assert undo_result.exit_code == 0
    assert read_data(config, initialize_missing=False).active[1].text == "changed"


def test_cli_import_merge_rejects_conflicting_ids_without_mutating_board(
    runner, write_config, tmp_path
):
    config = write_config()
    runner.invoke(main, ["add", "current"])
    path = tmp_path / "conflict.json"
    payload = export_payload(Board(active={1: task(1, TaskState.TODO, "incoming")}))
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(main, ["import", str(path), "--mode", "merge"])

    assert result.exit_code != 0
    board = read_data(config, initialize_missing=False)
    assert board.active[1].text == "current"
