"""Authenticated loopback HTTP adapter for the board import use case."""

import hmac
import json
import secrets
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from .application import BoardApplication, IdempotencyConflict, StoreError
from .idempotency import digest_idempotency_key, digest_import_request
from .imports import ImportMode
from .policy import BoardPolicy, PolicyViolation
from .transfer_format import TransferFormatError, board_from_export

MAX_BODY_BYTES = 1024 * 1024
MAX_IDEMPOTENCY_KEY_LENGTH = 128


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: dict[str, object]
    diagnostic: str | None = None


def error(
    status: int,
    code: str,
    *,
    message: str | None = None,
    details: Mapping[str, object] | None = None,
    diagnostic: str | None = None,
) -> ApiResponse:
    error_body: dict[str, object] = {"code": code}
    if message is not None:
        error_body["message"] = message
    if details is not None:
        error_body.update(details)
    return ApiResponse(status, {"error": error_body}, diagnostic)


def _safe_validation_message(error: ValueError, *, limit: int = 400) -> str:
    """Bound client-owned validation details without exposing internal failures."""
    message = str(error)
    return message if len(message) <= limit else f"{message[: limit - 3]}..."


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


class ImportApi:
    """Socket-free controller; owns neither board selection nor persistence."""

    def __init__(
        self, application: BoardApplication, policy: BoardPolicy, *, token: str
    ) -> None:
        if not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise ValueError(
                "API token must be nonempty printable ASCII without spaces"
            )
        self.application = application
        self.policy = policy
        self._authorization = f"Bearer {token}".encode("ascii")

    def authorized(self, authorization: str) -> bool:
        return hmac.compare_digest(authorization.encode("utf-8"), self._authorization)

    def import_payload(
        self,
        mode: str,
        body: bytes,
        *,
        idempotency_key: str | None = None,
    ) -> ApiResponse:
        if len(body) > MAX_BODY_BYTES:
            return error(413, "payload_too_large")
        try:
            selected = ImportMode(mode)
        except ValueError:
            return error(400, "invalid_mode")
        if idempotency_key is not None and (
            not idempotency_key
            or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH
            or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key)
        ):
            return error(400, "invalid_idempotency_key")
        try:
            payload = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
        except (ValueError, RecursionError):
            return error(400, "invalid_json")
        try:
            imported = board_from_export(payload)
        except TransferFormatError as exc:
            return error(
                400,
                "invalid_import_format",
                message=_safe_validation_message(exc),
            )
        try:
            if idempotency_key is None:
                _, result = self.application.import_board(
                    self.policy, imported, selected
                )
            else:
                _, result = self.application.import_board_once(
                    self.policy,
                    imported,
                    selected,
                    key_digest=digest_idempotency_key(idempotency_key),
                    request_digest=digest_import_request(selected.value, body),
                )
        except IdempotencyConflict:
            return error(409, "idempotency_conflict")
        except PolicyViolation as exc:
            details = {
                key: value
                for key, value in {
                    "rule": exc.rule,
                    "limit": exc.limit,
                    "actual": exc.actual,
                    "task_id": exc.task_id,
                }.items()
                if value is not None
            }
            return error(
                422,
                "policy_violation",
                message=_safe_validation_message(exc),
                details=details,
            )
        except StoreError as exc:
            return error(
                503,
                "store_unavailable",
                diagnostic=type(exc).__name__,
            )
        except Exception as exc:
            return error(500, "internal_error", diagnostic=type(exc).__name__)
        return ApiResponse(
            200,
            {
                "outcome": "changed" if result.changed else "unchanged",
                "mode": selected.value,
                "id_mapping": {
                    str(old): new
                    for item in result.items
                    for old, new in item.id_mapping
                },
            },
        )


def _stderr_log(message: str) -> None:
    print(message, file=sys.stderr)


