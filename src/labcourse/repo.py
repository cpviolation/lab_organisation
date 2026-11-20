"""Data access: small functions over the schema, all with parameterised SQL."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from .names import name_key, normalise
from .rules import SessionInfo


@dataclass(frozen=True)
class StudentRow:
    id: int
    matricola: str
    surname: str
    name: str
    email: str | None
    lab_group: int | None = None
    cohort: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.surname} {self.name}"


# ---------------------------------------------------------------- cohorts

def cohort_id(conn: sqlite3.Connection, name: str, create: bool = False) -> int:
    row = conn.execute("SELECT id FROM cohort WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    if not create:
        known = ", ".join(list_cohorts(conn)) or "none"
        raise LookupError(f"Cohort {name!r} not found (known cohorts: {known})")
    return conn.execute("INSERT INTO cohort (name) VALUES (?)", (name,)).lastrowid


def list_cohorts(conn: sqlite3.Connection) -> list[str]:
    return [r["name"] for r in conn.execute("SELECT name FROM cohort ORDER BY name")]


# ---------------------------------------------------------------- students

def student_by_matricola(conn: sqlite3.Connection, matricola: str) -> StudentRow | None:
    row = conn.execute(
        "SELECT id, matricola, surname, name, email FROM student WHERE matricola = ?",
        (str(matricola),),
    ).fetchone()
    return StudentRow(**row) if row else None


def upsert_student(
    conn: sqlite3.Connection, matricola: str, surname: str, name: str, email: str | None
) -> tuple[int, str, list[str]]:
    """Insert or update a student identified by matricola.

    Returns ``(id, outcome, changes)`` where outcome is 'new', 'updated' or 'same'.
    """
    current = student_by_matricola(conn, matricola)
    if current is None:
        sid = conn.execute(
            "INSERT INTO student (matricola, surname, name, email) VALUES (?, ?, ?, ?)",
            (str(matricola), surname, name, email),
        ).lastrowid
        return sid, "new", []
    changes = []
    for field, new in (("surname", surname), ("name", name), ("email", email)):
        old = getattr(current, field)
        if new is not None and new != old:
            changes.append(f"{field}: {old!r} -> {new!r}")
    if changes:
        conn.execute(
            "UPDATE student SET surname = ?, name = ?, email = COALESCE(?, email) WHERE id = ?",
            (surname, name, email, current.id),
        )
        return current.id, "updated", changes
    return current.id, "same", []


def enrol(conn: sqlite3.Connection, student_id: int, cohort: int) -> bool:
    """Enrol a student in a cohort; returns True if the enrolment is new."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO enrolment (student_id, cohort_id) VALUES (?, ?)", (student_id, cohort)
    )
    return cur.rowcount == 1


def set_group(conn: sqlite3.Connection, student_id: int, cohort: int, group: int | None) -> int | None:
    """Set the lab group; returns the previous group."""
    row = conn.execute(
        "SELECT lab_group FROM enrolment WHERE student_id = ? AND cohort_id = ?", (student_id, cohort)
    ).fetchone()
    if row is None:
        raise LookupError(f"Student {student_id} is not enrolled in cohort {cohort}")
    conn.execute(
        "UPDATE enrolment SET lab_group = ? WHERE student_id = ? AND cohort_id = ?",
        (group, student_id, cohort),
    )
    return row["lab_group"]


def cohort_students(
    conn: sqlite3.Connection, cohort: int, group: int | None = None, order: str = "name"
) -> list[StudentRow]:
    order_sql = {
        "name": "s.surname COLLATE NOCASE, s.name COLLATE NOCASE",
        "group": "e.lab_group IS NULL, e.lab_group, s.surname COLLATE NOCASE, s.name COLLATE NOCASE",
        "matricola": "s.matricola",
    }[order]
    sql = (
        "SELECT s.id, s.matricola, s.surname, s.name, s.email, e.lab_group, c.name AS cohort "
        "FROM student s JOIN enrolment e ON e.student_id = s.id JOIN cohort c ON c.id = e.cohort_id "
        "WHERE e.cohort_id = ?"
    )
    params: list = [cohort]
    if group is not None:
        sql += " AND e.lab_group = ?"
        params.append(group)
    sql += f" ORDER BY {order_sql}"
    return [StudentRow(**r) for r in conn.execute(sql, params)]


