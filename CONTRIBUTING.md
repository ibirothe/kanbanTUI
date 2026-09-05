# Contributing

Bug fixes, documentation improvements and focused features are welcome. Open pull
requests against `develop`, the default development branch. Check existing issues
and pull requests before starting overlapping work.

## Development setup

Use Python 3.11 or newer in a project virtual environment:

```bash
git clone https://github.com/ibirothe/kanbanTUI.git
cd kanbanTUI
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Arch Linux is the primary target. Keep application dependencies out of the system
Python environment; see the [installation guide](README.md#arch-linux-installation)
for the end-user pipx flow.

## Local checks

Run the shared check command before submitting a change:

```bash
python scripts/check.py
```

It runs the following checks, stopping at the first failure. All commands use the
active Python environment, with tool configuration in `pyproject.toml`:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src/kanban_tui
```

For coverage or a focused iteration:

```bash
python -m pytest --cov=kanban_tui --cov-report=term-missing
python -m pytest tests/test_storage.py -q
```

Use `python -m ruff format .` to apply formatting. Include only formatting changes
relevant to your contribution.

## Where changes belong

| Concern | Location |
| --- | --- |
| Task invariants and persistence schema | `src/kanban_tui/models.py` |
| Mutations, ordering and capacity rules | `src/kanban_tui/services.py` |
| Datastore locking, atomic writes and undo | `src/kanban_tui/storage.py` |
| Paths, named boards and config validation | `src/kanban_tui/config.py` |
| CLI commands and terminal interaction | `src/kanban_tui/cli.py`, `src/kanban_tui/tui.py` |
| Presentation and palettes | `src/kanban_tui/rendering.py`, `src/kanban_tui/themes.py` |
| Import and export | `src/kanban_tui/transfer.py` |
| Behavioral regression tests | `tests/` |

Read the [architecture](docs/architecture.md) before changing persistence or
workflow semantics. CLI and TUI should share domain behavior through services.
Preserve legacy valid data, side-effect-free reads, atomic writes and semantic
no-op handling for undo.

Tests isolate application state with `KANBAN_TUI_HOME` and temporary directories
in `tests/conftest.py`. Reuse these fixtures for config/datastore tests. Add a
regression test for a behavior fix; avoid assertions that only mirror source code.

For manual checks, use a disposable directory rather than your personal board:

```bash
KANBAN_TUI_HOME="$(mktemp -d)" kanban-tui tui
```

## Preparing a pull request

- Explain the problem, the resulting behavior and how you verified it.
- Keep each contribution focused and include relevant regression tests.
- Update the relevant [user reference](docs/README.md) when commands or behavior change.
- Add a concise entry under `Unreleased` in `CHANGELOG.md`; leave `VERSION` changes
  to release preparation.
- Report checks that could not run, including the reason.

Bug reports should include the kanbanTUI version, Python version, operating system,
command or TUI steps, expected and actual behavior, and a minimal reproduction.
Remove personal task contents and sensitive paths from examples.
