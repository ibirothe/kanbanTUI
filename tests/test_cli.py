import json
from datetime import datetime
from pathlib import Path

from kanban_tui.cli import main
from kanban_tui.storage import read_data


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


def test_empty_board_has_actionable_hint(runner, write_config):
    write_config()

    result = runner.invoke(main, ["show"])

    assert result.exit_code == 0
    assert "No tasks yet." in result.output
    assert "kanban-tui add <task>" in result.output


def test_add_show_start_todo_delete(runner, write_config):
    write_config()

    add_result = runner.invoke(main, ["add", "task", "one"])
    show_result = runner.invoke(main, ["show"])
    start_result = runner.invoke(main, ["start", "1"])
    todo_result = runner.invoke(main, ["todo", "1"])
    delete_result = runner.invoke(main, ["delete", "1"])

    assert add_result.exit_code == 0
    assert "Added #1: task one" in add_result.output
    assert show_result.exit_code == 0
    assert "task one" in show_result.output
    assert "Started #1." in start_result.output
    assert "Moved #1 to TODO." in todo_result.output
    assert "Archived #1." in delete_result.output


def test_done_completes_task_directly(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "finish", "me"])

    result = runner.invoke(main, ["done", "1"])
    payload = json.loads(runner.invoke(main, ["show", "--format", "json"]).output)

    assert result.exit_code == 0
    assert "Completed #1." in result.output
    assert payload["tasks"][0]["state"] == "done"
    assert payload["tasks"][0]["completed_at"] is not None


def test_legacy_relative_transition_commands_remain_available(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "task"])

    promote_result = runner.invoke(main, ["promote", "1"])
    regress_result = runner.invoke(main, ["regress", "1"])

    assert promote_result.exit_code == 0
    assert promote_result.output == "Started #1.\n"
    assert regress_result.exit_code == 0
    assert regress_result.output == "Moved #1 to TODO.\n"


def test_add_unquoted_words_create_one_task(runner, write_config):
    write_config()

    result = runner.invoke(main, ["add", "Fix", "login", "bug"])
    show_result = runner.invoke(main, ["show"])

    assert result.exit_code == 0
    assert "Added #1: Fix login bug" in result.output
    assert "[1] Fix login bug" in show_result.output
    assert "[2]" not in show_result.output


def test_edit_updates_active_task_text(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "old", "text"])
    runner.invoke(main, ["start", "1"])

    edit_result = runner.invoke(main, ["edit", "1", "new", "text"])
    show_result = runner.invoke(main, ["show"])

    assert edit_result.exit_code == 0
    assert "Updated #1: new text" in edit_result.output
    assert "new text" in show_result.output
    assert "IN PROGRESS" in show_result.output


def test_edit_deleted_task_is_rejected(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "task"])
    runner.invoke(main, ["delete", "1"])

    result = runner.invoke(main, ["edit", "1", "new"])

    assert result.exit_code == 1
    assert "Error: archived task #1 cannot be edited." in result.output


def test_history_lists_archived_tasks_and_restore_recovers_them(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "recover", "me"])
    runner.invoke(main, ["delete", "1"])

    history_result = runner.invoke(main, ["history"])
    restore_result = runner.invoke(main, ["restore", "1"])
    show_result = runner.invoke(main, ["show"])

    assert history_result.exit_code == 0
    assert "recover me" in history_result.output
    assert "archived / modified" in history_result.output
    assert restore_result.exit_code == 0
    assert "Restored #1 to TODO." in restore_result.output
    assert "[1] recover me" in show_result.output


def test_restore_respects_todo_limit(runner, write_config):
    write_config(limits={"todo": 1})
    runner.invoke(main, ["add", "old"])
    runner.invoke(main, ["delete", "1"])
    runner.invoke(main, ["add", "active"])

    result = runner.invoke(main, ["restore", "1"])

    assert result.exit_code == 1
    assert "Error: TODO limit reached (1/1)." in result.output


def test_unique_command_prefixes_are_supported_when_unambiguous(runner, write_config):
    write_config()

    assert runner.invoke(main, ["a", "task"]).exit_code == 0
    assert "task" in runner.invoke(main, ["sh"]).output
    assert "Started #1." in runner.invoke(main, ["st", "1"]).output
    assert "Archived #1." in runner.invoke(main, ["de", "1"]).output


def test_ambiguous_command_prefix_is_rejected(runner, write_config):
    write_config()

    result = runner.invoke(main, ["d", "1"])

    assert result.exit_code != 0
    assert "Too many matches" in result.output


def test_taskname_limit_returns_failure(runner, write_config):
    write_config(limits={"taskname": 5})

    result = runner.invoke(main, ["add", "too", "long"])

    assert result.exit_code == 1
    assert "Error: task text exceeds limit (8/5 characters)." in result.output


