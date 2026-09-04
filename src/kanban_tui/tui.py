from collections.abc import Callable

import click
from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from .models import AppConfig, Board, Task, TaskState
from .rendering import column_label, visible_tasks
from .services import (
    OperationResult,
    add_tasks,
    delete_tasks,
    edit_task,
    move_tasks_to_state,
    reorder_task,
    restore_tasks,
)
from .storage import datastore_lock, read_data, write_data


class PromptScreen(ModalScreen[str | None]):
    """Small modal text prompt used for add/edit/search/restore actions."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    PromptScreen {
        align: center middle;
    }

    #prompt-dialog {
        width: 70%;
        max-width: 80;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }

    #prompt-dialog Label {
        margin-bottom: 1;
        text-style: bold;
    }

    #prompt-hint {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        prompt: str,
        *,
        initial: str = "",
        input_type: str = "text",
    ) -> None:
        super().__init__()
        self.prompt = prompt
        self.initial = initial
        self.input_type = input_type

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-dialog"):
            yield Label(self.prompt)
            yield Input(
                value=self.initial,
                type=self.input_type,
                select_on_focus=True,
                id="prompt-input",
            )
            yield Static("Enter to confirm · Esc to cancel", id="prompt-hint")

    def on_mount(self) -> None:
        self.query_one("#prompt-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """Keyboard reference modal."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("question_mark", "close", "Close", show=False),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-dialog {
        width: 72;
        max-width: 90%;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("kanbanTUI keyboard")
            yield Static(
                "↑/↓ or j/k  select task\n"
                "←/→ or h/l  move task between states\n"
                "Shift+↑/↓    reprioritize within a column\n"
                "a            add task\n"
                "e            edit selected task\n"
                "d            archive selected task\n"
                "r            restore archived task by ID\n"
                "/            search/filter\n"
                "c            clear filter\n"
                "?            this help\n"
                "q            quit"
            )

    def action_close(self) -> None:
        self.dismiss(None)


class TaskListItem(ListItem):
    """List item carrying the task ID represented by the row."""

    def __init__(self, task: Task) -> None:
        super().__init__(Label(f"#{task.id}  {escape(task.text)}"))
        self.task_id = task.id


