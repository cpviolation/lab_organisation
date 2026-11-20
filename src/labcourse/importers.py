"""Importers: parse a file, validate it, reconcile it with the database.

Every importer writes through ``repo`` and returns an :class:`ImportReport`.
Callers run them inside ``db.transaction(conn, dry_run=...)`` so a dry run
shows exactly what would change and then rolls back.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import repo
from .config import Config
from .marks import Mark

# ---------------------------------------------------------------- report


@dataclass
class ImportReport:
    title: str
    counts: dict[str, int] = field(default_factory=dict)
    changes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def count(self, what: str, n: int = 1) -> None:
        self.counts[what] = self.counts.get(what, 0) + n

    def change(self, msg: str) -> None:
        self.changes.append(msg)

    def problem(self, msg: str) -> None:
        self.problems.append(msg)

    def summary(self) -> str:
        parts = [f"{n} {what}" for what, n in self.counts.items() if n]
        return ", ".join(parts) if parts else "nothing to do"

    def render(self, verbose: bool = False) -> str:
        lines = [f"{self.title}: {self.summary()}"]
        if self.problems:
            lines.append(f"  {len(self.problems)} problem(s):")
            lines += [f"    ! {p}" for p in self.problems]
        if verbose and self.changes:
            lines.append("  changes:")
            lines += [f"    - {c}" for c in self.changes]
        return "\n".join(lines)


# ---------------------------------------------------------------- helpers

MONTHS_IT = {
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
}
MONTHS_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_TEXT_DATE = re.compile(r"(\d{1,2})\s+([A-Za-zàèéìòù]{3,})\.?\s+(\d{4})")


def parse_date(value: Any) -> str:
    """Return an ISO date (YYYY-MM-DD) from the formats seen in course files."""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip().strip("'\"")
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = _TEXT_DATE.search(text)
    if m:
        day, month, year = m.groups()
        key = month[:3].lower()
        month_n = MONTHS_IT.get(key) or MONTHS_EN.get(key)
        if month_n:
            return date(int(year), month_n, int(day)).isoformat()
    raise ValueError(f"Unrecognised date: {value!r}")


def find_date(text: str) -> str | None:
    """Date contained in a longer string (e.g. an Excel column header), or None."""
    m = _TEXT_DATE.search(str(text))
    if m:
        try:
            return parse_date(m.group(0))
        except ValueError:
            return None
    m = re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}", str(text))
    if m:
        try:
            return parse_date(m.group(0))
        except ValueError:
            return None
    return None


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == ""


def _clean(value: Any) -> str | None:
    return None if _is_blank(value) else str(value).strip()


def _clean_id(value: Any) -> str | None:
    """Student ids from Excel may arrive as floats (123456.0)."""
    if _is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _lower_keys(rec: dict) -> dict:
    return {str(k).strip().lower(): v for k, v in rec.items()}


def load_records(path: str | Path) -> list[dict]:
    """Rows from a JSON list (optionally nested in an outer list), CSV or Excel file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        # e-learning exports wrap the list in another list
        while isinstance(data, list) and len(data) == 1 and isinstance(data[0], list):
            data = data[0]
        if not isinstance(data, list):
            raise ValueError(f"{path}: expected a list of records")
        return [_lower_keys(r) for r in data]
    import pandas as pd

    if suffix == ".csv":
        df = pd.read_csv(path, dtype=str, sep=None, engine="python")
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str, engine=_excel_engine(path))
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    return [_lower_keys(r) for r in df.to_dict("records")]


def _excel_engine(path: str | Path) -> str | None:
    """openpyxl for .xlsx (pandas' current default, kept explicit); default engine otherwise."""
    return "openpyxl" if Path(path).suffix.lower() == ".xlsx" else None


def _first(rec: dict, *keys: str) -> Any:
    for k in keys:
        if k in rec and not _is_blank(rec[k]):
            return rec[k]
    return None


# ---------------------------------------------------------------- students


