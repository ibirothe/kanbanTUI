# Changelog

## 0.5.0

Current maintained kanbanTUI baseline.

### Architecture

- moved production code into `src/kanban_tui/` with separated CLI, configuration, models, services, storage, rendering, transfer, and TUI modules;
- moved tests into `tests/` with isolated temporary board state;
- centralized project/tool configuration in `pyproject.toml`;
- added typed task/config/board domain models while retaining backward-compatible YAML reads;
- added atomic datastore/config replacement and stale writer-lock recovery.

### UX

- added the full-screen Textual TUI with keyboard navigation, task editing, state movement, ordering, search, archive/restore, and undo;
- added persistent manual ordering for TODO and IN PROGRESS tasks;
- added explicit `start`, `done`, and `todo` state commands;
- added improved capacity-aware table rendering, search/state filters, and deterministic view sorting;
- added named boards with `--board`, `board create`, and `board list`;
- added `config path`, `config show`, and validated `config set` commands;
- standardized concise task-centric command feedback.

### Data safety and portability

- task IDs remain unique across active and archived history;
- TODO/WIP invariants are enforced on all relevant transitions;
- timestamps are timezone-aware ISO 8601 on new writes;
- added complete versioned JSON board export/import with merge and replace modes;
- added one-level atomic undo for successful mutations, including imports;
- deleted history can be inspected and restored.

### Maintainer

Pascal Rothe <ibirothe@gmail.com>
