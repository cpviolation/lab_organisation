"""Statistics on students' results: distributions, appelli, correlations, timing.

Everything returns pandas DataFrames built from the database, so the GUI (or a
notebook) can chart and filter them.

Conventions:
* 30L counts as 30 in averages; cum laude marks are counted separately.
* Written marks: absent (A) and withdrawn (R) are not "sat"; insufficient (I) is a
  fail without a numeric value; numeric marks below the pass mark are fails.
* Report score = mean points per experiment (so students with a different number of
  experiments are comparable).
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

from . import repo
from .analysis import attendance_table
from .config import Config
from .marks import Mark


def _value(mark: Mark) -> float | None:
    """Numeric value for statistics (30L -> 30); None when there is no number."""
    if mark.is_cum_laude:
        return 30.0
    if mark.raw == "I" or not mark.sat:
        return None
    return float(mark.numeric)


def _days(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return float((date.fromisoformat(b) - date.fromisoformat(a)).days)


def results_frame(conn: sqlite3.Connection, cfg: Config, cohorts: list[str] | None = None) -> pd.DataFrame:
    """One row per enrolment with the student's results and their timing.

    Columns: cohort, matricola, group, attendance, lessons_end,
    written, written_date, written_attempts, first_written_date, written_passed,
    oral, oral_cum_laude, oral_date, report_mean, report_n, report_date,
    days_end_to_written, days_written_to_oral, days_end_to_oral, oral_minus_written.
    """
    rows = []
    for cohort in cohorts or repo.list_cohorts(conn):
        cid = repo.cohort_id(conn, cohort)
        sessions, att = attendance_table(conn, cohort, cfg)
        lessons_end = max((s.date for s in sessions), default=None)
        results = repo.cohort_results(conn, cid)
        scale = cfg.exams.report_scale
        for a in att:
            res = results.get(a.student.id, [])
            written = [(r.date, Mark.parse(r.raw_mark)) for r in res if r.kind == "written"]
            sat = [(d, m) for d, m in written if m.sat]
            passed = [(d, m) for d, m in sat if m.is_pass(cfg.exams.written_pass)]
            # the written exam that led to the oral: best passing one (or the latest sat)
            if passed:
                w_date, w_mark = max(passed, key=lambda dm: (_value(dm[1]) or 0, dm[0]))
            elif sat:
                w_date, w_mark = max(sat, key=lambda dm: dm[0])
            else:
                w_date, w_mark = None, None
            orals = [(r.date, Mark.parse(r.raw_mark)) for r in res if r.kind == "oral"]
            orals_sat = [(d, m) for d, m in orals if m.sat]
            o_date, o_mark = max(orals_sat, key=lambda dm: dm[0]) if orals_sat else (None, None)
            reports = [r for r in res if r.kind == "report"]
            points = []
            for r in reports:
                try:
                    points.append(scale.points(r.raw_mark))
                except ValueError:
                    pass
            w_val = _value(w_mark) if w_mark else None
            o_val = _value(o_mark) if o_mark else None
            rows.append({
                "cohort": cohort,
                "matricola": a.student.matricola,
                "group": a.student.lab_group,
                "attendance": a.fraction,
                "lessons_end": lessons_end,
                "written": w_val,
                "written_raw": w_mark.raw if w_mark else None,
                "written_date": w_date,
                "written_attempts": len(sat),
                "first_written_date": min((d for d, _ in sat), default=None),
                "written_passed": bool(passed),
                "oral": o_val,
                "oral_cum_laude": bool(o_mark and o_mark.is_cum_laude),
                "oral_date": o_date,
                "report_mean": sum(points) / len(points) if points else None,
                "report_n": len(points),
                "report_date": max((r.date for r in reports), default=None),
                "days_end_to_written": _days(lessons_end, w_date),
                "days_written_to_oral": _days(w_date, o_date),
                "days_end_to_oral": _days(lessons_end, o_date),
                "oral_minus_written": (o_val - w_val) if (o_val is not None and w_val is not None) else None,
            })
    df = pd.DataFrame(rows)
    for col in ("written", "oral", "report_mean", "attendance", "days_end_to_written",
                "days_written_to_oral", "days_end_to_oral", "oral_minus_written"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def summary(df: pd.DataFrame) -> pd.DataFrame:
    """Count, mean, median and spread of written, oral and report score per cohort."""
    out = []
    for cohort, g in df.groupby("cohort"):
        for col, label in (("written", "Scritto"), ("oral", "Orale"), ("report_mean", "Relazioni (punti medi)")):
            s = g[col].dropna()
            n = len(s)
            out.append({
                "coorte": cohort, "prova": label, "n": n,
                "media": round(s.mean(), 1) if n else None,
                "mediana": round(s.median(), 1) if n else None,
                "dev. std": round(s.std(), 1) if n > 1 else None,
                "min": round(s.min(), 1) if n else None,
                "max": round(s.max(), 1) if n else None,
                "lodi": str(int(g["oral_cum_laude"].sum())) if col == "oral" else "",
            })
    return pd.DataFrame(out)


def appelli_frame(conn: sqlite3.Connection, cfg: Config, cohorts: list[str] | None = None) -> pd.DataFrame:
    """One row per (written appello date, cohort): how many sat, passed, average mark,
    and how long after the end of that cohort's lessons the appello was."""
    rows = []
    for cohort in cohorts or repo.list_cohorts(conn):
        cid = repo.cohort_id(conn, cohort)
        sessions = repo.list_sessions(conn, cid, held_only=True)
        lessons_end = max((s.date for s in sessions), default=None)
        by_date: dict[str, list[Mark]] = {}
        for res in repo.cohort_results(conn, cid, kind="written").values():
            for r in res:
                by_date.setdefault(r.date, []).append(Mark.parse(r.raw_mark))
        for d, marks in sorted(by_date.items()):
            sat = [m for m in marks if m.sat]
            passed = [m for m in sat if m.is_pass(cfg.exams.written_pass)]
            values = [v for v in (_value(m) for m in sat) if v is not None]
            rows.append({
                "date": d, "cohort": cohort,
                "registered": len(marks), "sat": len(sat),
                "absent": sum(m.is_absent for m in marks), "withdrawn": sum(m.is_withdrawn for m in marks),
                "passed": len(passed),
                "pass_rate": len(passed) / len(sat) if sat else None,
                "mean": sum(values) / len(values) if values else None,
                "mean_passed": (sum(_value(m) for m in passed) / len(passed)) if passed else None,
                "days_after_lessons": _days(lessons_end, d),
            })
    return pd.DataFrame(rows)


def correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Spearman correlation (robust to the 18-30 scale) between pairs of measures, with n."""
    pairs = [
        ("written", "oral", "Scritto ↔ Orale"),
        ("report_mean", "oral", "Relazioni ↔ Orale"),
        ("report_mean", "written", "Relazioni ↔ Scritto"),
        ("attendance", "written", "Presenze ↔ Scritto"),
        ("attendance", "oral", "Presenze ↔ Orale"),
        ("days_end_to_written", "written", "Attesa fine corso→scritto ↔ Scritto"),
        ("days_written_to_oral", "oral", "Attesa scritto→orale ↔ Orale"),
    ]
    out = []
    for a, b, label in pairs:
        sub = df[[a, b]].dropna()
        n = len(sub)
        # Spearman = Pearson on ranks (avoids depending on scipy)
        rho = sub[a].rank().corr(sub[b].rank()) if n >= 5 else None
        out.append({"coppia": label, "n": n, "rho (Spearman)": None if rho is None or pd.isna(rho) else round(rho, 2)})
    return pd.DataFrame(out)


WAIT_BINS = [-10_000, 0, 30, 90, 180, 365, 10_000]
WAIT_LABELS = ["entro 1 mese", "1–3 mesi", "3–6 mesi", "6–12 mesi", "oltre 1 anno"]


def by_wait(df: pd.DataFrame, days_col: str, value_col: str, first_label: str = "prima o lo stesso giorno") -> pd.DataFrame:
    """Mean of ``value_col`` grouped by how long the student waited (``days_col``).

    The first bin holds waits of zero or negative days (e.g. a written exam taken
    before the end of the lessons); ``first_label`` names it.
    """
    labels = [first_label, *WAIT_LABELS]
    sub = df[[days_col, value_col]].dropna()
    if sub.empty:
        return pd.DataFrame({"attesa": labels, "n": 0, "media": None})
    cats = pd.cut(sub[days_col], WAIT_BINS, labels=labels, right=True)
    g = sub.groupby(cats, observed=False)[value_col]
    return pd.DataFrame({"attesa": labels, "n": g.count().values, "media": g.mean().round(1).values})
