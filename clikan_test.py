#!/usr/bin/env python

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from clikan import clikan, show


@pytest.fixture(autouse=True)
def isolated_clikan_home(tmp_path, monkeypatch):
    """Keep every test completely isolated from the user's real board."""
    monkeypatch.setenv("CLIKAN_HOME", str(tmp_path))
    return tmp_path


def write_config(home, *, limits=None, repaint=None):
    """Create the minimal configuration required by a test."""
    config = {"clikan_data": str(home / ".clikan.dat")}
    if limits is not None:
        config["limits"] = limits
    if repaint is not None:
        config["repaint"] = repaint

    (home / ".clikan.yaml").write_text(
        yaml.safe_dump(config),
        encoding="utf-8",
    )


def add_tasks(runner, *tasks):
    result = runner.invoke(clikan, ["add", *tasks])
    assert result.exit_code == 0
    return result


# Configure tests


def test_command_help():
    runner = CliRunner()
    result = runner.invoke(clikan, ["--help"])

    assert result.exit_code == 0
    assert "Usage: clikan [OPTIONS] COMMAND [ARGS]..." in result.output
    assert "clikan: CLI personal kanban" in result.output


def test_command_version():
    version = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
    runner = CliRunner()
    result = runner.invoke(clikan, ["--version"])

    assert result.exit_code == 0
    assert "clikan, version {}".format(version) in result.output


def test_command_configure(isolated_clikan_home):
    runner = CliRunner()
    result = runner.invoke(clikan, ["configure"])

    assert result.exit_code == 0
    assert "Creating" in result.output
    assert (isolated_clikan_home / ".clikan.yaml").exists()


def test_command_configure_existing(isolated_clikan_home):
    runner = CliRunner()
    first_result = runner.invoke(clikan, ["configure"])
    result = runner.invoke(clikan, ["configure"], input="n\n")

    assert first_result.exit_code == 0
    assert result.exit_code == 0
    assert "Config file exists" in result.output
    assert (isolated_clikan_home / ".clikan.yaml").exists()


# Single argument tests


