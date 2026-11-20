"""Import data from the old ``lborg`` databases (students.db, dates_*.db, attendance.db, exams.db)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import repo
from .config import Config
from .importers import ImportReport, parse_date
from .marks import Mark


def _rows(path: Path, table: str) -> tuple[list[str], list[tuple]]:
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cur = src.execute(f'SELECT * FROM "{table}"')  # table name is a fixed literal
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()
    except sqlite3.OperationalError as e:
        raise ValueError(f"{path}: cannot read table {table!r} ({e})") from None
    finally:
        src.close()


def _id(value) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def cohort_from_dates_file(path: Path) -> str | None:
    """``dates_2023_24.db`` -> ``2023/24``."""
    m = re.fullmatch(r"dates_(\d{4})_(\d{2,4})", path.stem)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def migrate_legacy(
    conn: sqlite3.Connection,
    cfg: Config,
    students_db: Path,
    attendance_db: Path | None = None,
    dates_dbs: dict[str, Path] | None = None,
    exams_db: Path | None = None,
    default_hours: float | None = None,
) -> list[ImportReport]:
    reports = []

    # ---- students and groups
    rep = ImportReport("Legacy students")
    cols, rows = _rows(students_db, "students")
    best: dict[tuple[str, str], dict] = {}
    for row in rows:
        rec = dict(zip(cols, row))
        matricola = _id(rec.get("matricola"))
        cohort = (rec.get("coorte") or "").strip()
        if not matricola or not cohort:
            rep.problem(f"skipped row without matricola/coorte: {rec}")
            continue
        key = (matricola, cohort)
        if key in best:
            rep.count("duplicate rows merged")
            # keep the row that has a group
            if not best[key].get("gruppo") and rec.get("gruppo"):
                best[key] = rec
            continue
        best[key] = rec
    student_cohorts: dict[str, list[str]] = {}
    for (matricola, cohort), rec in sorted(best.items(), key=lambda kv: kv[0][1]):
        cid = repo.cohort_id(conn, cohort, create=True)
        sid, outcome, _ = repo.upsert_student(
            conn, matricola, (rec.get("cognome") or "").strip(), (rec.get("nome") or "").strip(),
            (rec.get("mail") or None),
        )
        rep.count({"new": "students", "updated": "students updated", "same": "students unchanged"}[outcome])
        if repo.enrol(conn, sid, cid):
            rep.count("enrolments")
        group = rec.get("gruppo")
        if group not in (None, "", 0, "0"):
            if repo.set_group(conn, sid, cid, int(group)) != int(group):
                rep.count("groups set")
        student_cohorts.setdefault(matricola, []).append(cohort)
    reports.append(rep)

    # ---- sessions
    dates_dbs = dict(dates_dbs or {})
    if not dates_dbs:
        for p in sorted(students_db.parent.glob("dates_*.db")):
            c = cohort_from_dates_file(p)
            if c:
                dates_dbs[c] = p
    for cohort, path in dates_dbs.items():
        rep = ImportReport(f"Legacy sessions {cohort} ({path.name})")
        cid = repo.cohort_id(conn, cohort, create=True)
        try:
            cols, rows = _rows(path, "dates")
        except ValueError as e:
            rep.problem(str(e))
            rows = []
        for row in rows:
            rec = dict(zip(cols, row))
            try:
                iso = parse_date(rec["date"])
                _, outcome = repo.upsert_session(conn, cid, iso, float(rec["hours"]))
                rep.count({"new": "sessions", "updated": "sessions updated", "same": "unchanged"}[outcome])
            except (ValueError, TypeError) as e:
                rep.problem(f"{rec}: {e}")
        reports.append(rep)

    # ---- attendance
    if attendance_db:
        rep = ImportReport(f"Legacy attendance ({attendance_db.name})")
        try:
            cols, rows = _rows(attendance_db, "attendance")
        except ValueError as e:
            rep.problem(str(e))
            cols, rows = ["matricola"], []
        date_cols = {}
        for c in cols[1:]:
            try:
                date_cols[c] = parse_date(c)
            except ValueError:
                rep.problem(f"column {c!r} is not a date; skipped")
        for row in rows:
            rec = dict(zip(cols, row))
            matricola = _id(rec.get("matricola"))
            cohorts = student_cohorts.get(matricola or "", [])
            st = repo.student_by_matricola(conn, matricola) if matricola else None
            if st is None or not cohorts:
                rep.problem(f"attendance for unknown matricola {matricola}")
                continue
            for col, iso in date_cols.items():
                value = rec[col]
                if value is None:
                    continue
                # pick the cohort that has a session on that day (students may repeat the course)
                session = None
                for cohort in reversed(cohorts):
                    session = repo.session_by_date(conn, repo.cohort_id(conn, cohort), iso)
                    if session:
                        break
                if session is None:
                    if not default_hours:
                        rep.problem(f"{iso}: no session in {', '.join(cohorts)} (use --hours to create it)")
                        continue
                    sid, _ = repo.upsert_session(conn, repo.cohort_id(conn, cohorts[-1]), iso, default_hours)
                    rep.count("sessions created")
                    session_id = sid
                else:
                    session_id = session.id
                status = "P" if value in (1, "1", True, "True", "true") else "A"
                outcome = repo.set_attendance(conn, session_id, st.id, status)
                rep.count({"new": "records", "updated": "records changed", "same": "unchanged"}[outcome])
        # de-duplicate repeated problems
        rep.problems = list(dict.fromkeys(rep.problems))
        reports.append(rep)

    # ---- exams
    if exams_db:
        rep = ImportReport(f"Legacy exams ({exams_db.name})")
        scale = cfg.exams.report_scale
        try:
            cols, rows = _rows(exams_db, "exams")
        except ValueError as e:
            rep.problem(str(e))
            cols, rows = ["matricola"], []
        for row in rows:
            rec = dict(zip(cols, row))
            matricola = _id(rec.get("matricola"))
            cohorts = student_cohorts.get(matricola or "", [])
            st = repo.student_by_matricola(conn, matricola) if matricola else None
            if st is None or not cohorts:
                rep.problem(f"exam results for unknown matricola {matricola}")
                continue
            cid = repo.cohort_id(conn, cohorts[-1])  # most recent enrolment

            def put(kind: str, date_raw, raw_mark: str, label: str = "") -> None:
                try:
                    iso = parse_date(date_raw)
                except ValueError:
                    rep.problem(f"{st.full_name}: {kind} {label} has invalid date {date_raw!r}")
                    return
                aid, _ = repo.assessment_id(conn, cid, kind, iso, label)
                outcome, _ = repo.set_result(conn, aid, st.id, raw_mark)
                rep.count({"new": f"{kind} marks", "updated": f"{kind} marks changed",
                           "same": "unchanged"}[outcome])

            for kind, mcol, dcol in (("written", "written", "written_date"), ("oral", "result", "oral_date")):
                if rec.get(mcol) in (None, ""):
                    continue
                try:
                    put(kind, rec.get(dcol), Mark.parse(rec[mcol]).raw)
                except ValueError as e:
                    rep.problem(f"{st.full_name}: {kind}: {e}")
            if rec.get("reports"):
                for item in str(rec["reports"]).split():
                    if ":" not in item:
                        rep.problem(f"{st.full_name}: report entry {item!r} not understood")
                        continue
                    label, grade = item.rsplit(":", 1)
                    try:
                        put("report", rec.get("reports_date"), scale.validate(grade), label)
                    except ValueError as e:
                        rep.problem(f"{st.full_name}: report {label}: {e}")
        reports.append(rep)

    return reports
