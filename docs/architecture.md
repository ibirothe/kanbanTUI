# Architecture

## Target environment

kanbanTUI is a terminal-first Python application with Arch Linux as the primary developer desktop target. End-user installation is designed around the Arch `python-pipx` package and a Git source install, keeping application dependencies isolated from Arch's externally managed system Python.

The runtime dependency set is deliberately small: Click, PyYAML, Rich, and Textual. The root CLI is implemented directly with `click.Group`; no default-group extension is required.

## Package layout

Production code lives under `src/kanban_tui/`:

- `cli.py` — Click command surface, native prefix/board/theme completion, board/config selection, theme selection, transfer and undo wiring.
- `config.py` — XDG/portable/legacy path resolution, named boards, presentation-independent YAML validation and atomic config writes.
- `resources.py` — shared canonical config/datastore/lock paths and collision checks.
- `models.py` — typed domain model and business invariants.
- `policy.py` — presentation-independent TODO/WIP capacity and task-text policy with pure domain errors.
- `results.py` — typed per-item operation codes, parameters and statuses.
- `services.py` — task mutations returning typed results and depending only on the domain model, policy and result contract.
- `imports.py` — pure merge/replace import composition and deterministic ID remapping.
- `application.py` — application-owned store/transaction protocols plus shared read, mutation, import and undo use cases.
- `operation_messages.py` — English terminal presentation for operation results.
- `settings.py` — compatible `AppConfig` composition of infrastructure, policy and presentation settings.
- `atomic.py` — shared same-directory temporary-file lifecycle and cleanup.
- `transactions.py` — temporary config-based compatibility wrappers around `BoardApplication`.
- `storage.py` — YAML implementation of the application ports plus side-effect-free reads, cross-process writer locking, atomic writes and undo.
- `codec.py` — strict YAML parsing, datastore schema versioning and legacy record migration.
- `themes.py` — semantic built-in palettes plus XDG/portable custom-theme discovery and YAML validation.
- `transfer.py` — complete JSON export/import, validation and merge ID remapping.
- `rendering.py` — themed Rich table/history rendering plus plain/JSON views, filters and sorting.
- `tui.py` — Textual full-screen UI using the same services, persistence layer and semantic theme palette as the CLI.

Tests live under `tests/`. Focused suites cover models, services, storage, transfer, CLI, configuration, multi-board behavior, metadata, undo, built-in/custom themes, TUI behavior, Arch/XDG integration and production-readiness invariants.

## CLI behavior

The root command is a normal `click.Group` with `invoke_without_command=True`. Running `kanban-tui` without a subcommand calls the normal board display path, while explicit commands use the same group and unique-prefix resolution.

Click's built-in shell completion protocol is used for Bash, Zsh and Fish. Choice/path parameters inherit Click completion, `--board` adds dynamic completion from existing named board configs, and theme arguments validate through a lazy Click parameter type. Filesystem discovery is deferred to invocation/completion, so invalid filenames cannot prevent basic CLI help or version output. Completion scripts are generated from the installed `kanban-tui` entry point and require no additional runtime package.

## Runtime flow

For a mutation:

1. The CLI or TUI resolves the selected configuration and constructs one `BoardApplication` with `YamlBoardStore` at its entry point.
2. `config.py` validates it into the compatible `AppConfig` composition. `AppConfig.policy` maps only TODO/WIP and task-text limits into the immutable `BoardPolicy`; paths and presentation settings are not passed to services.
3. `application.py` owns the mutation use case and opens the `BoardStore.transaction()` port. The YAML adapter acquires the datastore writer lock before exposing its transaction context.
4. `BoardTransaction.load()` returns a detached validated `Board`. The YAML adapter decodes it through `codec.py`; a missing datastore is represented as an empty board without creating files or printing output.
   Snapshot-dependent TUI commands then compare their task expectations against this current board while still holding the writer lock. A conflict returns the current board through `TaskConflict` before the operation or any write occurs.
5. The transaction captures a detached pre-mutation board; `services.py` applies the operation and returns an `OperationResult` containing ordered per-item outcomes.
6. Only outcomes with status `changed` can write the datastore. `unchanged` outcomes are accepted no-ops; `rejected` outcomes identify domain validation failures. The transaction still compares complete board state before committing.
7. `BoardTransaction.commit()` stores the board and captured previous snapshot in the same atomic replacement, without rereading the datastore.

Task commands, imports and TUI mutations share this application object and transaction policy. `BoardApplication.read()` uses the separate `BoardStore.read()` path and never opens a writer transaction. `BoardApplication.undo()` runs through the same writer transaction contract. Presentation, exit codes and selection remain in their adapters.

