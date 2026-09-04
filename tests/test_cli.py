from kanban_tui.cli import clikan


def test_help_and_version(runner):
    help_result = runner.invoke(clikan, ["--help"])
    version_result = runner.invoke(clikan, ["--version"])

    assert help_result.exit_code == 0
    assert "clikan: CLI personal kanban" in help_result.output
    assert version_result.exit_code == 0
    assert "clikan, version" in version_result.output


def test_configure_creates_default_config(runner, isolated_clikan_home):
    result = runner.invoke(clikan, ["configure"])

    assert result.exit_code == 0
    assert (isolated_clikan_home / ".clikan.yaml").exists()
    assert "Creating" in result.output


def test_add_show_promote_regress_delete(runner, write_config):
    write_config()

    add_result = runner.invoke(clikan, ["add", "task", "one"])
    show_result = runner.invoke(clikan, ["show"])
    promote_result = runner.invoke(clikan, ["promote", "1"])
    regress_result = runner.invoke(clikan, ["regress", "1"])
    delete_result = runner.invoke(clikan, ["delete", "1"])

    assert add_result.exit_code == 0
    assert "Creating new task w/ id: 1 -> task one" in add_result.output
    assert show_result.exit_code == 0
    assert "task one" in show_result.output
    assert "Promoting task 1 to in-progress." in promote_result.output
    assert "Regressing task 1 to todo." in regress_result.output
    assert "Removed task 1." in delete_result.output


def test_add_unquoted_words_create_one_task(runner, write_config):
    write_config()

    result = runner.invoke(clikan, ["add", "Fix", "login", "bug"])
    show_result = runner.invoke(clikan, ["show"])

    assert result.exit_code == 0
    assert "Creating new task w/ id: 1 -> Fix login bug" in result.output
    assert "[1] Fix login bug" in show_result.output
    assert "[2]" not in show_result.output


def test_unique_command_prefixes_are_supported(runner, write_config):
    write_config()

    assert runner.invoke(clikan, ["a", "task"]).exit_code == 0
    assert "task" in runner.invoke(clikan, ["s"]).output
    assert "Promoting task 1 to in-progress." in runner.invoke(
        clikan, ["p", "1"]
    ).output
    assert "Removed task 1." in runner.invoke(clikan, ["d", "1"]).output


def test_taskname_limit_returns_failure(runner, write_config):
    write_config(limits={"taskname": 5})

    result = runner.invoke(clikan, ["add", "too", "long"])

    assert result.exit_code == 1
    assert "Brevity counts:" in result.output


def test_empty_task_text_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(clikan, ["add", "   "])

    assert result.exit_code == 1
    assert "Task text cannot be empty." in result.output


def test_missing_operands_use_click_usage_errors(runner, write_config):
    write_config()

    assert runner.invoke(clikan, ["add"]).exit_code == 2
    assert runner.invoke(clikan, ["promote"]).exit_code == 2


def test_repaint_outputs_board(runner, write_config):
    write_config(repaint=True)

    result = runner.invoke(clikan, ["add", "task"])

    assert result.exit_code == 0
    assert "task" in result.output
    assert "todo" in result.output


def test_invalid_task_id_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(clikan, ["regress", "abc"])

    assert result.exit_code == 1
    assert "Invalid task id" in result.output


def test_unknown_task_id_returns_failure(runner, write_config):
    write_config()

    result = runner.invoke(clikan, ["promote", "99"])

    assert result.exit_code == 1
    assert "No existing task with that id: 99" in result.output


def test_mixed_batch_returns_failure_if_any_item_fails(runner, write_config):
    write_config(limits={"wip": 1})
    runner.invoke(clikan, ["add", "one"])
    runner.invoke(clikan, ["add", "two"])

    result = runner.invoke(clikan, ["promote", "1", "2"])

    assert result.exit_code == 1
    assert "Promoting task 1 to in-progress." in result.output
    assert "Can not promote, in-progress limit of 1 reached." in result.output
