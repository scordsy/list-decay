# Scope

list-decay does one job: tell you which companies on a UK list are trading, closing or dissolved, using the free Companies House register. It stays small on purpose, so it keeps working.

## In scope

- Checking a list of UK company numbers against the live register.
- Reading the lists people actually have: CRM exports, spreadsheets, text files.
- The decay study, and reproducing its published figures from the bundled sample.

## Not planned

- **Companies registered outside the UK.** Other countries keep their own registers with their own rules.
- **Matching on company name.** See [ADR 0003](docs/adr/0003-company-number-is-the-only-input.md).
- **Checking contacts or email addresses.** list-decay checks the company. Verify the people with a tool built for that, after the dissolved companies are out.
- **Runtime dependencies.** See [ADR 0002](docs/adr/0002-standard-library-only.md).
- **A web app or a hosted service.** It runs on your machine, so your list stays there.