def test_command_a(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    result = runner.invoke(clikan, ["a", "n_--task_test"])

    assert result.exit_code == 0
    assert "Creating new task w/ id: 1 -> n_--task_test" in result.output


def test_no_command(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(runner, "n_--task_test")

    result = runner.invoke(clikan, [])

    assert result.exit_code == 0
    assert "n_--task_test" in result.output


def test_command_s(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(runner, "n_--task_test")

    result = runner.invoke(clikan, ["s"])

    assert result.exit_code == 0
    assert "n_--task_test" in result.output


def test_command_show(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(runner, "n_--task_test")

    result = runner.invoke(show)

    assert result.exit_code == 0
    assert "n_--task_test" in result.output


def test_command_not_show(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()

    result = runner.invoke(show)

    assert result.exit_code == 0
    assert "blahdyblah" not in result.output


def test_command_promote(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(runner, "promotion task")

    result = runner.invoke(clikan, ["promote", "1"])
    assert result.exit_code == 0
    assert "Promoting task 1 to in-progress." in result.output

    result = runner.invoke(clikan, ["promote", "1"])
    assert result.exit_code == 0
    assert "Promoting task 1 to done." in result.output


def test_command_delete(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(runner, "delete task")

    result = runner.invoke(clikan, ["delete", "1"])
    assert result.exit_code == 0
    assert "Removed task 1." in result.output

    result = runner.invoke(clikan, ["delete", "1"])
    assert result.exit_code == 0
    assert "No existing task with that id: 1" in result.output


# Multiple argument tests


def test_command_a_multi(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()

    result = runner.invoke(
        clikan,
        [
            "a",
            "n_--task_test_multi_1",
            "n_--task_test_multi_2",
            "n_--task_test_multi_3",
        ],
    )

    assert result.exit_code == 0
    assert "Creating new task w/ id: 1 -> n_--task_test_multi_1" in result.output
    assert "Creating new task w/ id: 2 -> n_--task_test_multi_2" in result.output
    assert "Creating new task w/ id: 3 -> n_--task_test_multi_3" in result.output


def test_command_show_multi(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(
        runner,
        "n_--task_test_multi_1",
        "n_--task_test_multi_2",
        "n_--task_test_multi_3",
    )

    result = runner.invoke(show)

    assert result.exit_code == 0
    assert "n_--task_test_multi_1" in result.output
    assert "n_--task_test_multi_2" in result.output
    assert "n_--task_test_multi_3" in result.output


def test_command_promote_multi(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(runner, "task 1", "task 2", "task 3")

    result = runner.invoke(clikan, ["promote", "1", "2"])
    assert result.exit_code == 0
    assert "Promoting task 1 to in-progress." in result.output
    assert "Promoting task 2 to in-progress." in result.output

    result = runner.invoke(clikan, ["promote", "2", "3"])
    assert result.exit_code == 0
    assert "Promoting task 2 to done." in result.output
    assert "Promoting task 3 to in-progress." in result.output


def test_command_delete_multi(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(runner, "task 1", "task 2", "task 3")

    result = runner.invoke(clikan, ["delete", "1", "2"])
    assert result.exit_code == 0
    assert "Removed task 1." in result.output
    assert "Removed task 2." in result.output

    result = runner.invoke(clikan, ["delete", "1", "2"])
    assert result.exit_code == 0
    assert "No existing task with that id: 1" in result.output
    assert "No existing task with that id: 2" in result.output


def test_command_show_multi_after_delete(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(
        runner,
        "n_--task_test_multi_1",
        "n_--task_test_multi_2",
        "n_--task_test_multi_3",
    )
    delete_result = runner.invoke(clikan, ["delete", "1", "2"])
    assert delete_result.exit_code == 0

    result = runner.invoke(show)

    assert result.exit_code == 0
    assert "n_--task_test_multi_1" not in result.output
    assert "n_--task_test_multi_2" not in result.output
    assert "n_--task_test_multi_3" in result.output


# Known uncovered command path


@pytest.mark.xfail(
    strict=True,
    reason="KT-002: regress Click argument binding is currently broken",
)
def test_command_regress_known_issue(isolated_clikan_home):
    """Capture KT-002 without making the KT-009 isolation change depend on it."""
    write_config(isolated_clikan_home)
    runner = CliRunner()
    add_tasks(runner, "regress task")
    assert runner.invoke(clikan, ["promote", "1"]).exit_code == 0
    assert runner.invoke(clikan, ["promote", "1"]).exit_code == 0

    result = runner.invoke(clikan, ["regress", "1"])

    assert result.exit_code == 0
    assert "Regressing task 1 to in-progress." in result.output


# Repaint tests


def test_repaint_config_option(isolated_clikan_home):
    write_config(isolated_clikan_home, repaint=True)
    version = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
    runner = CliRunner()

    result = runner.invoke(clikan, ["a", "n_--task_test"])

    assert result.exit_code == 0
    assert "n_--task_test" in result.output
    assert version in result.output


def test_no_repaint_config_option(isolated_clikan_home):
    write_config(isolated_clikan_home, repaint=False)
    version = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
    runner = CliRunner()

    result = runner.invoke(clikan, ["a", "n_--task_test"])

    assert result.exit_code == 0
    assert "n_--task_test" in result.output
    assert version not in result.output


# Task-name length tests


def test_taskname_config_option(isolated_clikan_home):
    write_config(isolated_clikan_home, limits={"taskname": 80})
    runner = CliRunner()
    task = "This is a long task name, more than 40 characters (66 to be exact)"

    result = runner.invoke(clikan, ["a", task])

    assert result.exit_code == 0
    assert "Creating new task" in result.output
    assert task in result.output


def test_no_taskname_config_option(isolated_clikan_home):
    write_config(isolated_clikan_home)
    runner = CliRunner()
    task = "This is a long task name, more than 40 characters (66 to be exact)"

    result = runner.invoke(clikan, ["a", task])

    assert result.exit_code == 0
    assert "Brevity counts:" in result.output
