from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402
from test_legacy_and_cli import course, ok  # noqa: E402,F401  (shared fixture)

GUI = str(Path(__file__).parents[1] / "src" / "labcourse" / "gui.py")


def test_every_page_renders(course, monkeypatch, tmp_path):
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "groups", "assign", "groups.json")
    ok(course, "sessions", "add", "sessions.json")
    ok(course, "attendance", "import", "attendance.json")
    ok(course, "exams", "import", "written.json", "--kind", "written")
    ok(course, "exams", "import", "reports.json", "--kind", "report")
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))

    at = AppTest.from_file(GUI, default_timeout=30).run()
    assert not at.exception
    pages = at.sidebar.radio[0].options
    assert len(pages) == 10
    for page in pages:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, (page, at.exception)
        assert at.header[0].value  # every page has a title


def test_missing_config(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "missing.toml"))
    at = AppTest.from_file(GUI, default_timeout=30).run()
    assert at.error and "lab init" in at.error[0].value


def test_exams_hide_students_below_attendance(course, monkeypatch, tmp_path):
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "sessions", "add", "sessions.json")
    ok(course, "attendance", "import", "attendance.json")   # Baker absent -> 0%
    ok(course, "exams", "import", "written.json", "--kind", "written")
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))

    at = AppTest.from_file(GUI, default_timeout=30).run()
    at.sidebar.radio[0].set_value("📝 Esami").run()

    def names():
        return set(at.dataframe[0].value["cognome"])

    show_all = next(t for t in at.toggle if t.label == "Mostra anche i non ammessi")
    show_all.set_value(True).run()
    assert "Baker" not in names()                       # below 75%: hidden by default
    assert any("sotto il 75%" in c.value for c in at.caption)
    show_low = next(t for t in at.toggle if t.label.startswith("Mostra anche sotto"))
    show_low.set_value(True).run()
    assert "Baker" in names()
    assert not at.exception



def test_appelli_page_renders(course, monkeypatch, tmp_path):
    from test_legacy_and_cli import _esse3_xlsx
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "appelli", "import", str(_esse3_xlsx(tmp_path / "iscritti.xlsx")))
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))
    at = AppTest.from_file(GUI, default_timeout=30).run()
    at.sidebar.radio[0].set_value("🗓️ Appelli").run()
    assert not at.exception
    assert at.metric[0].value == "6"            # registered
    assert set(at.dataframe[0].value["matricola"]) >= {"100001", "555"}


def test_appello_report_detail_on_click(course, monkeypatch, tmp_path):
    from test_legacy_and_cli import _esse3_xlsx
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "groups", "assign", "groups.json")
    ok(course, "exams", "import", "reports.json", "--kind", "report")
    ok(course, "appelli", "import", str(_esse3_xlsx(tmp_path / "iscritti.xlsx")))
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))
    at = AppTest.from_file(GUI, default_timeout=30).run()
    at.sidebar.radio[0].set_value("🗓️ Appelli").run()
    table = at.dataframe[0].value
    row = list(table["cognome"]).index("Clapton")
    key = f"appello-table-{at.session_state['appello-date']}-False-False"
    at.session_state[key] = {"selection": {"rows": [], "columns": [], "cells": [[row, "relazioni /30"]]}}
    at.run()
    assert not at.exception
    assert at.subheader[-1].value == "Relazioni di Clapton Eric"
    detail = at.dataframe[1].value
    assert list(detail["esperienza"]) == ["Ottica", "Pendolo"] and list(detail["voto"]) == ["A", "B+"]


