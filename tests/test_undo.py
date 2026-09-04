import json

from kanban_tui.cli import main


def show_tasks(runner):
    result = runner.invoke(main, ["show", "--format", "json"])
    assert result.exit_code == 0
    return json.loads(result.output)["tasks"]


def test_undo_add_restores_empty_board_and_is_one_level(runner, write_config):
    write_config()
    assert runner.invoke(main, ["add", "task"]).exit_code == 0

    undo = runner.invoke(main, ["undo"])
    second_undo = runner.invoke(main, ["undo"])

    assert undo.exit_code == 0
    assert "Undid last board change." in undo.output
    assert show_tasks(runner) == []
    assert second_undo.exit_code != 0
    assert "Nothing to undo" in second_undo.output


def test_undo_edit_restores_previous_text(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "before"])
    runner.invoke(main, ["edit", "1", "after"])

    assert show_tasks(runner)[0]["text"] == "after"
    assert runner.invoke(main, ["undo"]).exit_code == 0
    assert show_tasks(runner)[0]["text"] == "before"


def test_undo_state_change_restores_previous_state(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "task"])
    runner.invoke(main, ["start", "1"])

    assert show_tasks(runner)[0]["state"] == "inprogress"
    runner.invoke(main, ["undo"])
    assert show_tasks(runner)[0]["state"] == "todo"


def test_undo_archive_and_restore(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "task"])
    runner.invoke(main, ["delete", "1"])

    assert show_tasks(runner) == []
    runner.invoke(main, ["undo"])
    assert show_tasks(runner)[0]["text"] == "task"

    runner.invoke(main, ["delete", "1"])
    runner.invoke(main, ["restore", "1"])
    assert show_tasks(runner)[0]["state"] == "todo"

    runner.invoke(main, ["undo"])
    assert show_tasks(runner) == []
    history = runner.invoke(main, ["history"])
    assert "task" in history.output


def test_undo_reorder_restores_previous_manual_order(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "one"])
    runner.invoke(main, ["add", "two"])
    runner.invoke(main, ["move", "2", "top"])

    assert [item["id"] for item in show_tasks(runner)] == [2, 1]
    runner.invoke(main, ["undo"])
    assert [item["id"] for item in show_tasks(runner)] == [1, 2]


def test_failed_operation_does_not_replace_last_successful_snapshot(
    runner, write_config
):
    write_config()
    runner.invoke(main, ["add", "task"])
    runner.invoke(main, ["start", "1"])

    failed = runner.invoke(main, ["start", "1"])
    assert failed.exit_code != 0

    runner.invoke(main, ["undo"])
    assert show_tasks(runner)[0]["state"] == "todo"


def test_mixed_batch_undo_restores_entire_pre_batch_board(runner, write_config):
    write_config(limits={"wip": 1})
    runner.invoke(main, ["add", "one"])
    runner.invoke(main, ["add", "two"])

    mixed = runner.invoke(main, ["start", "1", "2"])
    assert mixed.exit_code != 0
    tasks = show_tasks(runner)
    assert [item["state"] for item in tasks] == ["todo", "inprogress"]

    assert runner.invoke(main, ["undo"]).exit_code == 0
    tasks = show_tasks(runner)
    assert [item["state"] for item in tasks] == ["todo", "todo"]


def test_import_can_be_undone(runner, write_config, tmp_path):
    write_config()
    runner.invoke(main, ["add", "original"])
    export_path = tmp_path / "original.json"
    runner.invoke(main, ["export", str(export_path)])

    runner.invoke(main, ["edit", "1", "changed"])
    runner.invoke(main, ["import", str(export_path), "--mode", "replace"])
    assert show_tasks(runner)[0]["text"] == "original"

    runner.invoke(main, ["undo"])
    assert show_tasks(runner)[0]["text"] == "changed"
