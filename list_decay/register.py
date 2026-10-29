"""Where company records come from: a saved snapshot of the register, or the live register."""

from __future__ import annotations

import base64
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Protocol

from list_decay._version import __version__
from list_decay.company import Company, parse_date

_SNAPSHOT_FIELDS = [
    "company_number",
    "company_status",
    "company_status_detail",
    "date_of_creation",
    "date_of_cessation",
    "type",
    "sic_codes",
    "last_accounts_type",
    "checked_on",
]

BUNDLED_SNAPSHOT = "register-sample-2026-07-20.csv"

API_BASE = "https://api.company-information.service.gov.uk"
KEY_URL = "https://developer.company-information.service.gov.uk/manage-applications"

# Companies House allows 600 requests in any five minutes, then refuses every request until the
# window resets. 1.9 a second stays just under the 2.0 that works out to.
LOOKUPS_PER_SECOND = 1.9
_TIMEOUT_SECONDS = 30.0
_MAX_ATTEMPTS = 6
_DEFAULT_RATE_LIMIT_WAIT = 60.0


class RegisterError(Exception):
    """The register could not answer."""


class ApiKeyRejected(RegisterError):
    """Companies House refused the API key."""


class RegisterUnavailable(RegisterError):
    """Companies House kept failing, after waiting and retrying."""


class Register(Protocol):
    """Anything that can look up a company by its number."""

    @property
    def source(self) -> str:
        """Where the records come from, in words, for the top of a report."""
        ...

    def lookup(self, number: str) -> Company | None:
        """The company's record, or None if the register has no company with that number."""
        ...


class SnapshotRegister:
    """Register records saved on a known date. Needs no API key and makes no network calls."""

    def __init__(self, companies: Iterable[Company], checked_on: date) -> None:
        self._by_number = {company.number: company for company in companies}
        self.checked_on = checked_on

    @classmethod
    def bundled(cls) -> SnapshotRegister:
        """The 5,000-company sample from 20 Jul 2026 that ships with list-decay."""
        data = resources.files("list_decay") / "data" / BUNDLED_SNAPSHOT
        with resources.as_file(data) as path:
            return cls.from_csv(path)

    @classmethod
    def from_csv(cls, path: Path) -> SnapshotRegister:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        checked = [day for row in rows if (day := parse_date(row["checked_on"]))]
        if not checked:
            raise ValueError(f"{path} has no checked_on dates, so its age can't be known")
        return cls((_company_from_row(row) for row in rows), max(checked))

    @property
    def source(self) -> str:
        return f"Companies House, saved {self.checked_on.day} {self.checked_on:%b %Y}"

    @property
    def companies(self) -> list[Company]:
        return list(self._by_number.values())

    def lookup(self, number: str) -> Company | None:
        return self._by_number.get(number)

    def to_csv(self, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=_SNAPSHOT_FIELDS, lineterminator="\n")
            writer.writeheader()
            for company in sorted(self._by_number.values(), key=lambda c: c.number):
                writer.writerow(
                    {**_row_from_company(company), "checked_on": self.checked_on.isoformat()}
                )


class LiveRegister:
    """The live Companies House register, read through its free REST API.

    Paces itself under the rate limit, waits and retries when rate-limited or when the service
    stumbles, and stops with a clear error when the key is refused. The key is never printed.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = API_BASE,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._auth = "Basic " + base64.b64encode(f"{api_key}:".encode()).decode()
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None

    def __repr__(self) -> str:
        return f"LiveRegister(base_url={self._base_url!r})"

    @property
    def source(self) -> str:
        return "the live Companies House register"

    def lookup(self, number: str) -> Company | None:
        url = f"{self._base_url}/company/{urllib.parse.quote(number)}"
        problem, wait = "", 0.0
        for attempt in range(_MAX_ATTEMPTS):
            if attempt:
                self._sleep(wait)
            self._pace()
            try:
                return self._fetch(url)
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 404:
                    return None
                if error.code in (401, 403):
                    raise ApiKeyRejected(
                        f"Companies House refused the API key (HTTP {error.code}). "
                        f"Check CH_API_KEY holds a live REST key from {KEY_URL}"
                    ) from None
                if error.code != 429 and error.code < 500:
                    raise RegisterUnavailable(
                        f"Companies House answered HTTP {error.code} for {number}"
                    ) from None
                problem = f"HTTP {error.code}"
                wait = _rate_limit_wait(error) if error.code == 429 else _backoff(attempt)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                problem = f"no connection ({getattr(error, 'reason', error)})"
                wait = _backoff(attempt)
        raise RegisterUnavailable(
            f"Companies House did not answer for {number} after {_MAX_ATTEMPTS} attempts "
            f"(last: {problem}). Try again in a few minutes."
        )

    def _fetch(self, url: str) -> Company:
        request = urllib.request.Request(url)
        request.add_header("Authorization", self._auth)
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", f"list-decay/{__version__}")
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return Company.from_register(json.load(response))

    def _pace(self) -> None:
        if self._last_request is not None:
            gap = 1 / LOOKUPS_PER_SECOND - (self._clock() - self._last_request)
            if gap > 0:
                self._sleep(gap)
        self._last_request = self._clock()


class CachedRegister:
    """Remembers every lookup in a file, so an interrupted run resumes and a re-run costs nothing.

    "Not found" is remembered too: a number that was never issued is never asked about twice.
    """

    def __init__(self, inner: Register, path: Path) -> None:
        self._inner = inner
        self._path = path
        self._known: dict[str, Company | None] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a half-written last line from an interrupted run
                stored = record["company"]
                self._known[record["number"]] = _company_from_json(stored) if stored else None

    @property
    def source(self) -> str:
        return self._inner.source

    def lookup(self, number: str) -> Company | None:
        if number in self._known:
            return self._known[number]
        company = self._inner.lookup(number)
        self._known[number] = company
        record = {"number": number, "company": _company_to_json(company) if company else None}
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        return company


def _rate_limit_wait(error: urllib.error.HTTPError) -> float:
    """Honour Retry-After when Companies House sends one, capped at the five-minute window."""
    try:
        return min(float(error.headers.get("Retry-After", "")), 300.0)
    except ValueError:
        return _DEFAULT_RATE_LIMIT_WAIT


def _backoff(attempt: int) -> float:
    """1, 2, 4, 8, 16 seconds between tries when the service stumbles."""
    return float(min(2**attempt, 30))


def _company_from_row(row: dict[str, str]) -> Company:
    return Company(
        number=row["company_number"],
        status=row["company_status"],
        status_detail=row["company_status_detail"],
        incorporated_on=parse_date(row["date_of_creation"]),
        dissolved_on=parse_date(row["date_of_cessation"]),
        company_type=row["type"],
        sic_codes=tuple(code for code in row["sic_codes"].split("|") if code),
        last_accounts_type=row["last_accounts_type"],
    )


def _row_from_company(company: Company) -> dict[str, str]:
    return {
        "company_number": company.number,
        "company_status": company.status,
        "company_status_detail": company.status_detail,
        "date_of_creation": _iso(company.incorporated_on),
        "date_of_cessation": _iso(company.dissolved_on),
        "type": company.company_type,
        "sic_codes": "|".join(company.sic_codes),
        "last_accounts_type": company.last_accounts_type,
    }


def _company_to_json(company: Company) -> dict[str, str]:
    return {**_row_from_company(company), "company_name": company.name}


def _company_from_json(stored: dict[str, str]) -> Company:
    return replace(_company_from_row(stored), name=stored.get("company_name", ""))


def _iso(day: date | None) -> str:
    return day.isoformat() if day else ""
