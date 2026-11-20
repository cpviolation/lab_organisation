import pandas as pd
from conftest import run

from labcourse import importers, repo, stats


def course_with_results(conn, fx, cfg, tmp_path):
    run(conn, importers.import_students, fx / "students_2025.json", "2025/26")
    run(conn, importers.import_groups, fx / "groups.json", "2025/26")
    run(conn, importers.import_sessions, fx / "sessions.json", "2025/26")
    run(conn, importers.import_attendance, fx / "attendance.json", "2025/26", cfg)   # lessons end 2025-10-01
    run(conn, importers.import_marks, fx / "written.json", "2025/26", "written")
    run(conn, importers.import_reports, fx / "reports.json", "2025/26", cfg)
    oral = tmp_path / "oral.json"
    oral.write_text('{"2026-02-01": {"100001": "28", "100004": "30L", "100005": "20"}}')
    run(conn, importers.import_marks, oral, "2025/26", "oral")


def test_results_frame(conn, fx, cfg, tmp_path):
    course_with_results(conn, fx, cfg, tmp_path)
    df = stats.results_frame(conn, cfg).set_index("matricola")
    assert df.loc["100001", "written"] == 27 and df.loc["100001", "oral"] == 28
    assert df.loc["100001", "oral_minus_written"] == 1
    assert df.loc["100004", "written"] == 30 and df.loc["100004", "oral_cum_laude"]   # 30L counts 30
    assert df.loc["100002", "written"] == 19 and df.loc["100002", "written_attempts"] == 2
    assert df.loc["100003", "written_attempts"] == 1                                   # absent not counted
    assert df.loc["100001", "days_end_to_written"] == (pd.Timestamp("2026-01-20") - pd.Timestamp("2025-10-01")).days
    assert df.loc["100001", "days_written_to_oral"] == 12
    assert df.loc["100001", "report_mean"] == (27 + 30) / 2


def test_summary_appelli_correlations_and_wait(conn, fx, cfg, tmp_path):
    course_with_results(conn, fx, cfg, tmp_path)
    df = stats.results_frame(conn, cfg)
    summ = stats.summary(df).set_index("prova")
    assert summ.loc["Orale", "n"] == 3 and summ.loc["Orale", "lodi"] == "1"

    ap = stats.appelli_frame(conn, cfg).set_index("date")
    jan = ap.loc["2026-01-20"]
    assert (jan["registered"], jan["sat"], jan["absent"], jan["passed"]) == (5, 4, 1, 3)
    assert jan["pass_rate"] == 0.75

    corr = stats.correlations(df).set_index("coppia")
    assert corr.loc["Scritto ↔ Orale", "n"] == 3
    assert pd.isna(corr.loc["Scritto ↔ Orale", "rho (Spearman)"])      # fewer than 5 students

    w = stats.by_wait(df, "days_end_to_written", "written")
    assert list(w["attesa"])[0] == "prima o lo stesso giorno"
    assert w["n"].sum() == df["written"].notna().sum()


def test_spearman_on_ranks():
    df = pd.DataFrame({"written": [18, 20, 22, 24, 26, 28], "oral": [19, 21, 20, 25, 27, 30],
                       "report_mean": [None] * 6, "attendance": [1.0] * 6,
                       "days_end_to_written": [None] * 6, "days_written_to_oral": [None] * 6})
    corr = stats.correlations(df).set_index("coppia")
    assert 0.9 < corr.loc["Scritto ↔ Orale", "rho (Spearman)"] <= 1
