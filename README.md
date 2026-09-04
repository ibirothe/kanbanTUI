# kanbanTUI / clikan

A small terminal-based personal Kanban board. The installed command remains `clikan` for compatibility.

![icon](docs/icon-256x256.png)

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

Create a default configuration with:

```bash
clikan configure
```

Or create `~/.clikan.yaml` manually. See [`examples/clikan.yaml`](examples/clikan.yaml).

Supported settings:

- `clikan_data`: datastore path. Relative paths are resolved relative to the configuration file directory.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum done items displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: display the board after successful mutations; default `false`.

## Usage

```bash
clikan show
clikan add Fix login bug
clikan edit 1 Fix login timeout handling
clikan promote 1
clikan regress 1
clikan delete 1
clikan history
clikan restore 1
```

`add` treats all words after the command as one task description, so quoting normal task text is optional. `edit` uses the same text normalization and length rules while preserving the task ID, state, and creation timestamp. Deleted tasks cannot be edited directly.

`history` shows the deleted-task archive. `restore` moves deleted tasks back to TODO with their original IDs and creation timestamps; restoration respects the configured TODO capacity.

Commands that require task IDs or task text report a standard Click usage error when their operand is missing. Rejected task operations such as invalid IDs, unknown IDs, capacity-limit failures, or invalid task text return a non-zero exit code. For commands that accept multiple IDs, the command returns non-zero if any requested operation fails, even when other items succeed.

Unique command prefixes are accepted. `s`, `a`, `p`, and `d` remain the short forms for `show`, `add`, `promote`, and `delete` respectively.

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

See [`docs/architecture.md`](docs/architecture.md) for module responsibilities, domain models, task transitions, persistence format, and locking behavior.

## Development

This is a solo-maintained project. Changes may be committed directly to the active development branch.

Run the test suite:

```bash
pytest
```

Run tests with coverage:

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

Build wheel and source distributions:

```bash
python -m build
```

Project metadata, dependencies, tooling, Python compatibility, and build configuration live in `pyproject.toml`.

## Maintainer

Pascal Rothe  
GitHub: `ibirothe`  
Email: `ibirothe@gmail.com`

## License

MIT. See [`LICENSE`](LICENSE). The license file retains the original copyright notice required by the original MIT grant.

## Support

GitHub Issues: https://github.com/ibirothe/kanbanTUI/issues
