from kanban_tui.cli import main
from kanban_tui.models import Board
from kanban_tui.storage import read_data
from kanban_tui.tui import KanbanApp


def test_failed_first_cli_mutation_does_not_create_datastore(runner, write_config):
    config = write_config(limits={"taskname": 3})

    result = runner.invoke(main, ["add", "too long"])

    assert result.exit_code == 1
    assert "Error: task text exceeds limit" in result.output
    assert "No data" not in result.output
    assert not config.data_path.exists()


def test_first_successful_cli_mutation_creates_datastore_and_can_be_undone(
    runner, write_config
):
    config = write_config()

    add_result = runner.invoke(main, ["add", "first task"])

    assert add_result.exit_code == 0
    assert add_result.output == "Added #1: first task\n"
    assert config.data_path.exists()
    assert read_data(config).active[1].text == "first task"

    undo_result = runner.invoke(main, ["undo"])
    assert undo_result.exit_code == 0
    assert read_data(config) == Board()


async def test_first_tui_mutation_creates_datastore_without_preinitialization(write_config):
    config = write_config()
    app = KanbanApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert not config.data_path.exists()

        await app._add_prompt_result("first tui task")
        await pilot.pause()

        assert config.data_path.exists()
        assert app.board.active[1].text == "first tui task"

    assert read_data(config).active[1].text == "first tui task"
