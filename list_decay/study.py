"""The decay study: how much of a UK company list is gone or going, by the age of the list."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from list_decay.company import Company, Verdict
from list_decay.register import Register

# Company types a B2B list is built from.
_PROSPECT_TYPES = {"ltd", "plc", "llp", "private-unlimited", "private-unlimited-nsc"}
# SIC codes that mark a company as not trading: 99999 dormant, 74990 non-trading.
_NON_TRADING_SIC = {"99999", "74990"}
# Last-accounts types that mean nothing is happening in the company.
_DORMANT_ACCOUNTS = {"dormant", "no-accounts", "null", ""}
# Holding companies and vehicles that own or let property: legally companies, not buyers.
_HOLDING_AND_PROPERTY_SIC = {
    "64110", "64191", "64205", "64206", "64209", "64999",  # holding and financial vehicles
    "68100", "68201", "68209",  # buying, selling and letting own property
}  # fmt: skip


class Population(Enum):
    """Which companies count as being on a list."""

    ALL = "All companies"
    REAL_PROSPECTS = "Real prospects"
    OPERATING_BUSINESSES = "Operating businesses"

    @property
    def description(self) -> str:
        return {
            Population.ALL: "every company in the sample, dormant ones included",
            Population.REAL_PROSPECTS: "company types a B2B list is built from, "
            "not dormant, filing real accounts",
            Population.OPERATING_BUSINESSES: "real prospects minus holding companies "
            "and property vehicles",
        }[self]

    def includes(self, company: Company) -> bool:
        if self is Population.ALL:
            return True
        if not _is_real_prospect(company):
            return False
        if self is Population.REAL_PROSPECTS:
            return True
        primary_sic = company.sic_codes[0] if company.sic_codes else ""
        return primary_sic not in _HOLDING_AND_PROPERTY_SIC


def _is_real_prospect(company: Company) -> bool:
    if company.company_type not in _PROSPECT_TYPES:
        return False
    if not company.sic_codes or all(code in _NON_TRADING_SIC for code in company.sic_codes):
        return False
    return company.last_accounts_type not in _DORMANT_ACCOUNTS


@dataclass(frozen=True, slots=True)
class Cohort:
    """The companies a study samples from: England and Wales, incorporated between two dates."""

    incorporated_from: date
    incorporated_to: date

    def includes(self, company: Company) -> bool:
        return (
            company.incorporated_on is not None
            and self.incorporated_from <= company.incorporated_on <= self.incorporated_to
        )


def list_as_built(
    companies: Iterable[Company], *, on: date, population: Population
) -> list[Company]:
    """The companies a list built on `on` would have held: open that day, and in the population."""
    return [c for c in companies if c.was_open_on(on) and population.includes(c)]


@dataclass(frozen=True, slots=True)
class DecayPoint:
    """One point on the decay curve: a list built on `list_date`, re-checked later."""

    list_date: date
    list_age_years: float
    size: int
    dissolved: int
    insolvency: int
    striking_off: int

    @property
    def gone_or_going(self) -> int:
        return self.dissolved + self.insolvency + self.striking_off

    @property
    def share_dissolved(self) -> float:
        return self._share(self.dissolved)

    @property
    def share_dissolved_or_insolvent(self) -> float:
        return self._share(self.dissolved + self.insolvency)

    @property
    def share_gone_or_going(self) -> float:
        return self._share(self.gone_or_going)

    @property
    def confidence_interval(self) -> tuple[float, float]:
        """95% Wilson interval for the share gone or going."""
        return wilson_interval(self.gone_or_going, self.size)

    def _share(self, count: int) -> float:
        return count / self.size if self.size else 0.0


def decay_curve(
    companies: Iterable[Company],
    *,
    list_dates: Iterable[date],
    checked_on: date,
    population: Population,
) -> list[DecayPoint]:
    """For a list built on each date, how much of it is gone or going on `checked_on`.

    The same companies are re-used for every list date, so one sample gives the whole curve.
    A company only counts against a list if it was open the day the list was built.
    """
    pool = [company for company in companies if population.includes(company)]
    curve = []
    for list_date in list_dates:
        on_list = [company for company in pool if company.was_open_on(list_date)]
        closing = [company for company in on_list if company.verdict is Verdict.CLOSING]
        curve.append(
            DecayPoint(
                list_date=list_date,
                list_age_years=(checked_on - list_date).days / 365.25,
                size=len(on_list),
                dissolved=sum(company.verdict is Verdict.DISSOLVED for company in on_list),
                insolvency=sum(company.in_insolvency for company in closing),
                striking_off=sum(not company.in_insolvency for company in closing),
            )
        )
    return curve


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """The 95% Wilson score interval for a proportion: honest at small samples and near 0 or 1."""
    if trials == 0:
        return (0.0, 0.0)
    z = 1.96
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    half_width = (z / denominator) * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials**2))
    return (max(0.0, centre - half_width), min(1.0, centre + half_width))


# England and Wales company numbers are eight digits, issued in order. This sits comfortably
# above the highest number issued so far.
NUMBER_SPACE_MAX = 17_000_000
# When a probed number was never issued, try its neighbours before giving up on that spot.
_PROBE_OFFSETS = (0, 1, -1, 2, -2, 5, -5, 10, -10, 20, -20)


def draw_sample(
    register: Register,
    *,
    cohort: Cohort,
    open_on: date,
    size: int,
    seed: int = 42,
    max_lookups: int = 40_000,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[Company]:
    """Draw a random sample of a cohort, dissolved companies included.

    The register's free bulk download leaves dissolved companies out, so a sample taken from it
    can never show decay. Company numbers are issued in order, though, and the API still answers
    for dissolved companies. So: find the band of numbers issued across the cohort's
    incorporation dates, draw numbers from it at random, and keep the companies that were open
    on `open_on`.

    Stops at `size` companies, after `max_lookups` lookups, or when the band runs out.
    `on_progress` is called with (companies kept, lookups made) after every lookup.
    """
    lo = _first_number_incorporated_on_or_after(register, cohort.incorporated_from)
    hi = _first_number_incorporated_on_or_after(
        register, cohort.incorporated_to + timedelta(days=1)
    )
    margin = (hi - lo) // 20  # numbers are only roughly in date order, so widen the band a little
    lo, hi = max(1, lo - margin), min(NUMBER_SPACE_MAX, hi + margin)

    rng = random.Random(seed)
    band_size = hi - lo + 1
    seen: set[int] = set()
    kept: list[Company] = []
    while len(kept) < size and len(seen) < min(band_size, max_lookups):
        number = rng.randint(lo, hi)
        if number in seen:
            continue
        seen.add(number)
        company = register.lookup(_company_number(number))
        if company is not None and cohort.includes(company) and company.was_open_on(open_on):
            kept.append(company)
        if on_progress:
            on_progress(len(kept), len(seen))
    return kept


def _first_number_incorporated_on_or_after(register: Register, day: date) -> int:
    """Binary-search the number space for where companies incorporated on `day` begin."""
    lo, hi = 1, NUMBER_SPACE_MAX
    while lo < hi:
        mid = (lo + hi) // 2
        incorporated = _incorporation_date_near(register, mid)
        if incorporated is not None and incorporated < day:
            lo = mid + 1
        else:  # on or after the day, or nothing issued here yet: the answer is at or below
            hi = mid
    return lo


def _incorporation_date_near(register: Register, number: int) -> date | None:
    for offset in _PROBE_OFFSETS:
        candidate = number + offset
        if 1 <= candidate <= NUMBER_SPACE_MAX:
            company = register.lookup(_company_number(candidate))
            if company is not None and company.incorporated_on is not None:
                return company.incorporated_on
    return None


def _company_number(number: int) -> str:
    """An England and Wales company number in the register's eight-digit form."""
    return f"{number:08d}"
