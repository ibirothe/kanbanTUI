import json
from datetime import datetime
from pathlib import Path

from kanban_tui.cli import main


def test_help_and_version(runner):
    help_result = runner.invoke(main, ["--help"])
    version_result = runner.invoke(main, ["--version"])

    assert help_result.exit_code == 0
    assert "kanbanTUI: terminal personal Kanban board." in help_result.output
    assert version_result.exit_code == 0
    assert "kanban-tui, version" in version_result.output


def test_configure_creates_default_config(runner, isolated_app_home):
    result = runner.invoke(main, ["configure"])

    assert result.exit_code == 0
    assert (isolated_app_home / ".kanban-tui.yaml").exists()
    assert "Creating" in result.output


def test_add_show_promote_regress_delete(runner, write_config):
    write_config()

    add_result = runner.invoke(main, ["add", "task", "one"])
    show_result = runner.invoke(main, ["show"])
    promote_result = runner.invoke(main, ["promote", "1"])
    regress_result = runner.invoke(main, ["regress", "1"])
    delete_result = runner.invoke(main, ["delete", "1"])

    assert add_result.exit_code == 0
    assert "Creating new task w/ id: 1 -> task one" in add_result.output
    assert show_result.exit_code == 0
    assert "task one" in show_result.output
    assert "Promoting task 1 to in-progress." in promote_result.output
    assert "Regressing task 1 to todo." in regress_result.output
    assert "Removed task 1." in delete_result.output


def test_add_unquoted_words_create_one_task(runner, write_config):
    write_config()

    result = runner.invoke(main, ["add", "Fix", "login", "bug"])
    show_result = runner.invoke(main, ["show"])

    assert result.exit_code == 0
    assert "Creating new task w/ id: 1 -> Fix login bug" in result.output
    assert "[1] Fix login bug" in show_result.output
    assert "[2]" not in show_result.output


def test_edit_updates_active_task_text(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "old", "text"])
    runner.invoke(main, ["promote", "1"])

    edit_result = runner.invoke(main, ["edit", "1", "new", "text"])
    show_result = runner.invoke(main, ["show"])

    assert edit_result.exit_code == 0
    assert "Updated task 1 -> new text" in edit_result.output
    assert "new text" in show_result.output
    assert "in-progress" in show_result.output


def test_edit_deleted_task_is_rejected(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "task"])
    runner.invoke(main, ["delete", "1"])

    result = runner.invoke(main, ["edit", "1", "new"])

    assert result.exit_code == 1
    assert "Can not edit deleted task 1." in result.output


def test_history_lists_deleted_tasks_and_restore_recovers_them(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "recover", "me"])
    runner.invoke(main, ["delete", "1"])

    history_result = runner.invoke(main, ["history"])
    restore_result = runner.invoke(main, ["restore", "1"])
    show_result = runner.invoke(main, ["show"])

    assert history_result.exit_code == 0
    assert "recover me" in history_result.output
    assert "deleted / modified" in history_result.output
    assert restore_result.exit_code == 0
    assert "Restored task 1 to todo." in restore_result.output
    assert "[1] recover me" in show_result.output


def test_restore_respects_todo_limit(runner, write_config):
    write_config(limits={"todo": 1})
    runner.invoke(main, ["add", "old"])
    runner.invoke(main, ["delete", "1"])
    runner.invoke(main, ["add", "active"])

    result = runner.invoke(main, ["restore", "1"])

    assert result.exit_code == 1
    assert "Can not restore, todo limit of 1 reached." in result.output


def test_unique_command_prefixes_are_supported(runner, write_config):
    write_config()

    assert runner.invoke(main, ["a", "task"]).exit_code == 0
    assert "task" in runner.invoke(main, ["s"]).output
    assert "Promoting task 1 to in-progress." in runner.invoke(
        main, ["p", "1"]
    ).output
    assert "Removed task 1." in runner.invoke(main, ["d", "1"]).output


def test_taskname_limit_returns_failure(runner, write_config):
    write_config(limits={"taskname": 5})

    result = runner.invoke(main, ["add", "too", "long"])

    assert result.exit_code == 1
    assert "Brevity counts:" in result.output


def test_empty_task_text_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(main, ["add", "   "])

    assert result.exit_code == 1
    assert "Task text cannot be empty." in result.output


def test_missing_operands_use_click_usage_errors(runner, write_config):
    write_config()

    assert runner.invoke(main, ["add"]).exit_code == 2
    assert runner.invoke(main, ["edit", "1"]).exit_code == 2
    assert runner.invoke(main, ["promote"]).exit_code == 2
    assert runner.invoke(main, ["restore"]).exit_code == 2


def test_repaint_outputs_board(runner, write_config):
    write_config(repaint=True)

    result = runner.invoke(main, ["add", "task"])

    assert result.exit_code == 0
    assert "task" in result.output
    assert "todo" in result.output


def test_invalid_task_id_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(main, ["regress", "abc"])

    assert result.exit_code == 1
    assert "Invalid task id" in result.output


def test_unknown_task_id_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(main, ["promote", "99"])

    assert result.exit_code == 1
    assert "No existing task with that id: 99" in result.output


def test_mixed_batch_returns_failure_if_any_item_fails(runner, write_config):
    write_config(limits={"wip": 1})
    runner.invoke(main, ["add", "one"])
    runner.invoke(main, ["add", "two"])

    result = runner.invoke(main, ["promote", "1", "2"])

    assert result.exit_code == 1
    assert "Promoting task 1 to in-progress." in result.output
    assert "Can not promote, in-progress limit of 1 reached." in result.output


def test_show_reads_existing_data_without_writer_lock(runner, write_config):
    config = write_config()
    runner.invoke(main, ["add", "task"])
    lock_path = Path(f"{config.data_path}.lock")
    lock_path.mkdir()

    result = runner.invoke(main, ["show"])

    assert result.exit_code == 0
    assert "task" in result.output


def test_show_json_is_machine_readable(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "json", "task"])

    result = runner.invoke(main, ["show", "--format", "json"])
    payload = json.loads(result.output)
    created_at = datetime.fromisoformat(payload["tasks"][0]["created_at"])

    assert result.exit_code == 0
    assert payload["tasks"][0]["id"] == 1
    assert payload["tasks"][0]["state"] == "todo"
    assert payload["tasks"][0]["text"] == "json task"
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() is not None


def test_show_plain_is_color_free(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "plain", "task"])

    result = runner.invoke(main, ["show", "--format", "plain"])

    assert result.exit_code == 0
    assert result.output.startswith("id\tstate\ttext\tcreated_at\tmodified_at\n")
    assert "1\ttodo\tplain task\t" in result.output
    assert "\x1b[" not in result.output


def test_show_rejects_unknown_format(runner, write_config):
    write_config()

    result = runner.invoke(main, ["show", "--format", "xml"])

    assert result.exit_code == 2