def import_students(conn: sqlite3.Connection, path: str | Path, cohort_name: str) -> ImportReport:
    """E-learning participant export (JSON/CSV/XLSX with nome, cognome, matricola, email)."""
    rep = ImportReport(f"Students -> {cohort_name}")
    cohort = repo.cohort_id(conn, cohort_name, create=True)
    seen: set[str] = set()
    for i, rec in enumerate(load_records(path), start=1):
        matricola = _clean_id(_first(rec, "matricola", "id", "student_id"))
        surname = _clean(_first(rec, "cognome", "surname"))
        name = _clean(_first(rec, "nome", "name"))
        email = _clean(_first(rec, "indirizzoemail", "email", "mail", "indirizzo email"))
        if not (matricola and surname and name):
            rep.problem(f"row {i}: missing matricola/cognome/nome ({rec})")
            continue
        if matricola in seen:
            rep.problem(f"row {i}: matricola {matricola} repeated in file")
            continue
        seen.add(matricola)
        sid, outcome, changes = repo.upsert_student(conn, matricola, surname, name, email)
        if outcome == "new":
            rep.count("new students")
            rep.change(f"new student {surname} {name} ({matricola})")
        elif outcome == "updated":
            rep.count("students updated")
            rep.change(f"{surname} {name} ({matricola}): " + "; ".join(changes))
        if repo.enrol(conn, sid, cohort):
            rep.count("enrolled")
        else:
            rep.count("already enrolled")
    return rep


# ---------------------------------------------------------------- groups


def import_groups(conn: sqlite3.Connection, path: str | Path, cohort_name: str) -> ImportReport:
    """Group list: records with gruppo and either matricola or nome + cognome."""
    rep = ImportReport(f"Groups -> {cohort_name}")
    cohort = repo.cohort_id(conn, cohort_name)
    matcher = repo.StudentMatcher(conn, cohort)
    for i, rec in enumerate(load_records(path), start=1):
        group_raw = _first(rec, "gruppo", "group", "lab_group")
        try:
            number = float(group_raw)
            if not math.isfinite(number) or not number.is_integer():
                raise ValueError("group must be an integer")
            group = int(number)
        except (TypeError, ValueError):
            rep.problem(f"row {i}: invalid group {group_raw!r}")
            continue
        st, problem = matcher.match(
            _clean_id(_first(rec, "matricola")), _clean(_first(rec, "cognome", "surname")),
            _clean(_first(rec, "nome", "name")),
        )
        if st is None:
            rep.problem(f"row {i}: {problem}")
            continue
        old = repo.set_group(conn, st.id, cohort, group)
        if old == group:
            rep.count("unchanged")
        else:
            rep.count("assigned")
            rep.change(f"{st.full_name}: group {old} -> {group}")
    without = [s for s in repo.cohort_students(conn, cohort) if s.lab_group is None]
    if without:
        rep.problem(f"{len(without)} student(s) in the cohort still have no group: "
                    + ", ".join(s.full_name for s in without[:10]) + (" ..." if len(without) > 10 else ""))
    return rep


# ---------------------------------------------------------------- sessions


def import_sessions(conn: sqlite3.Connection, path: str | Path, cohort_name: str) -> ImportReport:
    """Lesson dates and hours: JSON ``{"2025-10-01": 4, ...}`` or records with date, hours."""
    rep = ImportReport(f"Sessions -> {cohort_name}")
    cohort = repo.cohort_id(conn, cohort_name)
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        items = list(data.items()) if isinstance(data, dict) else [
            (_first(_lower_keys(r), "date", "data"), _first(_lower_keys(r), "hours", "ore")) for r in data
        ]
    else:
        items = [(_first(r, "date", "data"), _first(r, "hours", "ore")) for r in load_records(path)]
    for d, h in items:
        try:
            iso = parse_date(d)
            hours = float(h)
            if hours <= 0:
                raise ValueError("hours must be positive")
        except (TypeError, ValueError) as e:
            rep.problem(f"{d}: {e}")
            continue
        _, outcome = repo.upsert_session(conn, cohort, iso, hours)
        rep.count({"new": "new sessions", "updated": "sessions updated", "same": "unchanged"}[outcome])
        if outcome != "same":
            rep.change(f"{iso}: {hours:g} h ({outcome})")
    return rep


# ---------------------------------------------------------------- attendance


@dataclass
class AttendanceEntry:
    date: str
    status: str
    matricola: str | None = None
    surname: str | None = None
    name: str | None = None
    source: str = ""


