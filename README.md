# kanbanTUI

A terminal-based personal Kanban board for managing TODO, in-progress, completed, and archived tasks.

## Requirements

Python 3.11 or newer.

## Installation

Install from a checkout:

```bash
python -m pip install .
```

For local development:

```bash
python -m pip install -e ".[dev]"
```

## Configuration

Create the default configuration:

```bash
kanban-tui configure
```

The default configuration is `~/.kanban-tui.yaml`. An example is available at [`examples/kanban-tui.yaml`](examples/kanban-tui.yaml).

Supported settings:

- `data_path`: datastore path. Relative paths are resolved relative to the configuration file directory.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum completed tasks displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: display the board after successful mutations; default `false`.

Configuration selection precedence:

1. explicit root option `--config PATH`;
2. `$KANBAN_TUI_HOME/.kanban-tui.yaml` when `KANBAN_TUI_HOME` is set;
3. `~/.kanban-tui.yaml`.

Use `--config` for independent boards:

```bash
kanban-tui --config ~/boards/work.yaml configure
kanban-tui --config ~/boards/work.yaml add Fix production bug
kanban-tui --config ~/boards/personal.yaml configure
kanban-tui --config ~/boards/personal.yaml add Buy groceries
kanban-tui --config ~/boards/work.yaml show
```

`configure` honors the selected path and creates a datastore with the same basename and a `.dat` suffix. Relative `data_path` values are always resolved against the selected configuration file.

## Usage

```bash
kanban-tui show
kanban-tui add Fix login bug
kanban-tui edit 1 Fix login timeout handling
kanban-tui start 1
kanban-tui done 1
kanban-tui todo 1
kanban-tui move 1 top
kanban-tui move 3 before 1
kanban-tui delete 1
kanban-tui history
kanban-tui restore 1
```

`start`, `done`, and `todo` move tasks directly to the requested state. The older `promote` and `regress` commands remain available as one-step transition shortcuts.

TODO and IN PROGRESS tasks have persistent manual ordering. Use `move <id> top`, `move <id> bottom`, `move <id> before <other-id>`, or `move <id> after <other-id>` to reprioritize a task within its current column. Completed tasks remain ordered by completion time.

`add` treats all words after the command as one task description. `edit` preserves task ID, state, creation time, and manual position. `history` lists archived tasks, and `restore` returns archived tasks to TODO while respecting configured capacity limits.

Successful mutations use short task-centric messages such as `Added #12`, `Started #12`, and `Completed #12`. Rejected operations begin with `Error:` and return a non-zero exit status. For multi-ID commands, the command returns non-zero if any requested operation fails.

Unique command prefixes are accepted only when unambiguous.

## Board view and filters

The table view renders one task per row, wraps long descriptions, shows TODO/WIP capacity, marks full columns, and provides actionable empty states.

`show` supports state and text filtering without changing the board:

```bash
kanban-tui show --state todo
kanban-tui show --state inprogress
kanban-tui show --search login
kanban-tui show --state todo --search login
```

Search is case-insensitive. Manual task order is the default, but temporary sort views are available:

```bash
kanban-tui show --sort id
kanban-tui show --sort created
kanban-tui show --sort modified
```

Sorting changes only the current view; it does not rewrite persisted manual ordering.

## Output formats

```bash
kanban-tui show --format table
kanban-tui show --format plain
kanban-tui show --format json
```

- `table` is the default Rich terminal view.
- `plain` emits deterministic tab-separated text without color codes.
- `json` emits structured task data with timezone-aware ISO 8601 timestamps.

Filters and sorting apply consistently to all three formats. All formats use the configured completed-task display limit. Rich output honors `NO_COLOR`.

## Project structure

```text
src/kanban_tui/
  __init__.py
  cli.py
  config.py
  models.py
  rendering.py
  services.py
  storage.py

tests/
  conftest.py
  test_*.py
```

See [`docs/architecture.md`](docs/architecture.md) for module responsibilities and persistence behavior. See [`CHANGELOG.md`](CHANGELOG.md) for version history.

## Development

Run tests:

```bash
pytest
```

Run coverage:

```bash
pytest --cov=kanban_tui --cov-report=term-missing
```

Lint and verify formatting:

```bash
ruff check .
ruff format --check .
```

Apply formatting:

```bash
ruff format .
```

Run static type checking:

```bash
mypy src/kanban_tui
```

## Maintainer

Pascal Rothe  
GitHub: `ibirothe`  
Email: `ibirothe@gmail.com`

## License

MIT. See [`LICENSE`](LICENSE).

## Support

GitHub Issues: https://github.com/ibirothe/kanbanTUI/issues
