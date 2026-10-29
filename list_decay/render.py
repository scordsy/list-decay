"""Terminal output. Coloured on a terminal, plain when piped, never coloured if NO_COLOR is set."""

from __future__ import annotations

import math
import os
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import TextIO

from list_decay.check import CheckedCompany, Tally
from list_decay.company import Verdict
from list_decay.company_list import CompanyList
from list_decay.register import LOOKUPS_PER_SECOND
from list_decay.study import DecayPoint, Population

BOLD, DIM, RED, AMBER, GREEN = "1", "2", "1;31", "1;33", "32"


class Painter:
    """Wraps text in ANSI colour codes, or leaves it alone when colour is off.

    Falls back to plain ASCII rules and dots on a stream that can't encode them, such as a
    Windows console piped to a file.
    """

    def __init__(self, stream: TextIO) -> None:
        if os.environ.get("NO_COLOR"):
            self.enabled = False
        else:
            self.enabled = bool(os.environ.get("FORCE_COLOR")) or stream.isatty()
        try:
            "─·".encode(stream.encoding or "ascii")
            fancy = True
        except (LookupError, UnicodeEncodeError):
            fancy = False
        self.rule = ("─" if fancy else "-") * 46
        self.dot = "·" if fancy else "."

    def __call__(self, text: str, style: str) -> str:
        return f"\033[{style}m{text}\033[0m" if self.enabled else text


def format_date(value: date) -> str:
    """20 Jul 2026."""
    return f"{value.day} {value:%b %Y}"


def format_interval(low: float, high: float) -> str:
    """30.9-33.9%."""
    return f"{low * 100:.1f}-{high * 100:.1f}%"


# ---------------------------------------------------------------------------- check


def check_header(paint: Painter, count: int, source: str, notes: Sequence[str]) -> str:
    lines = ["", paint(f"  Checking {count:,} companies against {source}", BOLD)]
    lines += [paint(f"  {note}", DIM) for note in notes]
    return "\n".join([*lines, ""])


def list_notes(listing: CompanyList, file_name: str) -> list[str]:
    """What the reader should know about their file before the results start."""
    column = f', column "{listing.column}"' if listing.column else ""
    minutes = math.ceil(len(listing.numbers) / LOOKUPS_PER_SECOND / 60)
    duration = "under a minute" if minutes <= 1 else f"{minutes} minutes"
    notes = [f"{file_name}{column}. Takes {duration} at Companies House's rate limit."]
    if listing.duplicates:
        notes.append(f"Skipped {listing.duplicates:,} duplicates.")
    if listing.unreadable:
        lines = ", ".join(str(line) for line, _ in listing.unreadable[:5])
        more = ", ..." if len(listing.unreadable) > 5 else ""
        notes.append(
            f"{len(listing.unreadable):,} rows had no readable company number "
            f"(lines {lines}{more})."
        )
    return notes


def check_line(paint: Painter, result: CheckedCompany, *, show_name: bool) -> str:
    mark, style, label, detail = _describe(result, paint.dot)
    name = result.name[:40] if show_name else ""
    line = f"  {result.number}  {paint(mark, style)}  "
    if not detail and not name:
        return line + paint(label, style)
    line += paint(label.ljust(17), style) + paint(detail.ljust(20) if name else detail, DIM)
    return line + (paint(name, DIM) if name else "")


def _describe(result: CheckedCompany, dot: str) -> tuple[str, str, str, str]:
    """(mark, style, label, detail) for one result. The one place a verdict becomes words."""
    match result.verdict:
        case Verdict.TRADING:
            return dot, DIM, "trading", ""
        case Verdict.CLOSING:
            return "!", AMBER, (result.closing_reason or "closing").upper(), ""
        case Verdict.DISSOLVED:
            when = f"dissolved {result.dissolved_on:%b %Y}" if result.dissolved_on else ""
            return "x", RED, "DISSOLVED", when
        case Verdict.NOT_FOUND:
            return "?", DIM, "not found", "check the number"
        case Verdict.UNCLEAR:
            return "?", DIM, "unclear", f"the register says '{result.register_status}'"