def _status_from_cell(value: Any) -> str | None:
    """Map a register cell to P/A/R/G; None for an empty cell."""
    if _is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "P" if value else "A"
    if isinstance(value, bool):
        return "P" if value else "A"
    text = str(value).strip().upper()
    if text in ("1", "TRUE", "SI", "SÌ", "YES"):
        return "P"
    if text in ("0", "FALSE", "NO"):
        return "A"
    if text[:1] in ("P", "A", "R", "G"):
        return text[:1]
    raise ValueError(f"unrecognised attendance value {value!r}")


def read_attendance_json(path: str | Path) -> tuple[list[AttendanceEntry], list[str]]:
    """``{"2025-10-01": [{"nome":..., "cognome":..., "presente": 1}, ...]}``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries, problems = [], []
    for d, students in data.items():
        try:
            iso = parse_date(d)
        except ValueError as e:
            problems.append(str(e))
            continue
        for rec in students:
            rec = _lower_keys(rec)
            try:
                status = _status_from_cell(_first(rec, "stato", "status", "presente"))
            except ValueError as e:
                problems.append(f"{iso} {rec}: {e}")
                continue
            if status is None:
                continue
            entries.append(AttendanceEntry(
                iso, status, _clean_id(_first(rec, "matricola")),
                _clean(_first(rec, "cognome", "surname")), _clean(_first(rec, "nome", "name")),
            ))
    return entries, problems


def read_attendance_excel(path: str | Path, cfg: Config) -> tuple[list[AttendanceEntry], list[str]]:
    """Register with one row per student and one column per lesson date."""
    import pandas as pd

    fmt = cfg.excel
    df = pd.read_excel(path, dtype={fmt.matricola_column: str} if fmt.matricola_column else None,
                       engine=_excel_engine(path))
    if df.empty:
        raise ValueError(f"No data found in {path}")
    for col in (fmt.name_column, fmt.surname_column):
        if col not in df.columns:
            raise ValueError(f"{path}: column {col!r} not found (columns: {', '.join(map(str, df.columns))})")
    date_cols: dict[str, str] = {}
    problems = []
    for col in df.columns:
        if fmt.time_marker and fmt.time_marker not in str(col):
            continue
        iso = find_date(col)
        if iso is None:
            continue
        if iso in date_cols:
            problems.append(f"two columns for {iso}: {date_cols[iso]!r} and {col!r}; using the first "
                            "(set excel.time_marker to choose)")
            continue
        date_cols[iso] = col
    if not date_cols:
        raise ValueError(f"{path}: no column header contains a date")
    entries = []
    for idx, row in df.iterrows():
        for iso, col in date_cols.items():
            try:
                status = _status_from_cell(row[col])
            except ValueError as e:
                problems.append(f"row {idx + 2}, {iso}: {e}")
                continue
            if status is None:
                continue
            entries.append(AttendanceEntry(
                iso, status,
                _clean_id(row[fmt.matricola_column]) if fmt.matricola_column else None,
                _clean(row[fmt.surname_column]), _clean(row[fmt.name_column]),
                source=f"row {idx + 2}",
            ))
    return entries, problems


def import_attendance(
    conn: sqlite3.Connection, path: str | Path, cohort_name: str, cfg: Config,
    default_hours: float | None = None,
) -> ImportReport:
    path = Path(path)
    rep = ImportReport(f"Attendance -> {cohort_name}")
    cohort = repo.cohort_id(conn, cohort_name)
    if path.suffix.lower() == ".json":
        entries, problems = read_attendance_json(path)
    else:
        entries, problems = read_attendance_excel(path, cfg)
    for p in problems:
        rep.problem(p)
    matcher = repo.StudentMatcher(conn, cohort)
    sessions: dict[str, int | None] = {}
    unmatched: set[str] = set()
    for e in entries:
        if e.date not in sessions:
            s = repo.session_by_date(conn, cohort, e.date)
            if s is None and default_hours:
                sid, _ = repo.upsert_session(conn, cohort, e.date, default_hours)
                rep.count("new sessions")
                rep.change(f"session {e.date} created with {default_hours:g} h")
                sessions[e.date] = sid
            elif s is None:
                rep.problem(f"no session on {e.date}: add it with `lab sessions add` or pass --hours")
                sessions[e.date] = None
            else:
                sessions[e.date] = s.id
        session_id = sessions[e.date]
        if session_id is None:
            continue
        st, problem = matcher.match(e.matricola, e.surname, e.name)
        if st is None:
            if problem not in unmatched:
                unmatched.add(problem)
                rep.problem(problem)
            continue
        outcome = repo.set_attendance(conn, session_id, st.id, e.status)
        rep.count({"new": "records added", "updated": "records changed", "same": "unchanged"}[outcome])
        if outcome != "same":
            rep.change(f"{e.date} {st.full_name}: {e.status} ({outcome})")
    return rep


# ---------------------------------------------------------------- results


def import_marks(
    conn: sqlite3.Connection, path: str | Path, cohort_name: str, kind: str,
) -> ImportReport:
    """Written or oral marks: ``{"2026-01-20": {"<matricola>": "27", ...}}``."""
    if kind not in ("written", "oral"):
        raise ValueError("kind must be 'written' or 'oral'")
    rep = ImportReport(f"{kind.capitalize()} marks -> {cohort_name}")
    cohort = repo.cohort_id(conn, cohort_name)
    matcher = repo.StudentMatcher(conn, cohort)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for d, marks in data.items():
        try:
            iso = parse_date(d)
        except ValueError as e:
            rep.problem(str(e))
            continue
        aid, new = repo.assessment_id(conn, cohort, kind, iso)
        if new:
            rep.count("new exam dates")
        for matricola, raw in marks.items():
            try:
                mark = Mark.parse(raw)
            except ValueError as e:
                rep.problem(f"{iso} {matricola}: {e}")
                continue
            st, problem = matcher.match(str(matricola))
            if st is None:
                rep.problem(f"{iso}: {problem}")
                continue
            outcome, old = repo.set_result(conn, aid, st.id, mark.raw)
            rep.count({"new": "marks added", "updated": "marks changed", "same": "unchanged"}[outcome])
            if outcome == "updated":
                rep.change(f"{iso} {st.full_name}: {old} -> {mark}")
            elif outcome == "new":
                rep.change(f"{iso} {st.full_name}: {mark}")
    return rep


def import_reports(conn: sqlite3.Connection, path: str | Path, cohort_name: str, cfg: Config) -> ImportReport:
    """Report grades per group: ``{"2025-12-01": {"<group>": {"<experiment>": "B+"}}}``.

    The grade is copied to every student in the group at import time, so a later
    group change does not alter marks already earned.
    """
    rep = ImportReport(f"Report grades -> {cohort_name}")
    cohort = repo.cohort_id(conn, cohort_name)
    scale = cfg.exams.report_scale
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for d, groups in data.items():
        try:
            iso = parse_date(d)
        except ValueError as e:
            rep.problem(str(e))
            continue
        for group_raw, grades in groups.items():
            try:
                group = int(group_raw)
            except ValueError:
                rep.problem(f"{iso}: invalid group {group_raw!r}")
                continue
            members = repo.cohort_students(conn, cohort, group=group)
            if not members:
                rep.problem(f"{iso}: group {group} has no students")
                continue
            for experiment, grade in grades.items():
                try:
                    g = scale.validate(grade)
                except ValueError as e:
                    rep.problem(f"{iso} group {group} {experiment}: {e}")
                    continue
                aid, new = repo.assessment_id(conn, cohort, "report", iso, str(experiment))
                if new:
                    rep.count("new experiments")
                for st in members:
                    outcome, old = repo.set_result(conn, aid, st.id, g)
                    rep.count({"new": "grades added", "updated": "grades changed", "same": "unchanged"}[outcome])
                    if outcome != "same":
                        rep.change(f"{iso} {experiment} {st.full_name}: {old or '-'} -> {g}")
    return rep


# ---------------------------------------------------------------- appelli (registrations and marks)

_MARK_WORDS = {
    "assente": "A", "ass": "A", "ass.": "A",
    "ritirato": "R", "ritirata": "R", "ritiro": "R", "rit": "R", "rit.": "R",
    "insufficiente": "I", "respinto": "I", "respinta": "I", "non superato": "I", "bocciato": "I", "insuff": "I",
}
_NO_MARK = {"", "-", "--", "nan", "none", "iscritto", "iscritta", "prenotato", "prenotata"}


def parse_exam_mark(value: Any) -> str | None:
    """Mark as stored (``'27'``, ``'30L'``, ``'A'``…), or None for a registration without a mark.

    Understands the words used in Esse3 exports (Assente, Ritirato, Respinto, 30 e lode…).
    """
    if _is_blank(value):
        return None
    text = str(value).strip()
    low = re.sub(r"\s+", " ", text.lower())
    if low in _NO_MARK:
        return None
    if low in _MARK_WORDS:
        return _MARK_WORDS[low]
    if "lode" in low or low in ("30+", "30 +", "31"):
        return "30L"
    return Mark.parse(text).raw


_COLUMN_SYNONYMS = {
    "matricola": ("matricola", "matr", "matr.", "student id", "id studente"),
    "surname": ("cognome", "surname", "last name"),
    "name": ("nome", "name", "first name"),
    "email": ("email", "e-mail", "indirizzo email", "indirizzoemail", "mail", "indirizzo e-mail"),
    "mark": ("voto", "esito", "voto/esito", "risultato", "mark", "grade", "voto finale"),
}


def _find_column(columns: list[str], key: str) -> str | None:
    norm = {c: re.sub(r"\s+", " ", str(c).strip().lower()) for c in columns}
    for syn in _COLUMN_SYNONYMS[key]:
        for c, n in norm.items():
            if n == syn:
                return c
    if key in ("email", "mark"):  # looser match: "Email istituzionale", "Voto (/30)"
        for c, n in norm.items():
            if any(n.startswith(s) for s in _COLUMN_SYNONYMS[key]):
                return c
    return None


@dataclass
class RegistrationRow:
    matricola: str
    surname: str | None
    name: str | None
    email: str | None
    mark: str | None


def read_registration_table(
    path: str | Path, sheet: str | int | None = None,
) -> tuple[list[RegistrationRow], str | None, list[str]]:
    """Registered students from an Esse3/e-learning list (XLSX, XLS or CSV).

    The header row is found automatically (the first row with a "Matricola" column), so
    exports with a title block above the table work. Returns rows, a date found in the
    title block or sheet name (or None), and problems.
    """
    import pandas as pd

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        raw = _read_csv_table(path)
        sheet_name = ""
    elif suffix in (".xlsx", ".xls", ".ods"):
        xl = pd.ExcelFile(path, engine=_excel_engine(path))
        sheet_name = xl.sheet_names[0] if sheet is None else (
            xl.sheet_names[sheet] if isinstance(sheet, int) else sheet)
        if sheet_name not in xl.sheet_names:
            raise ValueError(f"{path.name}: no sheet {sheet!r} (sheets: {', '.join(xl.sheet_names)})")
        raw = pd.read_excel(xl, sheet_name=sheet_name, header=None, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported file type for a registration list: {path.suffix}")

    header_idx = None
    for i in range(min(len(raw), 40)):
        cells = [str(v) for v in raw.iloc[i].tolist()]
        if _find_column(cells, "matricola") is not None:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"{path.name}: no 'Matricola' column found")

    # a date in the title block (e.g. "Data appello: 17/11/2026"), the sheet name or the file name
    found_date = None
    for text in [*(" ".join(map(str, raw.iloc[i].tolist())) for i in range(header_idx)), sheet_name, path.stem]:
        found_date = find_date(text) or _compact_date(text)
        if found_date:
            break

    header = [str(v).strip() for v in raw.iloc[header_idx].tolist()]
    body = raw.iloc[header_idx + 1:]
    cols = {k: _find_column(header, k) for k in _COLUMN_SYNONYMS}
    idx = {k: header.index(c) for k, c in cols.items() if c is not None}
    rows, problems = [], []
    for n, (_, r) in enumerate(body.iterrows(), start=header_idx + 2):
        values = r.tolist()
        matricola = _clean_id(values[idx["matricola"]])
        if not matricola:
            continue  # blank or footer line
        if not re.fullmatch(r"[0-9A-Za-z]+", matricola):
            continue  # footer text such as "Totale iscritti: 23"
        mark = None
        if "mark" in idx:
            try:
                mark = parse_exam_mark(values[idx["mark"]])
            except ValueError as e:
                problems.append(f"row {n} ({matricola}): {e}")
        rows.append(RegistrationRow(
            matricola,
            _clean(values[idx["surname"]]) if "surname" in idx else None,
            _clean(values[idx["name"]]) if "name" in idx else None,
            _clean(values[idx["email"]]) if "email" in idx else None,
            mark,
        ))
    return rows, found_date, problems


def _read_csv_table(path: Path):
    """CSV that may have a title block above the table: the delimiter is taken from the
    header line (the one containing "matricola"), not from the first line."""
    import csv
    import io

    import pandas as pd

    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lines = text.splitlines()
    header = next((ln for ln in lines if "matricola" in ln.lower()), lines[0] if lines else "")
    delim = max([";", ",", "\t", "|"], key=header.count)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    width = max((len(r) for r in rows), default=0)
    return pd.DataFrame([r + [""] * (width - len(r)) for r in rows], dtype=str)


def _compact_date(text: str) -> str | None:
    """``exams_20261117`` -> 2026-11-17."""
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", str(text))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def excel_sheets(path: str | Path) -> list[str]:
    import pandas as pd

    return pd.ExcelFile(path, engine=_excel_engine(path)).sheet_names


def import_appello(
    conn: sqlite3.Connection, path: str | Path, appello_date: str | None = None, sheet: str | int | None = None,
) -> list[ImportReport]:
    """Register students for written appelli and record their marks.

    * JSON results ``{"2026-11-17": {"<matricola>": "27"}}``: one appello per date.
    * Esse3/e-learning list (XLSX/XLS/CSV): one appello, date from ``appello_date``
      or found in the file. Rows without a mark only register the student.

    Marks of students in the database are also stored as written results in their
    most recent cohort, so they count for admission to the oral.
    """
    path = Path(path)
    batches: dict[str, list[RegistrationRow]] = {}
    problems: list[str] = []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f'{path}: expected {{"<date>": {{"<matricola>": "<mark>"}}}}')
        for d, marks in data.items():
            try:
                iso = parse_date(d)
            except ValueError as e:
                problems.append(str(e))
                continue
            if appello_date and iso != parse_date(appello_date):
                continue
            for m, raw in marks.items():
                try:
                    mark = parse_exam_mark(raw)
                except ValueError as e:
                    problems.append(f"{iso} {m}: {e}")
                    continue
                batches.setdefault(iso, []).append(RegistrationRow(str(m).strip(), None, None, None, mark))
    else:
        rows, found, problems = read_registration_table(path, sheet)
        iso = parse_date(appello_date) if appello_date else found
        if not iso:
            raise ValueError(f"{path}: appello date not found in the file; give it explicitly")
        batches[iso] = rows

    reports = []
    for iso, rows in sorted(batches.items()):
        rep = ImportReport(f"Appello {iso}")
        for p in problems:
            rep.problem(p)
        problems = []
        try:
            aid = repo.appello_id(conn, iso)
        except LookupError:
            aid = repo.appello_id(conn, iso, create=True)
            rep.count("new appello")
        for row in rows:
            outcome, old = repo.upsert_registration(conn, aid, row.matricola, row.surname, row.name, row.email, row.mark)
            rep.count({"new": "registered", "updated": "registrations updated", "same": "unchanged"}[outcome])
            who = " ".join(x for x in (row.surname, row.name) if x) or row.matricola
            if outcome == "new":
                rep.change(f"{who} ({row.matricola}) registered" + (f", mark {row.mark}" if row.mark else ""))
            elif outcome == "updated" and row.mark and row.mark != old:
                rep.change(f"{who} ({row.matricola}): mark {old or '-'} -> {row.mark}")
            if row.mark is None:
                continue
            cohort = repo.latest_cohort(conn, row.matricola)
            if cohort is None:
                rep.count("marks of students not in the database (kept in the appello only)")
                continue
            st = repo.student_by_matricola(conn, row.matricola)
            assessment, _ = repo.assessment_id(conn, repo.cohort_id(conn, cohort), "written", iso)
            res, _ = repo.set_result(conn, assessment, st.id, row.mark)
            if res != "same":
                rep.count("written results stored")
        reports.append(rep)
    if not reports:
        raise ValueError(f"{path}: nothing to import" + (f" for {appello_date}" if appello_date else ""))
    return reports
