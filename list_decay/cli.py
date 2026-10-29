"""The list-decay command: `check` a list of UK companies, or rerun the decay `study`."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import TypeVar

from list_decay import render
from list_decay._version import __version__
from list_decay.check import CheckedCompany, check, write_results
from list_decay.company_list import read_company_list
from list_decay.find import Finding, find, write_found
from list_decay.name_list import NoNameColumn, read_name_list
from list_decay.register import (
    API_BASE,
    KEY_URL,
    CachedRegister,
    LiveRegister,
    Register,
    RegisterError,
    SnapshotRegister,
)
from list_decay.study import Cohort, Population, decay_curve, draw_sample, list_as_built

UK_ONLY = (
    "UK-registered companies only: England, Wales, Scotland and Northern Ireland. "
    "Sole traders and ordinary partnerships are not on the register."
)

NO_KEY = f"""no Companies House API key found.

  A key is free and takes two minutes:
    1. Register with the Companies House Developer Hub
    2. Under "Your applications", create one for the live environment
    3. Create a REST key for it, then: export CH_API_KEY=your-key
       (or put CH_API_KEY=your-key in a .env file in this folder)

  Start here: {KEY_URL}

  Or see it work without a key: list-decay check --demo"""

DEMO_LIST_DATE = date(2023, 7, 1)
PUBLISHED_LIST_DATES = [date(2025, 7, 1), date(2024, 7, 1), date(2023, 7, 1)]


class UsageError(Exception):
    """Something the person running the command can fix."""


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "check":
            return _check(args)
        if args.command == "find":
            return _find(args)
        return _study(args)
    except UsageError as error:
        print(f"list-decay: {error}", file=sys.stderr)
        return 2
    except RegisterError as error:
        print(f"list-decay: {error}", file=sys.stderr)
        return 1


def run() -> None:
    try:
        code = main()
        sys.stdout.flush()  # surface a closed pipe here, not at interpreter exit
    except BrokenPipeError:  # output piped into `head` or similar, which stopped reading
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 0
    sys.exit(code)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="list-decay",
        description="Check a list of UK companies against Companies House: "
        "trading, closing or dissolved.",
        epilog=UK_ONLY,
    )
    parser.add_argument("--version", action="version", version=f"list-decay {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    check_cmd = commands.add_parser(
        "check",
        help="check a list of company numbers against the register",
        description="Check every company on a list against Companies House. Reads a CSV or "
        "text file and uses only the company number column. Needs a free API key in CH_API_KEY.",
        epilog=UK_ONLY,
    )
    check_cmd.add_argument("file", nargs="?", type=Path, help="CSV or text file of company numbers")
    check_cmd.add_argument(
        "--demo",
        action="store_true",
        help="check a built-in list of 3,829 companies as they stood on 1 Jul 2023 (no key needed)",
    )
    check_cmd.add_argument("--out", type=Path, metavar="CSV", help="write every result to a CSV")
    check_cmd.add_argument("--names", action="store_true", help="show company names (live only)")
    check_cmd.add_argument("--quiet", action="store_true", help="print the summary only")
    check_cmd.add_argument(
        "--pace", type=float, default=0.0, metavar="SECONDS", help="pause between lines (demos)"
    )

    find_cmd = commands.add_parser(
        "find",
        help="find company numbers from company names",
        description="Find the company number for each company name on a list. A number is "
        "filled in only when it is certain: exactly one company on the register has the name "
        "(Ltd and Limited count as the same, as do '&' and 'and'), and the same registered "
        "postcode where the file has one. Everything else is marked for checking by hand, with "
        "the candidates listed. The file needs a header row naming the company name column. "
        "Needs a free API key in CH_API_KEY.",
        epilog=UK_ONLY,
    )
    find_cmd.add_argument("file", type=Path, help="CSV or text file of company names")
    find_cmd.add_argument(
        "--out",
        type=Path,
        metavar="CSV",
        help="where to write the list with numbers added (default: FILE-numbers.csv)",
    )
    find_cmd.add_argument("--quiet", action="store_true", help="print the summary only")

    study_cmd = commands.add_parser(
        "study",
        help="show how fast a UK company list decays, by list age",
        description="Reproduce the decay curve from the sample bundled with list-decay, or draw "
        "a fresh sample from the live register with --live (needs CH_API_KEY).",
        epilog="The sample is England and Wales companies only. A --live run saves every "
        "lookup as it goes, so it can be stopped and resumed the same day.",
    )
    study_cmd.add_argument(
        "--live", action="store_true", help="draw a new sample from the register"
    )
    study_cmd.add_argument("--size", type=int, default=5000, help="companies to sample (live)")
    study_cmd.add_argument("--seed", type=int, default=42, help="random seed (live)")
    study_cmd.add_argument(
        "--incorporated",
        nargs=2,
        type=_date,
        default=[date(2016, 1, 1), date(2021, 12, 31)],
        metavar=("FROM", "TO"),
        help="the cohort's incorporation dates (live, default 2016 to 2021)",
    )
    study_cmd.add_argument(
        "--list-dates",
        type=_dates,
        metavar="DATES",
        help="comma-separated dates the lists were built on (live, default 1, 2 and 3 years ago)",
    )
    study_cmd.add_argument(
        "--cache",
        type=Path,
        default=Path(".list-decay-cache"),
        help="folder for a live run's saved lookups and its sample",
    )
    return parser


def _check(args: argparse.Namespace) -> int:
    if args.demo == bool(args.file):
        raise UsageError("give a file of company numbers, or --demo, but not both")

    register: Register
    if args.demo:
        register = snapshot = SnapshotRegister.bundled()
        demo = list_as_built(
            snapshot.companies, on=DEMO_LIST_DATE, population=Population.REAL_PROSPECTS
        )
        numbers = [company.number for company in demo]
        notes = [f"Demo: a list of companies trading on {render.format_date(DEMO_LIST_DATE)}"]
    else:
        if not args.file.is_file():
            raise UsageError(f"can't find {args.file}")
        listing = read_company_list(args.file)
        if not listing.numbers:
            raise UsageError(f"no company numbers found in {args.file}")
        register = LiveRegister(_api_key(), base_url=API_BASE)
        numbers = listing.numbers
        notes = render.list_notes(listing, args.file.name)

    paint = render.Painter(sys.stdout)
    print(render.check_header(paint, len(numbers), register.source, notes))
    results: list[CheckedCompany] = _stream(
        check(numbers, register),
        paint,
        total=len(numbers),
        line=None if args.quiet else lambda r: render.check_line(paint, r, show_name=args.names),
        pace=args.pace,
    )
    print(render.check_summary(paint, results))

    if args.out:
        write_results(args.out, results)
        print(paint(f"  Results written to {args.out}\n", render.DIM))
    return 0


def _find(args: argparse.Namespace) -> int:
    if not args.file.is_file():
        raise UsageError(f"can't find {args.file}")
    try:
        names = read_name_list(args.file)
    except NoNameColumn as error:
        raise UsageError(f"{args.file}: {error}") from None
    if not names.records:
        raise UsageError(f"no company names found in {args.file}")
    register = LiveRegister(_api_key(), base_url=API_BASE)
    out = args.out or args.file.with_name(f"{args.file.stem}-numbers.csv")

    paint = render.Painter(sys.stdout)
    print(render.find_header(paint, names, args.file.name))
    findings: list[Finding] = _stream(
        find(names.companies, register),
        paint,
        total=len(names.records),
        line=None if args.quiet else lambda f: render.find_line(paint, f),
    )
    write_found(out, names, findings)
    print(render.find_summary(paint, findings, rows=len(names.records), written_to=str(out)))
    return 0


Item = TypeVar("Item")


def _stream(
    items: Iterable[Item],
    paint: render.Painter,
    *,
    total: int,
    line: Callable[[Item], str] | None,
    pace: float = 0.0,
) -> list[Item]:
    """Collect results as they arrive, printing each with `line` unless it is None.

    Ctrl-C stops the run and keeps everything that came back, so the summary and any output
    file still cover the companies already checked.
    """
    collected: list[Item] = []
    try:
        for item in items:
            collected.append(item)
            if line is not None:
                print(line(item), flush=True)
                time.sleep(pace)
    except KeyboardInterrupt:
        print(paint(render.stopped(len(collected), total), render.BOLD))
    if line is not None:
        print()
    return collected


def _study(args: argparse.Namespace) -> int:
    paint = render.Painter(sys.stdout)
    if not args.live:
        snapshot = SnapshotRegister.bundled()
        companies, checked_on, list_dates = (
            snapshot.companies,
            snapshot.checked_on,
            PUBLISHED_LIST_DATES,
        )
        source = snapshot.source
        note = (
            f"{len(companies):,} England and Wales companies incorporated 2016 to 2021, "
            "drawn at random from the register"
        )
    else:
        checked_on = date.today()
        list_dates = args.list_dates or [_years_before(checked_on, n) for n in (1, 2, 3)]
        cohort = Cohort(*args.incorporated)
        args.cache.mkdir(parents=True, exist_ok=True)
        # One lookup file per day: a resumed run is free, but a later run asks the register
        # again rather than passing off old answers as today's.
        lookups = args.cache / f"lookups-{checked_on.isoformat()}.jsonl"
        register = CachedRegister(LiveRegister(_api_key()), lookups)
        companies = draw_sample(
            register,
            cohort=cohort,
            open_on=min(list_dates),
            size=args.size,
            seed=args.seed,
            on_progress=_progress(args.size),
        )
        print(file=sys.stderr)
        saved = args.cache / f"sample-{checked_on.isoformat()}.csv"
        SnapshotRegister(companies, checked_on).to_csv(saved)
        source = f"the live Companies House register, {render.format_date(checked_on)}"
        note = (
            f"{len(companies):,} England and Wales companies incorporated "
            f"{cohort.incorporated_from.year} to {cohort.incorporated_to.year}, "
            f"drawn at random. Sample saved to {saved}"
        )

    curves = {
        population: decay_curve(
            companies, list_dates=list_dates, checked_on=checked_on, population=population
        )
        for population in Population
    }
    print(render.study_report(paint, source=source, sample_note=note, curves=curves))
    return 0


def _api_key() -> str:
    key = os.environ.get("CH_API_KEY", "").strip()
    if not key and Path(".env").is_file():
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip().removeprefix("export ") == "CH_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        raise UsageError(NO_KEY)
    return key


def _progress(target: int) -> Callable[[int, int], None]:
    def report(kept: int, lookups: int) -> None:
        if lookups % 10 == 0 or kept == target:
            print(f"\r  kept {kept:,} of {target:,}, {lookups:,} lookups", end="", file=sys.stderr)

    return report


def _date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text}") from None


def _dates(text: str) -> list[date]:
    return [_date(part.strip()) for part in text.split(",") if part.strip()]


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)