def search_students(
    conn: sqlite3.Connection,
    matricole: list[str] | None = None,
    name: str | None = None,
    surname: str | None = None,
    cohort: int | None = None,
) -> list[StudentRow]:
    sql = (
        "SELECT s.id, s.matricola, s.surname, s.name, s.email, e.lab_group, c.name AS cohort "
        "FROM student s LEFT JOIN enrolment e ON e.student_id = s.id "
        "LEFT JOIN cohort c ON c.id = e.cohort_id"
    )
    params: list = []
    where = []
    if cohort is not None:
        where.append("e.cohort_id = ?")
        params.append(cohort)
    if matricole:
        where.append(f"s.matricola IN ({','.join('?' * len(matricole))})")
        params.extend(str(m) for m in matricole)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.surname COLLATE NOCASE, s.name COLLATE NOCASE, c.name"
    rows = [StudentRow(**r) for r in conn.execute(sql, params)]
    if name:
        rows = [r for r in rows if normalise(name) in normalise(r.name)]
    if surname:
        rows = [r for r in rows if normalise(surname) in normalise(r.surname)]
    return rows


class StudentMatcher:
    """Finds students of one cohort by matricola or by normalised name."""

    def __init__(self, conn: sqlite3.Connection, cohort: int):
        self.students = cohort_students(conn, cohort)
        self.by_matricola = {s.matricola: s for s in self.students}
        self.by_name: dict[tuple[str, str], list[StudentRow]] = defaultdict(list)
        for s in self.students:
            self.by_name[name_key(s.surname, s.name)].append(s)

    def match(
        self, matricola: str | None = None, surname: str | None = None, name: str | None = None
    ) -> tuple[StudentRow | None, str | None]:
        """Returns ``(student, problem)``; exactly one of the two is None."""
        if matricola not in (None, ""):
            s = self.by_matricola.get(str(matricola).strip())
            return (s, None) if s else (None, f"matricola {matricola} not in cohort")
        if not surname or not name:
            return None, "no matricola and no full name"
        hits = self.by_name.get(name_key(surname, name), [])
        if len(hits) == 1:
            return hits[0], None
        if not hits:
            return None, f"{surname} {name}: no student with this name in cohort"
        ids = ", ".join(h.matricola for h in hits)
        return None, f"{surname} {name}: ambiguous name (matricole {ids})"


# ---------------------------------------------------------------- sessions

def upsert_session(conn: sqlite3.Connection, cohort: int, date: str, hours: float) -> tuple[int, str]:
    row = conn.execute(
        "SELECT id, hours FROM session WHERE cohort_id = ? AND date = ?", (cohort, date)
    ).fetchone()
    if row is None:
        sid = conn.execute(
            "INSERT INTO session (cohort_id, date, hours) VALUES (?, ?, ?)", (cohort, date, hours)
        ).lastrowid
        return sid, "new"
    if row["hours"] != hours:
        conn.execute("UPDATE session SET hours = ? WHERE id = ?", (hours, row["id"]))
        return row["id"], "updated"
    return row["id"], "same"


def session_by_date(conn: sqlite3.Connection, cohort: int, date: str) -> SessionInfo | None:
    row = conn.execute(
        "SELECT id, date, hours FROM session WHERE cohort_id = ? AND date = ?", (cohort, date)
    ).fetchone()
    return SessionInfo(**row) if row else None


