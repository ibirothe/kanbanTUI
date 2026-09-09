# ADR 0003: Own persistence ports in the application layer

- Status: Accepted
- Date: 2026-09-07

## Context

The shared transaction function imported concrete global YAML storage functions and required `AppConfig`. CLI and TUI also read storage directly, while import merge/replace orchestration lived in a Click command closure. Tests had to monkeypatch module globals, and another persistence adapter would have needed to replace globals or reproduce locking, conflict and undo behavior.

## Decision

`application.py` defines two structural protocols:

- `BoardStore.read()` performs a detached, side-effect-free read without a writer transaction.
- `BoardStore.transaction()` returns a context holding the writer guarantee. Its `BoardTransaction` loads one detached working board, atomically commits it with the prior snapshot, and performs undo.

`BoardApplication` owns read, mutation, import and undo use cases. Mutation keeps load, task-expectation checks, operation execution and commit inside one transaction. It commits only when a typed result reports a change and the board actually differs. Exceptions and conflicts leave persistence untouched; context exit releases the writer guarantee.

`YamlBoardStore` is the production adapter. It maps the file lock, codec and atomic writer to the protocols and translates adapter errors into application-level `StoreError`. CLI and TUI construct and inject one application object at their entry points.

Pure merge/replace composition moved to `imports.py`. The JSON adapter decodes and encodes files; `BoardApplication.import_board()` validates policy, merges or replaces, reports remapped IDs and commits through the same transaction as other mutations.

## Consequences

- Application code imports no YAML, Click, paths, locks or concrete store.
- YAML and in-memory implementations run through the same behavioral contract tests.
- Read-only paths cannot accidentally acquire the exclusive writer transaction.
- Partial batches commit exactly once and create one detached undo snapshot.
- Failed operations, exceptions, no-ops and conflicts do not commit; writer ownership is released on every path.
- Adding persistence backends requires implementing two small protocols, not changing services or terminal adapters.
- The in-memory implementation is a test double, not a second production database or plugin framework.
