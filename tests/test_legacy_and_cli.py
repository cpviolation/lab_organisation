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


def test_expand_multi():
    from labcourse.cli import expand_multi
    assert expand_multi(["exams", "eligible", "-m", "1", "2", "3", "--all"]) == \
        ["exams", "eligible", "-m", "1", "-m", "2", "-m", "3", "--all"]
    assert expand_multi(["-m", "1", "--matricola", "2", "4"]) == ["-m", "1", "--matricola", "2", "--matricola", "4"]
    assert expand_multi(["-C", "2025/26", "-m", "1"]) == ["-C", "2025/26", "-m", "1"]


def test_cli_multiple_matricole(course):
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "exams", "import", "written.json", "--kind", "written")
    from labcourse.cli import expand_multi
    for args in (["-m", "100001", "100004"], ["-m", "100001,100004"], ["-m", "100001", "-m", "100004"]):
        out = ok(course, *expand_multi(["exams", "eligible", *args]))
        assert "Clapton" in out and "D'Angelo" in out and "Baker" not in out
        out = ok(course, *expand_multi(["students", "search", *args]))
        assert "Clapton" in out and "D'Angelo" in out and "Baker" not in out


def test_cli_eligible_across_cohorts_with_warnings(course):
    ok(course, "cohort", "import", "students_2024.json", "--cohort", "2024/25")
    ok(course, "cohort", "import", "students_2025.json", "--cohort", "2025/26")
    # explicit cohort: ids elsewhere or unknown are warnings, not errors
    r = course.invoke(app, ["exams", "eligible", "--cohort", "2025/26", "-m", "100001", "-m", "090001", "-m", "999"])
    assert r.exit_code == 0, r.output
    assert "Warning: matricola 090001 (Clapton Eric) is not enrolled in 2025/26 (enrolled in: 2024/25)" in r.output
    assert "Warning: matricola 999 is not in the database" in r.output
    # without --cohort, -m searches every cohort and shows the cohort column
    out = ok(course, "exams", "eligible", "-m", "100001", "-m", "090001")
    assert "coorte" in out and "2024/25" in out and "2025/26" in out
    out = ok(course, "exams", "eligible", "--cohort", "all", "--all")
    assert "6 students" not in out and "of 7 students" in out  # 5 + 2 enrolments (Bruce in both)



def _esse3_xlsx(path):
    """An Esse3-like export: title block above the table, words for marks, a footer line."""
    import pandas as pd
    rows = [
        ["Università degli Studi", None, None, None, None, None],
        ["Lista iscritti - Data appello: 01/03/2026", None, None, None, None, None],
        [None, None, None, None, None, None],
        ["#", "Matricola", "Cognome", "Nome", "Email", "Esito"],
        [1, "100001", "Clapton", "Eric", "e.clapton@example.org", "25"],
        [2, "100002", "Baker", "Ginger", "g.baker@example.org", "Assente"],
        [3, "100003", "Bruce", "Jack", "j.bruce@example.org", "Respinto"],
        [4, "100004", "D'Angelo", "Pino", "p.dangelo@example.org", "30 e lode"],
        [5, "555", "Altro", "Turno", "a.t@example.org", "28"],
        [6, "100005", "Rossi", "Nicolò", "n.rossi@example.org", None],   # registered, no mark yet
        ["Totale iscritti: 6", None, None, None, None, None],
    ]
    pd.DataFrame(rows).to_excel(path, index=False, header=False)
    return path


def test_read_esse3_list(tmp_path):
    from labcourse import importers
    rows, found, problems = importers.read_registration_table(_esse3_xlsx(tmp_path / "iscritti.xlsx"))
    assert found == "2026-03-01" and not problems
    assert [r.matricola for r in rows] == ["100001", "100002", "100003", "100004", "555", "100005"]
    assert [r.mark for r in rows] == ["25", "A", "I", "30L", "28", None]
    assert rows[4].surname == "Altro" and rows[4].email == "a.t@example.org"


