# Standard library only

list-decay has no runtime dependencies. HTTP, CSV, JSON and the statistics are all done with what ships with Python, so there is nothing to install beyond Python itself, nothing that can break on an upgrade, and nothing for a cautious team to vet before running it on their list. `requests` and `pandas` would make some of the code shorter; they would also make the tool harder to trust and to run. Test, lint and type-check tools are development dependencies only.
