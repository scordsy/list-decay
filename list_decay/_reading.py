"""Helpers shared by every reader of a list file: decoding, separators and header names."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from pathlib import Path


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")  # older Excel exports


def sniff_dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    """Comma, semicolon, tab or pipe, whichever the file uses. Comma if it can't tell."""
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def header_key(cell: str) -> str:
    """A header with case, spaces and punctuation taken out: 'Company Number' -> 'companynumber'."""
    return re.sub(r"[^a-z]", "", cell.lower())


def find_header(header: list[str], wanted: Iterable[str]) -> str | None:
    """The first header in `wanted` order that the file has, as the file spells it."""
    keys = {header_key(cell): cell for cell in header}
    return next((keys[key] for key in wanted if key in keys), None)
