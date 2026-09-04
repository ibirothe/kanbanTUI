from textual.widgets import ListView

from kanban_tui.models import Board, TaskState
from kanban_tui.services import add_tasks
from kanban_tui.storage import datastore_lock, read_data, write_data
from kanban_tui.tui import KanbanApp


def seed_board(config, *tasks: str) -> None:
    board = Board()
    add_tasks(config, board, tasks)
    with datastore_lock(config):
        write_data(config, board)


async def test_tui_initial_selection_and_state_movement(write_config):
    config = write_config()
    seed_board(config, "first task")
    app = KanbanApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        todo = app.query_one("#todo-list", ListView)
        assert todo.index == 0
        assert app._selected_task().id == 1

        await pilot.press("right")
        await pilot.pause()

        assert app.board.active[1].state is TaskState.IN_PROGRESS
        assert app._last_list_id == "inprogress-list"
        assert app.query_one("#inprogress-list", ListView).index == 0

    persisted = read_data(config, initialize_missing=False)
    assert persisted.active[1].state is TaskState.IN_PROGRESS


async def test_tui_add_and_search_refresh_the_live_board(write_config):
    config = write_config()
    seed_board(config, "alpha", "beta search target")
    app = KanbanApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        await app._add_prompt_result("gamma")
        assert [task.text for task in app.board.ordered_tasks(TaskState.TODO)] == [
            "alpha",
            "beta search target",
            "gamma",
        ]

        await app._search_prompt_result("SEARCH TARGET")
        todo = app.query_one("#todo-list", ListView)
        assert len(todo.children) == 1
        assert app._selected_task().text == "beta search target"
        assert app.filter_text == "SEARCH TARGET"

        await app.action_clear_search()
        assert len(todo.children) == 3
        assert app.filter_text == ""


async def test_tui_keyboard_reprioritizes_selected_task(write_config):
    config = write_config()
    seed_board(config, "first", "second", "third")
    app = KanbanApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("j")
        await pilot.pause()
        assert app._selected_task().id == 2

        await pilot.press("shift+up")
        await pilot.pause()

        assert [task.id for task in app.board.ordered_tasks(TaskState.TODO)] == [2, 1, 3]
        assert app._selected_task().id == 2

    persisted = read_data(config, initialize_missing=False)
    assert [task.id for task in persisted.ordered_tasks(TaskState.TODO)] == [2, 1, 3]


async def test_tui_capacity_rejection_keeps_focus_and_state(write_config):
    config = write_config(limits={"wip": 1})
    seed_board(config, "one", "two")
    board = read_data(config, initialize_missing=False)
    board.active[1].state = TaskState.IN_PROGRESS
    board.active[1].position = 1
    board.active[2].position = 1
    with datastore_lock(config):
        write_data(config, board)

    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.pause()

        todo = app.query_one("#todo-list", ListView)
        todo.focus()
        todo.index = 0
        app._last_list_id = "todo-list"

        await pilot.press("right")
        await pilot.pause()

        assert app.board.active[2].state is TaskState.TODO
        assert app._last_list_id == "todo-list"
        assert app._selected_task().id == 2