def test_appello_table(course, tmp_path):
    from labcourse import analysis, db
    from labcourse.config import load_config
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "sessions", "add", "sessions.json")
    ok(course, "attendance", "import", "attendance.json")   # Baker (100002) absent -> 0%
    w = tmp_path / "w.json"
    w.write_text('{"2026-01-20": {"100002": "24", "100003": "20"}}')
    ok(course, "appelli", "import", str(w))
    out = ok(course, "appelli", "import", str(_esse3_xlsx(tmp_path / "iscritti.xlsx")))
    assert "6 registered" in out and "1 marks of students not in the database" in out

    cfg = load_config(tmp_path / "course.toml")
    conn = db.connect(cfg.database)
    rows = analysis.appello_table(conn, cfg, "2026-03-01")
    by_m = {r.matricola: r for r in rows}
    assert by_m["100001"].eligible and by_m["100001"].appello_mark == "25"
    assert not by_m["100002"].eligible and "attendance" in by_m["100002"].reason  # passed before, 0% attendance
    assert by_m["100003"].eligible and by_m["100003"].exam.written.startswith("20")  # best mark counts
    assert by_m["100004"].eligible and by_m["100004"].exam.written.startswith("30L")
    assert by_m["100005"].appello_mark == "" and not by_m["100005"].eligible       # registered, no mark
    assert by_m["555"].exam is None and by_m["555"].surname == "Altro"             # kept from the list
    # marks of known students were stored as written results too
    assert conn.execute("SELECT COUNT(*) FROM result r JOIN assessment a ON a.id = r.assessment_id "
                        "WHERE a.kind = 'written' AND a.date = '2026-03-01'").fetchone()[0] == 4
    # re-importing changes nothing
    again = ok(course, "appelli", "import", str(tmp_path / "iscritti.xlsx"))
    assert "registered" not in again.replace("unchanged", "")
    conn.close()


def test_cli_appelli(course, tmp_path):
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "sessions", "add", "sessions.json")
    ok(course, "attendance", "import", "attendance.json")
    ok(course, "appelli", "import", str(_esse3_xlsx(tmp_path / "iscritti.xlsx")))
    out = ok(course, "appelli", "list")
    assert "2026-03-01" in out
    out = ok(course, "appelli", "show")
    assert "6 registered, 5 with a mark, 2 admitted" in out and "Altro" in out
    out = ok(course, "appelli", "show", "--admitted")
    assert "Clapton" in out and "Baker" not in out
    from labcourse.cli import expand_multi
    ok(course, *expand_multi(["appelli", "add", "--date", "2026-03-01", "-m", "100003", "777"]))
    out = ok(course, "appelli", "show")
    assert "7 registered" in out
    ok(course, "appelli", "remove", "--date", "2026-03-01", "-m", "777")
    assert "6 registered" in ok(course, "appelli", "show")
    r = course.invoke(app, ["appelli", "show", "--date", "2025-01-01"])
    assert r.exit_code == 1 and "no appello" in r.output
    ok(course, "appelli", "show", "-f", "xlsx")
    assert (tmp_path / "output" / "2026-03-01_appello.xlsx").exists()
    if shutil.which("pdflatex"):
        ok(course, "appelli", "show", "-f", "pdf")
        ok(course, "appelli", "show", "--oral", "-f", "pdf")
        assert (tmp_path / "output" / "2026-03-01_appello.pdf").exists()
        assert (tmp_path / "output" / "2026-03-01_orali.pdf").exists()


def test_appello_needs_a_date(course, tmp_path):
    import pandas as pd
    f = tmp_path / "lista.csv"
    pd.DataFrame({"Matricola": ["1"], "Cognome": ["A"], "Nome": ["B"]}).to_csv(f, index=False)
    r = course.invoke(app, ["appelli", "import", str(f)])
    assert r.exit_code == 1 and "date" in r.output
    ok(course, "appelli", "import", str(f), "--date", "2026-05-05")


def test_read_csv_with_title_block(tmp_path):
    from labcourse import importers
    f = tmp_path / "iscritti.csv"
    f.write_text("Data appello: 15/01/2027\n\nMatricola;Cognome;Nome;Esito\n1;Rossi;Anna;Assente\n2;Neri;Luca;27\n3;Bo;Ugo;\n",
                 encoding="cp1252")
    rows, found, problems = importers.read_registration_table(f)
    assert found == "2027-01-15" and not problems
    assert [(r.matricola, r.mark) for r in rows] == [("1", "A"), ("2", "27"), ("3", None)]
