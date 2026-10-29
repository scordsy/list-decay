"""Reading a company list the way it actually arrives: a CRM export, a spreadsheet, a text file.

Only company numbers are read. Every other column is ignored, so a list can be checked without
sharing anything about the people on it.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

# Header names that mean "this column holds the company number", compared with case, spaces
# and punctuation stripped.
_NUMBER_HEADERS = {
    "companynumber",
    "companyno",
    "companieshousenumber",
    "companyregistrationnumber",
    "registrationnumber",
    "registerednumber",
    "regno",
    "crn",
    "number",
}

# Letters then digits: SC (Scotland), NI and R0 (Northern Ireland), OC/SO/NC (LLPs) and so on.
_PREFIXED = re.compile(r"([A-Z]{1,2})(\d{1,7})")


def normalise_company_number(raw: str) -> str | None:
    """Return a company number in the register's eight-character form, or None if it isn't one.

    Repairs what spreadsheets do to company numbers: dropped leading zeros, a trailing ".0",
    Excel's force-text apostrophe, stray spaces and lowercase prefixes.
    """
    text = re.sub(r"\s+", "", raw).upper().lstrip("'").removesuffix(".0")
    if not text:
        return None
    if text.isascii() and text.isdigit():
        return text.zfill(8) if len(text) <= 8 else None
    match = _PREFIXED.fullmatch(text)
    if match is None:
        return None
    prefix, digits = match.groups()
    width = 8 - len(prefix)
    return prefix + digits.zfill(width) if len(digits) <= width else None


@dataclass(frozen=True, slots=True)
class CompanyList:
    """The company numbers in a file, in first-seen order, and what could not be read."""

    numbers: list[str]
    column: str | None = None
    duplicates: int = 0
    unreadable: list[tuple[int, str]] = field(default_factory=list)


def read_company_list(path: Path) -> CompanyList:
    """Read the company numbers from a CSV or plain-text file.

    Uses the column whose header names a company number if there is one, otherwise the first
    column. Comma, semicolon, tab and pipe separators are all recognised.
    """
    text = _read_text(path)
    rows = csv.reader(text.splitlines(), dialect=_sniff_dialect(text))

    numbers: list[str] = []
    seen: set[str] = set()
    duplicates = 0
    unreadable: list[tuple[int, str]] = []
    column_index: int | None = None
    column_name: str | None = None

    for row in rows:
        if not any(cell.strip() for cell in row):
            continue
        if column_index is None:
            column_index, column_name, is_header = _choose_column(row)
            if is_header:
                continue
        cell = row[column_index].strip() if column_index < len(row) else ""
        number = normalise_company_number(cell)
        if number is None:
            unreadable.append((rows.line_num, cell))
        elif number in seen:
            duplicates += 1
        else:
            seen.add(number)
            numbers.append(number)

    return CompanyList(numbers, column_name, duplicates, unreadable)


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")  # older Excel exports; numbers are ASCII either way


def _sniff_dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _choose_column(first_row: list[str]) -> tuple[int, str | None, bool]:
    """Pick the column to read from the first non-blank row: (index, header name, is_header)."""
    for index, cell in enumerate(first_row):
        if re.sub(r"[^a-z]", "", cell.lower()) in _NUMBER_HEADERS:
            return index, cell.strip(), True
    if normalise_company_number(first_row[0]) is not None:
        return 0, None, False
    return 0, first_row[0].strip() or None, True
