import yaml

from kanban_tui.cli import main
from kanban_tui.config import get_board_data_path
from kanban_tui.storage import YamlBoardStore


class FakeServer:
    server_address = ("127.0.0.1", 43210)

    def __init__(self, *, failure=None):
        self.failure = failure
        self.entered = False
        self.closed = False
        self.served = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        self.closed = True

    def serve_forever(self):
        self.served = True
        if self.failure is not None:
            raise self.failure
        raise KeyboardInterrupt


def install_server(monkeypatch, *, failure=None):
    captured = {}
    server = FakeServer(failure=failure)

    def create(api, *, port):
        captured.update(api=api, port=port)
        return server

    monkeypatch.setattr("kanban_tui.cli.create_server", create)
    return server, captured


def test_api_command_wires_selected_config_once_and_stops_cleanly(
    runner, write_config, monkeypatch
):
    config = write_config()
    secret = "secret-that-must-not-be-printed"
    monkeypatch.setenv("KANBAN_TUI_API_TOKEN", secret)
    server, captured = install_server(monkeypatch)

    result = runner.invoke(main, ["serve-api", "--port", "0"])

    assert result.exit_code == 0, result.output
    assert captured["port"] == 0
    store = captured["api"].application.store
    assert isinstance(store, YamlBoardStore)
    assert store.config is config or store.config.data_path == config.data_path
    assert server.entered and server.served and server.closed
    assert result.output == (
        "Serving local API for 'default' on http://127.0.0.1:43210\n"
        "Local API stopped.\n"
    )
    assert secret not in result.output


def test_api_command_uses_named_board_selection(runner, isolated_app_home, monkeypatch):
    config_path = isolated_app_home / "boards" / "work.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump({"data_path": str(get_board_data_path("work"))}),
        encoding="utf-8",
    )
    monkeypatch.setenv("KANBAN_TUI_API_TOKEN", "test-secret")
    _, captured = install_server(monkeypatch)

    result = runner.invoke(main, ["--board", "work", "serve-api"])

    assert result.exit_code == 0, result.output
    store = captured["api"].application.store
    assert isinstance(store, YamlBoardStore)
    assert store.config.data_path == get_board_data_path("work")
    assert "Serving local API for 'work'" in result.output


def test_api_command_requires_environment_token_before_configuration(
    runner, monkeypatch
):
    monkeypatch.delenv("KANBAN_TUI_API_TOKEN", raising=False)
    result = runner.invoke(main, ["serve-api"])

    assert result.exit_code != 0
    assert "Set KANBAN_TUI_API_TOKEN" in result.output
    assert "Could not read config" not in result.output


def test_api_command_rejects_invalid_token_and_port(runner, write_config, monkeypatch):
    write_config()
    monkeypatch.setenv("KANBAN_TUI_API_TOKEN", "has space")
    result = runner.invoke(main, ["serve-api"])
    assert result.exit_code != 0
    assert "printable ASCII without spaces" in result.output
    assert "has space" not in result.output

    result = runner.invoke(main, ["serve-api", "--port", "65536"])
    assert result.exit_code != 0
    assert "not in the range 0<=x<=65535" in result.output


def test_api_command_closes_server_and_translates_runtime_failure(
    runner, write_config, monkeypatch
):
    write_config()
    monkeypatch.setenv("KANBAN_TUI_API_TOKEN", "test-secret")
    server, _ = install_server(monkeypatch, failure=OSError("socket failed"))

    result = runner.invoke(main, ["serve-api"])

    assert result.exit_code != 0
    assert "Local API failed: socket failed" in result.output
    assert server.closed


def test_api_command_exposes_no_host_or_token_option(runner):
    result = runner.invoke(main, ["serve-api", "--help"])
    help_text = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "--port" in help_text
    assert "KANBAN_TUI_API_TOKEN" in help_text
    assert "IPv4 loopback" in help_text
    assert "never binds to an external interface" in help_text
    assert "--host" not in help_text
    assert "--token" not in help_text
