# Changelog

## Unreleased

- CI: macOS runs the newest Python only. A second macOS job kept being cancelled for lack of a free GitHub runner, and Linux already covers Python 3.10.

## 0.2.0 (29 Oct 2026)

- `list-decay find`: fills in company numbers from company names, for CRMs that don't hold them. A number is filled in only when it is certain: exactly one company with that name and legal form, and the same registered postcode where the file has one. Everything else is marked "check by hand" with every candidate listed. Every original column is kept, and an existing company number column has its gaps filled, so the file can go straight back into a CRM, or straight into `list-decay check`.
- `check` counts rows with no company number yet separately from unreadable ones.
- CI: Linux on every supported Python, macOS and Windows on the oldest and newest, current action versions, and superseded runs cancelled.

## 0.1.0 (29 Oct 2026)

First public version.

- `list-decay check`: check a CSV or text file of UK company numbers against the live Companies House register, with a verdict per company and a summary.
- `list-decay check --demo`: replay a 3,829-company list built on 1 Jul 2023 against the bundled 20 Jul 2026 snapshot, no API key needed.
- `list-decay study`: reproduce the decay curve from the bundled sample, or draw a fresh one with `--live`.
