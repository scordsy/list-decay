"""Reading a list of company names, the way a CRM exports it, for `find`.

The file is kept whole, every column and row, so `find` can write it back with company numbers
added and nothing else touched.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from list_decay._reading import find_header, read_text, sniff_dialect
from list_decay.company_list import is_number_header, normalise_company_number

# Headers that name the company, most specific first. A bare "Name" is left out on purpose:
# in a contacts export it is usually a person.
NAME_HEADERS = [
    "companyname",
    "accountname",
    "organisationname",
    "organizationname",
    "businessname",
    "registeredname",
    "firmname",
    "company",
    "account",
    "organisation",
    "organization",
    "business",
    "firm",
]
POSTCODE_HEADERS = [
    "postcode",
    "postalcode",
    "billingpostcode",
    "billingpostalcode",
    "billingzippostalcode",
    "registeredpostcode",
    "zipcode",
    "zip",
]


class NoNameColumn(Exception):
    """The file has no header that names a company name column."""


@dataclass(frozen=True, slots=True)
class ListedCompany:
    """One row of a name list: the company as the list names it."""

    name: str
    postcode: str = ""
    number: str | None = None  # a company number the list already holds for it


@dataclass(frozen=True, slots=True)
class NameList:
    """A file of company names, every column and row kept so it can be written back."""

    header: list[str]
    records: list[list[str]]
    name_column: str
    postcode_column: str | None
    number_column: str | None  # an existing company number column, if the file has one

    @property
    def companies(self) -> list[ListedCompany]:
        name_at = self.header.index(self.name_column)
        postcode_at = self._index(self.postcode_column)
        number_at = self._index(self.number_column)
        return [
            ListedCompany(
                name=_cell(record, name_at),
                postcode="" if postcode_at is None else _cell(record, postcode_at),
                number=None
                if number_at is None
                else normalise_company_number(_cell(record, number_at)),
            )
            for record in self.records
        ]

    def padded(self, record: list[str]) -> list[str]:
        """A record with empty cells added so it is as wide as the header."""
        return record + [""] * (len(self.header) - len(record))

    def _index(self, column: str | None) -> int | None:
        return None if column is None else self.header.index(column)


def read_name_list(path: Path) -> NameList:
    """Read company names, with postcodes and company numbers where the file has them.

    Needs a header row naming the company name column ("Company Name", "Account Name",
    "Organisation" and the like). Raises NoNameColumn when there isn't one.
    """
    text = read_text(path)
    reader = csv.reader(text.splitlines(), dialect=sniff_dialect(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    header = [cell.strip() for cell in rows[0]] if rows else []
    name_column = find_header(header, NAME_HEADERS)
    if name_column is None:
        raise NoNameColumn(
            "find needs a header row naming the company name column, such as "
            '"Company Name", "Account Name" or "Organisation".'
        )
    return NameList(
        header=header,
        records=rows[1:],
        name_column=name_column,
        postcode_column=find_header(header, POSTCODE_HEADERS),
        number_column=next((cell for cell in header if is_number_header(cell)), None),
    )


def _cell(record: list[str], index: int) -> str:
    return record[index].strip() if index < len(record) else ""
