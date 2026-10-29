"""Checking a list of company numbers against a register, and counting what comes back."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from list_decay.company import Company, Verdict
from list_decay.register import Register


@dataclass(frozen=True, slots=True)
class CheckedCompany:
    """One company number and what the register said about it."""

    number: str
    company: Company | None

    @property
    def verdict(self) -> Verdict:
        return Verdict.NOT_FOUND if self.company is None else self.company.verdict

    @property
    def closing_reason(self) -> str | None:
        return None if self.company is None else self.company.closing_reason

    @property
    def dissolved_on(self) -> date | None:
        if self.company is None or self.verdict is not Verdict.DISSOLVED:
            return None
        return self.company.dissolved_on

    @property
    def name(self) -> str:
        return "" if self.company is None else self.company.name

    @property
    def in_insolvency(self) -> bool:
        return self.company is not None and self.company.in_insolvency

    @property
    def register_status(self) -> str:
        """The register's own status field, word for word."""
        return "" if self.company is None else self.company.status


def check(numbers: Iterable[str], register: Register) -> Iterator[CheckedCompany]:
    """Look up each company number on the register, yielding results as they arrive.

    Lazy on purpose: a live check runs at the register's rate limit, so callers can show each
    result the moment it lands rather than waiting for the whole list.
    """
    for number in numbers:
        yield CheckedCompany(number, register.lookup(number))


@dataclass(frozen=True, slots=True)
class Tally:
    """How many companies on a list landed in each verdict."""

    trading: int = 0
    closing: int = 0
    dissolved: int = 0
    not_found: int = 0
    unclear: int = 0

    @classmethod
    def of(cls, results: Iterable[CheckedCompany]) -> Tally:
        counts = dict.fromkeys(Verdict, 0)
        for result in results:
            counts[result.verdict] += 1
        return cls(
            trading=counts[Verdict.TRADING],
            closing=counts[Verdict.CLOSING],
            dissolved=counts[Verdict.DISSOLVED],
            not_found=counts[Verdict.NOT_FOUND],
            unclear=counts[Verdict.UNCLEAR],
        )

    @property
    def found(self) -> int:
        """Companies the register knows. Numbers it doesn't know are typos, not decay."""
        return self.trading + self.closing + self.dissolved + self.unclear

    @property
    def gone_or_going(self) -> int:
        return self.closing + self.dissolved

    @property
    def share_gone_or_going(self) -> float:
        return self.gone_or_going / self.found if self.found else 0.0


def write_results(path: Path, results: Sequence[CheckedCompany]) -> None:
    """One row per company: number, verdict, how it is closing, date dissolved, registered name."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company_number", "verdict", "closing_reason", "dissolved_on", "name"])
        for result in results:
            writer.writerow(
                [
                    result.number,
                    result.verdict.value,
                    result.closing_reason or "",
                    result.dissolved_on.isoformat() if result.dissolved_on else "",
                    result.name,
                ]
            )
