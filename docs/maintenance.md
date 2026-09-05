# Maintenance

[Documentation index](README.md) · [Contributing](../CONTRIBUTING.md)

## Dependencies and compatibility

`pyproject.toml` is the source of truth for runtime dependencies, development
tools, supported Python versions and packaging. `VERSION` supplies the build
version. Do not introduce a second version or dependency list to keep in sync.

For dependency changes, install `.[dev]` in a fresh virtual environment and run
`python scripts/check.py`. Check Python 3.11 (the declared minimum) and the Python
version used by the target Arch installation before changing support claims.
Exercise the Textual UI when updating Textual or Rich, including task selection,
dialogs, themes and keyboard actions. Record the versions actually checked.

## Release preparation

1. Review pending changes and run the local checks from a clean checkout.
2. Move `Unreleased` entries into the intended release section in `CHANGELOG.md`
   and update `VERSION`. Keep existing release history intact.
3. Build both source and wheel distributions in the project virtual environment:

   ```bash
   python -m pip install build
   python -m build
   ```

4. Install the newly built wheel in a separate virtual environment. From outside
   the source checkout, verify `kanban-tui --version` matches `VERSION` and
   `kanban-tui --help` works. Also build a wheel from the generated source archive
   to check that it contains all build inputs, including `VERSION` and `LICENSE`.
5. With a disposable `KANBAN_TUI_HOME`, smoke-test configuration, add/start/done,
   archive/restore, undo, JSON export/import and the TUI. Verify an existing valid
   datastore remains readable when persistence changes are included.
6. Confirm installation and upgrade instructions still match the release source.
   Tag or publish only after the release changes have been reviewed.

Building artifacts does not publish a release. The project uses local quality
checks; remote CI is not required by the current project model.

## Documentation upkeep

Keep installation and everyday usage in the root README. Put detailed settings
and customization in the linked user references. Update the architecture guide
when responsibilities or persistence invariants change, and update the
documentation index when adding or moving a guide.

Check examples against `kanban-tui --help` and the appropriate subcommand help.
Shell snippets should work with unset XDG variables, and manual checks should use
disposable application state. Lock files may remain after normal shutdown: they
coordinate OS-managed locks and are not evidence of a currently running writer.
