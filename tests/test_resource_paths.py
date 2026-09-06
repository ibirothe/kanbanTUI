import os
import subprocess
import sys
from pathlib import Path

import click
import pytest
import yaml

from kanban_tui.cli import main
from kanban_tui.config import (
    create_default_config,
    create_named_board,
    read_config,
    set_config_value,
    validate_config,
)
from kanban_tui.models import AppConfig
from kanban_tui.storage import datastore_lock


def symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")


@pytest.mark.parametrize("relative", [False, True])
def test_config_cannot_be_datastore_lock(tmp_path, relative):
    config_path = tmp_path / "board.dat.lock"
    data_path = "./board.dat" if relative else str(tmp_path / "board.dat")
    config_path.write_text(yaml.safe_dump({"data_path": data_path}))
    original = config_path.read_bytes()

    with pytest.raises(click.ClickException, match="config file.*datastore lock"):
        read_config(config_path)

    assert config_path.read_bytes() == original
    assert not (tmp_path / "board.dat").exists()


@pytest.mark.parametrize("alias_role", ["config", "data", "lock"])
def test_config_lock_collision_through_symlink(tmp_path, alias_role):
    config_path = tmp_path / "board.dat.lock"
    data_path = tmp_path / "board.dat"
    if alias_role == "config":
        alias = tmp_path / "config.yaml"
        symlink(alias, config_path)
        config_path = alias
    elif alias_role == "data":
        alias = tmp_path / "alias.dat"
        symlink(alias, data_path)
        data_path = alias
    else:
        config_path = tmp_path / "config.yaml"
        symlink(tmp_path / "board.dat.lock", config_path)

    with pytest.raises(click.ClickException, match="config file.*datastore lock"):
        validate_config({"data_path": str(data_path)}, config_path)


def test_lock_cannot_alias_datastore(tmp_path):
    data_path = tmp_path / "board.dat"
    data_path.write_text("data: {}\ndeleted: {}\n")
    symlink(tmp_path / "board.dat.lock", data_path)
    original = data_path.read_bytes()

    with pytest.raises(click.ClickException, match="datastore.*datastore lock"):
        with datastore_lock(AppConfig(data_path)):
            pytest.fail("A colliding lock was acquired")

    assert data_path.read_bytes() == original


def test_configure_rejects_candidate_config_datastore_collision(tmp_path):
    config_path = tmp_path / "board.dat"
    config_path.write_text("existing content\n")
    with pytest.raises(click.ClickException, match="config file itself"):
        create_default_config(config_path)
    assert config_path.read_text() == "existing content\n"


def test_named_board_creation_checks_resource_aliases(tmp_path):
    boards = tmp_path / "boards"
    boards.mkdir()
    config_path = boards / "work.yaml"
    symlink(boards / "work.dat.lock", config_path)

    with pytest.raises(click.ClickException, match="config file.*datastore lock"):
        create_named_board("work")

    assert not config_path.exists()
    assert not (boards / "work.dat").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX inode/lock regression")
@pytest.mark.parametrize("edit", ["setting", "data_path", "configure"])
def test_rejected_config_write_preserves_lock_against_second_process(tmp_path, edit):
    config_path = tmp_path / "board.dat.lock"
    data_path = tmp_path / "board.dat"
    config_path.write_text(yaml.safe_dump({"data_path": str(data_path)}))
    original = config_path.read_bytes()
    # Simulate a writer started before this invalid legacy layout was detected.
    with datastore_lock(AppConfig(data_path)):
        inode = config_path.stat().st_ino
        with pytest.raises(click.ClickException, match="config file.*datastore lock"):
            if edit == "configure":
                create_default_config(config_path)
            elif edit == "data_path":
                set_config_value("data_path", str(tmp_path / "other.dat"), config_path)
            else:
                set_config_value("repaint", "true", config_path)
        assert config_path.stat().st_ino == inode
        assert config_path.read_bytes() == original
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, click\n"
                "from pathlib import Path\n"
                "from kanban_tui.models import AppConfig\n"
                "from kanban_tui.storage import datastore_lock\n"
                "try:\n"
                "    with datastore_lock(AppConfig(Path(sys.argv[1]))):\n"
                "        sys.exit(2)\n"
                "except click.ClickException as exc:\n"
                "    print(exc)\n"
                "    sys.exit(0 if 'locked by another' in str(exc) else 3)\n",
                str(data_path),
            ],
            env=dict(
                os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")
            ),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert child.returncode == 0, child.stdout + child.stderr
    assert not data_path.exists()


def test_export_rejects_symlink_to_lock(runner, write_config, tmp_path):
    config = write_config()
    lock_path = Path(f"{config.data_path}.lock")
    lock_path.write_bytes(b"\0")
    target = tmp_path / "export.json"
    symlink(target, lock_path)

    result = runner.invoke(main, ["export", str(target), "--force"])

    assert result.exit_code != 0
    assert "reserved for the selected board" in result.output
    assert lock_path.read_bytes() == b"\0"


def test_configure_can_still_repair_malformed_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("[invalid yaml")
    create_default_config(config_path)
    assert read_config(config_path).data_path == tmp_path / "config.dat"
