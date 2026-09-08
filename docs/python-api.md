# Python API compatibility

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

## Deprecated compatibility surface

The following symbols remain functional in the `0.x` series, emit
`DeprecationWarning` when used and will be removed together in `1.0.0`.

| Legacy symbol | Decision | Replacement |
| --- | --- | --- |
| `transactions.mutate_board` | Deprecate; remove in `1.0.0` | Inject a `BoardApplication` and call `mutate` |
| `transactions.undo_board` | Deprecate; remove in `1.0.0` | Inject a `BoardApplication` and call `undo` |
| `transactions.TaskConflict` | Deprecate re-export; remove in `1.0.0` | `application.TaskConflict` |
| `transactions.TaskExpectation` | Deprecate re-export; remove in `1.0.0` | `application.TaskExpectation` |
| `read_data(..., initialize_missing=...)` | Deprecate keyword; remove in `1.0.0` | Omit the keyword; reads never initialize storage |
| `config.get_app_home` | Deprecate; remove in `1.0.0` | Use `get_config_root` or `get_data_root` explicitly |
| Transfer-format symbols re-exported by `transfer` | Deprecate re-exports; remove in `1.0.0` | Import from `transfer_format` |
| `transfer.merge_boards` | Deprecate re-export; remove in `1.0.0` | `imports.merge_boards` |

Regular product code and tests use only the canonical modules. The dedicated
legacy API tests verify that the temporary shims warn and continue to work until
their coordinated removal.
