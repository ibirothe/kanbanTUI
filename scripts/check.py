"""Run the project's local quality checks with the active Python environment."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    ("pytest",),
    ("ruff", "check", "."),
    ("ruff", "format", "--check", "."),
    ("mypy", "src/kanban_tui"),
)


def main() -> int:
    for check in CHECKS:
        command = [sys.executable, "-m", *check]
        print(f"Running: {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
