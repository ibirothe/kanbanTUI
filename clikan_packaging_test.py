from pathlib import Path
import tomllib


ROOT = Path(__file__).parent


def load_pyproject():
    with (ROOT / "pyproject.toml").open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)


def test_pyproject_defines_supported_python_and_entrypoint():
    config = load_pyproject()
    project = config["project"]

    assert project["requires-python"] == ">=3.11"
    assert project["scripts"]["clikan"] == "clikan:clikan"
    assert project["dynamic"] == ["version"]


def test_pyproject_is_single_runtime_dependency_source():
    project = load_pyproject()["project"]

    assert "Click>=8.0.1" in project["dependencies"]
    assert "click-default-group>=1.2.4" in project["dependencies"]
    assert "PyYAML>=6.0" in project["dependencies"]
    assert "rich>=13.0" in project["dependencies"]
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "setup.py").exists()


def test_setuptools_reads_version_from_version_file():
    config = load_pyproject()

    assert config["build-system"]["build-backend"] == "setuptools.build_meta"
    assert config["tool"]["setuptools"]["dynamic"]["version"] == {
        "file": "VERSION"
    }
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip()