def check_summary(paint: Painter, results: Sequence[CheckedCompany]) -> str:
    tally = Tally.of(results)
    # The same split as the study: formal insolvency, or the register striking the company off.
    routes = Counter(
        "insolvency" if r.in_insolvency else r.closing_reason
        for r in results
        if r.verdict is Verdict.CLOSING
    )
    closing_note = ", ".join(f"{route} {count:,}" for route, count in routes.most_common())

    def row(label: str, count: int, style: str, note: str = "", share: bool = True) -> str:
        line = f"  {paint(label.ljust(15), style)}{paint(f'{count:>6,}', style)}"
        if share and tally.found:
            line += f"   {paint(f'{count / tally.found:4.0%}', style)}"
        else:
            line += " " * 7
        return line + (f"  {paint(note, DIM)}" if note else "")

    lines = [
        paint(f"  {paint.rule}", DIM),
        row("Still trading", tally.trading, GREEN),
        row("Closing", tally.closing, AMBER, closing_note),
        row("Dissolved", tally.dissolved, RED, "legally gone"),
    ]
    if tally.unclear:
        lines.append(row("Unclear", tally.unclear, DIM, "status not recognised"))
    if tally.not_found:
        lines.append(row("Not found", tally.not_found, DIM, "check the number", share=False))
    lines += [paint(f"  {paint.rule}", DIM), paint(f"  {headline(tally)}", BOLD), ""]
    return "\n".join(lines)


def headline(tally: Tally) -> str:
    if not tally.found:
        return "None of these numbers are on the register. Check they are UK company numbers."
    if not tally.gone_or_going:
        return f"All {tally.found:,} are still trading."
    text = (
        f"{tally.gone_or_going:,} of {tally.found:,} are gone or going: "
        f"{tally.share_gone_or_going:.0%}"
    )
    ratio = tally.found / tally.gone_or_going
    nearest = round(ratio)
    if nearest >= 2 and abs(ratio - nearest) / nearest < 0.05:
        text += f", or 1 in {nearest}"
    return text + "."


# ---------------------------------------------------------------------------- study


def study_report(
    paint: Painter,
    *,
    source: str,
    sample_note: str,
    curves: dict[Population, list[DecayPoint]],
) -> str:
    lines = ["", paint(f"  Decay study {paint.dot} {source}", BOLD), paint(f"  {sample_note}", DIM)]
    header = (
        f"    {'list built':<12}{'age':>6}{'on list':>10}{'dissolved':>12}"
        f"{'+ insolvent':>14}{'+ striking off':>16}{'95% CI':>14}"
    )
    for population, curve in curves.items():
        lines += ["", paint(f"  {population.value}: {population.description}", BOLD)]
        lines.append(paint(header, DIM))
        for point in curve:
            lines.append(
                f"    {format_date(point.list_date):<12}{point.list_age_years:>5.1f}y"
                f"{point.size:>10,}{point.share_dissolved:>12.1%}"
                f"{point.share_dissolved_or_insolvent:>14.1%}"
                f"{paint(f'{point.share_gone_or_going:>16.1%}', BOLD)}"
                f"{format_interval(*point.confidence_interval):>14}"
            )
    oldest = max(curves[Population.REAL_PROSPECTS], key=lambda point: point.list_age_years)
    notes = [
        "'+ insolvent' adds companies in liquidation, administration or receivership.",
        "'+ striking off' adds companies the register has started to strike off.",
        "'95% CI': the true share gone or going sits in this range 19 times in 20.",
    ]
    lines += [
        "",
        paint(
            f"  A list of real prospects built {oldest.list_age_years:.1f} years ago is "
            f"{oldest.share_gone_or_going:.1%} gone or going "
            f"(95% CI {format_interval(*oldest.confidence_interval)}).",
            BOLD,
        ),
        paint(f"  {oldest.share_dissolved:.1%} of it is dissolved outright.", DIM),
        "",
        *(paint(f"  {note}", DIM) for note in notes),
        "",
    ]
    return "\n".join(lines)
