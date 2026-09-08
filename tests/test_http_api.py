import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.client import HTTPConnection
from threading import Thread

import pytest

from kanban_tui.application import BoardApplication
from kanban_tui.http_api import MAX_BODY_BYTES, ImportApi, create_server
from kanban_tui.models import Board
from kanban_tui.policy import BoardPolicy
from kanban_tui.services import add_tasks
from kanban_tui.storage import YamlBoardStore, datastore_lock
from kanban_tui.transfer_format import export_payload
from tests.store_test_double import FailOnceCommitStore, MemoryBoardStore

TOKEN = "test-secret"


def payload(text="incoming"):
    board = Board()
    add_tasks(BoardPolicy(), board, [text])
    return json.dumps(export_payload(board)).encode()


@contextmanager
def running(api, *, logger=None):
    with create_server(api, logger=logger) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()


def request(
    port, body=b"", *, path="/v1/board/import?mode=merge", method="POST", headers=None
):
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(
            method,
            path,
            body,
            headers
            if headers is not None
            else {
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read()), dict(response.getheaders())
    finally:
        connection.close()


def test_controller_merge_replace_noop_and_undo():
    store = MemoryBoardStore()
    app = BoardApplication(store)
    api = ImportApi(app, BoardPolicy(), token=TOKEN)
    body = payload()
    assert api.import_payload("replace", body).body == {
        "outcome": "changed",
        "mode": "replace",
        "id_mapping": {},
    }
    assert api.import_payload("replace", body).body == {
        "outcome": "unchanged",
        "mode": "replace",
        "id_mapping": {},
    }
    assert store.commits == 1
    result = api.import_payload("merge", body)
    assert result.body == {
        "outcome": "changed",
        "mode": "merge",
        "id_mapping": {"1": 2},
    }
    assert store.commits == 2
    assert len(app.undo().active) == 1
    assert (
        api.import_payload(
            "replace", json.dumps(export_payload(Board())).encode()
        ).status
        == 200
    )
    assert not app.read().active


@pytest.mark.parametrize(
    "body,mode,status,code",
    [
        (b"{", "merge", 400, "invalid_json"),
        (b"\xff", "merge", 400, "invalid_json"),
        (b'{"version":1,"version":2}', "merge", 400, "invalid_json"),
        (b'{"value":NaN}', "merge", 400, "invalid_json"),
        (b"{}", "unknown", 400, "invalid_mode"),
        (b" " * (MAX_BODY_BYTES + 1), "merge", 413, "payload_too_large"),
    ],
)
def test_controller_rejects_invalid_input_without_transaction(body, mode, status, code):
    store = MemoryBoardStore()
    api = ImportApi(BoardApplication(store), BoardPolicy(), token=TOKEN)
    response = api.import_payload(mode, body)
    assert (response.status, response.body) == (status, {"error": {"code": code}})
    assert store.transactions == 0


def test_controller_returns_actionable_bounded_import_format_error():
    store = MemoryBoardStore()
    api = ImportApi(BoardApplication(store), BoardPolicy(), token=TOKEN)

    response = api.import_payload("merge", b"{}")
    assert response.status == 400
    assert response.body == {
        "error": {
            "code": "invalid_import_format",
            "message": "unsupported export format: None",
        }
    }

    oversized_value = "x" * 1000
    response = api.import_payload(
        "merge",
        json.dumps(
            {
                "format": oversized_value,
                "version": 1,
                "active": [],
                "archived": [],
            }
        ).encode(),
    )
    assert response.status == 400
    assert len(response.body["error"]["message"]) == 400
    assert store.transactions == 0


def test_policy_and_commit_failure_preserve_state_and_release_lock():
    store = MemoryBoardStore()
    app = BoardApplication(FailOnceCommitStore(store))
    api = ImportApi(app, BoardPolicy(task_text_limit=4), token=TOKEN)
    response = api.import_payload("merge", payload())
    assert response.status == 422
    assert response.body == {
        "error": {
            "code": "policy_violation",
            "message": "Imported task #1 text exceeds limit (8/4 characters).",
            "rule": "task_text_limit",
            "limit": 4,
            "actual": 8,
            "task_id": 1,
        }
    }
    store_error = api.import_payload("merge", payload("one"))
    assert store_error.status == 503
    assert store_error.body == {"error": {"code": "store_unavailable"}}
    assert not store.board.active and not store.locked and store.previous is None
    assert api.import_payload("merge", payload("one")).status == 200
    assert not app.undo().active


def test_policy_capacity_error_exposes_stable_rule_and_counts():
    store = MemoryBoardStore()
    api = ImportApi(BoardApplication(store), BoardPolicy(todo_limit=0), token=TOKEN)

    response = api.import_payload("replace", payload("one"))

    assert response.status == 422
    assert response.body == {
        "error": {
            "code": "policy_violation",
            "message": "Imported board exceeds TODO limit (1/0).",
            "rule": "todo_limit",
            "limit": 0,
            "actual": 1,
        }
    }
    assert store.transactions == 0
    assert not store.board.active


def test_unexpected_error_is_sanitized():
    class BrokenApplication(BoardApplication):
        def import_board(self, *args, **kwargs):
            raise RuntimeError("secret path and token")

    api = ImportApi(BrokenApplication(MemoryBoardStore()), BoardPolicy(), token=TOKEN)
    response = api.import_payload("merge", payload())
    assert response.status == 500
    assert response.body == {"error": {"code": "internal_error"}}


def test_http_internal_error_has_correlating_sanitized_log():
    class BrokenApplication(BoardApplication):
        def import_board(self, *args, **kwargs):
            raise RuntimeError("secret path, token and payload")

    logs = []
    api = ImportApi(BrokenApplication(MemoryBoardStore()), BoardPolicy(), token=TOKEN)
    with running(api, logger=logs.append) as port:
        status, body, _ = request(port, payload())

    request_id = body["error"]["request_id"]
    assert status == 500
    assert body == {
        "error": {
            "code": "internal_error",
            "request_id": request_id,
        }
    }
    assert isinstance(request_id, str) and len(request_id) == 16
    int(request_id, 16)
    assert logs == [f"local-api request_id={request_id} status=500 error=RuntimeError"]
    assert not any(
        secret in logs[0]
        for secret in (TOKEN, "secret path", "payload", "/v1/board/import")
    )


@pytest.mark.parametrize("token", ["", "has space", "\n", "ä"])
def test_invalid_token_rejected(token):
    with pytest.raises(ValueError):
        ImportApi(BoardApplication(MemoryBoardStore()), BoardPolicy(), token=token)


def test_listener_is_fixed_loopback_and_port_validated():
    api = ImportApi(BoardApplication(MemoryBoardStore()), BoardPolicy(), token=TOKEN)
    with create_server(api) as server:
        assert server.server_address[0] == "127.0.0.1"
    for port in (-1, 65536, True, "8765"):
        with pytest.raises(ValueError):
            create_server(api, port=port)
    with pytest.raises(TypeError):
        create_server(api, host="0.0.0.0")


def test_http_authentication_health_and_import(capsys):
    store = MemoryBoardStore()
    api = ImportApi(BoardApplication(store), BoardPolicy(), token=TOKEN)
    with running(api) as port:
        for authorization in ("", "Bearer wrong", "Basic test-secret"):
            status, _, headers = request(
                port, payload(), headers={"Authorization": authorization}
            )
            assert status == 401
            assert headers["WWW-Authenticate"] == "Bearer"
        assert store.transactions == 0
        assert request(port, method="GET", path="/health")[0:2] == (
            200,
            {"status": "ok"},
        )
        assert request(port, payload(), path="/v1/board/import?mode=replace")[0] == 200
        status, body, headers = request(port, payload())
        assert status == 200 and body["id_mapping"] == {"1": 2}
        assert "Access-Control-Allow-Origin" not in headers
        assert headers["Cache-Control"] == "no-store"
    assert TOKEN not in capsys.readouterr().err


@pytest.mark.parametrize(
    "path,extra,status",
    [
        ("/v1/board/import", {}, 400),
        ("/v1/board/import?mode=merge&mode=replace", {}, 400),
        ("/v1/board/import?mode=merge&board=other", {}, 400),
        ("/v1/board/import?mode=bad", {}, 400),
        ("/other", {}, 404),
        ("/v1/board/import?mode=merge", {"Content-Type": "text/plain"}, 415),
        ("/v1/board/import?mode=merge", {"Transfer-Encoding": "chunked"}, 400),
        (
            "/v1/board/import?mode=merge",
            {"Content-Length": str(MAX_BODY_BYTES + 1)},
            413,
        ),
        ("/v1/board/import?mode=merge", {"Content-Length": "-1"}, 400),
    ],
)
def test_http_rejections_do_not_write(path, extra, status):
    store = MemoryBoardStore()
    api = ImportApi(BoardApplication(store), BoardPolicy(), token=TOKEN)
    logs = []
    with running(api, logger=logs.append) as port:
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            **extra,
        }
        assert request(port, payload(), path=path, headers=headers)[0] == status
    assert store.transactions == 0
    assert logs == []


def test_http_yaml_lock_and_concurrent_imports(write_config):
    config = write_config()
    app = BoardApplication(YamlBoardStore(config))
    api = ImportApi(app, config.policy, token=TOKEN)
    body = payload()
    logs = []
    with running(api, logger=logs.append) as port:
        with datastore_lock(config):
            status, response_body, _ = request(port, body)
            assert status == 503
            request_id = response_body["error"]["request_id"]
            assert response_body == {
                "error": {
                    "code": "store_unavailable",
                    "request_id": request_id,
                }
            }
            assert logs == [
                f"local-api request_id={request_id} status=503 error=StoreError"
            ]
            assert not config.data_path.exists()
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: request(port, body), range(2)))
        assert all(response[0] == 200 for response in responses)
        assert len(app.read().active) == 2
        assert (
            request(
                port,
                payload("replacement"),
                path="/v1/board/import?mode=replace",
            )[0]
            == 200
        )
        assert [task.text for task in app.read().active.values()] == ["replacement"]
        assert len(app.undo().active) == 2
