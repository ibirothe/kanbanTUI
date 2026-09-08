# Local HTTP import adapter

Start the foreground server for the default board:

```bash
export KANBAN_TUI_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
kanban-tui serve-api
```

Select a named board or explicit configuration with the existing root options:

```bash
kanban-tui --board work serve-api --port 8765
kanban-tui --config ./board.yaml serve-api --port 8765
```

The startup message repeats the selected board (or explicit configuration file
name) together with the bound loopback address so the mutation target is visible
before requests are accepted.

The command resolves configuration, policy and datastore once at startup. Restart
it after changing the selected configuration. It runs in the foreground and stops
cleanly on Ctrl+C. Port 8765 is the default; port 0 lets the OS select an available
port and the actual address is printed. The token environment variable must be set.

The adapter uses Python's standard-library HTTP server for this bounded local
interface. It always binds to numeric `127.0.0.1`; there is no host override,
DNS resolution or IPv6 wildcard. Port 0 asks the OS for an available port.
This is not a remote HTTP deployment interface.

## Request contract

Both routes require `Authorization: Bearer <token>`:

- `GET /health` returns `{"status":"ok"}` without reading the datastore.
- `POST /v1/board/import?mode=merge` or `?mode=replace` imports the body.

For example, import an existing export file:

```bash
curl --fail-with-body \
  -H "Authorization: Bearer $KANBAN_TUI_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @board.json \
  "http://127.0.0.1:8765/v1/board/import?mode=merge"
```

The mode is required and must occur exactly once. Other query parameters are
rejected. The body is the existing `kanbanTUI-board` version 1 JSON envelope,
including both `active` and `archived` arrays. No board selector or resource
path is accepted. Application and policy are fixed when constructing the adapter.

POST requires `Content-Type: application/json`, UTF-8 and one nonnegative
`Content-Length`. The body limit is 1 MiB. Transfer/content encodings, duplicate
JSON keys and non-finite JSON numbers are rejected. Authentication and body-size
checks happen before reading the body. Connections have a five-second socket
inactivity timeout and close after one request. Requests are served serially;
other CLI/TUI processes continue to coordinate through the existing datastore lock.

Tokens must be nonempty printable ASCII without whitespace. Callers should supply
a randomly generated secret. Authorization uses a constant-time byte comparison.
The adapter emits no request logs and no CORS headers. Responses have `no-store`
caching and never include exception messages, filesystem paths or tracebacks.
Loopback limits network reach; the token limits callers who can perform imports.
Environment variables can be read by sufficiently privileged local processes; the
token is authentication between cooperating local clients, not isolation from the
machine administrator.

## Responses

Successful imports return HTTP 200, including semantic no-ops:

```json
{"outcome":"changed","mode":"merge","id_mapping":{"1":2}}
```

`outcome` is `changed` when the board was committed and `unchanged` for an
accepted semantic no-op. The HTTP contract does not expose internal application
result counters. The ID map contains string source IDs and integer destination
IDs; it is empty when there are no collisions. Replace preserves imported IDs.
Merge appends independent tasks and remaps collisions; it is not an upsert and
repeated requests can add duplicates. Clients must not blindly retry a merge
after an uncertain response.

Errors have the shape `{"error":{"code":"store_unavailable"}}`:

| Status | Codes / meaning |
| --- | --- |
| 400 | `invalid_json`, `invalid_import_format`, `invalid_mode`, `invalid_framing`, `incomplete_body`, `invalid_request` |
| 401 | `unauthorized`; includes `WWW-Authenticate: Bearer` |
| 404 | `not_found` |
| 408 | `request_timeout` during body read |
| 413 | `payload_too_large` |
| 415 | `unsupported_media_type` |
| 422 | `policy_violation` |
| 503 | `store_unavailable` (including writer-lock contention) |
| 500 | `internal_error` |

Transfer-format errors include a bounded, safe validation message:

```json
{"error":{"code":"invalid_import_format","message":"export must contain active and archived arrays"}}
```

Policy errors additionally identify the stable rule, configured limit and actual
value. Task-specific rules also include the task ID:

```json
{"error":{"code":"policy_violation","message":"Imported task #1 text exceeds limit (48/40 characters).","rule":"task_text_limit","limit":40,"actual":48,"task_id":1}}
```

Storage and unexpected internal failures never include messages, filesystem
paths, tracebacks or other implementation details.

Every `5xx` response includes a server-generated request ID, for example:

```json
{"error":{"code":"internal_error","request_id":"31f7d1d630d27da4"}}
```

The same ID is written to stderr with only the HTTP status and exception type.
Request targets, authorization headers, payloads, exception messages and storage
paths are never logged. Expected `4xx` responses do not create log entries.

Unsupported HTTP methods use the server's 501 status with a JSON
`invalid_request` error. Transport disconnects can prevent response delivery.

The controller calls only `BoardApplication.import_board()`. Parsing and policy
failures do not write. A successful semantic change is one atomic commit with one
undo snapshot; a no-op preserves the snapshot. Responses are formed from that
transaction's result without rereading the store. Application and domain modules
remain independent of the HTTP adapter. Tests cover the socket-free controller,
ephemeral loopback requests, YAML lock contention, concurrent imports and undo.
