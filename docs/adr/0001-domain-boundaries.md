# ADR 0001: Keep domain policy independent from terminal adapters

- Status: Accepted
- Date: 2026-09-07

## Context

Task and board rules were previously reached through `AppConfig`. Importing the domain model therefore also imported theme discovery, while services received datastore paths, repaint and display settings they did not use. Import validation raised Click exceptions directly. These dependencies made another delivery or storage adapter carry terminal-specific packages and error behavior.

## Decision

The dependency direction is:

1. `models.py` owns task and board state plus intrinsic invariants.
2. `policy.py` owns `BoardPolicy`, TODO/WIP capacity, task-text limits and pure `PolicyViolation` errors. It may depend on `models.py` only.
3. `services.py` owns domain mutations and depends on `models.py` and `policy.py` only.
4. `settings.py` composes path, legacy config-file limits and presentation settings into the compatible `AppConfig` used at program entry points. `AppConfig.policy` is the explicit mapping into the domain.
5. CLI, TUI, configuration, transfer codecs, rendering and persistence are adapters. They translate domain failures into Click/Textual behavior and pass only `BoardPolicy` to services.

TODO/WIP capacity and task-text length are domain policy. DONE display count, repaint and theme are presentation settings. The datastore path is infrastructure configuration. Import parsing remains in the JSON adapter; policy validation of the resulting board is pure.

No interface is introduced for data classes. Typed operation-result DTOs were deferred to issue #79 and are now specified by [ADR 0002](0002-typed-operation-results.md). Store and transaction ports were deferred to issue #78 and are now specified by [ADR 0003](0003-persistence-ports.md).

## Consequences

- Domain models, policies and services import without Click, PyYAML, Rich, Textual, theme discovery or path access.
- CLI/TUI behavior and the existing YAML configuration shape remain compatible.
- Adapters must explicitly select `config.policy`; accidental access to unrelated application configuration becomes visible in code review and typing.
- `AppConfig` remains a transitional composition object. Later ports can accept its individual path, policy and presentation values without changing the domain.
