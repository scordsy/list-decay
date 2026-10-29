"""Finding company numbers from company names, and refusing to guess when it can't be sure."""

from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from list_decay.name_list import ListedCompany, NameList
from list_decay.register import Candidate

# The ways a name can spell its legal form, and the form each one means. "Ltd" and "Limited"
# are the same form; "Ltd" and "LLP" are not, and never match each other.
_LEGAL_FORMS = {
    ("LIMITED",): "LIMITED",
    ("LTD",): "LIMITED",
    ("CYFYNGEDIG",): "LIMITED",
    ("CYF",): "LIMITED",
    ("PUBLIC", "LIMITED", "COMPANY"): "PLC",
    ("PLC",): "PLC",
    ("CWMNI", "CYFYNGEDIG", "CYHOEDDUS"): "PLC",
    ("CCC",): "PLC",
    ("LIMITED", "LIABILITY", "PARTNERSHIP"): "LLP",
    ("LLP",): "LLP",
    ("PARTNERIAETH", "ATEBOLRWYDD", "CYFYNGEDIG"): "LLP",
    ("COMMUNITY", "INTEREST", "COMPANY"): "CIC",
    ("CIC",): "CIC",
    ("CWMNI", "BUDDIANT", "CYMUNEDOL"): "CIC",
    ("LIMITED", "PARTNERSHIP"): "LP",
    ("LP",): "LP",
    ("UNLIMITED",): "UNLIMITED",
    ("ANGHYFYNGEDIG",): "UNLIMITED",
}
_SPELLINGS = sorted(_LEGAL_FORMS, key=len, reverse=True)  # longest first
_CLOSEST_SHOWN = 3  # for a name with no match, how many of the search's top picks to list


class Searcher(Protocol):
    """Anything that can search the register by company name."""

    def search(self, name: str) -> list[Candidate]: ...


class FindOutcome(Enum):
    MATCHED = "matched"
    CHECK_BY_HAND = "check by hand"
    NO_MATCH = "no match"
    ALREADY_NUMBERED = "already had a number"


class MatchedOn(Enum):
    NAME = "name"
    NAME_AND_POSTCODE = "name and postcode"


@dataclass(frozen=True, slots=True)
class Finding:
    """What `find` concluded about one row of the list."""

    listed: ListedCompany
    outcome: FindOutcome
    number: str | None = None
    matched_on: MatchedOn | None = None
    candidates: tuple[Candidate, ...] = ()


@dataclass(frozen=True, slots=True)
class CompanyName:
    """A company name split into what identifies it and the legal form it declares.

    'The Acme & Sons Ltd.' becomes base 'ACME AND SONS', form 'LIMITED'.
    """

    base: str
    form: str | None

    @classmethod
    def parse(cls, name: str) -> CompanyName:
        text = unicodedata.normalize("NFKD", name)
        text = "".join(char for char in text if not unicodedata.combining(char)).upper()
        text = re.sub(r"[.'\u2018\u2019`]", "", text.replace("&", " AND "))
        words = re.findall(r"[A-Z0-9]+", text)
        if words[:1] == ["THE"]:
            words = words[1:]
        for spelling in _SPELLINGS:
            if len(words) > len(spelling) and tuple(words[-len(spelling) :]) == spelling:
                return cls(" ".join(words[: -len(spelling)]), _LEGAL_FORMS[spelling])
        return cls(" ".join(words), None)

    def is_same_as(self, other: CompanyName) -> bool:
        """Same base, and the same legal form unless this name doesn't state one."""
        return self.base == other.base and (self.form is None or self.form == other.form)


def find(companies: Iterable[ListedCompany], register: Searcher) -> Iterator[Finding]:
    """Find the company number for each listed company, filling it in only when certain.

    Certain means exactly one company on the register has the same name, and, where the list
    gives a postcode, that company's registered postcode is the same. Anything less goes back
    with the candidates for a person to decide. Rows that already hold a company number are
    passed through untouched, and each distinct name is searched once.
    """
    searched: dict[CompanyName, list[Candidate]] = {}
    for listed in companies:
        if listed.number:
            yield Finding(listed, FindOutcome.ALREADY_NUMBERED, listed.number)
            continue
        name = CompanyName.parse(listed.name)
        if not name.base:
            yield Finding(listed, FindOutcome.NO_MATCH)
            continue
        if name not in searched:
            searched[name] = register.search(listed.name)
        yield _decide(listed, name, searched[name])


def _decide(listed: ListedCompany, name: CompanyName, candidates: list[Candidate]) -> Finding:
    same_name = [c for c in candidates if name.is_same_as(CompanyName.parse(c.name))]
    if not same_name:
        other_forms = [c for c in candidates if CompanyName.parse(c.name).base == name.base]
        if other_forms:  # the right name but a different legal form: a person decides
            return Finding(listed, FindOutcome.CHECK_BY_HAND, candidates=tuple(other_forms))
        return Finding(listed, FindOutcome.NO_MATCH, candidates=tuple(candidates[:_CLOSEST_SHOWN]))
    if len(same_name) > 1:  # namesakes, even if a postcode agrees with one: a person decides
        agrees_first = sorted(same_name, key=lambda c: not same_postcode(listed.postcode, c))
        return Finding(listed, FindOutcome.CHECK_BY_HAND, candidates=tuple(agrees_first))
    [only] = same_name
    if not listed.postcode:
        return Finding(listed, FindOutcome.MATCHED, only.number, MatchedOn.NAME)
    if same_postcode(listed.postcode, only):
        return Finding(listed, FindOutcome.MATCHED, only.number, MatchedOn.NAME_AND_POSTCODE)
    return Finding(listed, FindOutcome.CHECK_BY_HAND, candidates=(only,))


def same_postcode(postcode: str, candidate: Candidate) -> bool:
    """Does a full postcode match the candidate's registered postcode? Spacing and case ignored."""
    given, registered = (re.sub(r"\s", "", p).upper() for p in (postcode, candidate.postcode))
    return bool(given) and given == registered


def write_found(path: Path, names: NameList, findings: Sequence[Finding]) -> None:
    """Write the list back with company numbers filled in, every original column kept.

    Numbers go into the file's own company number column if it has one, filling its gaps and
    leaving numbers already there alone, or into a new `company_number` column. Rows a stopped
    run never reached are kept, marked "not searched".
    """
    number_at = names.header.index(names.number_column) if names.number_column else None
    header = [*names.header, *([] if number_at is not None else ["company_number"])]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([*header, "match", "matched_on", "candidates"])
        for index, record in enumerate(names.records):
            row = names.padded(record)
            finding = findings[index] if index < len(findings) else None
            matched = finding is not None and finding.outcome is FindOutcome.MATCHED
            number = finding.number if finding is not None and matched else None
            if number_at is None:
                row.append(number or "")
            elif number:
                row[number_at] = number
            writer.writerow([*row, *_finding_columns(finding)])


def _finding_columns(finding: Finding | None) -> list[str]:
    if finding is None:
        return ["not searched", "", ""]
    candidates = "; ".join(
        f"{c.number} {c.name} ({c.postcode or 'no registered postcode'}, {c.register_status})"
        for c in finding.candidates
    )
    matched_on = finding.matched_on.value if finding.matched_on else ""
    return [finding.outcome.value, matched_on, candidates]
