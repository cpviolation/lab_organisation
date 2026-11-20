import pandas as pd
import pytest
from conftest import run

from labcourse import analysis, db, importers, render, repo


def load_course(conn, fx, cfg):
    run(conn, importers.import_students, fx / "students_2024.json", "2024/25")
    run(conn, importers.import_students, fx / "students_2025.json", "2025/26")
    run(conn, importers.import_groups, fx / "groups.json", "2025/26")
    run(conn, importers.import_sessions, fx / "sessions.json", "2025/26")


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------- schema

def test_schema_is_versioned_and_idempotent(cfg):
    c1 = db.connect(cfg.database)
    assert db.schema_version(c1) == len(db.MIGRATIONS)
    c1.close()
    c2 = db.connect(cfg.database)
    assert db.schema_version(c2) == len(db.MIGRATIONS)
    c2.close()


def test_backup(cfg, conn):
    copy = db.backup(cfg.database, cfg.backup_dir)
    assert copy.exists() and copy.parent == cfg.backup_dir


# ---------------------------------------------------------------- students

def test_student_import_is_idempotent(conn, fx):
    rep1 = run(conn, importers.import_students, fx / "students_2025.json", "2025/26")
    assert rep1.counts["new students"] == 5
    rep2 = run(conn, importers.import_students, fx / "students_2025.json", "2025/26")
    assert "new students" not in rep2.counts and rep2.counts["already enrolled"] == 5
    assert count(conn, "student") == 5
    assert repo.student_by_matricola(conn, "100004").surname == "D'Angelo"


def test_repeating_student_gets_second_enrolment(conn, fx):
    run(conn, importers.import_students, fx / "students_2024.json", "2024/25")
    run(conn, importers.import_students, fx / "students_2025.json", "2025/26")
    assert count(conn, "student") == 6  # Jack Bruce is one student in two cohorts
    rows = repo.search_students(conn, matricole=["100003"])
    assert sorted(r.cohort for r in rows) == ["2024/25", "2025/26"]


def test_email_change_is_reported(conn, fx, tmp_path):
    run(conn, importers.import_students, fx / "students_2025.json", "2025/26")
    changed = tmp_path / "s.json"
    changed.write_text((fx / "students_2025.json").read_text().replace("e.clapton@", "eric@"))
    rep = run(conn, importers.import_students, changed, "2025/26")
    assert rep.counts["students updated"] == 1
    assert "email" in rep.changes[0]


def test_dry_run_writes_nothing(conn, fx):
    rep = run(conn, importers.import_students, fx / "students_2025.json", "2025/26", dry_run=True)
    assert rep.counts["new students"] == 5
    assert count(conn, "student") == 0 and count(conn, "cohort") == 0


# ---------------------------------------------------------------- groups

def test_groups_match_within_cohort_only(conn, fx, cfg):
    load_course(conn, fx, cfg)
    groups = {s.matricola: s.lab_group for s in repo.cohort_students(conn, repo.cohort_id(conn, "2025/26"))}
    assert groups == {"100001": 1, "100002": 2, "100003": 1, "100004": 2, "100005": 3}
    # the 2024/25 namesake Eric Clapton is untouched
    old = {s.matricola: s.lab_group for s in repo.cohort_students(conn, repo.cohort_id(conn, "2024/25"))}
    assert old == {"090001": None, "100003": None}


def test_unmatched_group_rows_are_reported(conn, fx, cfg):
    run(conn, importers.import_students, fx / "students_2025.json", "2025/26")
    rep = run(conn, importers.import_groups, fx / "groups.json", "2025/26")
    assert any("Unknown Nobody" in p for p in rep.problems)


def test_ambiguous_names_are_reported(conn, tmp_path):
    f = tmp_path / "s.json"
    f.write_text('[{"nome":"Anna","cognome":"Neri","matricola":"1"},{"nome":"Anna","cognome":"Neri","matricola":"2"}]')
    run(conn, importers.import_students, f, "2025/26")
    g = tmp_path / "g.json"
    g.write_text('[{"nome":"anna","cognome":"NERI","gruppo":1}]')
    rep = run(conn, importers.import_groups, g, "2025/26")
    assert "ambiguous" in rep.problems[0]


def test_unknown_cohort(conn, fx):
    with pytest.raises(LookupError):
        run(conn, importers.import_groups, fx / "groups.json", "1999/00")


# ---------------------------------------------------------------- attendance

def test_attendance_json(conn, fx, cfg):
    load_course(conn, fx, cfg)
    rep = run(conn, importers.import_attendance, fx / "attendance.json", "2025/26", cfg)
    assert rep.counts["records added"] == 5 and not rep.problems
    sessions, rows = analysis.attendance_table(conn, "2025/26", cfg)
    assert [s.date for s in sessions] == ["2025-10-01"]  # only sessions held count
    by_m = {r.student.matricola: r.fraction for r in rows}
    assert by_m["100001"] == 1.0 and by_m["100002"] == 0.0


