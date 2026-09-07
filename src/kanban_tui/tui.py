from collections.abc import Callable
from typing import Literal

import click
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from .application import BoardApplication, StoreError, TaskConflict, TaskExpectation
from .models import Board, Task, TaskPriority, TaskState
from .operation_messages import format_result, format_task_conflict
from .rendering import column_label, task_rich_text, visible_tasks
from .results import OperationResult
from .services import (
    add_tasks,
    delete_tasks,
    edit_task,
    move_tasks_to_state,
    reorder_task_relative,
    restore_tasks,
    set_task_priority,
    set_task_tags,
)
from .settings import AppConfig
from .storage import YamlBoardStore
from .themes import Theme, get_theme


def _style_dialog(screen: ModalScreen, dialog_id: str, theme: Theme) -> None:
    screen.styles.background = theme.background
    screen.styles.color = theme.text
    dialog = screen.query_one(dialog_id, Vertical)
    dialog.styles.background = theme.surface
    dialog.styles.color = theme.text
    dialog.styles.border = ("round", theme.accent)


class PromptScreen(ModalScreen[str | None]):
    """Small modal text prompt used for board actions."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    PromptScreen {
        align: center middle;
    }

    #prompt-dialog {
        width: 70%;
        max-width: 80;
        height: auto;
        padding: 1 2;
    }

    #prompt-dialog Label {
        margin-bottom: 1;
        text-style: bold;
    }

    #prompt-hint {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        prompt: str,
        palette: Theme,
        *,
        initial: str = "",
        input_type: Literal["integer", "number", "text"] = "text",
    ) -> None:
        super().__init__()
        self.prompt = prompt
        self.palette = palette
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
            yield Static("", id="prompt-status")

    def on_mount(self) -> None:
        _style_dialog(self, "#prompt-dialog", self.palette)
        input_widget = self.query_one("#prompt-input", Input)
        input_widget.styles.border = ("round", self.palette.accent)
        input_widget.styles.background = self.palette.background
        input_widget.styles.color = self.palette.text
        self.query_one("#prompt-hint", Static).styles.color = self.palette.muted
        input_widget.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class MutationPromptScreen(PromptScreen):
    """Prompt that keeps its draft until a board mutation succeeds."""

    def __init__(
        self,
        config: AppConfig,
        application: BoardApplication,
        prompt: str,
        palette: Theme,
        *,
        initial: str = "",
    ) -> None:
        super().__init__(prompt, palette, initial=initial)
        self.config = config
        self.application = application
        self.current_board: Board | None = None
        self.outcome: OperationResult | None = None
        self._applying = False

    def _apply(self, board: Board, value: str) -> OperationResult:
        raise NotImplementedError

    def _expected_tasks(self) -> tuple[TaskExpectation, ...]:
        return ()

    def _blocked_message(self) -> str | None:
        return None

    def _status(self, message: str, *, error: bool = True) -> None:
        input_widget = self.query_one("#prompt-input", Input)
        input_widget.styles.border = (
            "round",
            self.palette.priority_urgent if error else self.palette.accent,
        )
        self.query_one("#prompt-status", Static).update(Text(message))
        input_widget.focus()

    def _handle_conflict(self, exc: TaskConflict) -> None:
        self.current_board = exc.board
        self._status(f"{format_task_conflict(exc.task_id)} Draft kept; Esc to cancel.")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        event.prevent_default()
        if self._applying:
            return
        blocked = self._blocked_message()
        if blocked is not None:
            self._status(blocked)
            return

        input_widget = self.query_one("#prompt-input", Input)
        self._applying = True
        input_widget.disabled = True
        conflict: TaskConflict | None = None
        error: click.ClickException | StoreError | None = None
        try:
            board, result = self.application.mutate(
                lambda board: self._apply(board, event.value),
                expected_tasks=self._expected_tasks(),
            )
        except TaskConflict as exc:
            conflict = exc
        except (click.ClickException, StoreError) as exc:
            error = exc
        finally:
            input_widget.disabled = False
            self._applying = False

        if conflict is not None:
            self._handle_conflict(conflict)
            return
        if error is not None:
            self._status(f"Error: {error}")
            return

        self.current_board = board
        if result.changed or result.unchanged:
            self.outcome = result
            self.dismiss(event.value)
        else:
            self._status(" ".join(format_result(result)))


class AddTaskPromptScreen(MutationPromptScreen):
    """Add one task without discarding rejected input."""

    def __init__(
        self, config: AppConfig, application: BoardApplication, palette: Theme
    ) -> None:
        super().__init__(config, application, "Add task", palette)

    def _apply(self, board: Board, value: str) -> OperationResult:
        return add_tasks(self.config.policy, board, [value])


class TaskPromptScreen(MutationPromptScreen):
    """Edit a captured task, retaining the draft until a conflict is reviewed."""

    BINDINGS = [Binding("ctrl+r", "review_current", "Review current task")]

    def __init__(
        self,
        config: AppConfig,
        application: BoardApplication,
        task: Task,
        field: Literal["text", "tags"],
        palette: Theme,
    ) -> None:
        super().__init__(
            config,
            application,
            "Edit task" if field == "text" else "Set tags (comma-separated)",
            palette,
            initial=task.text if field == "text" else ", ".join(task.tags),
        )
        self.field = field
        self.expected = TaskExpectation.capture(task)
        self.conflicted = False

    def _apply(self, board: Board, value: str) -> OperationResult:
        task_id = str(self.expected.task_id)
        if self.field == "text":
            return edit_task(self.config.policy, board, task_id, value)
        tags = [part.strip() for part in value.split(",") if part.strip()]
        return set_task_tags(board, task_id, tags)

    def _expected_tasks(self) -> tuple[TaskExpectation, ...]:
        return (self.expected,)

    def _blocked_message(self) -> str | None:
        if self.conflicted:
            return "Conflict: press Ctrl+R to review the current task first."
        return None

    def _handle_conflict(self, exc: TaskConflict) -> None:
        self.current_board = exc.board
        self.conflicted = True
        self._status(
            f"{format_task_conflict(exc.task_id)} Your draft is kept. "
            "Ctrl+R to review · Esc to cancel."
        )

    def action_review_current(self) -> None:
        try:
            self.current_board = self.application.read()
        except (click.ClickException, StoreError) as exc:
            self._status(f"Error: {exc}")
            return
        task = self.current_board.active.get(self.expected.task_id)
        if task is None:
            self.conflicted = True
            self._status("Task is archived or missing. Draft kept; Esc to cancel.")
            return
        self.expected = TaskExpectation.capture(task)
        self.conflicted = False
        priority = task.priority.value if task.priority else "none"
        tags = ", ".join(task.tags) or "none"
        self._status(
            f"Current #{task.id}: {task.text}\n"
            f"State: {task.state.value} · Priority: {priority} · Tags: {tags}\n"
            f"Your draft is unchanged. Enter to apply your {self.field} · Esc to cancel.",
            error=False,
        )


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
        padding: 1 2;
    }
    """

    def __init__(self, palette: Theme) -> None:
        super().__init__()
        self.palette = palette

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("kanbanTUI keyboard")
            yield Static(
                "↑/↓ or j/k  select task\n"
                "←/→ or h/l  move task between states\n"
                "Shift+↑/↓    reprioritize within a column\n"
                "a            add task\n"
                "e            edit selected task\n"
                "p            cycle selected task priority\n"
                "t            set selected task tags\n"
                "d            archive selected task\n"
                "r            browse and restore archived tasks\n"
                "Ctrl+R       refresh external changes\n"
                "u            undo last board change\n"
                "/            search text/tags/priority\n"
                "c            clear filter\n"
                "?            this help\n"
                "q            quit"
            )

    def on_mount(self) -> None:
        _style_dialog(self, "#help-dialog", self.palette)

    def action_close(self) -> None:
        self.dismiss(None)


