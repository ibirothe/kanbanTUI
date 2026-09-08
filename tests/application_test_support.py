from kanban_tui.application import BoardApplication
from kanban_tui.settings import AppConfig
from kanban_tui.storage import YamlBoardStore


def yaml_application(config: AppConfig) -> BoardApplication:
    """Build the canonical application adapter used by integration tests."""
    return BoardApplication(YamlBoardStore(config))