def create_server(
    api: ImportApi,
    *,
    port: int = 0,
    logger: Callable[[str], None] | None = None,
) -> HTTPServer:
    """Bind exclusively to numeric IPv4 loopback; caller owns serve/close lifecycle."""
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("API port must be an integer between 0 and 65535")

    log = _stderr_log if logger is None else logger

    class Handler(BaseHTTPRequestHandler):
        # One request per connection avoids ambiguous body framing and pipelining.
        protocol_version = "HTTP/1.0"

        def setup(self) -> None:
            self.request.settimeout(5)
            super().setup()

        def log_message(self, format: str, *args: object) -> None:
            # Request targets and credentials must never enter terminal logs.
            pass

        def send_error(
            self, code: int, message: str | None = None, explain: str | None = None
        ) -> None:
            self.respond(error(code, "invalid_request"))

        def respond(self, response: ApiResponse) -> None:
            if response.status >= 500:
                request_id = secrets.token_hex(8)
                raw_error = response.body.get("error")
                error_body = dict(raw_error) if isinstance(raw_error, dict) else {}
                error_body["request_id"] = request_id
                response = ApiResponse(
                    response.status,
                    {"error": error_body},
                    response.diagnostic,
                )
                diagnostic = response.diagnostic or str(
                    error_body.get("code", "server_error")
                )
                log(
                    "local-api "
                    f"request_id={request_id} status={response.status} "
                    f"error={diagnostic}"
                )
            data = json.dumps(response.body, separators=(",", ":")).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            if response.status == 401:
                self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            self.close_connection = True
            if self.command != "HEAD":
                self.wfile.write(data)

        def authenticated(self) -> bool:
            headers = self.headers.get_all("Authorization", [])
            if len(headers) != 1 or not api.authorized(headers[0]):
                self.respond(error(401, "unauthorized"))
                return False
            return True

        def do_GET(self) -> None:
            if self.authenticated():
                self.respond(
                    ApiResponse(200, {"status": "ok"})
                    if self.path == "/health"
                    else error(404, "not_found")
                )

        def do_POST(self) -> None:
            if not self.authenticated():
                return
            try:
                target = urlsplit(self.path)
                query = parse_qs(target.query, keep_blank_values=True, max_num_fields=2)
            except ValueError:
                self.respond(error(400, "invalid_request"))
                return
            if target.path != "/v1/board/import" or target.scheme or target.netloc:
                self.respond(error(404, "not_found"))
                return
            if target.fragment or set(query) != {"mode"} or len(query["mode"]) != 1:
                self.respond(error(400, "invalid_mode"))
                return
            if query["mode"][0] not in {"merge", "replace"}:
                self.respond(error(400, "invalid_mode"))
                return
            idempotency_keys = self.headers.get_all("Idempotency-Key", [])
            if len(idempotency_keys) > 1:
                self.respond(error(400, "invalid_idempotency_key"))
                return
            types = self.headers.get_all("Content-Type", [])
            if len(types) != 1 or self.headers.get_content_type() != "application/json":
                self.respond(error(415, "unsupported_media_type"))
                return
            lengths = self.headers.get_all("Content-Length", [])
            if (
                self.headers.get_all("Transfer-Encoding")
                or self.headers.get_all("Content-Encoding")
                or len(lengths) != 1
                or not lengths[0].isascii()
                or not lengths[0].isdigit()
                or len(lengths[0]) > 10
            ):
                self.respond(error(400, "invalid_framing"))
                return
            length = int(lengths[0])
            if length > MAX_BODY_BYTES:
                self.respond(error(413, "payload_too_large"))
                return
            try:
                body = self.rfile.read(length)
            except TimeoutError:
                self.respond(error(408, "request_timeout"))
                return
            if len(body) != length:
                self.respond(error(400, "incomplete_body"))
                return
            try:
                response = api.import_payload(
                    query["mode"][0],
                    body,
                    idempotency_key=(idempotency_keys[0] if idempotency_keys else None),
                )
            except Exception as exc:
                response = error(
                    500,
                    "internal_error",
                    diagnostic=type(exc).__name__,
                )
            self.respond(response)

    return HTTPServer(("127.0.0.1", port), Handler)