Each `OperationItem` carries a stable `OperationCode`, status, optional task ID and typed domain parameters such as state, limit, count, target, reference ID, priority or tags. Services do not produce English or terminal-formatted messages. CLI and TUI format the same outcomes through `operation_messages.py`. The CLI writes changed/unchanged feedback to stdout, rejected feedback to stderr and exits nonzero only when at least one item is rejected. A mixed batch retains ordered item attribution and still commits all accepted changes in one undoable transaction.

`TaskConflict` is a separate typed application exception carrying `TASK_CONFLICT` and the affected task ID. Infrastructure failures cross the persistence port as `StoreError` and are translated by terminal adapters. Adapters therefore never infer domain rejection, conflict or infrastructure failure from text or an `Error:` prefix. The result decision is recorded in [ADR 0002](adr/0002-typed-operation-results.md).

The persistence contract and dependency direction are recorded in [ADR 0003](adr/0003-persistence-ports.md). `BoardStore` and `BoardTransaction` are deliberately small `typing.Protocol` ports owned by the application. `YamlBoardStore` implements them; the contract suite uses an in-memory implementation to verify substitution without filesystem access or monkeypatching concrete storage globals. The compatibility functions in `transactions.py` may be removed after downstream callers migrate to explicit `BoardApplication` injection.

Read-only operations (`show`, `history`, export and normal TUI reads) do not acquire the exclusive writer lock.

## Color themes

`themes.py` owns the semantic visual palette shared by Rich and Textual. A theme supplies colors for background/surface/text, accent/muted content, TODO/WIP/DONE states and all four priority levels.

Nord is the sole built-in theme and the default. `AppConfig.theme` stores only the normalized theme name. Existing configuration files without a `theme` field remain valid and resolve to `nord`.

User-defined themes are discovered from:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/themes/<name>.yaml
```

When `KANBAN_TUI_HOME` is set, discovery switches to:

```text
$KANBAN_TUI_HOME/themes/<name>.yaml
```

The filename stem is the theme name and must be a lowercase slug of at most 32 characters. Built-in names are reserved and cannot be shadowed by a user file.

Custom YAML has three supported top-level fields: optional `description`, optional `extends`, and optional `colors`. `extends` defaults to `nord` and may reference the Nord built-in theme only. This deliberately prevents custom-to-custom inheritance cycles. `colors` may override any subset of the semantic roles; omitted roles are inherited from the built-in parent. Supplied colors are restricted to explicit `#RRGGBB` values so Rich and Textual receive the same deterministic color representation. The `selection` and `selection_text` roles specifically control the active TUI row.

Theme loading is strict: invalid YAML, unsupported top-level keys, unknown color roles, invalid colors, invalid filenames, invalid parents, and built-in-name collisions raise an actionable `ThemeError`. The error type is both a validation error and a Click exception, so explicit theme commands and styled adapters produce normal CLI errors rather than tracebacks.

Base config validation normalizes and validates the selected theme name without resolving its palette or reading the custom-theme directory. This keeps datastore operations, export, config inspection, and plain/JSON output independent from presentation files. Explicit theme selection still resolves the candidate before writing it. Rich table/history rendering and TUI startup also resolve strictly because they require a palette; an unavailable selected custom theme therefore blocks only those styled entry points. Repaint is styled output and follows the same strict policy.

The theme parameter validates through `get_theme()` at command invocation and calls `theme_names()` for completion. It does not pass an eagerly materialized sequence to `click.Choice`, keeping selection and completion synchronized with themes created after CLI import.

The selected theme remains per board/config. `theme list`, `theme current`, `theme set`, and `config set theme` all operate on the currently selected default, named or explicit config; custom theme definitions themselves are user-global within the active XDG/portable root.

Rich and Textual consume the same immutable `Theme` value. A TUI resolves it once during application construction and injects that instance into prompts, help and the archive list; later removal or corruption of the source file cannot invalidate the running session:

- Rich column headers use TODO/WIP/DONE colors;
- task priorities use priority-level colors;
- tags use the accent color;
- Textual uses the same palette for screen/surface colors, header/footer, column borders/titles, dialog chrome, selection surfaces and task metadata.

Plain and JSON formats contain no visual styling. Rich honors `NO_COLOR`, which disables ANSI color without changing the selected persistent theme.

## Domain invariants

The domain boundary consists of `models.py`, `policy.py`, `results.py` and `services.py`. These modules do not import Click, PyYAML, Rich, Textual, themes, filesystem paths or application configuration. `models.py` enforces intrinsic validity; `BoardPolicy` supplies configured business limits; services receive that policy directly and return the application result contract. The accepted dependency direction and follow-up boundaries are recorded in [ADR 0001](adr/0001-domain-boundaries.md).

