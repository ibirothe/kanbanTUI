# Changelog

## 0.5.0 - 2026-09-04

First Pascal-maintained release baseline after the repository modernization.

### Added

- `src/kanban_tui/` package layout with separated CLI, config, models, services, storage, and rendering modules.
- Typed `Task`, `TaskState`, `Limits`, `AppConfig`, and `Board` domain models.
- `edit`, `history`, and `restore` commands.
- Global `--config PATH` support for multiple independent boards.
- `show --format table|plain|json` output modes.
- Local Ruff, mypy, pytest-cov, and modern `pyproject.toml` tooling.
- Timezone-aware ISO 8601 timestamps for new datastore writes.
- Stale datastore lock recovery and read-only lock-free display.

### Changed

- Maintainer metadata now identifies Pascal Rothe <ibirothe@gmail.com>.
- Python support is Python 3.11+.
- Normal `add` input treats unquoted words as one task description.
- Rejected task operations return non-zero exit codes.
- Relative datastore paths resolve relative to their selected config file.
- DONE tasks are ordered by most recent completion/modification time.
- Tests are isolated under `tests/` and no longer depend on real user state.

### Fixed

- CLI startup/version lookup failures around `importlib.metadata`.
- Broken `regress` command argument binding and invalid-ID handling.
- WIP and TODO capacity invariant violations during transitions.
- Task-ID reuse across deleted history.
- Non-atomic/unlocked datastore writes and stale writer locks.
- Missing/invalid configuration and datastore validation behavior.

### Distribution note

This release baseline is intended for GitHub/source-checkout use. The inherited PyPI distribution name `clikan` is owned by the upstream project, while `kanban-tui` is already used by another active project. PyPI publication is therefore deferred until KT-034 selects a unique distribution name.
