# Documentation

Start with the [README](../README.md) for installation, the quick start, task
commands, keyboard controls, filters, undo and board transfer.

| Guide | Use it for |
| --- | --- |
| [Configuration and named boards](configuration.md) | XDG paths, portable mode, limits and config commands |
| [Color themes](themes.md) | Built-in palettes, custom YAML and color-free output |
| [Shell completion](shell-completion.md) | Bash, Zsh and Fish setup |
| [Contributing](../CONTRIBUTING.md) | Development setup, local checks and pull requests |
| [Architecture](architecture.md) | Module responsibilities, invariants and persistence |
| [Local HTTP API](local-api.md) | Foreground server, authentication, requests and responses |
| [Python API](python-api.md) | Canonical integration modules |
| [ADR 0005](adr/0005-idempotent-http-imports.md) | Durable bounded idempotency for HTTP imports |
| [ADR 0001: Domain boundaries](adr/0001-domain-boundaries.md) | Dependency direction, policy ownership and adapter errors |
| [ADR 0002: Typed operation results](adr/0002-typed-operation-results.md) | Stable result codes, statuses and adapter presentation |
| [ADR 0003: Persistence ports](adr/0003-persistence-ports.md) | Store protocol, transaction guarantees and adapter wiring |
| [ADR 0004: Local HTTP API](adr/0004-local-http-api.md) | Loopback boundary, authentication and server composition |
| [Maintenance](maintenance.md) | Dependency updates, packaging and release checks |
| [Changelog](../CHANGELOG.md) | Released changes and pending work |

Example files: [configuration](../examples/kanban-tui.yaml) and
[custom theme](../examples/theme-custom.yaml). Copy commands in the theme guide
assume a repository checkout; installed users can create the shown YAML directly.
