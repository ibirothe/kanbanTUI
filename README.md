# kanbanTUI

A terminal-based personal Kanban board for managing TODO, in-progress, completed, and deleted tasks.

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
kanban-tui promote 1
kanban-tui regress 1
kanban-tui delete 1
kanban-tui history
kanban-tui restore 1
```

`add` treats all words after the command as one task description. `edit` preserves task ID, state, and creation time. `history` lists deleted tasks, and `restore` returns deleted tasks to TODO while respecting configured capacity limits.

Commands that require operands use standard Click usage errors when operands are missing. Rejected operations return a non-zero exit status. For multi-ID commands, the command returns non-zero if any requested operation fails.

Unique command prefixes are accepted when unambiguous.

## Output formats

```bash
kanban-tui show --format table
kanban-tui show --format plain
kanban-tui show --format json
```

- `table` is the default Rich terminal view.
- `plain` emits deterministic tab-separated text without color codes.
- `json` emits structured task data with timezone-aware ISO 8601 timestamps.

All formats use the same deterministic ordering and completed-task display limit. Rich output honors `NO_COLOR`.

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
