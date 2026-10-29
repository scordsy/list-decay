# CLAUDE.md

The brief for any agent working on list-decay. Read [`GLOSSARY.md`](GLOSSARY.md) first and use its words exactly, in code and in output.

## What this is

A command-line tool that checks a list of UK company numbers against the Companies House register and says which companies are trading, closing or dissolved. Plus the study that measured how fast a UK list decays. UK-registered companies only.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                      # all tests, under a second, no network
.venv/bin/ruff format . && .venv/bin/ruff check .
.venv/bin/mypy                        # strict
.venv/bin/list-decay check --demo     # the end-to-end smoke run
```

Run all four before every commit. CI runs the same.

## Layout

| Module | Owns |
|---|---|
| `company_list.py` | Reading a file into company numbers, and repairing what spreadsheets do to them |
| `company.py` | One register record and its verdict |
| `register.py` | Where records come from: `SnapshotRegister`, `LiveRegister`, `CachedRegister`, all behind the `Register` interface |
| `check.py` | Checking numbers against a register, the tally, and the results CSV |
| `study.py` | The decay curve, the populations, and drawing a sample |
| `render.py` | Terminal output, and every word in it |
| `cli.py` | Argument parsing, finding the API key, and wiring. Nothing else |

## Rules

- **Standard library only at runtime.** No new dependencies. See [ADR 0002](docs/adr/0002-standard-library-only.md).
- **Tests live at four seams, and only there:** reading lists, checking a list against a register (saved and live), the live connection, and the study. Plus smoke runs of each command, error paths included, in `tests/test_cli.py`. The fake Companies House lives in `tests/conftest.py`. Test through the public interface. Mock nothing of ours; time and HTTP are the only things faked.
- **Expected values come from outside the code.** The study's figures are pinned to the published July 2026 run. Never recompute an expected value the way the code does.
- **The published figures are a contract.** If `tests/test_study.py` or the demo test fails, the change is wrong, not the test.
- **Never print, log or store the API key.** It travels in one header and nowhere else.
- **The bundled snapshot carries no company names**, and nothing about people.
- **Plain English in output and docs.** Short sentences. No em dashes.
