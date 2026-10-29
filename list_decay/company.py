"""A company as the register records it, and what that record says about it today."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any


class Verdict(Enum):
    """What the register says about one company on the day it was checked."""

    TRADING = "trading"
    CLOSING = "closing"
    DISSOLVED = "dissolved"
    NOT_FOUND = "not found"
    UNCLEAR = "unclear"


# The register's company_status values, grouped by verdict. Anything not listed is UNCLEAR.
_DISSOLVED_STATUSES = {"dissolved", "converted-closed", "closed", "removed"}
_INSOLVENCY_STATUSES = {
    "liquidation": "liquidation",
    "administration": "administration",
    "in-administration": "administration",
    "receivership": "receivership",
    "receiver-manager": "receivership",
    "voluntary-arrangement": "voluntary arrangement",
    "insolvency-proceedings": "insolvency proceedings",
}
_TRADING_STATUSES = {"active", "open", "registered"}

# A company can be "active" on the register while a closure is already underway.
_CLOSING_DETAILS = {
    "active-proposal-to-strike-off": "being struck off",
    "petition-to-restore-dissolved": "restoration petition",
}


@dataclass(frozen=True, slots=True)
class Company:
    """One company's register record: only the fields list-decay reads."""

    number: str
    status: str
    status_detail: str = ""
    incorporated_on: date | None = None
    dissolved_on: date | None = None
    company_type: str = ""
    sic_codes: tuple[str, ...] = ()
    last_accounts_type: str = ""
    name: str = ""

    @classmethod
    def from_register(cls, profile: Mapping[str, Any]) -> Company:
        """Build a Company from a Companies House company profile (the API's JSON)."""
        last_accounts = (profile.get("accounts") or {}).get("last_accounts") or {}
        return cls(
            number=str(profile["company_number"]),
            status=str(profile.get("company_status") or "").lower(),
            status_detail=str(profile.get("company_status_detail") or "").lower(),
            incorporated_on=parse_date(profile.get("date_of_creation")),
            dissolved_on=parse_date(profile.get("date_of_cessation")),
            company_type=str(profile.get("type") or "").lower(),
            sic_codes=tuple(str(code) for code in profile.get("sic_codes") or ()),
            last_accounts_type=str(last_accounts.get("type") or "").lower(),
            name=str(profile.get("company_name") or ""),
        )

    @property
    def verdict(self) -> Verdict:
        if self.status in _DISSOLVED_STATUSES:
            return Verdict.DISSOLVED
        if self.status in _INSOLVENCY_STATUSES or self.status_detail in _CLOSING_DETAILS:
            return Verdict.CLOSING
        if self.status in _TRADING_STATUSES:
            return Verdict.TRADING
        return Verdict.UNCLEAR

    @property
    def closing_reason(self) -> str | None:
        """How a closing company is closing, in plain words. None unless the verdict is CLOSING."""
        if self.verdict is not Verdict.CLOSING:
            return None
        return _INSOLVENCY_STATUSES.get(self.status) or _CLOSING_DETAILS[self.status_detail]

    @property
    def in_insolvency(self) -> bool:
        """Closing through a formal insolvency process, rather than being struck off."""
        return self.status in _INSOLVENCY_STATUSES

    def was_open_on(self, day: date) -> bool:
        """Was this company incorporated, and not yet dissolved, on `day`?

        A dissolved company with no recorded dissolution date can't be shown to have been open,
        so it counts as not open rather than being guessed at.
        """
        if self.incorporated_on is None or self.incorporated_on > day:
            return False
        if self.verdict is Verdict.DISSOLVED:
            return self.dissolved_on is not None and self.dissolved_on > day
        return True


def parse_date(value: object) -> date | None:
    """Parse the register's YYYY-MM-DD dates. Anything else is None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