def test_attendance_missing_session(conn, fx, cfg, tmp_path):
    load_course(conn, fx, cfg)
    f = tmp_path / "a.json"
    f.write_text('{"2025-11-05": [{"matricola": "100001", "presente": 1}]}')
    rep = run(conn, importers.import_attendance, f, "2025/26", cfg)
    assert "no session on 2025-11-05" in rep.problems[0]
    rep = run(conn, importers.import_attendance, f, "2025/26", cfg, default_hours=3)
    assert rep.counts["new sessions"] == 1 and rep.counts["records added"] == 1


def test_attendance_excel_with_blanks(conn, fx, cfg, tmp_path):
    load_course(conn, fx, cfg)
    xlsx = tmp_path / "register.xlsx"
    pd.DataFrame({
        "Cognome": ["Clapton", "Baker", "D’Angelo", "Rossi"],
        "Nome": ["Eric", "Ginger", "Pino", "Nicolo"],
        "Email": ["", "", "", ""],
        "1 ott 2025 10.30AM - 2:30PM": ["P", "A", "R", None],
        "8 ott 2025 10.30AM - 2:30PM": ["G", None, "Presente", "P"],
    }).to_excel(xlsx, index=False)
    rep = run(conn, importers.import_attendance, xlsx, "2025/26", cfg)
    assert not rep.problems, rep.problems
    assert rep.counts["records added"] == 6
    _, rows = analysis.attendance_table(conn, "2025/26", cfg)
    st = {r.student.matricola: r.statuses for r in rows}
    assert sorted(st["100004"].values()) == ["P", "R"]
    assert len(st["100005"]) == 1  # blank cell -> no record, not a crash


# ---------------------------------------------------------------- exams

def test_written_marks_keep_history(conn, fx, cfg):
    load_course(conn, fx, cfg)
    run(conn, importers.import_attendance, fx / "attendance.json", "2025/26", cfg)
    rep = run(conn, importers.import_marks, fx / "written.json", "2025/26", "written")
    assert rep.counts["marks added"] == 7 and rep.counts["new exam dates"] == 2
    rows = {r.student.matricola: r for r in analysis.exam_table(conn, "2025/26", cfg)}
    assert rows["100002"].written.startswith("19 (2026-02-15)")  # 15 then 19
    assert rows["100003"].written.startswith("18")                # absent then 18
    assert rows["100004"].written.startswith("30L")
    assert rows["100001"].eligible
    assert not rows["100002"].eligible and "attendance 0%" in rows["100002"].reasons


def test_reports_copied_to_group_members(conn, fx, cfg):
    load_course(conn, fx, cfg)
    rep = run(conn, importers.import_reports, fx / "reports.json", "2025/26", cfg)
    assert rep.counts["grades added"] == 2 * 2 + 2  # group 1: 2 students x 2 exps; group 2: 2 x 1
    # moving a student to another group later does not change grades earned
    repo.set_group(conn, repo.student_by_matricola(conn, "100001").id, repo.cohort_id(conn, "2025/26"), 2)
    rows = {r.student.matricola: r for r in analysis.exam_table(conn, "2025/26", cfg)}
    assert rows["100001"].report_points == 27 + 30
    assert rows["100002"].report_points == 22


def test_invalid_marks_are_reported(conn, fx, cfg, tmp_path):
    load_course(conn, fx, cfg)
    f = tmp_path / "w.json"
    f.write_text('{"2026-01-20": {"100001": "33", "999": "20"}}')
    rep = run(conn, importers.import_marks, f, "2025/26", "written")
    assert len(rep.problems) == 2


# ---------------------------------------------------------------- dates and sheets

@pytest.mark.parametrize("raw,iso", [
    ("2025-10-01", "2025-10-01"), ("20251001", "2025-10-01"), ("01/10/2025", "2025-10-01"),
    ("'2025-10-01'", "2025-10-01"), ("1 ott 2025", "2025-10-01"), ("15 dic 2025", "2025-12-15"),
])
def test_parse_date(raw, iso):
    assert importers.parse_date(raw) == iso


def test_signature_tables_keep_every_group(conn, fx, cfg):
    load_course(conn, fx, cfg)
    students = repo.cohort_students(conn, repo.cohort_id(conn, "2025/26"), order="group")
    # 3 groups, 2 rows per table: each group fits, none is dropped or split
    grouped = {}
    for s in students:
        grouped.setdefault(s.lab_group, []).append(s)
    tables = render.chunk_groups(list(grouped.items()), max_rows=2)
    assert [g for t in tables for g, _ in t] == [1, 2, 3]
    tex = render.signature_tex(students, "Lab & Co", "2025-10-01", max_rows=40)
    for s in students:
        assert s.surname.replace("'", "'") in tex
    assert r"Lab \& Co" in tex
