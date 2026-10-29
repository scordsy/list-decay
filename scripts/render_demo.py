"""Render the README's terminal image from a real run of `list-decay check --demo`.

Development only: needs `rich` (pip install rich). Run from the repo root:

    python scripts/render_demo.py
"""

import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.terminal_theme import MONOKAI
from rich.text import Text

SHOWN_LINES = 12  # company lines to show, cut from the full run
GONE_IN_WINDOW = 4  # a third of the window, the same share as the whole list
OUT = Path("docs/images/check-demo.svg")

run = subprocess.run(
    [sys.executable, "-m", "list_decay", "check", "--demo"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    check=True,
    env={**os.environ, "FORCE_COLOR": "1", "NO_COLOR": ""},
)
lines = run.stdout.splitlines()
first_result = next(i for i, line in enumerate(lines) if line.startswith("  0"))
summary = next(i for i, line in enumerate(lines) if "─" in line)
results = lines[first_result : summary - 1]


def gone(line: str) -> bool:
    return "\033[1;31m" in line or "\033[1;33m" in line  # dissolved or closing


# The first run of consecutive lines that is a fair picture of the whole list: a third gone.
start = next(
    i
    for i in range(len(results) - SHOWN_LINES)
    if sum(gone(line) for line in results[i : i + SHOWN_LINES]) == GONE_IN_WINDOW
)
after = len(results) - start - SHOWN_LINES
kept = [
    "$ list-decay check --demo",
    *lines[:first_result],
    f"\033[2m  ... {start:,} earlier\033[0m",
    *results[start : start + SHOWN_LINES],
    f"\033[2m  ... {after:,} more\033[0m",
    "",
    *lines[summary:],
]

console = Console(record=True, width=86, force_terminal=True, color_system="truecolor")
console.print(Text.from_ansi("\n".join(kept).rstrip() + "\n"))
console.save_svg(str(OUT), title="list-decay", theme=MONOKAI)
print(f"Wrote {OUT}")
