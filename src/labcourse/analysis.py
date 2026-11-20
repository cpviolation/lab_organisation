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
    if wanted is not None:
        missing = wanted - {r.student.matricola for r in out}
        for m in sorted(missing):
            raise LookupError(f"matricola {m} is not enrolled in {cohort_name}")
    return out