def test_appello_oral_marks_tab(course, monkeypatch, tmp_path):
    from test_legacy_and_cli import _esse3_xlsx
    from labcourse import db, importers
    from labcourse.config import load_config
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "appelli", "import", str(_esse3_xlsx(tmp_path / "iscritti.xlsx")))
    conn = db.connect(load_config(tmp_path / "course.toml").database)
    with db.transaction(conn):
        importers.set_oral_marks(conn, "2026-03-10", {"100001": "27"})
    conn.close()
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))

    at = AppTest.from_file(GUI, default_timeout=30).run()
    at.sidebar.radio[0].set_value("🗓️ Appelli").run()
    assert not at.exception
    at.date_input(key="oral-date").set_value(date(2026, 3, 10))
    at.toggle(key="oral-all").set_value(True).run()   # no attendance data: nobody is admitted
    assert not at.exception
    editor = next(d.value for d in at.dataframe if "ultimo orale" in d.value.columns)
    marks = dict(zip(editor["matricola"], editor["voto"]))
    assert marks["100001"] == "27" and pd.isna(marks["100003"])
    assert "555" not in marks                          # not in the database: no oral mark
    at.button(key="oral-save").click().run()          # the stored mark is saved again, unchanged
    assert not at.exception and at.success
    assert any("1 unchanged" in m.value for m in at.markdown)


def test_reports_page(course, monkeypatch, tmp_path):
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "groups", "assign", "groups.json")
    ok(course, "exams", "import", "reports.json", "--kind", "report")
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))

    at = AppTest.from_file(GUI, default_timeout=30).run()
    at.sidebar.radio[0].set_value("📄 Relazioni").run()
    assert not at.exception
    at.selectbox(key="reports-group").set_value(1).run()
    grid = at.dataframe[0].value
    assert list(grid["esperienza"]) == ["Ottica", "Pendolo"]
    assert set(grid.columns) == {"data", "esperienza", "Clapton Eric", "Bruce Jack"}
    assert list(grid["Clapton Eric"]) == ["A", "B+"]

    summary = at.dataframe[1].value.set_index("cognome")
    assert summary.loc["Clapton", "relazioni"] == "2: Ottica A · Pendolo B+"

    at.radio(key="reports-mode").set_value("Studente").run()
    label = next(o for o in at.selectbox(key="reports-student").options if "Baker" in o)
    at.selectbox(key="reports-student").set_value(label).run()
    assert not at.exception
    table = at.dataframe[0].value
    assert list(table["voto"]) == ["C"] and list(table["punti"]) == ["22"]


def test_reports_add_tab(course, monkeypatch, tmp_path):
    ok(course, "cohort", "import", "students_2025.json")
    ok(course, "groups", "assign", "groups.json")
    ok(course, "exams", "import", "reports.json", "--kind", "report")
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))

    at = AppTest.from_file(GUI, default_timeout=30).run()
    at.sidebar.radio[0].set_value("📄 Relazioni").run()
    assert not at.exception
    at.selectbox(key="add-group").set_value(1)
    at.date_input(key="add-date").set_value(date(2025, 12, 1)).run()
    assert not at.exception
    # the group members are preselected and the grades stored on that date prefilled,
    # so saving right away is allowed and changes nothing
    assert len(at.multiselect(key="add-students-1").value) == 2
    assert not at.button(key="add-save").disabled
    at.button(key="add-save").click().run()
    assert not at.exception and not at.error
    assert at.success and "Modifiche salvate" in at.success[0].value


def test_database_in_use_elsewhere(course, monkeypatch, tmp_path):
    from labcourse import lock
    from labcourse.config import load_config
    ok(course, "cohort", "import", "students_2025.json")
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))
    database = load_config(tmp_path / "course.toml").database
    lock.acquire(database, lock.Machine("f" * 32, "altro-mac"))

    at = AppTest.from_file(GUI, default_timeout=30).run()
    assert not at.exception
    assert at.warning and "altro-mac" in at.warning[0].value
    assert not at.sidebar.radio            # nothing else is shown

    at.button(key="lock-takeover").click().run()
    assert not at.exception and not at.warning
    assert at.sidebar.radio                 # the app is back
    assert lock.read(database).machine_id == lock.this_machine().id
