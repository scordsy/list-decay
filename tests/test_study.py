"""Seam (d): the decay study, from drawing a sample to the curve it produces."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from list_decay import Cohort, Company, Population, SnapshotRegister, decay_curve, draw_sample

CHECKED_ON = date(2026, 7, 20)
LIST_DATES = [date(2025, 7, 1), date(2024, 7, 1), date(2023, 7, 1)]

# Printed by the original study run on 20 Jul 2026 (the July summary and robustness tables).
# Per list date: companies on the list, % dissolved, % dissolved or in insolvency,
# % gone or going (adds companies being struck off).
PUBLISHED = {
    Population.ALL: [
        (4026, 10.6, 12.4, 23.3),
        (4467, 19.4, 21.1, 30.9),
        (5000, 28.0, 29.5, 38.3),
    ],
    Population.REAL_PROSPECTS: [
        (3260, 8.7, 10.7, 20.6),
        (3550, 16.1, 18.0, 27.1),
        (3829, 22.2, 24.0, 32.4),
    ],
    Population.OPERATING_BUSINESSES: [
        (2760, 9.1, 11.4, 22.5),
        (3032, 17.2, 19.3, 29.5),
        (3294, 23.8, 25.7, 35.1),
    ],
}


@pytest.mark.parametrize("population", list(Population))
def test_the_bundled_sample_reproduces_the_published_curve(population: Population) -> None:
    register = SnapshotRegister.bundled()
    curve = decay_curve(
        register.companies, list_dates=LIST_DATES, checked_on=CHECKED_ON, population=population
    )
    measured = [
        (
            point.size,
            round(point.share_dissolved * 100, 1),
            round(point.share_dissolved_or_insolvent * 100, 1),
            round(point.share_gone_or_going * 100, 1),
        )
        for point in curve
    ]
    assert measured == PUBLISHED[population]


def test_the_headline_carries_its_published_confidence_interval() -> None:
    curve = decay_curve(
        SnapshotRegister.bundled().companies,
        list_dates=[date(2023, 7, 1)],
        checked_on=CHECKED_ON,
        population=Population.REAL_PROSPECTS,
    )
    low, high = curve[0].confidence_interval
    assert (round(low * 100, 1), round(high * 100, 1)) == (30.9, 33.9)
    assert round(curve[0].list_age_years, 1) == 3.1


# A small invented register for the sampler: one company a day from 1 Jan 2015, numbered in
# order, with every seventh number never issued and every fifth company dissolved in 2022.
START = date(2015, 1, 1)


def invented_register(size: int = 3000) -> SnapshotRegister:
    companies = [
        Company(
            number=f"{n:08d}",
            status="dissolved" if n % 5 == 0 else "active",
            incorporated_on=START + timedelta(days=n),
            dissolved_on=date(2022, 6, 1) if n % 5 == 0 else None,
            company_type="ltd",
            sic_codes=("62020",),
            last_accounts_type="micro-entity",
        )
        for n in range(1, size)
        if n % 7
    ]
    return SnapshotRegister(companies, checked_on=CHECKED_ON)


def sample(seed: int = 7) -> list[Company]:
    return draw_sample(
        invented_register(),
        cohort=Cohort(date(2016, 1, 1), date(2017, 12, 31)),
        open_on=date(2023, 7, 1),
        size=200,
        seed=seed,
    )


def test_the_sample_holds_only_the_cohort_open_on_the_list_date() -> None:
    drawn = sample()
    assert len(drawn) == 200
    assert len({company.number for company in drawn}) == 200
    for company in drawn:
        assert company.incorporated_on is not None
        assert date(2016, 1, 1) <= company.incorporated_on <= date(2017, 12, 31)
        assert company.was_open_on(date(2023, 7, 1))


def test_the_same_seed_draws_the_same_sample() -> None:
    assert sample(seed=7) == sample(seed=7)
    assert sample(seed=7) != sample(seed=8)


def test_a_cohort_too_small_for_the_sample_stops_rather_than_looping() -> None:
    drawn = draw_sample(
        invented_register(),
        cohort=Cohort(date(2016, 1, 1), date(2016, 1, 31)),
        open_on=date(2023, 7, 1),
        size=500,
        seed=1,
    )
    assert 0 < len(drawn) < 500
