# ADR 0005: Persist bounded import receipts with the board

- Status: Accepted
- Date: 2026-09-08

## Context

A merge import is intentionally additive. If a client loses the response after a
successful commit, blindly retrying the same request can therefore duplicate every
imported task. Process-local request caches do not survive a server restart, while
a separate receipt file cannot be committed atomically with the board by one file
replacement.

The solution must retain the YAML persistence adapter, the existing board lock and
the transport-neutral import use case. Requests without retry semantics must keep
their current behavior.

## Decision

The HTTP adapter accepts an optional `Idempotency-Key` header containing 1 to 128
printable ASCII characters without whitespace. It hashes the key before it crosses
the application boundary and fingerprints the exact request body together with the
selected mode. Clear-text keys are neither persisted nor logged.

`BoardApplication.import_board_once()` uses an optional
`IdempotentBoardTransaction` capability extending the normal board transaction.
Within the existing exclusive writer transaction it either:

1. returns the stored result when key and request digests match;
2. rejects the request when the key digest exists for another request digest; or
3. computes the import and commits the board, undo snapshot and receipt together.

The YAML datastore schema advances to version 2 and may contain a top-level
`_import_receipts` list. Each receipt contains only the two SHA-256 digests, mode,
aggregate outcome and deterministic ID mapping needed to reproduce the original
successful API response. Schema 1 and unversioned documents remain readable. The
next successful write upgrades them to schema 2.

Only successful keyed imports are retained. The list keeps the latest 128 receipts
in insertion order; adding another evicts the oldest. Replays do not refresh that
order. Undo and unrelated mutations preserve receipts. Once a receipt is evicted,
its key is new again.

## Alternatives

- A client import ID inside `kanbanTUI-board` was rejected because it would change
  the transport-neutral export format for one adapter concern.
- A request fingerprint without a client key was rejected because identical
  intentional imports could no longer be distinguished from retries.
- A YAML sidecar was rejected because board and receipt would require two atomic
  replacements and could diverge after a crash.
- SQLite was rejected because the single-file transaction already provides the
  required atomic boundary and a second persistence technology adds no value here.

## Consequences

- A keyed request mutates the board at most once while its receipt is retained,
  including across process restarts and uncertain responses.
- Reusing a key for a different mode or byte-different payload returns HTTP 409.
- The successful replay body is identical to the original successful response.
- Recording a keyed semantic no-op writes a receipt but preserves the current undo
  snapshot.
- Older kanbanTUI versions reject a schema-2 datastore instead of silently dropping
  receipt state.
- The guarantee is intentionally bounded rather than a permanent request history.
