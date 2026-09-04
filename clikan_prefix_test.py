import yaml
from click.testing import CliRunner

from clikan import clikan


def write_config(home):
    (home / ".clikan.yaml").write_text(
        yaml.safe_dump({"clikan_data": str(home / ".clikan.dat")}),
        encoding="utf-8",
    )


def test_promote_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKAN_HOME", str(tmp_path))
    write_config(tmp_path)
    runner = CliRunner()

    assert runner.invoke(clikan, ["a", "task"]).exit_code == 0
    result = runner.invoke(clikan, ["p", "1"])

    assert result.exit_code == 0
    assert "Promoting task 1 to in-progress." in result.output


def test_delete_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKAN_HOME", str(tmp_path))
    write_config(tmp_path)
    runner = CliRunner()

    assert runner.invoke(clikan, ["a", "task"]).exit_code == 0
    result = runner.invoke(clikan, ["d", "1"])

    assert result.exit_code == 0
    assert "Removed task 1." in result.output
