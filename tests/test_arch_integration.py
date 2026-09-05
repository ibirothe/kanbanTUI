from kanban_tui.cli import _complete_board_name, main
from kanban_tui.config import create_named_board


def test_no_argument_invocation_still_shows_board(runner, write_config):
    write_config()

    result = runner.invoke(main, [])

    assert result.exit_code == 0
    assert "No tasks yet." in result.output
    assert "kanban-tui add <task>" in result.output


def test_click_generates_bash_zsh_and_fish_completion(runner):
    for shell in ("bash", "zsh", "fish"):
        result = runner.invoke(
            main,
            [],
            prog_name="kanban-tui",
            env={"_KANBAN_TUI_COMPLETE": f"{shell}_source"},
        )

        assert result.exit_code == 0
        assert "kanban-tui" in result.output
        assert "complete" in result.output.lower()


def test_named_board_completion_filters_existing_boards():
    create_named_board("work")
    create_named_board("personal")

    assert _complete_board_name(None, None, "w") == ["work"]
    assert _complete_board_name(None, None, "") == ["personal", "work"]
