"""Seam (e): finding company numbers from company names, against a fake Companies House."""

from pathlib import Path

import pytest
from conftest import TEST_KEY, FakeCompaniesHouse

from list_decay import (
    Finding,
    FindOutcome,
    ListedCompany,
    LiveRegister,
    MatchedOn,
    NoNameColumn,
    find,
    read_company_list,
    read_name_list,
    write_found,
)

CURLY_APOSTROPHE = chr(0x2019)
E_ACUTE = chr(0xE9)


def company(number: str, name: str, postcode: str, status: str = "active") -> dict[str, object]:
    return {
        "company_number": number,
        "company_name": name,
        "company_status": status,
        "registered_office_address": {"postal_code": postcode},
    }


@pytest.fixture
def register(companies_house: FakeCompaniesHouse) -> LiveRegister:
    return LiveRegister(TEST_KEY, base_url=companies_house.url, sleep=lambda _: None)


def find_one(register: LiveRegister, name: str, postcode: str = "") -> Finding:
    [finding] = find([ListedCompany(name, postcode)], register)
    return finding


@pytest.mark.parametrize(
    "name",
    ["TGP Couriers Ltd", "tgp couriers limited", "The TGP Couriers Ltd.", "TGP Couriers"],
)
def test_a_name_only_one_company_has_is_matched_on_name(
    companies_house: FakeCompaniesHouse, register: LiveRegister, name: str
) -> None:
    companies_house.add(company("09955390", "TGP COURIERS LTD", "BH2 5PS", "dissolved"))
    finding = find_one(register, name)
    assert (finding.outcome, finding.number, finding.matched_on) == (
        FindOutcome.MATCHED,
        "09955390",
        MatchedOn.NAME,
    )


@pytest.mark.parametrize("postcode", ["BH2 5PS", "bh25ps"])
def test_a_postcode_that_agrees_confirms_the_match(
    companies_house: FakeCompaniesHouse, register: LiveRegister, postcode: str
) -> None:
    companies_house.add(company("09955390", "TGP COURIERS LTD", "BH2 5PS"))
    finding = find_one(register, "TGP Couriers Ltd", postcode)
    assert (finding.outcome, finding.matched_on) == (
        FindOutcome.MATCHED,
        MatchedOn.NAME_AND_POSTCODE,
    )


@pytest.mark.parametrize("postcode", ["SW1A 1AA", "BH2"])
def test_a_postcode_that_is_different_or_partial_goes_to_check_by_hand(
    companies_house: FakeCompaniesHouse, register: LiveRegister, postcode: str
) -> None:
    # The register holds the registered office, often an accountant's, so a person decides.
    companies_house.add(company("09955390", "TGP COURIERS LTD", "BH2 5PS"))
    finding = find_one(register, "TGP Couriers Ltd", postcode)
    assert (finding.outcome, finding.number) == (FindOutcome.CHECK_BY_HAND, None)
    assert [c.number for c in finding.candidates] == ["09955390"]


@pytest.mark.parametrize("postcode", ["", "LS1 1AA"])
def test_namesakes_always_go_to_check_by_hand(
    companies_house: FakeCompaniesHouse, register: LiveRegister, postcode: str
) -> None:
    companies_house.add(company("01111111", "ACME WIDGETS LIMITED", "M1 1AA", "dissolved"))
    companies_house.add(company("02222222", "ACME WIDGETS LTD", "LS1 1AA"))
    finding = find_one(register, "Acme Widgets Ltd", postcode)
    assert (finding.outcome, finding.number) == (FindOutcome.CHECK_BY_HAND, None)
    assert {c.number for c in finding.candidates} == {"01111111", "02222222"}


def test_namesakes_list_the_one_whose_postcode_agrees_first(
    companies_house: FakeCompaniesHouse, register: LiveRegister
) -> None:
    companies_house.add(company("01111111", "ACME WIDGETS LIMITED", "M1 1AA", "dissolved"))
    companies_house.add(company("02222222", "ACME WIDGETS LTD", "LS1 1AA"))
    finding = find_one(register, "Acme Widgets Ltd", "LS1 1AA")
    assert finding.candidates[0].number == "02222222"


def test_every_namesake_is_listed(
    companies_house: FakeCompaniesHouse, register: LiveRegister
) -> None:
    for n in range(5):
        companies_house.add(company(f"0300000{n}", "ACME WIDGETS LIMITED", f"M{n} 1AA"))
    assert len(find_one(register, "Acme Widgets Ltd").candidates) == 5


@pytest.mark.parametrize("name", ["Acme LLP", "Acme PLC", "Acme CIC"])
def test_a_different_legal_form_is_never_a_match(
    companies_house: FakeCompaniesHouse, register: LiveRegister, name: str
) -> None:
    companies_house.add(company("04444444", "ACME LIMITED", "B1 1AA"))
    finding = find_one(register, name)
    assert (finding.outcome, finding.number) == (FindOutcome.CHECK_BY_HAND, None)
    assert [c.number for c in finding.candidates] == ["04444444"]


