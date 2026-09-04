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

- `clikan_data`: datastore path.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum done items displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: display the board after successful mutations; default `false`.

## Usage

```bash
clikan show
clikan add "Task text"
clikan promote 1
clikan regress 1
clikan delete 1
```

Unique command prefixes are accepted, so `s`, `a`, `p`, and `d` work for `show`, `add`, `promote`, and `delete` respectively.

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