A `Task` has a positive integer ID, a supported state, non-empty text, timezone-aware creation/modification timestamps, a positive manual position, optional priority/tags, and an optional completion timestamp.

`completed_at` is valid for DONE tasks and may be retained in archived history. TODO and IN PROGRESS tasks cannot carry a completion timestamp.

`Board` requires positive integer mapping keys, matching `Task.id` values, valid active/deleted bucket states, and no ID overlap between active and archived collections. New task IDs are allocated above complete active and archived history and are never reused.

## Ordering and completion time

TODO and IN PROGRESS use persistent numeric `position` ordering. Reordering normalizes positions to consecutive values. Already-satisfied reorder requests are semantic no-ops and therefore do not alter timestamps, persistence or undo history.

DONE is ordered by `completed_at` descending, with descending task ID as the deterministic tie-breaker. Entering DONE sets the timestamp; leaving DONE clears it; re-entering DONE creates a new completion time. Later text, priority or tag edits update `modified_at` without changing completion order.

Legacy DONE records without `completed_at` use their existing `modified_at` as the migration fallback and persist an explicit completion timestamp on their next write.

Current timestamps retain their available ISO 8601 microsecond precision across datastore, JSON export/import, display JSON and undo snapshots. Historical timestamps that contain only seconds remain valid and are emitted without invented fractional values. Time-dependent service operations accept an optional clock callable for deterministic integration and testing.

## XDG configuration and board selection

Fresh Linux installs use:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/config.yaml
${XDG_DATA_HOME:-~/.local/share}/kanban-tui/board.dat
```

Fresh named boards use:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/boards/<name>.yaml
${XDG_DATA_HOME:-~/.local/share}/kanban-tui/boards/<name>.dat
```

