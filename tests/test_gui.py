from pathlib import Path

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
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "course.toml"))

    at = AppTest.from_file(GUI, default_timeout=30).run()
    assert not at.exception
    pages = at.sidebar.radio[0].options
    assert len(pages) == 7
    for page in pages:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, (page, at.exception)
        assert at.header[0].value  # every page has a title


def test_missing_config(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_CONFIG", str(tmp_path / "missing.toml"))
    at = AppTest.from_file(GUI, default_timeout=30).run()
    assert at.error and "lab init" in at.error[0].value
