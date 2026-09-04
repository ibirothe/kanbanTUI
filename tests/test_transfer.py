import json
from datetime import datetime, timezone

import pytest

from kanban_tui.cli import main
from kanban_tui.models import Board, Task, TaskState
from kanban_tui.transfer import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    board_from_export,
    export_payload,
    merge_boards,
)


STAMP = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)


def task(task_id, state, text, position):
    return Task(
        id=task_id,
        state=state,
        text=text,
        created_at=EARLIER,
        modified_at=STAMP,
        position=position,
    )


def test_export_payload_round_trips_complete_board():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "todo", 2),
            2: task(2, TaskState.IN_PROGRESS, "doing", 1),
            3: task(3, TaskState.DONE, "done", 3),
        },
        deleted={4: task(4, TaskState.DELETED, "archived", 4)},
    )

    payload = export_payload(board)
    restored = board_from_export(payload)

    assert payload["format"] == EXPORT_FORMAT
    assert payload["version"] == EXPORT_VERSION
    assert set(restored.active) == {1, 2, 3}
    assert set(restored.deleted) == {4}
    assert restored.active[1].text == "todo"
    assert restored.active[2].state is TaskState.IN_PROGRESS
    assert restored.active[3].state is TaskState.DONE
    assert restored.deleted[4].state is TaskState.DELETED
    assert restored.active[1].created_at == EARLIER
    assert restored.active[1].modified_at == STAMP


def test_export_validation_rejects_bad_format_version_and_duplicate_ids():
    base = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "active": [],
        "archived": [],
    }

    with pytest.raises(ValueError, match="unsupported export format"):
        board_from_export({**base, "format": "other"})
    with pytest.raises(ValueError, match="unsupported export version"):
        board_from_export({**base, "version": 99})

    duplicate = {
        **base,
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
        board_from_export(duplicate)


def test_merge_preserves_ids_and_appends_manual_order():
    current = Board(
        active={1: task(1, TaskState.TODO, "current", 1)},
        deleted={7: task(7, TaskState.DELETED, "old", 7)},
    )
    imported = Board(
        active={
            2: task(2, TaskState.TODO, "imported first", 1),
            3: task(3, TaskState.TODO, "imported second", 2),
        }
    )

    merged = merge_boards(current, imported)

    assert [item.id for item in merged.ordered_tasks(TaskState.TODO)] == [1, 2, 3]
    assert set(merged.deleted) == {7}
    assert current.active[1].position == 1


def test_merge_rejects_task_id_conflicts():
    current = Board(active={1: task(1, TaskState.TODO, "current", 1)})
    imported = Board(active={1: task(1, TaskState.TODO, "incoming", 1)})

    with pytest.raises(Exception, match="task ID conflicts: 1"):
        merge_boards(current, imported)


def test_cli_export_contains_all_done_and_archived_tasks(runner, write_config, tmp_path):
    write_config(limits={"done": 1})
    runner.invoke(main, ["add", "one"])
    runner.invoke(main, ["done", "1"])
    runner.invoke(main, ["add", "two"])
    runner.invoke(main, ["done", "2"])
    runner.invoke(main, ["add", "archive me"])
    runner.invoke(main, ["delete", "3"])

    export_path = tmp_path / "backup.json"
    result = runner.invoke(main, ["export", str(export_path)])

    assert result.exit_code == 0
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert [item["id"] for item in payload["active"]] == [2, 1]
    assert [item["id"] for item in payload["archived"]] == [3]


def test_cli_import_replace_round_trip_and_merge_conflict(runner, write_config, tmp_path):
    write_config()
    runner.invoke(main, ["add", "original"])
    export_path = tmp_path / "board.json"
    assert runner.invoke(main, ["export", str(export_path)]).exit_code == 0

    runner.invoke(main, ["edit", "1", "changed"])
    replace = runner.invoke(
        main,
        ["import", str(export_path), "--mode", "replace"],
    )
    shown = json.loads(runner.invoke(main, ["show", "--format", "json"]).output)

    assert replace.exit_code == 0
    assert [item["text"] for item in shown["tasks"]] == ["original"]

    conflict = runner.invoke(main, ["import", str(export_path), "--mode", "merge"])
    assert conflict.exit_code != 0
    assert "task ID conflicts: 1" in conflict.output


def test_cli_import_validates_capacity_before_replacing_board(
    runner, write_config, tmp_path
):
    write_config(limits={"todo": 1})
    runner.invoke(main, ["add", "keep me"])

    payload = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "active": [
            {
                "id": task_id,
                "state": "todo",
                "text": f"incoming {task_id}",
                "created_at": EARLIER.isoformat(),
                "modified_at": STAMP.isoformat(),
                "position": task_id,
            }
            for task_id in (10, 11)
        ],
        "archived": [],
    }
    import_path = tmp_path / "too-many.json"
    import_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        main,
        ["import", str(import_path), "--mode", "replace"],
    )
    shown = json.loads(runner.invoke(main, ["show", "--format", "json"]).output)

    assert result.exit_code != 0
    assert "exceeds TODO limit (2/1)" in result.output
    assert [item["text"] for item in shown["tasks"]] == ["keep me"]


def test_export_refuses_overwrite_without_force(runner, write_config, tmp_path):
    write_config()
    export_path = tmp_path / "board.json"
    export_path.write_text("existing", encoding="utf-8")

    refused = runner.invoke(main, ["export", str(export_path)])
    forced = runner.invoke(main, ["export", str(export_path), "--force"])

    assert refused.exit_code != 0
    assert "Use --force" in refused.output
    assert forced.exit_code == 0
    assert json.loads(export_path.read_text(encoding="utf-8"))["format"] == EXPORT_FORMAT
