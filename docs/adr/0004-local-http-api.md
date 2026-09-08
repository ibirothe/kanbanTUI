# ADR 0004: Expose board import through an authenticated loopback adapter

- Status: Accepted
- Date: 2026-09-07

## Context

The versioned board transfer codec and `BoardApplication.import_board()` support
transport-independent merge and replace operations. Local automation still needs
an explicit process entry point. Allowing the HTTP layer to select resource paths,
write YAML directly or reproduce import rules would break the application and
persistence boundaries established in ADR 0003.

Loopback alone is not an authorization boundary: browsers and unrelated local
processes can send requests to local ports. A long-running server also differs
from a normal CLI invocation because its resolved configuration remains in memory.

## Decision

`http_api.py` is an inbound adapter injected with one `BoardApplication`, one
`BoardPolicy` and one token. It accepts only the versioned transfer payload and
calls the shared import use case. It binds to numeric IPv4 loopback, requires
Bearer authentication, limits request bodies and returns stable sanitized JSON.
Successful imports expose one aggregate `outcome` rather than leaking internal
application-result counters. Expected transfer-format and policy failures include
bounded actionable details; storage and unexpected failures remain opaque.

The `kanban-tui serve-api` command is the composition root. Its name preserves
`a` as the existing unique prefix for `add`. It resolves the existing `--board`
or `--config` selection once, reads the token only from
`KANBAN_TUI_API_TOKEN`, creates `YamlBoardStore` through the normal application
runtime, and serves in the foreground until interrupted. Port 8765 is the default;
port 0 is allowed for tests. There is no host option.

The startup output identifies the selected board. Server-side failures receive a
generated request ID that is returned to the client and written through an
injectable log sink. Logs contain only that ID, the status and the exception type;
they exclude request targets, credentials, payloads, exception messages and local
paths. Expected client failures remain silent.

The standard-library HTTP server is sufficient for the small serial local surface,
so the distribution gains no web-framework dependency. Configuration changes take
effect after restarting the process. The token is not accepted as a CLI argument
and is never printed or logged.

## Consequences

- CLI, TUI and HTTP imports share policy, locking, atomic commit and undo behavior.
- Requests cannot select a board, configuration file or datastore path.
- The API cannot bind to an external interface through supported configuration.
- Each foreground server instance owns exactly one resolved board and policy.
- Merge remains non-idempotent; clients must account for uncertain responses.
- Remote serving, TLS, daemon management and durable token storage remain outside
  this interface.