class KanbanApp(App[None]):
    """Interactive full-screen kanbanTUI application."""

    TITLE = "kanbanTUI"
    SUB_TITLE = "interactive board"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("a", "add_task", "Add"),
        Binding("e", "edit_task", "Edit"),
        Binding("d", "archive_task", "Archive"),
        Binding("r", "restore_task", "Restore"),
        Binding("/", "search", "Search"),
        Binding("c", "clear_search", "Clear filter", show=False),
        Binding("left", "move_left", "Move left"),
        Binding("right", "move_right", "Move right"),
        Binding("h", "move_left", "Move left", show=False),
        Binding("l", "move_right", "Move right", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("shift+up", "priority_up", "Priority up", show=False),
        Binding("shift+down", "priority_down", "Priority down", show=False),
        Binding("question_mark", "help", "Help"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #board {
        height: 1fr;
        padding: 0 1;
    }

    .column {
        width: 1fr;
        height: 1fr;
        margin: 0 1;
        border: round $primary;
    }

    .column-title {
        height: 3;
        padding: 1;
        text-style: bold;
        background: $boost;
    }

    ListView {
        height: 1fr;
    }

    ListItem {
        padding: 0 1;
    }

    #status {
        height: 1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    STATE_VIEWS = {
        TaskState.TODO: "todo-list",
        TaskState.IN_PROGRESS: "inprogress-list",
        TaskState.DONE: "done-list",
    }
    STATE_TITLES = {
        TaskState.TODO: "todo-title",
        TaskState.IN_PROGRESS: "inprogress-title",
        TaskState.DONE: "done-title",
    }

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.board = Board()
        self.filter_text = ""
        self._last_list_id = "todo-list"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="board"):
            with Vertical(classes="column"):
                yield Static("TODO", classes="column-title", id="todo-title")
                yield ListView(id="todo-list")
            with Vertical(classes="column"):
                yield Static(
                    "IN PROGRESS", classes="column-title", id="inprogress-title"
                )
                yield ListView(id="inprogress-list")
            with Vertical(classes="column"):
                yield Static("DONE", classes="column-title", id="done-title")
                yield ListView(id="done-list")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._reload_board()
        self._refresh_board()
        self.query_one("#todo-list", ListView).focus()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id:
            self._last_list_id = event.list_view.id

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _reload_board(self) -> None:
        try:
            self.board = read_data(self.config, initialize_missing=False)
        except click.ClickException as exc:
            self.board = Board()
            self._set_status(f"Error: {exc}")

    def _tasks_for_state(self, state: TaskState) -> list[Task]:
        return visible_tasks(
            self.config,
            self.board,
            state_filter=state,
            search=self.filter_text or None,
        )

    def _refresh_board(
        self,
        *,
        focus_task_id: int | None = None,
        focus_state: TaskState | None = None,
    ) -> None:
        for state, view_id in self.STATE_VIEWS.items():
            tasks = self._tasks_for_state(state)
            view = self.query_one(f"#{view_id}", ListView)
            view.clear()
            view.extend(TaskListItem(task) for task in tasks)

            title = self.query_one(f"#{self.STATE_TITLES[state]}", Static)
            title.update(
                column_label(
                    self.config,
                    self.board,
                    state,
                    visible_count=len(tasks),
                )
            )

            if focus_task_id is not None and focus_state is state:
                for index, task in enumerate(tasks):
                    if task.id == focus_task_id:
                        view.index = index
                        view.focus()
                        self._last_list_id = view_id
                        break

        self.sub_title = (
            f"filter: {self.filter_text}" if self.filter_text else "interactive board"
        )

    def _current_view(self) -> ListView:
        return self.query_one(f"#{self._last_list_id}", ListView)

    def _selected_task(self) -> Task | None:
        view = self._current_view()
        item = view.highlighted_child
        if isinstance(item, TaskListItem):
            return self.board.active.get(item.task_id)
        self._set_status("No task selected.")
        return None

    def _mutate(
        self,
        operation: Callable[[Board], OperationResult],
        *,
        focus_task_id: int | None = None,
        focus_state: TaskState | None = None,
    ) -> None:
        try:
            with datastore_lock(self.config):
                board = read_data(self.config)
                result = operation(board)
                if result.succeeded:
                    write_data(self.config, board)
            self.board = board
        except click.ClickException as exc:
            self._set_status(f"Error: {exc}")
            return

        self._set_status(" ".join(result.messages))
        self._refresh_board(
            focus_task_id=focus_task_id,
            focus_state=focus_state,
        )

    def action_cursor_down(self) -> None:
        self._current_view().action_cursor_down()

    def action_cursor_up(self) -> None:
        self._current_view().action_cursor_up()

    def action_add_task(self) -> None:
        self.push_screen(PromptScreen("Add task"), self._add_prompt_result)

    def _add_prompt_result(self, value: str | None) -> None:
        if value is None:
            return
        self._mutate(lambda board: add_tasks(self.config, board, [value]))

    def action_edit_task(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        self.push_screen(
            PromptScreen("Edit task", initial=task.text),
            lambda value: self._edit_prompt_result(task.id, value),
        )

    def _edit_prompt_result(self, task_id: int, value: str | None) -> None:
        if value is None:
            return
        state = self.board.active.get(task_id).state if task_id in self.board.active else None
        self._mutate(
            lambda board: edit_task(self.config, board, str(task_id), value),
            focus_task_id=task_id,
            focus_state=state,
        )

    def action_archive_task(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        self._mutate(lambda board: delete_tasks(board, [str(task.id)]))

    def action_restore_task(self) -> None:
        self.push_screen(
            PromptScreen("Restore archived task ID", input_type="integer"),
            self._restore_prompt_result,
        )

    def _restore_prompt_result(self, value: str | None) -> None:
        if value is None or not value.strip():
            return
        task_id = int(value)
        self._mutate(
            lambda board: restore_tasks(self.config, board, [str(task_id)]),
            focus_task_id=task_id,
            focus_state=TaskState.TODO,
        )

    def action_search(self) -> None:
        self.push_screen(
            PromptScreen("Search tasks", initial=self.filter_text),
            self._search_prompt_result,
        )

    def _search_prompt_result(self, value: str | None) -> None:
        if value is None:
            return
        self.filter_text = value.strip()
        self._set_status(
            f"Filter: {self.filter_text}" if self.filter_text else "Filter cleared."
        )
        self._refresh_board()

    def action_clear_search(self) -> None:
        self.filter_text = ""
        self._set_status("Filter cleared.")
        self._refresh_board()

    def _move_selected(self, delta: int) -> None:
        task = self._selected_task()
        if task is None:
            return
        states = [TaskState.TODO, TaskState.IN_PROGRESS, TaskState.DONE]
        current_index = states.index(task.state)
        target_index = current_index + delta
        if target_index < 0 or target_index >= len(states):
            self._set_status("Task is already at the edge of the workflow.")
            return
        target_state = states[target_index]
        self._mutate(
            lambda board: move_tasks_to_state(
                self.config,
                board,
                [str(task.id)],
                target_state,
            ),
            focus_task_id=task.id,
            focus_state=target_state,
        )

    def action_move_left(self) -> None:
        self._move_selected(-1)

    def action_move_right(self) -> None:
        self._move_selected(1)

    def _reprioritize(self, delta: int) -> None:
        task = self._selected_task()
        if task is None:
            return
        if task.state is TaskState.DONE:
            self._set_status("Completed tasks are ordered by completion time.")
            return

        ordered = self.board.ordered_tasks(task.state)
        index = next(index for index, candidate in enumerate(ordered) if candidate.id == task.id)
        neighbor_index = index + delta
        if neighbor_index < 0 or neighbor_index >= len(ordered):
            self._set_status("Task is already at the edge of the column.")
            return

        neighbor = ordered[neighbor_index]
        target = "before" if delta < 0 else "after"
        self._mutate(
            lambda board: reorder_task(
                board,
                str(task.id),
                target,
                str(neighbor.id),
            ),
            focus_task_id=task.id,
            focus_state=task.state,
        )

    def action_priority_up(self) -> None:
        self._reprioritize(-1)

    def action_priority_down(self) -> None:
        self._reprioritize(1)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())


def run_tui(config: AppConfig) -> None:
    """Run the interactive kanbanTUI application."""
    KanbanApp(config).run()
