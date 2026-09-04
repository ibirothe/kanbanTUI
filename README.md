# clikan: CLI (Personal) Kanban
There has been a little chatter about 'personal' kanban on the tubes lately.  I don't know about the need to hype it as personal, but if you're looking to get your head wrapped around stuff needing to get done - then kanban is a healthy tool.  clikan is a super simple command-line utility for tracking tasks following the Japanese Kanban (boarding) style.  clikan's core intent is to be easy to use, and to maintain simplicity.

![icon](docs/icon-256x256.png)

## Requirements

Python 3.11 or newer.

## Installation

From a checkout of this repository:

```bash
python -m pip install .
```

For local development, install the project and development tools in editable mode:

```bash
python -m pip install -e ".[dev]"
```

The distribution and CLI command retain the `clikan` name for compatibility.

### Create a `.clikan.yaml` in your $HOME directory

```yaml
---
clikan_data: /Users/kplummer/.clikan.dat
limits:
  todo: 10
  wip: 3
  done: 10
  taskname: 40
repaint: true
```

* `clikan_data` is the datastore file location.
* `limits:todo` is the max number of items allowed in the todo column, keep this small - you want a smart list, not an ice box of ideas here.
* `limits:wip` is the max number of items allowed in in-progress at a given time.  Context-switching is a farce, focus on one or two tasks at a time.
* `limits:done` is the max number of done items visible, they'll still be stored.  It's good to see a list of done items, for pure psyche.
* `limits:taskname` is the max length of a task text.
* `repaint` is used to tell `clikan` to show the display after every successful command - default is false/off.

-- or --

$ `clikan configure`

to create a default data file location.

This is where the tool will store the history of files.  It's configurable so you can put the data in a Dropbox or other cloud-watched directory for safe archiving/backing up.

If you're like me, even `clikan` is a bunch too many characters to type, so shorten with an alias in my shell config to `clik`.

## Usage
The basic usage of clikan breaks down into three basic commands:

### Show

$ `clikan show` (alias: s)

### Add

$ `clikan add [task text]` (alias: a)

### Promote

$ `clikan promote [task id]` (alias: p)

And there are more supporting commands:

### Regress

$ `clikan regress [task id]`

### Delete

$ `clikan delete [task id]` (alias: d)

### Configure

$ `clikan configure`

### Screenshot

![Screenshot](screenshot.png)

## Development

This fork is maintained as a solo-development project. Changes can be committed directly to the active development branch; no contribution or review workflow is required.

### Testing

Run the complete test suite with:

```bash
pytest
```

The test suite uses temporary `CLIKAN_HOME` locations and isolated configuration/datastore files, so it does not read or modify your real `~/.clikan.yaml` or Kanban data.

### Build

Build a wheel and source distribution with:

```bash
python -m build
```

Project metadata, runtime dependencies, the console entry point, Python compatibility, and build configuration live in `pyproject.toml`. The package version is read from `VERSION`.

## License

```
MIT License

Copyright 2018 Kit Plummer

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## Support

GitHub Issues: https://github.com/ibirothe/kanbanTUI/issues
