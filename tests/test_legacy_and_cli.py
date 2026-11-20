import shutil
import sqlite3

import pytest
from typer.testing import CliRunner

from labcourse import analysis, db, legacy, repo
from labcourse.cli import app


def make_legacy(d):
    """Old lborg layout, including its quirks: duplicate rows, quoted date columns, 'YYYYMMDD' dates."""
    s = sqlite3.connect(d / "students.db")
    s.execute("CREATE TABLE students (cognome text, nome text, matricola integer, mail text, coorte text, gruppo integer)")
    rows = [
        ("Clapton", "Eric", 100001, "e@x", "2025/26", 1),
        ("Clapton", "Eric", 100001, "e@x", "2025/26", 1),       # duplicate from re-import
        ("D'Angelo", "Pino", 100004, "p@x", "2025/26", 2),
        ("Bruce", "Jack", 100003, "j@x", "2024/25", 0),
        ("Bruce", "Jack", 100003, "j@x", "2025/26", 1),
    ]
    s.executemany("INSERT INTO students VALUES (?,?,?,?,?,?)", rows)
    s.commit(); s.close()

    dt = sqlite3.connect(d / "dates_2025_26.db")
    dt.execute("CREATE TABLE dates (date text, hours INTEGER)")
    dt.executemany("INSERT INTO dates VALUES (?,?)", [("2025-10-01", 4), ("2025-10-08", 4)])
    dt.commit(); dt.close()

    a = sqlite3.connect(d / "attendance.db")
    a.execute("""CREATE TABLE attendance (matricola integer, "'2025-10-01'" boolean, "'2025-10-08'" boolean)""")
    a.executemany("INSERT INTO attendance VALUES (?,?,?)", [(100001, 1, 1), (100004, 1, 0), (100003, 0, None)])
    a.commit(); a.close()

    e = sqlite3.connect(d / "exams.db")
    e.execute("CREATE TABLE exams (matricola integer, written_date text, written text, reports_date text, "
              "reports text, oral_date text, result text)")
    e.executemany("INSERT INTO exams VALUES (?,?,?,?,?,?,?)", [
        (100001, "20260120", "27", "20251201", "Pendolo:B+ Ottica:A", "20260201", "28"),
        (100004, "20260120", "31", "20251201", "Tubo Acustico:A/A- Molla:B", None, None),
    ])
    e.commit(); e.close()


def test_migrate_legacy(tmp_path, cfg):
    make_legacy(tmp_path)
    conn = db.connect(cfg.database)

    def go():
        with db.transaction(conn):
            return legacy.migrate_legacy(conn, cfg, tmp_path / "students.db", tmp_path / "attendance.db",
                                         None, tmp_path / "exams.db")

    reports = go()
    assert not [p for r in reports for p in r.problems], [r.render() for r in reports]
    assert reports[0].counts["duplicate rows merged"] == 1
    assert repo.list_cohorts(conn) == ["2024/25", "2025/26"]
    c25 = repo.cohort_id(conn, "2025/26")
    assert {s.matricola: s.lab_group for s in repo.cohort_students(conn, c25)} == \
        {"100001": 1, "100003": 1, "100004": 2}
    _, rows = analysis.attendance_table(conn, "2025/26", cfg)
    assert {r.student.matricola: r.fraction for r in rows} == {"100001": 1.0, "100003": 0.0, "100004": 0.5}
    ex = {r.student.matricola: r for r in analysis.exam_table(conn, "2025/26", cfg)}
    assert ex["100001"].written == "27 (2026-01-20)" and ex["100001"].report_points == 57
    assert ex["100001"].oral == "28 (2026-02-01)"
    assert ex["100004"].written.startswith("30L")  # old code stored 30L as 31
    assert ex["100004"].reports == "Molla:B Tubo Acustico:A/A-"
    assert ex["100004"].report_points == 26 + 29.5

    # re-running changes nothing
    again = go()
    assert all(set(r.counts) <= {"students unchanged", "unchanged", "duplicate rows merged"} for r in again), \
        [r.counts for r in again]
    conn.close()


# ---------------------------------------------------------------- CLI end to end

@pytest.fixture
def course(tmp_path, monkeypatch, fx):
    monkeypatch.chdir(tmp_path)
    for f in fx.iterdir():
        shutil.copy(f, tmp_path / f.name)
    runner = CliRunner()
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.output
    return runner


def ok(runner, *args):
    r = runner.invoke(app, list(args))
    assert r.exit_code == 0, r.output
    return r.output


def test_cli_workflow(course, tmp_path):
    out = ok(course, "cohort", "import", "students_2025.json", "--dry-run")
    assert "5 new students" in out and "Dry run" in out
    ok(course, "cohort", "import", "students_2025.json")
    out = ok(course, "cohort", "import", "students_2025.json")
    assert "new students" not in out
    assert "Backup:" in out
    ok(course, "groups", "assign", "groups.json")
    r = course.invoke(app, ["groups", "assign", "groups.json", "--strict"])
    assert r.exit_code == 1 and "nothing written" in r.output
    ok(course, "sessions", "add", "sessions.json")
    ok(course, "attendance", "import", "attendance.json")
    ok(course, "exams", "import", "written.json", "--kind", "written")
    ok(course, "exams", "import", "reports.json", "--kind", "report")

    out = ok(course, "students", "search", "--name", "eric")
    assert "Clapton" in out
    out = ok(course, "students", "search", "--surname", "dangelo")
    assert "D'Angelo" in out
    out = ok(course, "exams", "eligible", "--all")
    assert "admitted to the oral" in out
    ok(course, "exams", "eligible", "--format", "csv")
    assert (tmp_path / "output" / "2025_26_exams.csv").exists()
    ok(course, "attendance", "report", "--format", "xlsx")
    assert (tmp_path / "output" / "2025_26_attendance.xlsx").exists()
    ok(course, "sessions", "list")
    ok(course, "exams", "list")
    ok(course, "cohort", "list")


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_cli_pdfs(course, tmp_path):
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "groups", "assign", "groups.json")
    ok(course, "sessions", "add", "sessions.json")
    ok(course, "attendance", "import", "attendance.json")
    ok(course, "sheet", "signature", "--date", "2025-10-01")
    assert (tmp_path / "output" / "2025-10-01_signature.pdf").exists()
    ok(course, "attendance", "report", "--format", "pdf")
    assert (tmp_path / "output" / "2025_26_attendance.pdf").exists()
