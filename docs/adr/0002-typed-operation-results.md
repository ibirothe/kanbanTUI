# ADR 0002: Return typed operation results and present them in adapters

- Status: Accepted
- Date: 2026-09-07

## Context

Services returned counters plus preformatted English messages. CLI and TUI could not reliably identify the affected task, distinguish changed operations from accepted no-ops, or separate domain rejection from conflicts and infrastructure failures without interpreting text. This also coupled localization and stream/exit-code behavior to the domain service implementation.

## Decision

Services return ordered `OperationItem` values. Every item has a stable `OperationCode`, a status of `changed`, `unchanged` or `rejected`, an optional task ID and typed parameters required to present or inspect the outcome. Batch aggregates are derived from those items rather than maintained as independent mutable counters.

The application transaction commits only when at least one item is `changed` and the board actually differs from its previous snapshot. Accepted no-ops do not write or replace undo. Rejected items do not prevent accepted items in the same batch from being committed.

English text lives in `operation_messages.py`, outside the services. CLI sends changed and unchanged messages to stdout, rejected messages to stderr, and returns nonzero only for a rejection. TUI uses the same formatter but controls dialog retention and focus from status rather than message text.

Snapshot conflicts use the separate `TaskConflict` exception with code `TASK_CONFLICT` and task ID. Persistence failures remain infrastructure exceptions translated by the terminal adapters. Neither case is inferred from result text.

## Consequences

- Another adapter can consume codes and domain values without parsing English text.
- Mixed batches preserve per-item identity, ordering and partial-success semantics.
- Previously inconsistent already-satisfied commands now consistently succeed as `unchanged` no-ops.
- User-facing English remains compatible except that no-op messages lose the `Error:` prefix and no longer cause a nonzero exit.
- Adding a new operation outcome requires extending the code enum and its adapter presentation.
