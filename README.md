# kanbanTUI / clikan

A small terminal-based personal Kanban board. The installed command remains `clikan` for compatibility.

![icon](docs/icon-256x256.png)

## Requirements

Python 3.11 or newer.

## Installation

From a checkout of this repository:

```bash
python -m pip install .
```

For local development:

```bash
python -m pip install -e ".[dev]"
```

## Configuration

Create the default configuration with:

```bash
clikan configure
```

Or create `~/.clikan.yaml` manually. See [`examples/clikan.yaml`](examples/clikan.yaml).

Supported settings:

- `clikan_data`: datastore path.
- `limits.todo`: maximum visible/active TODO items when configured.
- `limits.wip`: maximum simultaneous in-progress items when configured.
- `limits.done`: maximum done items displayed.
- `limits.taskname`: maximum task text length.
- `repaint`: show the board after successful mutating commands.

## Usage

```bash
clikan show
clikan add "Task text"
clikan promote 1
clikan regress 1
clikan delete 1
```

Unique command prefixes are accepted, so `s`, `a`, `p`, and `d` work for `show`, `add`, `promote`, and `delete` respectively.

## Development

This is a solo-maintained project. Changes may be committed directly to the active development branch.

Run tests:

```bash
pytest
```

Build distributions:

```bash
python -m build
```

Project metadata, dependencies, Python compatibility, and build configuration live in `pyproject.toml`.

## Maintainer

Pascal Rothe  
GitHub: `ibirothe`  
Email: `ibirothe@gmail.com`

## License

MIT. See [`LICENSE`](LICENSE). The license file retains the original copyright notice required by the upstream MIT grant.

## Support

GitHub Issues: https://github.com/ibirothe/kanbanTUI/issues