class TaskListItem(ListItem):
    """List item carrying the task ID represented by the row."""

    def __init__(self, task: Task, theme: Theme) -> None:
        super().__init__(Label(task_rich_text(task, theme)))
        self.task_id = task.id


class ArchiveScreen(ModalScreen[tuple[Board, int] | None]):
    """Search archived tasks and restore through the shared transaction boundary."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    CSS = """
    ArchiveScreen { align: center middle; }
    #archive-dialog { width: 80%; max-width: 90; height: 75%; padding: 1 2; }
    #archive-list { height: 1fr; }
    #archive-status { height: auto; }
    """

    def __init__(
        self,
        config: AppConfig,
        application: BoardApplication,
        board: Board,
        palette: Theme,
    ) -> None:
        super().__init__()
        self.config = config
        self.application = application
        self.board = board
        self.palette = palette

    def compose(self) -> ComposeResult:
        with Vertical(id="archive-dialog"):
            yield Label("Restore archived task")
            yield Input(placeholder="Search by ID or text", id="archive-search")
            yield ListView(id="archive-list")
            yield Static(
                "Enter to restore · Tab to browse · Esc to cancel", id="archive-status"
            )

    async def on_mount(self) -> None:
        _style_dialog(self, "#archive-dialog", self.palette)
        await self._filter("")
        self.query_one("#archive-search", Input).focus()

    async def _filter(self, query: str) -> None:
        view = self.query_one("#archive-list", ListView)
        await view.clear()
        tasks = [
            task
            for task in sorted(self.board.deleted.values(), key=lambda task: task.id)
            if query.casefold() in f"{task.id} {task.text}".casefold()
        ]
        await view.extend(TaskListItem(task, self.palette) for task in tasks)
        if tasks:
            view.index = 0
        self.query_one("#archive-status", Static).update(
            "Enter to restore · Tab to browse · Esc to cancel"
            if tasks
            else "No matching archived tasks."
            if self.board.deleted
            else "No archived tasks to restore."
        )

    async def on_input_changed(self, event: Input.Changed) -> None:
        await self._filter(event.value.strip())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._restore_selected()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        self._restore_selected()

    def _restore_selected(self) -> None:
        item = self.query_one("#archive-list", ListView).highlighted_child
        if not isinstance(item, TaskListItem):
            return
        try:
            board, result = self.application.mutate(
                lambda board: restore_tasks(
                    self.config.policy, board, [str(item.task_id)]
                ),
                expected_tasks=(
                    TaskExpectation.capture(self.board.deleted[item.task_id]),
                ),
            )
        except TaskConflict as exc:
            self.query_one("#archive-status", Static).update(
                Text(
                    f"{format_task_conflict(exc.task_id)} "
                    "Close and reopen the archive to review current tasks."
                )
            )
            return
        except (click.ClickException, StoreError) as exc:
            self.query_one("#archive-status", Static).update(f"Error: {exc}")
            return
        if result.changed or result.unchanged:
            self.dismiss((board, item.task_id))
        else:
            self.query_one("#archive-status", Static).update(
                " ".join(format_result(result))
            )

    def action_cancel(self) -> None:
        self.dismiss(None)


class KanbanApp(App[None]):
    """Interactive full-screen kanbanTUI application."""

    TITLE = "kanbanTUI"
    SUB_TITLE = "interactive board"
    PRIORITY_CYCLE = (
        None,
        TaskPriority.LOW,
        TaskPriority.NORMAL,
        TaskPriority.HIGH,
        TaskPriority.URGENT,
    )

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("a", "add_task", "Add"),
        Binding("e", "edit_task", "Edit"),
        Binding("p", "cycle_priority", "Priority"),
        Binding("t", "set_tags", "Tags"),
        Binding("d", "archive_task", "Archive"),
        Binding("r", "restore_task", "Restore"),
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("u", "undo", "Undo"),
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
    }

    .column-title {
        height: 3;
        padding: 1;
        text-style: bold;
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

    def __init__(
        self,
        config: AppConfig,
        *,
        application: BoardApplication | None = None,
        board_name: str = "default",
    ) -> None:
        super().__init__()
        self.config = config
        self.application = application or BoardApplication(YamlBoardStore(config))
        self.board_name = board_name
        self.title = f"kanbanTUI · {board_name}"
        self._refreshing = False
        self.palette = get_theme(config.presentation.theme)
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

    async def on_mount(self) -> None:
        self._apply_theme()
        self._reload_board()
        await self._refresh_board()

    def _state_color(self, state: TaskState) -> str:
        return {
            TaskState.TODO: self.palette.todo,
            TaskState.IN_PROGRESS: self.palette.wip,
            TaskState.DONE: self.palette.done,
        }[state]

    def _apply_theme(self) -> None:
        self.screen.styles.background = self.palette.background
        self.screen.styles.color = self.palette.text

        header = self.query_one(Header)
        header.styles.background = self.palette.surface
        header.styles.color = self.palette.text
        footer = self.query_one(Footer)
        footer.styles.background = self.palette.surface
        footer.styles.color = self.palette.text
        status = self.query_one("#status", Static)
        status.styles.background = self.palette.surface
        status.styles.color = self.palette.muted

        for state, view_id in self.STATE_VIEWS.items():
            color = self._state_color(state)
            title = self.query_one(f"#{self.STATE_TITLES[state]}", Static)
            title.styles.background = self.palette.surface
            title.styles.color = color
            if title.parent is not None:
                title.parent.styles.background = self.palette.background
                title.parent.styles.border = ("round", color)
            view = self.query_one(f"#{view_id}", ListView)
            view.styles.background = self.palette.background
            view.styles.color = self.palette.text

    def _style_selection(self) -> None:
        for view_id in self.STATE_VIEWS.values():
            view = self.query_one(f"#{view_id}", ListView)
            for child in view.children:
                child.styles.background = self.palette.background
                child.styles.color = self.palette.text
            highlighted = view.highlighted_child
            if highlighted is not None:
                highlighted.styles.background = self.palette.selection
                highlighted.styles.color = self.palette.selection_text
                highlighted.styles.text_style = "bold"

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if not self._refreshing and event.list_view.has_focus and event.list_view.id:
            self._last_list_id = event.list_view.id
        self._style_selection()

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _reload_board(self) -> bool:
        try:
            self.board = self.application.read()
            return True
        except (click.ClickException, StoreError) as exc:
            self._set_status(f"Error: {exc}")
            return False

    def _tasks_for_state(self, state: TaskState) -> list[Task]:
        return visible_tasks(
            self.config,
            self.board,
            state_filter=state,
            search=self.filter_text or None,
        )

    async def _refresh_board(
        self,
        *,
        focus_task_id: int | None = None,
        focus_state: TaskState | None = None,
    ) -> None:
        previous_view = self._current_view()
        previous_view_id = previous_view.id
        previous_index = previous_view.index or 0
        item = previous_view.highlighted_child
        if focus_task_id is None and isinstance(item, TaskListItem):
            focus_task_id = item.task_id
        selected_task = (
            self.board.active.get(focus_task_id) if focus_task_id is not None else None
        )
        if selected_task is not None:
            focus_state = selected_task.state
        populated: list[ListView] = []
        selected: tuple[ListView, int] | None = None
        self._refreshing = True
        try:
            for state, view_id in self.STATE_VIEWS.items():
                tasks = self._tasks_for_state(state)
                view = self.query_one(f"#{view_id}", ListView)
                await view.clear()
                if tasks:
                    await view.extend(
                        TaskListItem(task, self.palette) for task in tasks
                    )
                    view.index = 0
                    populated.append(view)
                self.query_one(f"#{self.STATE_TITLES[state]}", Static).update(
                    column_label(
                        self.config, self.board, state, visible_count=len(tasks)
                    )
                )
                if focus_state is state:
                    for index, task in enumerate(tasks):
                        if task.id == focus_task_id:
                            selected = (view, index)
                            break
            if selected is None and populated:
                view = next(
                    (v for v in populated if v.id == previous_view_id), populated[0]
                )
                selected = (view, min(previous_index, len(view.children) - 1))
            if selected is not None:
                view, index = selected
                view.index = index
                view.focus()
                self._last_list_id = view.id or "todo-list"
            else:
                self._last_list_id = "todo-list"
                self._current_view().focus()
        finally:
            self._refreshing = False
        self._style_selection()
        self.sub_title = (
            f"filter: {self.filter_text}" if self.filter_text else "interactive board"
        )

    def _current_view(self) -> ListView:
        if (
            isinstance(self.focused, ListView)
            and self.focused.id in self.STATE_VIEWS.values()
        ):
            return self.focused
        return self.query_one(f"#{self._last_list_id}", ListView)

    def _selected_task(self) -> Task | None:
        view = self._current_view()
        item = view.highlighted_child
        if isinstance(item, TaskListItem):
            return self.board.active.get(item.task_id)
        self._set_status("No task selected.")
        return None

    async def _mutate(
        self,
        operation: Callable[[Board], OperationResult],
        *,
        focus_task_id: int | None = None,
        focus_state: TaskState | None = None,
        expected_tasks: tuple[TaskExpectation, ...] = (),
    ) -> None:
        try:
            board, result = self.application.mutate(
                operation, expected_tasks=expected_tasks
            )
            self.board = board
        except TaskConflict as exc:
            self.board = exc.board
            await self._refresh_board(focus_task_id=focus_task_id)
            self._set_status(
                f"{format_task_conflict(exc.task_id)} "
                "Board refreshed; review and retry."
            )
            return
        except (click.ClickException, StoreError) as exc:
            self._set_status(f"Error: {exc}")
            return

        actual_focus_state = focus_state
        if focus_task_id is not None and focus_task_id in board.active:
            actual_focus_state = board.active[focus_task_id].state

        self._set_status(" ".join(format_result(result)))
        await self._refresh_board(
            focus_task_id=focus_task_id,
            focus_state=actual_focus_state,
        )

    def action_cursor_down(self) -> None:
        self._current_view().action_cursor_down()

    def action_cursor_up(self) -> None:
        self._current_view().action_cursor_up()

    def action_add_task(self) -> None:
        screen = AddTaskPromptScreen(self.config, self.application, self.palette)
        self.push_screen(
            screen,
            lambda value: self._mutation_prompt_result(screen, value),
        )

    def action_edit_task(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        self._open_task_prompt(task, "text")

    def _open_task_prompt(self, task: Task, field: Literal["text", "tags"]) -> None:
        screen = TaskPromptScreen(
            self.config, self.application, task, field, self.palette
        )
        self.push_screen(
            screen,
            lambda value: self._mutation_prompt_result(screen, value, task.id),
        )

    async def _mutation_prompt_result(
        self,
        screen: MutationPromptScreen,
        value: str | None,
        focus_task_id: int | None = None,
    ) -> None:
        if screen.current_board is not None:
            self.board = screen.current_board
            await self._refresh_board(focus_task_id=focus_task_id)
        if value is not None and screen.outcome is not None:
            self._set_status(" ".join(format_result(screen.outcome)))

    async def action_cycle_priority(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        index = self.PRIORITY_CYCLE.index(task.priority)
        next_priority = self.PRIORITY_CYCLE[(index + 1) % len(self.PRIORITY_CYCLE)]
        await self._mutate(
            lambda board: set_task_priority(board, str(task.id), next_priority),
            focus_task_id=task.id,
            focus_state=task.state,
            expected_tasks=(TaskExpectation.capture(task),),
        )

    def action_set_tags(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        self._open_task_prompt(task, "tags")

    async def action_archive_task(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        await self._mutate(
            lambda board: delete_tasks(board, [str(task.id)]),
            expected_tasks=(TaskExpectation.capture(task),),
        )

    def action_restore_task(self) -> None:
        try:
            board = self.application.read()
        except (click.ClickException, StoreError) as exc:
            self._set_status(f"Error: {exc}")
            return
        self.push_screen(
            ArchiveScreen(self.config, self.application, board, self.palette),
            self._archive_result,
        )

    async def _archive_result(self, result: tuple[Board, int] | None) -> None:
        if result is not None:
            self.board, task_id = result
            self._set_status(f"Restored #{task_id} to TODO.")
            await self._refresh_board(focus_task_id=task_id, focus_state=TaskState.TODO)

    async def action_refresh(self) -> None:
        if self._reload_board():
            await self._refresh_board()
            self._set_status("Board refreshed.")

    async def _restore_prompt_result(self, value: str | None) -> None:
        if value is None or not value.strip():
            return
        raw_task_id = value.strip()
        focus_task_id = int(raw_task_id) if raw_task_id.isdecimal() else None
        await self._mutate(
            lambda board: restore_tasks(self.config.policy, board, [raw_task_id]),
            focus_task_id=focus_task_id,
            focus_state=TaskState.TODO if focus_task_id is not None else None,
        )

    async def action_undo(self) -> None:
        try:
            self.board = self.application.undo()
        except (click.ClickException, StoreError) as exc:
            self._set_status(str(exc))
            return

        self._set_status("Undid last board change.")
        await self._refresh_board()

    def action_search(self) -> None:
        self.push_screen(
            PromptScreen("Search tasks", self.palette, initial=self.filter_text),
            self._search_prompt_result,
        )

    async def _search_prompt_result(self, value: str | None) -> None:
        if value is None:
            return
        self.filter_text = value.strip()
        self._set_status(
            f"Filter: {self.filter_text}" if self.filter_text else "Filter cleared."
        )
        await self._refresh_board()

    async def action_clear_search(self) -> None:
        self.filter_text = ""
        self._set_status("Filter cleared.")
        await self._refresh_board()

    async def _move_selected(self, delta: int) -> None:
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
        await self._mutate(
            lambda board: move_tasks_to_state(
                self.config.policy,
                board,
                [str(task.id)],
                target_state,
            ),
            focus_task_id=task.id,
            focus_state=target_state,
            expected_tasks=(TaskExpectation.capture(task),),
        )

    async def action_move_left(self) -> None:
        await self._move_selected(-1)

    async def action_move_right(self) -> None:
        await self._move_selected(1)

    async def _reprioritize(self, delta: int) -> None:
        task = self._selected_task()
        if task is None:
            return
        await self._mutate(
            lambda board: reorder_task_relative(board, str(task.id), delta),
            focus_task_id=task.id,
            focus_state=task.state,
            expected_tasks=(TaskExpectation.capture(task),),
        )

    async def action_priority_up(self) -> None:
        await self._reprioritize(-1)

    async def action_priority_down(self) -> None:
        await self._reprioritize(1)

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.palette))


def run_tui(
    config: AppConfig,
    *,
    application: BoardApplication | None = None,
    board_name: str = "default",
) -> None:
    """Run the interactive kanbanTUI application."""
    KanbanApp(config, application=application, board_name=board_name).run()
