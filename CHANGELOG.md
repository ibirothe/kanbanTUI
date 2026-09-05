# Changelog

## 0.5.0

Current maintained kanbanTUI baseline.

### Architecture

- moved production code into `src/kanban_tui/` with separated CLI, configuration, models, services, storage, rendering, transfer, and TUI modules;
- moved tests into `tests/` with isolated temporary board state;
- centralized project/tool configuration in `pyproject.toml`;
- added typed task/config/board domain models while retaining backward-compatible valid YAML reads;
- added atomic datastore/config replacement.

### UX

- added the full-screen Textual TUI with keyboard navigation, task editing, state movement, ordering, metadata, search, archive/restore, and undo;
- added persistent manual ordering for TODO and IN PROGRESS tasks;
- added optional task priority (`low`, `normal`, `high`, `urgent`) and normalized tags, exposed consistently in CLI/TUI/rendering/filtering;
- added explicit `start`, `done`, and `todo` state commands;
- added improved capacity-aware table rendering, search/state/metadata filters, and deterministic view sorting;
- added named boards with `--board`, `board create`, and `board list`;
- added `config path`, `config show`, and validated `config set` commands;
- standardized concise task-centric command feedback;
- added persistent per-board color themes shared by Rich and Textual;
- added built-in `arch`, `nord`, `gruvbox`, `dracula`, and `mono` palettes with `arch` as the backward-compatible default;
- added `theme list`, `theme current`, and `theme set NAME`, plus `config set theme NAME`;
- added custom user themes from XDG/portable YAML files with built-in inheritance and semantic color-role overrides;
- made theme choices dynamically discoverable so newly created custom YAML files are immediately available to Click validation and shell completion;
- reject malformed custom theme YAML, invalid `#RRGGBB` colors, unknown roles/keys, invalid names, non-built-in parents, and built-in-name collisions with actionable CLI errors;
- themed TODO/WIP/DONE states, priority badges, tags, TUI chrome, dialogs and selection surfaces while keeping plain/JSON output color-free and honoring `NO_COLOR`.

### Data safety and portability

- task IDs remain unique across active and archived history;
- TODO/WIP invariants are enforced on all relevant transitions;
- timestamps are timezone-aware ISO 8601 on new writes;
- optional metadata is stored in a backward-compatible sixth task-record field;
- complete JSON transfers preserve metadata and completion time;
- added complete versioned JSON board export/import with merge and replace modes;
- added one-level atomic undo for successful semantic mutations;
- archived history can be inspected and restored with metadata preserved.

### Stabilization

- made datastore reads side-effect free: missing boards remain absent until a mutation actually succeeds;
- added explicit `completed_at` semantics so DONE ordering reflects completion time rather than later text or metadata edits;
- retained backward compatibility by deriving `completed_at` from `modified_at` for legacy DONE records;
- changed merge import to deterministically remap imported IDs that collide with existing active or archived history;
- made already-satisfied reorder requests and imports with no effective changes true semantic no-ops;
- semantic no-ops no longer update timestamps, write the datastore, or consume the single undo snapshot.

### Production hardening

- replaced PID/age stale-lock heuristics with OS-backed advisory writer locks using `fcntl.flock` on POSIX and `msvcrt.locking` on Windows;
- tightened task and board invariants: non-empty text, positive integer IDs/positions, consistent active/deleted buckets, matching mapping keys and task IDs, and valid completion-state semantics;
- stopped fractional numeric values from being silently truncated in persisted positions and configuration limits;
- validate imported task text against the selected board's configured task-name limit before mutation;
- reject configurations whose datastore path resolves to the configuration file itself;
- prevent export, including `--force`, from targeting the selected config, datastore, or lock file;
- route invalid TUI restore IDs through shared service validation rather than allowing callback conversion failures;
- reject non-positive task IDs consistently as invalid user input;
- reserve `default` as the implicit default board name to avoid named-board ambiguity;
- added focused regression coverage for cross-process lock lifecycle, schema constraints, import limits, internal path protection, TUI restore input, task-ID validation, and reserved board naming.

### Arch Linux integration

- made Arch Linux the primary documented developer/desktop target;
- changed end-user installation guidance to Arch's `python-pipx` package plus direct Git installation, avoiding system-site `pip install` usage;
- adopted XDG config/data defaults: `~/.config/kanban-tui/` and `~/.local/share/kanban-tui/`, honoring `XDG_CONFIG_HOME` and `XDG_DATA_HOME`;
- retained safe discovery of existing `~/.kanban-tui.yaml` and legacy `~/boards/` configurations when no XDG config exists;
- retained `KANBAN_TUI_HOME` as an explicit portable/test root override;
- store custom theme YAML files below the same XDG/portable config root under `themes/`;
- added Bash, Zsh and Fish completion documentation using Click's native completion protocol;
- added dynamic completion for existing `--board` names and discovered theme names;
- removed the `click-default-group` runtime dependency and implemented no-argument board display directly with `click.Group`;
- added Python 3.14 project metadata for the current Arch Python generation;
- added regression coverage for XDG paths, legacy discovery, native shell completion and no-argument root behavior.

### Maintainer

Pascal Rothe <ibirothe@gmail.com>
