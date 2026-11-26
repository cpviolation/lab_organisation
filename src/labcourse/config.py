"""Course configuration loaded from ``course.toml``."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .marks import ReportScale

DEFAULT_REPORT_SCALE = (
    "A+", "A", "A-", "A-/B+",
    "B+", "B", "B-", "B-/C+",
    "C+", "C", "C-", "C-/D+",
    "D+", "D", "D-", "E",
)


@dataclass(frozen=True)
class AttendanceRules:
    min_fraction: float = 0.75
    max_counted_hours: float = 56
    present_codes: tuple[str, ...] = ("P", "R", "G")


@dataclass(frozen=True)
class ExamRules:
    written_pass: int = 18
    written_policy: str = "best"  # or "latest"
    report_scale: ReportScale = field(default_factory=lambda: ReportScale(DEFAULT_REPORT_SCALE))


@dataclass(frozen=True)
class ExcelFormat:
    name_column: str = "Nome"
    surname_column: str = "Cognome"
    matricola_column: str = ""
    time_marker: str = ""


@dataclass(frozen=True)
class Config:
    root: Path = Path(".")
    title: str = "Laboratorio"
    database: Path = Path("data/lab.db")
    output_dir: Path = Path("output")
    backup_dir: Path = Path("data/backups")
    default_cohort: str | None = None
    attendance: AttendanceRules = field(default_factory=AttendanceRules)
    exams: ExamRules = field(default_factory=ExamRules)
    excel: ExcelFormat = field(default_factory=ExcelFormat)
    rows_per_table: int = 32


def load_config(path: str | Path) -> Config:
    path = Path(path).expanduser()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    root = path.resolve().parent

    def p(key: str, default: str) -> Path:
        # "~" and environment variables are expanded, so that one course.toml can point
        # to e.g. a Google Drive folder on computers with different home directories
        value = Path(os.path.expandvars(raw.get(key, default))).expanduser()
        return value if value.is_absolute() else root / value

    att = raw.get("attendance", {})
    ex = raw.get("exams", {})
    xl = raw.get("excel", {})
    sh = raw.get("sheets", {})

    policy = ex.get("written_policy", "best")
    if policy not in ("best", "latest"):
        raise ValueError(f"exams.written_policy must be 'best' or 'latest', not {policy!r}")

    return Config(
        root=root,
        title=raw.get("title", "Laboratorio"),
        database=p("database", "data/lab.db"),
        output_dir=p("output_dir", "output"),
        backup_dir=p("backup_dir", "data/backups"),
        default_cohort=raw.get("default_cohort") or None,
        attendance=AttendanceRules(
            min_fraction=float(att.get("min_fraction", 0.75)),
            max_counted_hours=float(att.get("max_counted_hours", 56)),
            present_codes=tuple(c.upper() for c in att.get("present_codes", ["P", "R", "G"])),
        ),
        exams=ExamRules(
            written_pass=int(ex.get("written_pass", 18)),
            written_policy=policy,
            report_scale=ReportScale(
                tuple(g.upper() for g in ex.get("report_scale", DEFAULT_REPORT_SCALE)),
                int(ex.get("report_top_points", 31)),
                tuple((str(k).replace(" ", "").upper(), str(v).replace(" ", "").upper())
                      for k, v in ex.get("report_aliases", {}).items()),
            ),
        ),
        excel=ExcelFormat(
            name_column=xl.get("name_column", "Nome"),
            surname_column=xl.get("surname_column", "Cognome"),
            matricola_column=xl.get("matricola_column", ""),
            time_marker=xl.get("time_marker", ""),
        ),
        rows_per_table=int(sh.get("rows_per_table", 32)),
    )
