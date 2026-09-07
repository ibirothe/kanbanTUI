# Local HTTP import adapter

`http_api.py` supplies `ImportApi(application, policy, token=...)` and
`create_server(api, port=...)`. CLI startup is delivered separately in #102;
there is currently no `kanban-tui api` command. The caller owns
`serve_forever()`, `shutdown()` and `server_close()` (or the server context manager).

The adapter uses Python's standard-library HTTP server for this bounded local
interface. It always binds to numeric `127.0.0.1`; there is no host override,
DNS resolution or IPv6 wildcard. Port 0 asks the OS for an available port.
This is not a remote HTTP deployment interface.

## Request contract

Both routes require `Authorization: Bearer <token>`:

- `GET /health` returns `{"status":"ok"}` without reading the datastore.
- `POST /v1/board/import?mode=merge` or `?mode=replace` imports the body.

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

## Responses

Successful imports return HTTP 200, including semantic no-ops:

```json
{"status":"changed","mode":"merge","changed":1,"unchanged":1,"id_mapping":{"1":2}}
```

`changed` and `unchanged` count application result items, not tasks. The ID map
contains string source IDs and integer destination IDs; it is empty when there
are no collisions. Replace preserves imported IDs. Merge appends independent
tasks and remaps collisions; it is not an upsert and repeated requests can add
duplicates. Clients must not blindly retry a merge after an uncertain response.

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

Unsupported HTTP methods use the server's 501 status with a JSON
`invalid_request` error. Transport disconnects can prevent response delivery.

The controller calls only `BoardApplication.import_board()`. Parsing and policy
failures do not write. A successful semantic change is one atomic commit with one
undo snapshot; a no-op preserves the snapshot. Responses are formed from that
transaction's result without rereading the store. Application and domain modules
remain independent of the HTTP adapter. Tests cover the socket-free controller,
ephemeral loopback requests, YAML lock contention, concurrent imports and undo.
