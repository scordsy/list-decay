# `find` fills in a number only when it is certain

Most CRMs hold company names, not numbers, so `list-decay find` searches the register by name. The register's search is loose: a search for one courier firm returned thousands of results, and names are reused after a company is dissolved. A wrong number is worse than none, because `check` would then give a confident verdict about the wrong company.

So `find` fills a number in only when exactly one company on the register has the same name, and, where the list gives a postcode, that company's registered postcode is the same full postcode. "The same name" ignores case, punctuation, accents, "&" versus "and", a leading "The" and different spellings of one legal form ("Ltd", "Limited", "Cyfyngedig"). It never ignores a different legal form: "Acme LLP" is not "Acme Limited". Everything else goes back to a person with the candidates listed:

- **Namesakes go to a person even when a postcode agrees with one of them.** That one is listed first.
- **A postcode that differs doesn't throw a match away.** The registered office is often an accountant's address, so the row goes to check by hand.
- **A file needs a header naming the company name column.** Headerless files and a bare "Name" column (usually a person, in a contacts export) are refused rather than guessed at.

Known limit: the search returns at most 100 candidates per name. In every case tested, companies with the exact name ranked first, but a namesake ranked below 100 would not be seen.
