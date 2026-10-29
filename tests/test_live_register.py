"""Seam (c): the live Companies House connection, run against a fake Companies House."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import TEST_KEY, FakeCompaniesHouse

from list_decay import ApiKeyRejected, CachedRegister, LiveRegister, RegisterUnavailable, Verdict

PROFILE = {
    "company_number": "08500000",
    "company_name": "EXAMPLE TRADING LIMITED",
    "company_status": "active",
    "date_of_creation": "2013-04-15",
    "type": "ltd",
    "sic_codes": ["62020"],
    "accounts": {"last_accounts": {"type": "total-exemption-full"}},
}


class FakeClock:
    """Stands in for time: sleeping moves the clock forward instead of waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def register(fake: FakeCompaniesHouse, clock: FakeClock, key: str = TEST_KEY) -> LiveRegister:
    return LiveRegister(key, base_url=fake.url, sleep=clock.sleep, clock=clock.monotonic)


def test_a_company_on_the_register_comes_back_with_its_verdict(
    companies_house: FakeCompaniesHouse,
) -> None:
    companies_house.add(PROFILE)
    company = register(companies_house, FakeClock()).lookup("08500000")
    assert company is not None
    assert company.name == "EXAMPLE TRADING LIMITED"
    assert company.verdict is Verdict.TRADING


def test_a_number_the_register_has_never_issued_is_none(
    companies_house: FakeCompaniesHouse,
) -> None:
    assert register(companies_house, FakeClock()).lookup("09999999") is None


def test_lookups_are_paced_under_the_rate_limit(companies_house: FakeCompaniesHouse) -> None:
    # Companies House allows 600 requests in five minutes: two a second, at most.
    companies_house.add(PROFILE)
    clock = FakeClock()
    live = register(companies_house, clock)
    for _ in range(3):
        live.lookup("08500000")
    assert len(clock.slept) == 2
    assert all(gap >= 0.5 for gap in clock.slept)


def test_being_rate_limited_waits_as_told_then_carries_on(
    companies_house: FakeCompaniesHouse,
) -> None:
    companies_house.add(PROFILE)
    companies_house.respond("08500000", (429, {"Retry-After": "30"}), (200, {}))
    clock = FakeClock()
    assert register(companies_house, clock).lookup("08500000") is not None
    assert 30 in clock.slept


def test_a_server_error_is_retried(companies_house: FakeCompaniesHouse) -> None:
    companies_house.add(PROFILE)
    companies_house.respond("08500000", (503, {}), (502, {}), (200, {}))
    assert register(companies_house, FakeClock()).lookup("08500000") is not None


def test_a_register_that_stays_down_stops_with_a_clear_error(
    companies_house: FakeCompaniesHouse,
) -> None:
    companies_house.respond("08500000", (503, {}))
    with pytest.raises(RegisterUnavailable, match="503") as error:
        register(companies_house, FakeClock()).lookup("08500000")
    assert TEST_KEY not in str(error.value)


def test_a_rejected_key_stops_at_once_without_echoing_the_key(
    companies_house: FakeCompaniesHouse,
) -> None:
    wrong = "wrong-key-not-a-secret"
    with pytest.raises(ApiKeyRejected) as error:
        register(companies_house, FakeClock(), key=wrong).lookup("08500000")
    assert len(companies_house.requests) == 1
    assert wrong not in str(error.value)
    assert wrong not in repr(register(companies_house, FakeClock(), key=wrong))


def test_a_cached_register_resumes_without_asking_twice(
    companies_house: FakeCompaniesHouse, tmp_path: Path
) -> None:
    companies_house.add(PROFILE)
    cache = tmp_path / "lookups.jsonl"
    first_run = CachedRegister(register(companies_house, FakeClock()), cache)
    first_run.lookup("08500000")
    first_run.lookup("09999999")

    rerun = CachedRegister(register(companies_house, FakeClock()), cache)
    company = rerun.lookup("08500000")
    assert company is not None
    assert company.name == "EXAMPLE TRADING LIMITED"
    assert rerun.lookup("09999999") is None
    assert len(companies_house.requests) == 2
