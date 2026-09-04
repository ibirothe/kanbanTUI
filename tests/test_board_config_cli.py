import json

import yaml

from kanban_tui.cli import main
from kanban_tui.config import get_board_config_path


def show_named_json(runner, name):
    result = runner.invoke(
        main,
        ["--board", name, "show", "--format", "json"],
    )
    assert result.exit_code == 0
    return json.loads(result.output)


def test_named_boards_are_created_listed_selected_and_isolated(
    runner, isolated_app_home
):
    work_create = runner.invoke(main, ["board", "create", "work"])
    personal_create = runner.invoke(main, ["board", "create", "personal"])

    assert work_create.exit_code == 0
    assert personal_create.exit_code == 0
    assert get_board_config_path("work").exists()
    assert get_board_config_path("personal").exists()

    assert runner.invoke(main, ["--board", "work", "add", "work task"]).exit_code == 0
    assert (
        runner.invoke(main, ["--board", "personal", "add", "personal task"]).exit_code
        == 0
    )

    assert [task["text"] for task in show_named_json(runner, "work")["tasks"]] == [
        "work task"
    ]
    assert [
        task["text"] for task in show_named_json(runner, "personal")["tasks"]
    ] == ["personal task"]

    listing = runner.invoke(main, ["--board", "work", "board", "list"])
    assert listing.exit_code == 0
    assert "* work\t" in listing.output
    assert "  personal\t" in listing.output


def test_named_board_validation_duplicate_and_selector_conflict(runner, tmp_path):
    assert runner.invoke(main, ["board", "create", "work"]).exit_code == 0

    duplicate = runner.invoke(main, ["board", "create", "work"])
    invalid = runner.invoke(main, ["board", "create", "not valid!"])
    conflict = runner.invoke(
        main,
        [
            "--board",
            "work",
            "--config",
            str(tmp_path / "other.yaml"),
            "show",
        ],
    )

    assert duplicate.exit_code != 0
    assert "already exists" in duplicate.output
    assert invalid.exit_code != 0
    assert "Board names must" in invalid.output
    assert conflict.exit_code == 2
    assert "--config and --board cannot be used together" in conflict.output


def test_named_board_can_be_bootstrapped_with_configure(runner):
    result = runner.invoke(main, ["--board", "work", "configure"])

    assert result.exit_code == 0
    config_path = get_board_config_path("work")
    assert config_path.exists()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["data_path"] == str(config_path.with_suffix(".dat"))


def test_config_path_show_and_set_preserve_unrelated_values(
    runner, isolated_app_home
):
    config_path = isolated_app_home / ".kanban-tui.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "data_path": "./board.dat",
                "limits": {"todo": 5},
                "repaint": False,
                "custom": {"keep": "me"},
            }
        ),
        encoding="utf-8",
    )

    path_result = runner.invoke(main, ["config", "path"])
    show_before = runner.invoke(main, ["config", "show"])
    set_wip = runner.invoke(main, ["config", "set", "limits.wip", "3"])
    set_repaint = runner.invoke(main, ["config", "set", "repaint", "true"])

    assert path_result.exit_code == 0
    assert str(config_path.resolve()) in path_result.output
    assert show_before.exit_code == 0
    assert "limits.todo: 5" in show_before.output
    assert "limits.wip: unlimited" in show_before.output
    assert set_wip.exit_code == 0
    assert set_repaint.exit_code == 0

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["limits"] == {"todo": 5, "wip": 3}
    assert raw["repaint"] is True
    assert raw["custom"] == {"keep": "me"}

    show_after = runner.invoke(main, ["config", "show"])
    assert "limits.wip: 3" in show_after.output
    assert "repaint: true" in show_after.output


def test_config_set_supports_unlimited_optional_limits_and_validation(
    runner, write_config
):
    write_config(limits={"todo": 2, "wip": 1})

    clear_todo = runner.invoke(
        main,
        ["config", "set", "limits.todo", "unlimited"],
    )
    bad_key = runner.invoke(main, ["config", "set", "unknown.key", "1"])
    bad_value = runner.invoke(main, ["config", "set", "limits.done", "none"])

    assert clear_todo.exit_code == 0
    assert "limits.todo: unlimited" in runner.invoke(main, ["config", "show"]).output
    assert bad_key.exit_code != 0
    assert "Unknown configuration key" in bad_key.output
    assert bad_value.exit_code != 0
    assert "requires a non-negative integer" in bad_value.output


def test_config_commands_target_selected_named_board_only(runner, isolated_app_home):
    runner.invoke(main, ["configure"])
    runner.invoke(main, ["board", "create", "work"])

    result = runner.invoke(
        main,
        ["--board", "work", "config", "set", "limits.wip", "4"],
    )

    assert result.exit_code == 0
    work_raw = yaml.safe_load(get_board_config_path("work").read_text(encoding="utf-8"))
    default_raw = yaml.safe_load(
        (isolated_app_home / ".kanban-tui.yaml").read_text(encoding="utf-8")
    )
    assert work_raw["limits"]["wip"] == 4
    assert "limits" not in default_raw
