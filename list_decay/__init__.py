"""Check a list of UK companies against Companies House: trading, closing or dissolved."""

from list_decay._version import __version__
from list_decay.check import CheckedCompany, Tally, check
from list_decay.company import Company, Verdict
from list_decay.company_list import CompanyList, normalise_company_number, read_company_list
from list_decay.find import CompanyName, Finding, FindOutcome, MatchedOn, find, write_found
from list_decay.name_list import ListedCompany, NameList, NoNameColumn, read_name_list
from list_decay.register import (
    ApiKeyRejected,
    CachedRegister,
    Candidate,
    LiveRegister,
    Register,
    RegisterError,
    RegisterUnavailable,
    SnapshotRegister,
)
from list_decay.study import (
    Cohort,
    DecayPoint,
    Population,
    decay_curve,
    draw_sample,
    list_as_built,
    wilson_interval,
)

__all__ = [
    "ApiKeyRejected",
    "CachedRegister",
    "Candidate",
    "CheckedCompany",
    "Cohort",
    "Company",
    "CompanyList",
    "CompanyName",
    "DecayPoint",
    "FindOutcome",
    "Finding",
    "ListedCompany",
    "LiveRegister",
    "MatchedOn",
    "NameList",
    "NoNameColumn",
    "Population",
    "Register",
    "RegisterError",
    "RegisterUnavailable",
    "SnapshotRegister",
    "Tally",
    "Verdict",
    "__version__",
    "check",
    "decay_curve",
    "draw_sample",
    "find",
    "list_as_built",
    "normalise_company_number",
    "read_company_list",
    "read_name_list",
    "wilson_interval",
    "write_found",
]
