# Python API

kanbanTUI is primarily a CLI/TUI application. Its supported Python integration
surface consists of the focused modules below; adapters should inject the
application and persistence ports instead of relying on config-based convenience
wrappers.

| Concern | Canonical API |
| --- | --- |
| Use cases and transaction ports | `kanban_tui.application` |
| Board merge policy | `kanban_tui.imports` |
| Import/export payload codec | `kanban_tui.transfer_format` |
| Import/export file I/O | `kanban_tui.transfer` (`read_export`, `write_export`) |
| Config and data roots | `kanban_tui.config.get_config_root`, `get_data_root` |
| Side-effect-free board read | `kanban_tui.storage.read_data(config)` |
