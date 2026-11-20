"""Combine stored data with the course rules into report rows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import repo
from .config import Config
from .marks import Mark
from .rules import SessionInfo, attendance_fraction, attended_hours, oral_eligibility, report_score


@dataclass(frozen=True)
class AttendanceRow:
    student: repo.StudentRow
    statuses: dict[int, str]
    hours: float
    fraction: float


def attendance_table(
    conn: sqlite3.Connection, cohort_name: str, cfg: Config, order: str = "name"
) -> tuple[list[SessionInfo], list[AttendanceRow]]:
    """Sessions held so far and each student's attendance in the cohort."""
    cohort = repo.cohort_id(conn, cohort_name)
    sessions = repo.list_sessions(conn, cohort, held_only=True)
    records = repo.cohort_attendance(conn, cohort)
    rows = []
    for st in repo.cohort_students(conn, cohort, order=order):
        statuses = records.get(st.id, {})
        rows.append(AttendanceRow(
            st, statuses,
            attended_hours(sessions, statuses, cfg.attendance),
            attendance_fraction(sessions, statuses, cfg.attendance),
        ))
    return sessions, rows


@dataclass(frozen=True)
class ExamRow:
    student: repo.StudentRow
    attendance: float
    written: str          # counting written mark, e.g. "27 (2026-01-20)"
    reports: str          # "Pendolo:B+ Ottica:A"
    report_points: float | None
    oral: str
    eligible: bool
    reasons: str


def exam_table(
    conn: sqlite3.Connection, cohort_name: str, cfg: Config,
    matricole: list[str] | None = None, order: str = "group",
) -> list[ExamRow]:
    cohort = repo.cohort_id(conn, cohort_name)
    _, att_rows = attendance_table(conn, cohort_name, cfg, order=order)
    results = repo.cohort_results(conn, cohort)
    wanted = {str(m) for m in matricole} if matricole else None
    out = []
    for a in att_rows:
        st = a.student
        if wanted is not None and st.matricola not in wanted:
            continue
        res = results.get(st.id, [])
        written = [(r.date, Mark.parse(r.raw_mark)) for r in res if r.kind == "written"]
        reports = [r for r in res if r.kind == "report"]
        orals = [r for r in res if r.kind == "oral"]
        el = oral_eligibility(written, a.fraction, cfg.exams, cfg.attendance)
        try:
            points = report_score([r.raw_mark for r in reports], cfg.exams) if reports else None
        except ValueError:
            points = None
        out.append(ExamRow(
            st, a.fraction,
            f"{el.written[1]} ({el.written[0]})" if el.written else "-",
            " ".join(f"{r.label}:{r.raw_mark}" for r in reports) or "-",
            points,
            f"{orals[-1].raw_mark} ({orals[-1].date})" if orals else "-",
            el.eligible,
            "; ".join(el.reasons),
        ))
    return out


def exam_table_multi(
    conn: sqlite3.Connection, cohort_names: list[str], cfg: Config,
    matricole: list[str] | None = None, order: str = "group",
) -> tuple[list[ExamRow], list[str]]:
    """Exam rows over several cohorts, plus warnings for requested ids not found.

    A student enrolled in more than one of the cohorts gets one row per enrolment.
    """
    rows: list[ExamRow] = []
    for name in cohort_names:
        rows += exam_table(conn, name, cfg, matricole=matricole, order=order)
    warnings = []
    if matricole:
        found = {r.student.matricola for r in rows}
        for m in dict.fromkeys(str(x) for x in matricole):
            if m in found:
                continue
            st = repo.student_by_matricola(conn, m)
            if st is None:
                warnings.append(f"matricola {m} is not in the database")
                continue
            other = [r.cohort for r in repo.search_students(conn, matricole=[m]) if r.cohort]
            where = ", ".join(other) if other else "no cohort"
            warnings.append(f"matricola {m} ({st.full_name}) is not enrolled in "
                            f"{', '.join(cohort_names)} (enrolled in: {where})")
    return rows, warnings
