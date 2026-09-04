import json

import yaml

from kanban_tui.cli import clikan


def write_board_config(path, data_name):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"clikan_data": f"./{data_name}"}),
        encoding="utf-8",
    )


def show_json(runner, config_path):
    result = runner.invoke(
        clikan,
        ["--config", str(config_path), "show", "--format", "json"],
    )
    assert result.exit_code == 0
    return json.loads(result.output)


def test_explicit_config_overrides_default_and_keeps_boards_independent(
    runner, isolated_clikan_home
):
    default_config = isolated_clikan_home / ".clikan.yaml"
    work_config = isolated_clikan_home / "boards" / "work.yaml"
    write_board_config(default_config, "default.dat")
    write_board_config(work_config, "work.dat")

    default_add = runner.invoke(clikan, ["add", "default", "task"])
    work_add = runner.invoke(
        clikan,
        ["--config", str(work_config), "add", "work", "task"],
    )

    assert default_add.exit_code == 0
    assert work_add.exit_code == 0

    default_payload = json.loads(
        runner.invoke(clikan, ["show", "--format", "json"]).output
    )
    work_payload = show_json(runner, work_config)

    assert [task["text"] for task in default_payload["tasks"]] == ["default task"]
    assert [task["text"] for task in work_payload["tasks"]] == ["work task"]
    assert (isolated_clikan_home / "default.dat").exists()
    assert (work_config.parent / "work.dat").exists()


def test_explicit_configure_bootstraps_selected_board(runner, tmp_path):
    config_path = tmp_path / "boards" / "personal.yaml"

    configure_result = runner.invoke(
        clikan,
        ["--config", str(config_path), "configure"],
    )

    assert configure_result.exit_code == 0
    assert config_path.exists()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["clikan_data"] == str(config_path.with_suffix(".dat").resolve())

    add_result = runner.invoke(
        clikan,
        ["--config", str(config_path), "add", "personal", "task"],
    )
    assert add_result.exit_code == 0
    assert config_path.with_suffix(".dat").exists()


def test_missing_explicit_config_fails_cleanly(runner, tmp_path):
    missing = tmp_path / "missing.yaml"

    result = runner.invoke(clikan, ["--config", str(missing), "show"])

    assert result.exit_code != 0
    assert f"Could not read config file {missing.resolve()}" in result.output


def test_invalid_explicit_config_fails_cleanly(runner, tmp_path):
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    result = runner.invoke(clikan, ["--config", str(config_path), "show"])

    assert result.exit_code != 0
    assert "must contain a YAML mapping" in result.output
