"""Output: LaTeX/PDF sheets from Jinja2 templates, CSV/Excel exports, terminal tables."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

import jinja2
from tabulate import tabulate

from .analysis import AttendanceRow, ExamRow, OralRow
from .repo import StudentRow
from .rules import SessionInfo

_TEX_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def tex_escape(value: object) -> str:
    return "".join(_TEX_ESCAPES.get(c, c) for c in str(value))


def _env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.PackageLoader("labcourse", "templates"),
        block_start_string="<%", block_end_string="%>",
        variable_start_string="<<", variable_end_string=">>",
        comment_start_string="<#", comment_end_string="#>",
        trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["tex"] = tex_escape
    return env


def chunk_groups(
    groups: Sequence[tuple[int | None, list[StudentRow]]], max_rows: int
) -> list[list[tuple[int | None, list[StudentRow]]]]:
    """Split groups into tables of at most ``max_rows`` students, never splitting a group
    (a group larger than ``max_rows`` gets a table of its own)."""
    tables: list[list] = []
    current: list = []
    rows = 0
    for group, students in groups:
        if current and rows + len(students) > max_rows:
            tables.append(current)
            current, rows = [], 0
        current.append((group, students))
        rows += len(students)
    if current:
        tables.append(current)
    return tables


def signature_tex(students: Iterable[StudentRow], title: str, date: str, max_rows: int) -> str:
    grouped: dict[int | None, list[StudentRow]] = {}
    for s in students:
        grouped.setdefault(s.lab_group, []).append(s)
    order = sorted(grouped, key=lambda g: (g is None, g or 0))
    tables = chunk_groups([(g, grouped[g]) for g in order], max_rows)
    return _env().get_template("signature.tex.j2").render(title=title, date=date, tables=tables)


def attendance_tex(
    sessions: list[SessionInfo], rows: list[AttendanceRow], title: str, cohort: str,
    min_fraction: float, max_rows: int,
) -> str:
    tables = [rows[i:i + max_rows] for i in range(0, len(rows), max_rows)] or [[]]
    return _env().get_template("attendance.tex.j2").render(
        title=title, cohort=cohort, sessions=sessions, tables=tables, min_fraction=min_fraction,
    )


def compile_pdf(tex: str, out_dir: Path, stem: str) -> Path:
    """Write ``<stem>.tex`` under ``out_dir/latex`` and compile it to ``out_dir/<stem>.pdf``."""
    latex_dir = out_dir / "latex"
    latex_dir.mkdir(parents=True, exist_ok=True)
    tex_path = latex_dir / f"{stem}.tex"
    tex_path.write_text(tex, encoding="utf-8")
    if shutil.which("pdflatex") is None:
        raise RuntimeError(f"pdflatex not found; the LaTeX source is in {tex_path}")
    proc = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={latex_dir}", tex_path.name],
        cwd=latex_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.splitlines()[-20:])
        raise RuntimeError(f"pdflatex failed on {tex_path}:\n{tail}")
    pdf = out_dir / f"{stem}.pdf"
    shutil.move(latex_dir / f"{stem}.pdf", pdf)
    return pdf


# ---------------------------------------------------------------- tabular data

def students_records(students: Iterable[StudentRow]) -> list[dict]:
    return [
        {"cognome": s.surname, "nome": s.name, "matricola": s.matricola, "email": s.email or "",
         "coorte": s.cohort or "", "gruppo": s.lab_group if s.lab_group is not None else ""}
        for s in students
    ]


def attendance_records(sessions: list[SessionInfo], rows: list[AttendanceRow]) -> list[dict]:
    out = []
    for r in rows:
        rec = {"cognome": r.student.surname, "nome": r.student.name, "matricola": r.student.matricola,
               "gruppo": r.student.lab_group if r.student.lab_group is not None else ""}
        for s in sessions:
            rec[s.date] = r.statuses.get(s.id, "")
        rec["ore"] = r.hours
        rec["%"] = round(r.fraction * 100)
        out.append(rec)
    return out


def exam_records(rows: list[ExamRow], with_cohort: bool = False) -> list[dict]:
    return [
        {"cognome": r.student.surname, "nome": r.student.name, "matricola": r.student.matricola,
         **({"coorte": r.student.cohort or ""} if with_cohort else {}),
         "gruppo": r.student.lab_group if r.student.lab_group is not None else "",
         "presenza %": round(r.attendance * 100), "scritto": r.written, "relazioni": r.reports,
         "punti relazioni": f"{r.report_points:g}" if r.report_points is not None else "",
         "orale": r.oral, "ammesso": "sì" if r.eligible else "no", "motivo": r.reasons}
        for r in rows
    ]


def oral_records(rows: list[OralRow], with_cohort: bool = True) -> list[dict]:
    out = []
    for i, r in enumerate(rows, start=1):
        e = r.exam
        rec = {"n.": i,
               "cognome": e.student.surname if e else "?",
               "nome": e.student.name if e else "?",
               "matricola": r.matricola}
        if with_cohort:
            rec["coorte"] = ", ".join(r.cohorts) or "-"
        rec.update({
            "gruppo": e.student.lab_group if e and e.student.lab_group is not None else "",
            "presenza %": round(e.attendance * 100) if e else "",
            "scritto appello": r.appello_mark,
            "scritto valido": e.written if e else "-",
            "punti relazioni": f"{e.report_points:g}" if e and e.report_points is not None else "",
            "orale": e.oral if e else "-",
            "ammesso": "sì" if r.eligible else "no",
            "motivo": r.reason,
        })
        out.append(rec)
    return out


def orals_tex(rows: list[OralRow], title: str, appello_date: str, max_rows: int) -> str:
    """Printable oral sheet: admitted students with empty columns for the oral mark and notes."""
    tables = [rows[i:i + max_rows] for i in range(0, len(rows), max_rows)] or [[]]
    return _env().get_template("orals.tex.j2").render(
        title=title, date=appello_date, tables=tables, offset=[i * max_rows for i in range(len(tables))],
    )


def print_table(records: list[dict]) -> None:
    if not records:
        print("(no rows)")
        return
    print(tabulate(records, headers="keys", tablefmt="simple", disable_numparse=True))


def export(records: list[dict], path: Path) -> Path:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        def csv_value(value):
            if isinstance(value, str) and (
                value.lstrip().startswith(("=", "+", "-", "@"))
                or value.startswith(("\t", "\r", "\n"))
            ):
                return "'" + value
            return value

        safe_records = [
            {key: csv_value(value) for key, value in record.items()}
            for record in records
        ]
        pd.DataFrame(safe_records).to_csv(path, index=False)
    elif path.suffix.lower() == ".xlsx":
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(records).to_excel(writer, index=False)
            for sheet in writer.book.worksheets:
                for row in sheet.iter_rows():
                    for cell in row:
                        if isinstance(cell.value, str):
                            cell.data_type = "s"
    else:
        raise ValueError("export format must be .csv or .xlsx")
    return path