@pytest.mark.parametrize(
    ("listed", "registered"),
    [
        ("Acme & Sons Ltd", "ACME AND SONS LIMITED"),
        ("Acme (UK) Ltd", "ACME (UK) LIMITED"),
        (f"O{CURLY_APOSTROPHE}Brien{CURLY_APOSTROPHE}s Bakery Ltd", "O'BRIEN'S BAKERY LIMITED"),
        (f"Caf{E_ACUTE} Rouge Ltd", "CAFE ROUGE LIMITED"),
        ("Acme Cyfyngedig", "ACME LIMITED"),
        ("Acme Public Limited Company", "ACME PLC"),
    ],
)
def test_spelling_differences_that_name_the_same_company(
    companies_house: FakeCompaniesHouse, register: LiveRegister, listed: str, registered: str
) -> None:
    companies_house.add(company("05555555", registered, "B1 1AA"))
    assert find_one(register, listed).number == "05555555"


def test_a_near_miss_is_no_match_but_shows_the_closest(
    companies_house: FakeCompaniesHouse, register: LiveRegister
) -> None:
    companies_house.add(company("12780627", "AC TGP I LIMITED", "W1K 4DG"))
    finding = find_one(register, "TGP Couriers Ltd")
    assert (finding.outcome, finding.number) == (FindOutcome.NO_MATCH, None)
    assert [c.number for c in finding.candidates] == ["12780627"]


def test_a_blank_name_is_no_match_without_a_search(
    companies_house: FakeCompaniesHouse, register: LiveRegister
) -> None:
    assert find_one(register, "  ").outcome is FindOutcome.NO_MATCH
    assert companies_house.requests == []


def test_each_name_is_searched_once(
    companies_house: FakeCompaniesHouse, register: LiveRegister
) -> None:
    companies_house.add(company("09955390", "TGP COURIERS LTD", "BH2 5PS"))
    listed = [ListedCompany("TGP Couriers Ltd"), ListedCompany("TGP Couriers Limited")]
    assert [f.number for f in find(listed, register)] == ["09955390", "09955390"]
    assert len(companies_house.requests) == 1


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "crm-export.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_find_output_goes_straight_into_check(
    companies_house: FakeCompaniesHouse, register: LiveRegister, tmp_path: Path
) -> None:
    companies_house.add(company("09955390", "TGP COURIERS LTD", "BH2 5PS"))
    names = read_name_list(
        write(
            tmp_path,
            "Account Name,Billing Postcode,Owner\n"
            "TGP Couriers Ltd,BH2 5PS,Sam\n"
            '"Smith, Jones & Co Ltd",,Alex\n',
        )
    )
    assert (names.name_column, names.postcode_column) == ("Account Name", "Billing Postcode")
    assert names.companies[1].name == "Smith, Jones & Co Ltd"

    out = tmp_path / "with-numbers.csv"
    write_found(out, names, list(find(names.companies, register)))

    assert read_company_list(out).numbers == ["09955390"]
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert (
        header == "Account Name,Billing Postcode,Owner,company_number,match,matched_on,candidates"
    )


def test_an_existing_number_column_has_its_gaps_filled(
    companies_house: FakeCompaniesHouse, register: LiveRegister, tmp_path: Path
) -> None:
    companies_house.add(company("09955390", "TGP COURIERS LTD", "BH2 5PS"))
    names = read_name_list(
        write(tmp_path, "Company Name,Company Number\nTGP Couriers Ltd,\nAcme Ltd,8500000\n")
    )
    findings = list(find(names.companies, register))
    assert [f.outcome for f in findings] == [FindOutcome.MATCHED, FindOutcome.ALREADY_NUMBERED]
    assert len(companies_house.requests) == 1

    out = tmp_path / "with-numbers.csv"
    write_found(out, names, findings)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Company Name,Company Number,match,matched_on,candidates"
    assert lines[1].startswith("TGP Couriers Ltd,09955390,matched")
    assert lines[2].startswith("Acme Ltd,8500000,already had a number")  # left as it was


def test_a_stopped_run_keeps_every_row(tmp_path: Path) -> None:
    names = read_name_list(write(tmp_path, "Company Name\nTGP Couriers Ltd\nAcme Ltd\n"))
    out = tmp_path / "with-numbers.csv"
    write_found(out, names, [])
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[1:] == ["TGP Couriers Ltd,,not searched,,", "Acme Ltd,,not searched,,"]


@pytest.mark.parametrize(
    "text",
    [
        "TGP Couriers Ltd\nAcme Ltd\n",  # no header at all
        "Firm Size,Employees\nTGP Couriers Ltd,12\n",  # no header that names the company
        "Name,Job Title\nJohn Smith,Director\n",  # a contacts export: "Name" is a person
    ],
)
def test_a_file_without_a_company_name_header_is_refused(tmp_path: Path, text: str) -> None:
    with pytest.raises(NoNameColumn):
        read_name_list(write(tmp_path, text))
