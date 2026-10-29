"""Seam (b): checking a list against a register, live or saved, and counting what comes back."""

from datetime import date
from pathlib import Path

import pytest
from conftest import TEST_KEY, FakeCompaniesHouse

from list_decay import (
    LiveRegister,
    Population,
    SnapshotRegister,
    Tally,
    Verdict,
    check,
    list_as_built,
)

SNAPSHOT = """\
company_number,company_status,company_status_detail,date_of_creation,date_of_cessation,type,sic_codes,last_accounts_type,checked_on
00000001,active,,2017-03-15,,ltd,62020,total-exemption-full,2026-07-20
00000002,dissolved,,2016-05-01,2024-03-12,ltd,62020,micro-entity,2026-07-20
00000003,liquidation,,2018-01-01,,ltd,43999,micro-entity,2026-07-20
00000004,active,active-proposal-to-strike-off,2019-01-01,,ltd,70229,micro-entity,2026-07-20
SC000005,administration,,2016-02-02,,ltd,47110,full,2026-07-20
"""

NUMBERS = ["00000001", "00000002", "00000003", "00000004", "SC000005"]


@pytest.fixture
def register(tmp_path: Path) -> SnapshotRegister:
    path = tmp_path / "snapshot.csv"
    path.write_text(SNAPSHOT, encoding="utf-8")
    return SnapshotRegister.from_csv(path)


def test_every_company_gets_a_verdict_from_the_register(register: SnapshotRegister) -> None:
    verdicts = [result.verdict for result in check(NUMBERS, register)]
    assert verdicts == [
        Verdict.TRADING,
        Verdict.DISSOLVED,
        Verdict.CLOSING,
        Verdict.CLOSING,
        Verdict.CLOSING,
    ]


def test_a_closing_company_says_how_it_is_closing(register: SnapshotRegister) -> None:
    reasons = [r.closing_reason for r in check(NUMBERS, register) if r.verdict is Verdict.CLOSING]
    assert reasons == ["liquidation", "being struck off", "administration"]


def test_a_dissolved_company_says_when(register: SnapshotRegister) -> None:
    [result] = check(["00000002"], register)
    assert result.dissolved_on == date(2024, 3, 12)


def test_a_number_the_register_does_not_know_is_not_found(register: SnapshotRegister) -> None:
    [result] = check(["09999999"], register)
    assert result.verdict is Verdict.NOT_FOUND


def test_the_tally_leaves_unfound_numbers_out_of_the_share(register: SnapshotRegister) -> None:
    tally = Tally.of(check([*NUMBERS, "09999999"], register))
    assert (tally.trading, tally.closing, tally.dissolved, tally.not_found) == (1, 3, 1, 1)
    assert tally.gone_or_going == 4
    assert tally.found == 5
    assert tally.share_gone_or_going == pytest.approx(0.8)


def test_the_live_register_gives_the_same_verdicts(companies_house: FakeCompaniesHouse) -> None:
    companies_house.add({"company_number": "00000001", "company_status": "active", "type": "ltd"})
    companies_house.add(
        {
            "company_number": "00000002",
            "company_status": "dissolved",
            "date_of_cessation": "2024-03-12",
        }
    )
    companies_house.add(
        {
            "company_number": "00000004",
            "company_status": "active",
            "company_status_detail": "active-proposal-to-strike-off",
        }
    )
    live = LiveRegister(TEST_KEY, base_url=companies_house.url, sleep=lambda _: None)
    results = list(check(["00000001", "00000002", "00000004", "09999999"], live))
    assert [r.verdict for r in results] == [
        Verdict.TRADING,
        Verdict.DISSOLVED,
        Verdict.CLOSING,
        Verdict.NOT_FOUND,
    ]
    assert results[1].dissolved_on == date(2024, 3, 12)
    assert results[2].closing_reason == "being struck off"


def test_the_demo_reproduces_the_published_run() -> None:
    # The 23 Oct 2026 post: 3,829 companies trading in July 2023, re-checked three years on.
    register = SnapshotRegister.bundled()
    demo = list_as_built(
        register.companies, on=date(2023, 7, 1), population=Population.REAL_PROSPECTS
    )
    tally = Tally.of(check([company.number for company in demo], register))
    assert tally.found == 3829
    assert (tally.trading, tally.closing, tally.dissolved) == (2589, 389, 851)
