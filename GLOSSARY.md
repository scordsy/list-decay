# list-decay

The words list-decay uses in its code, its output and its docs. One meaning each, so a reader never has to guess which "active" or "dead" is meant.

list-decay works on **UK-registered companies only**: England, Wales, Scotland and Northern Ireland. Sole traders and ordinary partnerships are not on the register, and companies registered in other countries are out of reach.

## Checking a list

**Company number**:
The eight-character number Companies House gives every UK company, such as `08500000` or `SC123456`. The only thing list-decay reads from a list.
_Avoid_: CRN, registration number, company ID

**Register**:
Companies House's record of every UK company, dissolved ones included.
_Avoid_: database, Companies House data

**Snapshot**:
Register records saved on a known date. The one bundled with list-decay was saved on 20 July 2026.
_Avoid_: export, dump

**Verdict**:
What the register says about one company on the day it is checked: trading, closing, dissolved, unclear or not found.
_Avoid_: status (that is the register's own field, which the verdict is read from)

**Trading**:
On the register as active, with nothing underway to close it.
_Avoid_: live, alive, active

**Closing**:
Still on the register, but a closure has started: an insolvency process, or a proposal to strike the company off.
_Avoid_: dying, at risk, facing closure

**Dissolved**:
Removed from the register. The company no longer legally exists.
_Avoid_: dead, closed, struck off (striking off is one route to being dissolved)

**Unclear**:
On the register, with a status list-decay does not recognise. Counted, never guessed at.
_Avoid_: unknown, other

**Not found**:
No company has that number. Usually a typo, never decay.
_Avoid_: missing, invalid

**Gone or going**:
Closing plus dissolved. The headline figure.
_Avoid_: dead or dying, churned

## The study

**List date**:
The day a list was built. A company only counts against a list if it was open that day.
_Avoid_: cutoff, snapshot date

**List age**:
The years between the list date and the day the list is checked.

**Decay curve**:
The share of a list that is gone or going, at each list age.
_Avoid_: rot curve

**Cohort**:
The companies a study samples from: England and Wales companies incorporated between two dates.

**All companies**:
Every company in the sample, dormant ones included.

**Real prospect**:
A company that could plausibly be on a B2B list: a private or public limited company, a private unlimited company or an LLP, not marked dormant or non-trading by its SIC codes, and filing accounts that are not dormant.
_Avoid_: prospectable, valid company

**Operating business**:
A real prospect that is not a holding company or a property vehicle.
_Avoid_: trading company (clashes with the Trading verdict)