def list_sessions(conn: sqlite3.Connection, cohort: int, held_only: bool = False) -> list[SessionInfo]:
    sql = "SELECT id, date, hours FROM session WHERE cohort_id = ?"
    if held_only:
        sql += " AND EXISTS (SELECT 1 FROM attendance a WHERE a.session_id = session.id)"
    sql += " ORDER BY date"
    return [SessionInfo(**r) for r in conn.execute(sql, (cohort,))]


# ---------------------------------------------------------------- attendance

def set_attendance(conn: sqlite3.Connection, session_id: int, student_id: int, status: str) -> str:
    row = conn.execute(
        "SELECT status FROM attendance WHERE session_id = ? AND student_id = ?", (session_id, student_id)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO attendance (session_id, student_id, status) VALUES (?, ?, ?)",
            (session_id, student_id, status),
        )
        return "new"
    if row["status"] != status:
        conn.execute(
            "UPDATE attendance SET status = ? WHERE session_id = ? AND student_id = ?",
            (status, session_id, student_id),
        )
        return "updated"
    return "same"


def cohort_attendance(conn: sqlite3.Connection, cohort: int) -> dict[int, dict[int, str]]:
    """student id -> {session id -> status} for one cohort."""
    out: dict[int, dict[int, str]] = defaultdict(dict)
    for r in conn.execute(
        "SELECT a.student_id, a.session_id, a.status FROM attendance a "
        "JOIN session s ON s.id = a.session_id WHERE s.cohort_id = ?",
        (cohort,),
    ):
        out[r["student_id"]][r["session_id"]] = r["status"]
    return out


# ---------------------------------------------------------------- assessments

def assessment_id(conn: sqlite3.Connection, cohort: int, kind: str, date: str, label: str = "") -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM assessment WHERE cohort_id = ? AND kind = ? AND date = ? AND label = ?",
        (cohort, kind, date, label),
    ).fetchone()
    if row:
        return row["id"], False
    aid = conn.execute(
        "INSERT INTO assessment (cohort_id, kind, date, label) VALUES (?, ?, ?, ?)",
        (cohort, kind, date, label),
    ).lastrowid
    return aid, True


def set_result(conn: sqlite3.Connection, assessment: int, student_id: int, raw_mark: str) -> tuple[str, str | None]:
    """Returns (outcome, previous mark)."""
    row = conn.execute(
        "SELECT raw_mark FROM result WHERE assessment_id = ? AND student_id = ?", (assessment, student_id)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO result (assessment_id, student_id, raw_mark) VALUES (?, ?, ?)",
            (assessment, student_id, raw_mark),
        )
        return "new", None
    if row["raw_mark"] != raw_mark:
        conn.execute(
            "UPDATE result SET raw_mark = ? WHERE assessment_id = ? AND student_id = ?",
            (raw_mark, assessment, student_id),
        )
        return "updated", row["raw_mark"]
    return "same", row["raw_mark"]


@dataclass(frozen=True)
class ResultRow:
    student_id: int
    kind: str
    date: str
    label: str
    raw_mark: str


def cohort_results(conn: sqlite3.Connection, cohort: int, kind: str | None = None) -> dict[int, list[ResultRow]]:
    sql = (
        "SELECT r.student_id, a.kind, a.date, a.label, r.raw_mark FROM result r "
        "JOIN assessment a ON a.id = r.assessment_id WHERE a.cohort_id = ?"
    )
    params: list = [cohort]
    if kind:
        sql += " AND a.kind = ?"
        params.append(kind)
    sql += " ORDER BY a.date, a.label"
    out: dict[int, list[ResultRow]] = defaultdict(list)
    for r in conn.execute(sql, params):
        out[r["student_id"]].append(ResultRow(**r))
    return out


def list_assessments(conn: sqlite3.Connection, cohort: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.kind, a.date, a.label, COUNT(r.student_id) AS n FROM assessment a "
        "LEFT JOIN result r ON r.assessment_id = a.id WHERE a.cohort_id = ? "
        "GROUP BY a.id ORDER BY a.date, a.kind, a.label",
        (cohort,),
    ).fetchall()
