"""Smoke runs of each command, end to end, as someone would type them."""

import csv
from pathlib import Path

import pytest
from conftest import TEST_KEY, FakeCompaniesHouse

from list_decay.cli import main


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CH_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # so no stray .env file is picked up


def test_the_demo_shows_the_published_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", "--demo", "--quiet"]) == 0
    output = capsys.readouterr().out
    assert "Checking 3,829 companies" in output
    assert "1,240 of 3,829 are gone or going: 32%, or 1 in 3." in output


def test_the_demo_writes_every_result_to_a_csv(tmp_path: Path) -> None:
    out = tmp_path / "results.csv"
    assert main(["check", "--demo", "--quiet", "--out", str(out)]) == 0
    with out.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3829
    assert sum(row["verdict"] == "dissolved" for row in rows) == 851


def test_the_study_reproduces_the_headline(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["study"]) == 0
    output = capsys.readouterr().out
    assert "32.4%" in output
    assert "30.9-33.9%" in output


def test_checking_a_real_list_without_a_key_explains_how_to_get_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    listing = tmp_path / "list.csv"
    listing.write_text("company_number\n08500000\n", encoding="utf-8")
    assert main(["check", str(listing)]) == 2
    error = capsys.readouterr().err
    assert "API key" in error
    assert "list-decay check --demo" in error


def test_a_missing_file_is_a_clear_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", "nowhere.csv"]) == 2
    assert "nowhere.csv" in capsys.readouterr().err


def test_names_never_run_into_the_verdict(
    companies_house: FakeCompaniesHouse,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    companies_house.add(
        {
            "company_number": "09955390",
            "company_name": "EXAMPLE COURIERS LTD",
            "company_status": "dissolved",
            "date_of_cessation": "2024-09-03",
        }
    )
    monkeypatch.setenv("CH_API_KEY", TEST_KEY)
    monkeypatch.setattr("list_decay.cli.API_BASE", companies_house.url)
    listing = tmp_path / "list.csv"
    listing.write_text("09955390\n", encoding="utf-8")
    assert main(["check", str(listing), "--names"]) == 0
    assert "dissolved Sep 2024  EXAMPLE COURIERS LTD" in capsys.readouterr().out
