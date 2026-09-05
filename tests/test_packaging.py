import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_pyproject():
    with (ROOT / "pyproject.toml").open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)


def test_pyproject_uses_src_layout_and_console_entrypoint():
    config = load_pyproject()

    assert config["project"]["name"] == "kanbanTUI"
    assert config["project"]["requires-python"] == ">=3.11"
    assert config["project"]["scripts"]["kanban-tui"] == "kanban_tui.cli:main"
    assert config["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_runtime_dependencies_are_cli_tui_core_only():
    config = load_pyproject()
    dependencies = config["project"]["dependencies"]

    assert any(item.startswith("Click") for item in dependencies)
    assert any(item.startswith("PyYAML") for item in dependencies)
    assert any(item.startswith("rich") for item in dependencies)
    assert any(item.startswith("textual") for item in dependencies)
    assert not any("click-default-group" in item.lower() for item in dependencies)
    assert "Programming Language :: Python :: 3.14" in config["project"]["classifiers"]


def test_local_project_configuration_is_authoritative():
    config = load_pyproject()

    assert config["build-system"]["build-backend"] == "setuptools.build_meta"
    assert config["tool"]["setuptools"]["dynamic"]["version"] == {
        "file": "VERSION"
    }
    assert not (ROOT / "setup.py").exists()
    assert not (ROOT / "requirements.txt").exists()
    assert (ROOT / "LICENSE").exists()
