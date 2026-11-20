# Lab Organisation

Tools to run a university lab course: load students from the e-learning export, split them into
groups, track attendance, record exam and report marks, and print signature sheets and reports.

Everything lives in one local SQLite database (`data/lab.db` by default). Student data is personal
data: `data/` and `output/` are git-ignored and must never be committed.

## Installation

```bash
source setup.sh          # creates .venv, installs the package and the `lab` command
```

or manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

PDF output needs `pdflatex` (TeX Live / MacTeX).

## Setup for a course

```bash
lab init                 # writes course.toml and creates the database
```

Edit `course.toml`: course title, `default_cohort`, attendance rules (minimum fraction, hour cap,
codes counted as present), exam rules (written pass mark, best/latest policy, report grade scale),
and the column names of the Excel attendance register. All commands read `course.toml` from the
current folder; use `lab -c path/to/course.toml ...` or `LAB_CONFIG` otherwise.

## Workflow

Every command that writes takes `--dry-run` (show what would change, write nothing), `-v` (list every
change) and `--strict` (write nothing if any row has a problem). A timestamped backup of the database
is made in `data/backups/` before each write. Imports are idempotent: re-running one after the
source changes only applies the differences.

```bash
# students (matched on matricola; a student repeating the course gets a second enrolment)
lab cohort import data/raw/partecipanti.json --cohort 2025/26 --dry-run
lab cohort import data/raw/partecipanti.json --cohort 2025/26

# groups: JSON/CSV/XLSX with `gruppo` and either `matricola` or `nome` + `cognome`
# (names are matched within the cohort, ignoring case, accents and apostrophes)
lab groups assign data/raw/gruppi.json
lab groups show

# lesson dates and hours: {"2025-10-01": 4, ...}
lab sessions add data/raw/date.json

# attendance from the Excel register (P/A/R/G per date column) or JSON
lab attendance import data/raw/registro.xlsx
lab attendance report                     # terminal table
lab attendance report --format pdf        # also csv, xlsx

# signature sheet for a lesson
lab sheet signature --date 2025-10-01

# marks
lab exams import data/raw/scritto.json --kind written   # {"2026-01-20": {"<matricola>": "27"}}
lab exams import data/raw/relazioni.json --kind report  # {"2025-12-01": {"<gruppo>": {"Pendolo": "B+"}}}
lab exams import data/raw/orale.json --kind oral
lab exams eligible                        # admitted to the oral; --all to include the others
lab exams eligible --format xlsx          # for the department office

lab students search --surname dangelo
lab students list --format csv
```

Marks are stored as written: numbers 0–30, `30L` (cum laude), `A` (absent), `R` (withdrawn),
`I` (insufficient). Every exam sitting is kept; `exams.written_policy` decides whether the best or the
most recent paper counts. Report grades are copied to each group member when imported, so a later
group change does not alter grades already earned.

Attendance fraction = hours attended (codes in `present_codes`) / hours of the sessions held so far,
with the denominator capped at `max_counted_hours`.

## Migrating from the old scripts

The previous `lborg` scripts have been removed (they are in the git history before this
version). To copy the data of their databases into the new one:

```bash
lab migrate-legacy --students data/students.db --attendance data/attendance.db \
                   --exams data/exams.db --dry-run
```

`dates_YYYY_YY.db` files next to `students.db` are picked up automatically (or pass
`--dates 2025/26=path/to/dates.db`). Duplicate student rows are merged. The migration is safe to
re-run. Check the dry-run output before running it for real.

## Development

```bash
pytest
```

Code layout (`src/labcourse/`): `db.py` schema and migrations, `marks.py` mark parsing, `rules.py`
attendance and eligibility rules (pure functions), `importers.py` file adapters with reconciliation,
`repo.py` data access, `analysis.py` report rows, `render.py` LaTeX (Jinja2 templates in
`templates/`) and CSV/XLSX output, `legacy.py` migration, `cli.py` the `lab` command.
