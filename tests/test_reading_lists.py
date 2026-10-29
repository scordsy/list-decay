"""Seam (a): reading a list as it arrives from a spreadsheet or a CRM export."""

from pathlib import Path

import pytest

from list_decay import normalise_company_number, read_company_list


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("08500000", "08500000"),
        ("8500000", "08500000"),  # a spreadsheet dropped the leading zero
        ("8500000.0", "08500000"),  # the column was read as a decimal
        ("'08500000", "08500000"),  # Excel's force-text apostrophe
        (" 0850 0000 ", "08500000"),
        ("SC123456", "SC123456"),
        ("sc 12345", "SC012345"),  # Scotland, lowercase, short
        ("NI012345", "NI012345"),
        ("OC301234", "OC301234"),  # an LLP
        ("R0012345", "R0012345"),  # an older Northern Ireland number
    ],
)
def test_company_numbers_come_out_in_register_form(raw: str, expected: str) -> None:
    assert normalise_company_number(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "Acme Ltd", "123456789", "8.5E+06", "SC1234567"])
def test_anything_that_is_not_a_company_number_is_refused(raw: str) -> None:
    assert normalise_company_number(raw) is None


def write(tmp_path: Path, text: str, name: str = "list.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_the_number_column_is_found_by_its_header(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "Company name,Company Number,Domain\n"
        "Acme Ltd,08500000,acme.co.uk\n"
        "Bravo Ltd,SC123456,bravo.co.uk\n",
    )
    assert read_company_list(path).numbers == ["08500000", "SC123456"]


def test_a_headerless_file_uses_the_first_column(tmp_path: Path) -> None:
    path = write(tmp_path, "08500000\n10673043\n", name="numbers.txt")
    assert read_company_list(path).numbers == ["08500000", "10673043"]


def test_semicolon_separated_exports_are_read(tmp_path: Path) -> None:
    path = write(tmp_path, "name;crn\nAcme Ltd;8500000\n")
    assert read_company_list(path).numbers == ["08500000"]


def test_duplicates_are_checked_once_and_counted(tmp_path: Path) -> None:
    path = write(tmp_path, "company_number\n08500000\n8500000\n08500000\n")
    result = read_company_list(path)
    assert result.numbers == ["08500000"]
    assert result.duplicates == 2


def test_unreadable_rows_are_reported_with_their_line_number(tmp_path: Path) -> None:
    path = write(tmp_path, "company_number\n08500000\nnot a number\n\n10673043\n")
    result = read_company_list(path)
    assert result.numbers == ["08500000", "10673043"]
    assert result.unreadable == [(3, "not a number")]


def test_an_excel_export_with_a_byte_order_mark_is_read(tmp_path: Path) -> None:
    path = tmp_path / "excel.csv"
    path.write_bytes("\ufeffcompany_number\n08500000\n".encode())
    assert read_company_list(path).numbers == ["08500000"]


def test_a_latin1_export_is_read(tmp_path: Path) -> None:
    path = tmp_path / "latin1.csv"
    path.write_bytes("name,company_number\nCaf\xe9 Ltd,08500000\n".encode("latin-1"))
    assert read_company_list(path).numbers == ["08500000"]


def test_rows_with_no_number_yet_are_counted_not_flagged(tmp_path: Path) -> None:
    path = write(tmp_path, "name,company_number\nAcme Ltd,08500000\nBravo Ltd,\n")
    result = read_company_list(path)
    assert result.numbers == ["08500000"]
    assert (result.blank, result.unreadable) == (1, [])
