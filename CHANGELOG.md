# Changelog

## 0.5.0 - 2026-09-04

First Pascal-maintained kanbanTUI baseline after the repository modernization.

### Added

- `src/kanban_tui/` package layout with separated CLI, config, models, services, storage, and rendering modules.
- Typed `Task`, `TaskState`, `Limits`, `AppConfig`, and `Board` domain models.
- `edit`, `history`, and `restore` commands.
- Global `--config PATH` support for multiple independent boards.
- `show --format table|plain|json` output modes.
- Local Ruff, mypy, and pytest-cov tooling.
- Timezone-aware ISO 8601 timestamps.
- Stale datastore lock recovery and lock-free read-only display.
- `kanban-tui` command, `KANBAN_TUI_HOME`, and `.kanban-tui.yaml` configuration identity.

### Changed

- Maintainer metadata identifies Pascal Rothe <ibirothe@gmail.com>.
- Python support is Python 3.11+.
- Normal `add` input treats unquoted words as one task description.
- Rejected task operations return non-zero exit codes.
- Relative datastore paths resolve against their selected configuration file.
- Completed tasks are ordered by most recent modification time.
- Tests are isolated under `tests/` and do not depend on user state.

### Fixed

- Startup version lookup.
- Regression command argument and invalid-ID handling.
- WIP and TODO capacity invariant violations.
- Task-ID reuse across deleted history.
- Non-atomic datastore writes and stale writer locks.
- Missing/invalid configuration and datastore validation.