Custom themes use the matching config root:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/themes/<name>.yaml
```

Selection semantics are:

1. `--config PATH` selects an explicit file.
2. `--board NAME` selects a named-board config.
3. `KANBAN_TUI_HOME`, when set, switches to a portable single-root layout for config, data, named boards and custom themes.
4. Otherwise the XDG config path is used.
5. If no XDG config exists, an existing legacy `~/.kanban-tui.yaml` is discovered. Legacy named boards below `~/boards/` remain discoverable as well.

This fallback is read-path compatibility rather than the layout for new installs: fresh `configure` and `board create` operations use XDG paths unless `KANBAN_TUI_HOME` or an explicit config path is selected.

`--config` and `--board` are mutually exclusive. Named boards are lowercase slugs; `default` is reserved for the implicit default board.

`data_path` is expanded and resolved deterministically. Relative paths are relative to the configuration file, never to the current shell directory. `resources.py` resolves the config, datastore and sibling lock paths, including symlink aliases, and rejects pairwise collisions. Config validation and export protection use this same resolver; storage uses it to derive the actual lock path and reject datastore/lock aliases.

All config writers validate the candidate before atomic replacement. When an existing config has readable resource paths, writers also check that previous layout, so changing `data_path` or running `configure` cannot replace an active lock inode. Invalid YAML and invalid selected themes can still be repaired when no colliding previous layout is known; filesystem read errors remain errors. These checks protect the selected board's known paths, not arbitrary external changes to symlinks or other boards' configurations.

Limits are strict non-negative integers (digit strings remain accepted for existing configs). Fractional numeric values are rejected rather than truncated. TODO/WIP may be configured as unlimited through the config command layer.

Config edits parse the current mapping, apply the edit and validate the full candidate before writing, allowing an invalid selected theme to be repaired.

Config, datastore and export writers share `atomic_text_writer`: register a sibling temporary file immediately, serialize, flush, `fsync` and `os.replace()`, with best-effort cleanup that preserves the primary error. Each caller provides contextual error messages. Text readers also translate invalid UTF-8 into actionable errors.

## Persistence and locking

Datastore reads are side-effect free. A missing datastore returns `Board()` and remains absent until a mutation succeeds.

Writers coordinate through a sibling `<datastore>.lock` file using OS-managed advisory locks:

- POSIX: `fcntl.flock(..., LOCK_EX | LOCK_NB)`;
- Windows: `msvcrt.locking(..., LK_NBLCK, 1)`.

The lock file may remain on disk as a harmless coordination file; ownership is held by the operating-system lock associated with the open file descriptor. Closing the descriptor or process termination releases the lock.

Datastore writes use a temporary file in the datastore directory, flush and `fsync`, then `os.replace()` the destination. Readers therefore observe a complete old or complete new file, not a partially written board.

## Datastore schema

The datastore envelope uses integer `schema_version: 1`, plus `data`, `deleted` and an optional `_undo` snapshot. Undo snapshots use the same versioned board envelope without nested undo history. The current YAML task record is a compact list: state, text, modified time, creation time and manual position, followed by an optional sixth mapping carrying priority, tags and/or completion time.

`codec.py` owns this representation; the `Task` and `Board` domain models contain only domain state and invariants. The YAML loader rejects duplicate keys at every mapping level before dictionaries are constructed. Current envelopes, task metadata and records use explicit field allowlists. Unknown versions or fields are rejected rather than silently discarded.

Unversioned legacy envelopes and their known four-, five- and six-field records remain readable. Legacy timestamps are accepted and normalized to timezone-aware `datetime` values. Numeric positions and IDs are validated strictly; fractional values are not coerced. Reading legacy data has no write side effect; the next successful mutation writes schema version 1 while preserving all known fields.

## Undo

The datastore may contain a top-level `_undo` mapping. The codec validates it independently and exposes it to the storage layer as an optional previous `Board`.

Each successful semantic mutation writes the new board and immediately previous board snapshot together in one atomic replacement. Failed operations, already-satisfied reorders and imports that result in no effective board change do not replace the undo snapshot.

`undo` restores `_undo` and removes the snapshot, intentionally providing one undo level and no redo chain.

## Transfer format

Complete transfer uses the distinct versioned `kanbanTUI-board` JSON envelope, version 1. It is not the datastore schema. Imports reject non-integer versions and unknown envelope or task fields. Exports include all active and archived tasks independent of view filters or DONE display limits.

Imports are parsed into the validated domain model by the JSON adapter before persistence. `BoardApplication.import_board()` owns merge/replace selection, deterministic remapping, policy validation and transactional commit. The CLI supplies only the decoded board, mode and display source, then translates a pure `PolicyViolation` into its Click error.

`replace` preserves imported IDs. `merge` preserves non-conflicting IDs and deterministically remaps collisions against active or archived history. Export refuses destinations that resolve to the selected board's config file, datastore or datastore lock file.

## TUI safety

`TaskExpectation` captures a detached, immutable representation of the complete task domain state and its active/archive bucket. Comparisons include identity fields, content, metadata, state and ordering, not just `modified_at`; no persistence record encoding leaks into this concurrency check. This is a state comparison, not a durable revision history: replacement with exactly identical task state is semantically indistinguishable.

Edit/tag dialogs retain their drafts on conflict and require explicit Ctrl+R review before a new submission. The subsequent commit checks the refreshed expectation again. Missing or archived tasks remain blocked. Other selected-task shortcuts reject stale state and refresh the board; archive conflicts require reopening the picker. Relative reordering checks the selected task and resolves its current neighbor inside the transaction, so unrelated neighbor changes do not apply an obsolete target. Changes to unrelated task content do not invalidate a task expectation.

Add, edit and tag dialogs submit through a shared transactional prompt. Rejected validation and capacity outcomes are formatted next to the focused input; lock and write failures use the same retry path. The draft remains unchanged and the input is disabled while one submission is applying, preventing duplicate confirmation. Changed and unchanged outcomes dismiss the dialog, while rejected outcomes retain it. Escape dismisses without another transaction and the board refresh restores the prior task selection.

The Textual TUI receives the same `BoardApplication` abstraction used by the CLI. Validation, capacity rules, locking, reads, mutations, undo, metadata normalization and ordering therefore have one implementation without global storage lookups. Palette resolution is a presentation-adapter concern and is not part of these application paths.

Prompt input is routed through shared service validation. A searchable archive picker restores tasks using the shared transaction boundary and keeps capacity errors in the dialog. Explicit Ctrl+R refreshes external changes without writing or acquiring a writer lock; failures retain the last valid display. Selection is restored by task ID after rebuilding columns, with a visible-task fallback. Only highlights in the focused list update selection tracking.

The CLI passes a display-only board identity into the TUI; filtering does not replace that identity. Theme application is presentation-only and never changes board persistence or business-rule behavior.

## Arch installation model

Arch owns the system Python and `pipx` executable:

```text
pacman -> python-pipx + git
```

pipx owns the isolated kanbanTUI virtual environment and user-facing `kanban-tui` executable:

```text
pipx install git+https://github.com/ibirothe/kanbanTUI.git
```

No system-site `pip install` is part of the end-user flow. Local development uses a project `.venv` and editable install.

## Local quality checks

Run `python scripts/check.py` from the repository root after installing `.[dev]`.
See [CONTRIBUTING.md](../CONTRIBUTING.md) for individual commands and test guidance,
and [maintenance.md](maintenance.md) for release checks.

No remote workflow is required by the project model.
