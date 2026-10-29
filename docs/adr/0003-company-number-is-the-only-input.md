# The company number is the only input

list-decay reads one column, the company number, and ignores everything else in the file. Matching on company name was rejected: the register holds many companies with the same or near-identical names (dormant entities inside a group, shells, firms sharing a trading name), so a name match is wrong often enough to make the verdict meaningless. Reading only the number also means a list can be checked without handling anything about the people on it.