def test_empty_task_text_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(main, ["add", "   "])

    assert result.exit_code == 1
    assert "Error: task text cannot be empty." in result.output


def test_missing_operands_use_click_usage_errors(runner, write_config):
    write_config()

    assert runner.invoke(main, ["add"]).exit_code == 2
    assert runner.invoke(main, ["edit", "1"]).exit_code == 2
    assert runner.invoke(main, ["start"]).exit_code == 2
    assert runner.invoke(main, ["done"]).exit_code == 2
    assert runner.invoke(main, ["todo"]).exit_code == 2
    assert runner.invoke(main, ["restore"]).exit_code == 2
    assert runner.invoke(main, ["move", "1"]).exit_code == 2


def test_repaint_outputs_board(runner, write_config):
    write_config(repaint=True)

    result = runner.invoke(main, ["add", "task"])

    assert result.exit_code == 0
    assert "task" in result.output
    assert "TODO" in result.output


def test_invalid_task_id_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(main, ["regress", "abc"])

    assert result.exit_code == 1
    assert "Error: invalid task ID 'abc'." in result.output


def test_unknown_task_id_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(main, ["promote", "99"])

    assert result.exit_code == 1
    assert "Error: task #99 does not exist." in result.output


def test_mixed_batch_returns_failure_if_any_item_fails(runner, write_config):
    write_config(limits={"wip": 1})
    runner.invoke(main, ["add", "one"])
    runner.invoke(main, ["add", "two"])

    result = runner.invoke(main, ["start", "1", "2"])

    assert result.exit_code == 1
    assert "Started #1." in result.output
    assert "Error: WIP limit reached (1/1)." in result.output


def test_move_reorders_tasks_and_persists_across_show(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "one"])
    runner.invoke(main, ["add", "two"])
    runner.invoke(main, ["add", "three"])

    move_result = runner.invoke(main, ["move", "3", "top"])
    show_result = runner.invoke(main, ["show", "--format", "json"])
    payload = json.loads(show_result.output)

    assert move_result.exit_code == 0
    assert "Moved #3 to top." in move_result.output
    assert [item["id"] for item in payload["tasks"]] == [3, 1, 2]


def test_noop_reorder_does_not_replace_previous_undo_snapshot(runner, write_config):
    config = write_config()
    runner.invoke(main, ["add", "one"])
    runner.invoke(main, ["add", "two"])

    result = runner.invoke(main, ["move", "1", "top"])

    assert result.exit_code == 1
    assert "already at top" in result.output

    undo_result = runner.invoke(main, ["undo"])
    assert undo_result.exit_code == 0
    assert list(read_data(config).active) == [1]


def test_move_before_requires_reference_id(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "task"])

    result = runner.invoke(main, ["move", "1", "before"])

    assert result.exit_code == 2
    assert "requires REFERENCE_ID" in result.output


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
    assert payload["tasks"][0]["completed_at"] is None
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() is not None


def test_show_plain_is_color_free(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "plain", "task"])

    result = runner.invoke(main, ["show", "--format", "plain"])

    assert result.exit_code == 0
    assert result.output.startswith(
        "id\tstate\ttext\tcreated_at\tmodified_at\tcompleted_at\tpriority\ttags\n"
    )
    assert "1\ttodo\tplain task\t" in result.output
    assert "\x1b[" not in result.output


def test_show_search_and_state_filters_apply_to_json(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "Fix", "Login"])
    runner.invoke(main, ["add", "login", "tests"])
    runner.invoke(main, ["start", "2"])
    runner.invoke(main, ["add", "docs"])

    result = runner.invoke(
        main,
        ["show", "--format", "json", "--state", "todo", "--search", "LOGIN"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert [item["id"] for item in payload["tasks"]] == [1]


def test_show_sort_id_can_override_manual_order(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "one"])
    runner.invoke(main, ["add", "two"])
    runner.invoke(main, ["move", "2", "top"])

    manual = json.loads(runner.invoke(main, ["show", "--format", "json"]).output)
    by_id = json.loads(
        runner.invoke(main, ["show", "--format", "json", "--sort", "id"]).output
    )

    assert [item["id"] for item in manual["tasks"]] == [2, 1]
    assert [item["id"] for item in by_id["tasks"]] == [1, 2]


def test_show_table_reports_no_matching_tasks(runner, write_config):
    write_config()
    runner.invoke(main, ["add", "task"])

    result = runner.invoke(main, ["show", "--search", "missing"])

    assert result.exit_code == 0
    assert "No matching tasks." in result.output


def test_show_rejects_unknown_format_state_and_sort(runner, write_config):
    write_config()

    assert runner.invoke(main, ["show", "--format", "xml"]).exit_code == 2
    assert runner.invoke(main, ["show", "--state", "blocked"]).exit_code == 2
    assert runner.invoke(main, ["show", "--sort", "priority"]).exit_code == 2
