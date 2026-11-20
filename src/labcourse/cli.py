"""The ``lab`` command."""

from __future__ import annotations

import sqlite3
from datetime import date as _date
from importlib import resources
from pathlib import Path
from typing import Callable, Optional

import typer

from . import analysis, db, importers, legacy, render, repo
from .config import Config, load_config
from .importers import ImportReport

app = typer.Typer(help="Manage a lab course: students, groups, attendance, exams and printable sheets.",
                  no_args_is_help=True, add_completion=False)
cohort_app = typer.Typer(help="Cohorts and student imports.", no_args_is_help=True)
students_app = typer.Typer(help="List and search students.", no_args_is_help=True)
groups_app = typer.Typer(help="Lab groups.", no_args_is_help=True)
sessions_app = typer.Typer(help="Lesson dates and hours.", no_args_is_help=True)
attendance_app = typer.Typer(help="Attendance records and reports.", no_args_is_help=True)
sheet_app = typer.Typer(help="Printable sheets.", no_args_is_help=True)
exams_app = typer.Typer(help="Exam results and eligibility.", no_args_is_help=True)
appelli_app = typer.Typer(help="Written appelli: registered students, marks, summary and oral sheets.",
                          no_args_is_help=True)
for name, sub in (("cohort", cohort_app), ("students", students_app), ("groups", groups_app),
                  ("sessions", sessions_app), ("attendance", attendance_app), ("sheet", sheet_app),
                  ("exams", exams_app), ("appelli", appelli_app)):
    app.add_typer(sub, name=name)


class State:
    config_path: Path = Path("course.toml")
    _cfg: Config | None = None

    @property
    def cfg(self) -> Config:
        if self._cfg is None:
            if not self.config_path.exists():
                fail(f"{self.config_path} not found. Run `lab init` or pass --config.")
            self._cfg = load_config(self.config_path)
        return self._cfg


state = State()


def fail(msg: str) -> None:
    typer.secho(f"Error: {msg}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


@app.callback()
def main(
    config: Path = typer.Option(Path("course.toml"), "--config", "-c", envvar="LAB_CONFIG",
                                help="Course configuration file."),
) -> None:
    state.config_path = config


def open_db() -> sqlite3.Connection:
    return db.connect(state.cfg.database)


def resolve_cohort(cohort: Optional[str]) -> str:
    c = cohort or state.cfg.default_cohort
    if not c:
        fail("no cohort given: pass --cohort or set default_cohort in course.toml")
    return c


CohortOpt = typer.Option(None, "--cohort", "-C", help="Cohort, e.g. 2025/26 (default: from course.toml).")
DryRunOpt = typer.Option(False, "--dry-run", "-n", help="Show what would change without writing.")
VerboseOpt = typer.Option(False, "--verbose", "-v", help="List every change.")
StrictOpt = typer.Option(False, "--strict", help="Write nothing if any problem is reported.")
MULTI_VALUE_FLAGS = ("-m", "--matricola")
MatricoleOpt = typer.Option(
    None, "--matricola", "-m",
    help="Student id(s): -m 100001 100002, -m 100001,100002 or -m 100001 -m 100002.",
)


def split_ids(values: Optional[list[str]]) -> list[str]:
    """Flatten ids given as repeated options and/or comma/space separated lists."""
    out: list[str] = []
    for v in values or []:
        out.extend(x for x in v.replace(",", " ").split() if x)
    return list(dict.fromkeys(out))


def run_import(
    fn: Callable[[sqlite3.Connection], ImportReport | list[ImportReport]],
    dry_run: bool, verbose: bool, strict: bool = False,
) -> None:
    cfg = state.cfg
    if not dry_run:
        copy = db.backup(cfg.database, cfg.backup_dir)
        if copy:
            typer.echo(f"Backup: {copy}")
    conn = open_db()
    try:
        conn.execute("BEGIN")
        try:
            result = fn(conn)
        except (LookupError, ValueError, FileNotFoundError) as e:
            conn.rollback()
            fail(str(e))
        reports = result if isinstance(result, list) else [result]
        for r in reports:
            typer.echo(r.render(verbose=verbose or dry_run))
        has_problems = any(r.problems for r in reports)
        if dry_run:
            conn.rollback()
            typer.secho("Dry run: nothing written.", fg=typer.colors.YELLOW)
        elif strict and has_problems:
            conn.rollback()
            fail("problems found and --strict given: nothing written.")
        else:
            conn.commit()
            if has_problems:
                typer.secho("Written, but some rows were skipped (see problems above).", fg=typer.colors.YELLOW)
    finally:
        conn.close()


def output_path(fmt: str, stem: str, output: Optional[Path]) -> Path:
    return output or state.cfg.output_dir / f"{stem}.{fmt}"


def emit(records: list[dict], fmt: str, stem: str, output: Optional[Path]) -> None:
    if fmt == "table":
        render.print_table(records)
    elif fmt in ("csv", "xlsx"):
        typer.echo(f"Written {render.export(records, output_path(fmt, stem, output))}")
    else:
        fail(f"unknown format {fmt!r}")


def slug(cohort: str) -> str:
    return cohort.replace("/", "_")


# ---------------------------------------------------------------- init

@app.command()
def init(force: bool = typer.Option(False, help="Overwrite an existing configuration.")) -> None:
    """Create course.toml (from the template) and the database."""
    path = state.config_path
    if path.exists() and not force:
        typer.echo(f"{path} already exists; leaving it untouched.")
    else:
        template = resources.files("labcourse").joinpath("course.example.toml").read_text(encoding="utf-8")
        path.write_text(template, encoding="utf-8")
        typer.echo(f"Created {path}; edit title, default_cohort and rules as needed.")
    state._cfg = None
    conn = open_db()
    conn.close()
    typer.echo(f"Database ready: {state.cfg.database}")


# ---------------------------------------------------------------- cohorts

@cohort_app.command("import")
def cohort_import(
    file: Path = typer.Argument(..., exists=True, help="E-learning export (JSON, CSV or XLSX)."),
    cohort: Optional[str] = CohortOpt, dry_run: bool = DryRunOpt, verbose: bool = VerboseOpt,
    strict: bool = StrictOpt,
) -> None:
    """Import or update the students of a cohort (matched on matricola)."""
    c = resolve_cohort(cohort)
    run_import(lambda conn: importers.import_students(conn, file, c), dry_run, verbose, strict)


@cohort_app.command("list")
def cohort_list() -> None:
    """List cohorts with number of students."""
    conn = open_db()
    rows = conn.execute(
        "SELECT c.name AS coorte, COUNT(e.student_id) AS studenti, COUNT(e.lab_group) AS con_gruppo "
        "FROM cohort c LEFT JOIN enrolment e ON e.cohort_id = c.id GROUP BY c.id ORDER BY c.name"
    ).fetchall()
    render.print_table([dict(r) for r in rows])


# ---------------------------------------------------------------- students

@students_app.command("list")
def students_list(
    cohort: Optional[str] = CohortOpt,
    group: Optional[int] = typer.Option(None, "--group", "-g"),
    order: str = typer.Option("name", help="name, group or matricola"),
    fmt: str = typer.Option("table", "--format", "-f", help="table, csv or xlsx"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
) -> None:
    """List the students of a cohort."""
    c = resolve_cohort(cohort)
    conn = open_db()
    try:
        rows = repo.cohort_students(conn, repo.cohort_id(conn, c), group=group, order=order)
    except LookupError as e:
        fail(str(e))
    emit(render.students_records(rows), fmt, f"{slug(c)}_students", output)


@students_app.command("search")
def students_search(
    matricola: Optional[list[str]] = MatricoleOpt,
    name: Optional[str] = typer.Option(None, "--name"),
    surname: Optional[str] = typer.Option(None, "--surname"),
    cohort: Optional[str] = typer.Option(None, "--cohort", "-C", help="Restrict to a cohort."),
) -> None:
    """Search students in all cohorts (names are matched ignoring case and accents)."""
    if not (matricola or name or surname):
        fail("give at least one of --matricola, --name, --surname")
    conn = open_db()
    try:
        cid = repo.cohort_id(conn, cohort) if cohort else None
    except LookupError as e:
        fail(str(e))
    rows = repo.search_students(conn, split_ids(matricola), name, surname, cid)
    if not rows:
        typer.echo("No student found.")
        raise typer.Exit(1)
    render.print_table(render.students_records(rows))


# ---------------------------------------------------------------- groups

@groups_app.command("assign")
def groups_assign(
    file: Path = typer.Argument(..., exists=True, help="JSON/CSV/XLSX with gruppo and matricola or nome+cognome."),
    cohort: Optional[str] = CohortOpt, dry_run: bool = DryRunOpt, verbose: bool = VerboseOpt,
    strict: bool = StrictOpt,
) -> None:
    """Assign students to lab groups."""
    c = resolve_cohort(cohort)
    run_import(lambda conn: importers.import_groups(conn, file, c), dry_run, verbose, strict)


@groups_app.command("show")
def groups_show(
    cohort: Optional[str] = CohortOpt,
    group: Optional[int] = typer.Option(None, "--group", "-g"),
) -> None:
    """Show students by group."""
    students_list(cohort=cohort, group=group, order="group", fmt="table", output=None)


# ---------------------------------------------------------------- sessions

@sessions_app.command("add")
def sessions_add(
    file: Path = typer.Argument(..., exists=True, help='JSON {"2025-10-01": 4, ...} or CSV/XLSX with date, hours.'),
    cohort: Optional[str] = CohortOpt, dry_run: bool = DryRunOpt, verbose: bool = VerboseOpt,
    strict: bool = StrictOpt,
) -> None:
    """Add (or update the hours of) lesson dates."""
    c = resolve_cohort(cohort)
    run_import(lambda conn: importers.import_sessions(conn, file, c), dry_run, verbose, strict)


@sessions_app.command("list")
def sessions_list(cohort: Optional[str] = CohortOpt) -> None:
    """List lesson dates, hours and number of attendance records."""
    c = resolve_cohort(cohort)
    conn = open_db()
    try:
        cid = repo.cohort_id(conn, c)
    except LookupError as e:
        fail(str(e))
    present_codes = state.cfg.attendance.present_codes
    rows = conn.execute(
        "SELECT s.date AS data, s.hours AS ore, COUNT(a.student_id) AS registrati, "
        f"SUM(a.status IN ({','.join('?' for _ in present_codes)})) AS presenti FROM session s "
        "LEFT JOIN attendance a ON a.session_id = s.id WHERE s.cohort_id = ? GROUP BY s.id ORDER BY s.date",
        (*present_codes, cid),
    ).fetchall()
    render.print_table([dict(r) for r in rows])
    total = sum(r["ore"] for r in rows)
    typer.echo(f"\n{len(rows)} sessions, {total:g} h (counted up to {state.cfg.attendance.max_counted_hours:g} h)")


# ---------------------------------------------------------------- attendance

@attendance_app.command("import")
def attendance_import(
    file: Path = typer.Argument(..., exists=True, help="Excel register or JSON."),
    cohort: Optional[str] = CohortOpt,
    hours: Optional[float] = typer.Option(None, "--hours", help="Create missing sessions with these hours."),
    dry_run: bool = DryRunOpt, verbose: bool = VerboseOpt, strict: bool = StrictOpt,
) -> None:
    """Import attendance (P/A/R/G) from an Excel register or a JSON file."""
    c = resolve_cohort(cohort)
    run_import(lambda conn: importers.import_attendance(conn, file, c, state.cfg, hours), dry_run, verbose, strict)


@attendance_app.command("report")
def attendance_report(
    cohort: Optional[str] = CohortOpt,
    fmt: str = typer.Option("table", "--format", "-f", help="table, pdf, csv or xlsx"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    order: str = typer.Option("name", help="name, group or matricola"),
) -> None:
    """Attendance per student with the fraction of hours attended."""
    c = resolve_cohort(cohort)
    cfg = state.cfg
    conn = open_db()
    try:
        sessions, rows = analysis.attendance_table(conn, c, cfg, order=order)
    except LookupError as e:
        fail(str(e))
    if fmt == "pdf":
        tex = render.attendance_tex(sessions, rows, cfg.title, c, cfg.attendance.min_fraction, cfg.rows_per_table)
        try:
            target = output_path("pdf", f"{slug(c)}_attendance", output).resolve()
            pdf = render.compile_pdf(tex, target.parent, target.stem)
        except RuntimeError as e:
            fail(str(e))
        typer.echo(f"Written {pdf}")
    else:
        emit(render.attendance_records(sessions, rows), fmt, f"{slug(c)}_attendance", output)
    below = [r for r in rows if r.fraction < cfg.attendance.min_fraction]
    typer.echo(f"{len(rows)} students, {len(sessions)} sessions held; "
               f"{len(below)} below {cfg.attendance.min_fraction:.0%}")


# ---------------------------------------------------------------- sheets

@sheet_app.command("signature")
def sheet_signature(
    date: str = typer.Option(_date.today().isoformat(), "--date", "-d", help="Date printed on the sheet."),
    cohort: Optional[str] = CohortOpt,
    group: Optional[list[int]] = typer.Option(None, "--group", "-g", help="Only these groups."),
) -> None:
    """Signature sheet for a lesson, by group."""
    c = resolve_cohort(cohort)
    cfg = state.cfg
    try:
        iso = importers.parse_date(date)
    except ValueError as e:
        fail(str(e))
    conn = open_db()
    try:
        students = repo.cohort_students(conn, repo.cohort_id(conn, c), order="group")
    except LookupError as e:
        fail(str(e))
    if group:
        students = [s for s in students if s.lab_group in group]
    if not students:
        fail("no students to print")
    tex = render.signature_tex(students, cfg.title, iso, cfg.rows_per_table)
    try:
        pdf = render.compile_pdf(tex, cfg.output_dir, f"{iso}_signature")
    except RuntimeError as e:
        fail(str(e))
    typer.echo(f"Written {pdf}")


# ---------------------------------------------------------------- exams

@exams_app.command("import")
def exams_import(
    file: Path = typer.Argument(..., exists=True),
    kind: str = typer.Option(..., "--kind", "-k", help="written, oral or report"),
    cohort: Optional[str] = CohortOpt, dry_run: bool = DryRunOpt, verbose: bool = VerboseOpt,
    strict: bool = StrictOpt,
) -> None:
    """Import marks.

    written/oral: {"2026-01-20": {"<matricola>": "27", ...}}  (A absent, R withdrawn, 30L cum laude)\n
    report:       {"2025-12-01": {"<group>": {"<experiment>": "B+"}}}
    """
    c = resolve_cohort(cohort)
    if kind == "report":
        fn = lambda conn: importers.import_reports(conn, file, c, state.cfg)  # noqa: E731
    elif kind in ("written", "oral"):
        fn = lambda conn: importers.import_marks(conn, file, c, kind)  # noqa: E731
    else:
        fail("--kind must be written, oral or report")
    run_import(fn, dry_run, verbose, strict)


@exams_app.command("list")
def exams_list(cohort: Optional[str] = CohortOpt) -> None:
    """List exam sessions and experiments with the number of marks."""
    c = resolve_cohort(cohort)
    conn = open_db()
    try:
        rows = repo.list_assessments(conn, repo.cohort_id(conn, c))
    except LookupError as e:
        fail(str(e))
    render.print_table([{"tipo": r["kind"], "data": r["date"], "esperienza": r["label"], "voti": r["n"]}
                        for r in rows])


@exams_app.command("eligible")
def exams_eligible(
    cohort: Optional[str] = typer.Option(
        None, "--cohort", "-C",
        help="Cohort, or 'all'. Default: all cohorts with -m, otherwise default_cohort from course.toml."),
    matricola: Optional[list[str]] = MatricoleOpt,
    show_all: bool = typer.Option(False, "--all", "-a", help="Also list students who are not admitted."),
    fmt: str = typer.Option("table", "--format", "-f", help="table, csv or xlsx"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
) -> None:
    """Students admitted to the oral: written passed and attendance above the minimum."""
    matricola = split_ids(matricola)
    conn = open_db()
    if cohort == "all" or (cohort is None and matricola):
        cohorts = repo.list_cohorts(conn)
        stem = "all_exams"
    else:
        c = resolve_cohort(cohort)
        cohorts = [c]
        stem = f"{slug(c)}_exams"
    try:
        rows, warnings = analysis.exam_table_multi(conn, cohorts, state.cfg, matricole=matricola)
    except LookupError as e:
        fail(str(e))
    for w in warnings:
        typer.secho(f"Warning: {w}", fg=typer.colors.YELLOW, err=True)
    shown = rows if (show_all or matricola) else [r for r in rows if r.eligible]
    emit(render.exam_records(shown, with_cohort=len(cohorts) > 1), fmt, stem, output)
    typer.echo(f"\n{sum(r.eligible for r in rows)} of {len(rows)} students admitted to the oral.")


# ---------------------------------------------------------------- appelli

def resolve_appello(conn: sqlite3.Connection, date: Optional[str]) -> str:
    """ISO date of the appello: the one given, or the most recent stored."""
    if date:
        try:
            iso = importers.parse_date(date)
        except ValueError as e:
            fail(str(e))
        try:
            repo.appello_id(conn, iso)
        except LookupError:
            known = ", ".join(r["date"] for r in repo.list_appelli(conn)) or "none"
            fail(f"no appello on {iso} (appelli: {known})")
        return iso
    rows = repo.list_appelli(conn)
    if not rows:
        fail("no appello yet: use `lab appelli import` or `lab appelli add`")
    return rows[-1]["date"]


DateOpt = typer.Option(None, "--date", "-d", help="Appello date (default: the most recent).")


@appelli_app.command("import")
def appelli_import(
    file: Path = typer.Argument(..., exists=True,
                                help="Esse3/e-learning list (XLSX, XLS, CSV) or written results JSON."),
    date: Optional[str] = typer.Option(None, "--date", "-d",
                                       help="Appello date (lists: if not found in the file; JSON: only this date)."),
    sheet: Optional[str] = typer.Option(None, "--sheet", help="Excel sheet (default: the first)."),
    dry_run: bool = DryRunOpt, verbose: bool = VerboseOpt, strict: bool = StrictOpt,
) -> None:
    """Register students for an appello and record their marks.

    Rows without a mark only register the student. Marks of students in the database
    are also stored as written results (so they count for admission to the oral);
    students who are not in the database are kept in the appello list.
    """
    run_import(lambda conn: importers.import_appello(conn, file, date, sheet), dry_run, verbose, strict)


@appelli_app.command("list")
def appelli_list() -> None:
    """Appelli with number of registered students and of marks."""
    conn = open_db()
    rows = repo.list_appelli(conn)
    render.print_table([{"data": r["date"], "iscritti": r["iscritti"], "con voto": r["con_voto"]} for r in rows])


@appelli_app.command("add")
def appelli_add(
    date: str = typer.Option(..., "--date", "-d", help="Appello date (created if new)."),
    matricola: list[str] = typer.Option(..., "--matricola", "-m",
                                        help="Student id(s): -m 100001 100002 or -m 100001,100002."),
    dry_run: bool = DryRunOpt, verbose: bool = VerboseOpt,
) -> None:
    """Register students for an appello by hand."""
    try:
        iso = importers.parse_date(date)
    except ValueError as e:
        fail(str(e))

    def fn(conn):
        rep = ImportReport(f"Appello {iso}")
        try:
            aid = repo.appello_id(conn, iso)
        except LookupError:
            aid = repo.appello_id(conn, iso, create=True)
            rep.count("new appello")
        for m in split_ids(matricola):
            outcome, _ = repo.upsert_registration(conn, aid, m)
            rep.count("registered" if outcome == "new" else "already registered")
            if repo.student_by_matricola(conn, m) is None:
                rep.problem(f"matricola {m} is not in the database (registered anyway)")
        return rep

    run_import(fn, dry_run, verbose)


@appelli_app.command("remove")
def appelli_remove(
    date: str = typer.Option(..., "--date", "-d"),
    matricola: list[str] = typer.Option(..., "--matricola", "-m"),
    dry_run: bool = DryRunOpt,
) -> None:
    """Remove students from an appello."""
    def fn(conn):
        iso = importers.parse_date(date)
        aid = repo.appello_id(conn, iso)
        rep = ImportReport(f"Appello {iso}")
        for m in split_ids(matricola):
            if repo.remove_registration(conn, aid, m):
                rep.count("removed")
            else:
                rep.problem(f"matricola {m} is not registered")
        return rep

    run_import(fn, dry_run, verbose=True)


@appelli_app.command("show")
def appelli_show(
    date: Optional[str] = DateOpt,
    oral: bool = typer.Option(False, "--oral", help="Oral exam sheet: admitted students only, with empty Orale/Note columns."),
    show_all: bool = typer.Option(True, "--all/--admitted", help="All registered students (default) or only those admitted."),
    fmt: str = typer.Option("table", "--format", "-f", help="table, pdf, csv or xlsx"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
) -> None:
    """Appello summary (registered students, marks, admission) or oral exam sheet."""
    cfg = state.cfg
    conn = open_db()
    iso = resolve_appello(conn, date)
    rows = analysis.appello_table(conn, cfg, iso)
    admitted = [r for r in rows if r.eligible]
    shown = admitted if (oral or not show_all) else rows
    stem = f"{iso}_{'orali' if oral else 'appello'}"
    unknown = [r.matricola for r in rows if r.exam is None]
    if unknown:
        typer.secho(f"Warning: not in the database: {', '.join(unknown)}", fg=typer.colors.YELLOW, err=True)
    if fmt == "pdf":
        if not shown:
            fail("no student to print")
        tex = render.appello_tex(shown, cfg.title, iso, cfg.rows_per_table, oral=oral)
        try:
            target = output_path("pdf", stem, output).resolve()
            pdf = render.compile_pdf(tex, target.parent, target.stem)
        except RuntimeError as e:
            fail(str(e))
        typer.echo(f"Written {pdf}")
    else:
        emit(render.appello_records(shown), fmt, stem, output)
    typer.echo(f"\nAppello {iso}: {len(rows)} registered, {sum(bool(r.appello_mark) for r in rows)} with a mark, "
               f"{len(admitted)} admitted to the oral.")


# ---------------------------------------------------------------- legacy

@app.command("migrate-legacy")
def migrate_legacy_cmd(
    students: Path = typer.Option(Path("data/students.db"), exists=True, help="Old students database."),
    attendance: Optional[Path] = typer.Option(None, exists=True, help="Old attendance database."),
    exams: Optional[Path] = typer.Option(None, exists=True, help="Old exams database."),
    dates: Optional[list[str]] = typer.Option(
        None, help="COHORT=PATH for each dates database; default: every dates_YYYY_YY.db next to --students."),
    hours: Optional[float] = typer.Option(None, help="Hours for attendance dates missing from the dates db."),
    dry_run: bool = DryRunOpt, verbose: bool = VerboseOpt, strict: bool = StrictOpt,
) -> None:
    """Copy data from the old lborg databases into the new database (safe to re-run)."""
    dates_map = {}
    for item in dates or []:
        if "=" not in item:
            fail(f"--dates expects COHORT=PATH, got {item!r}")
        c, p = item.split("=", 1)
        if not Path(p).exists():
            fail(f"{p} not found")
        dates_map[c] = Path(p)
    run_import(
        lambda conn: legacy.migrate_legacy(conn, state.cfg, students, attendance, dates_map, exams, hours),
        dry_run, verbose, strict,
    )


@app.command("gui")
def gui_cmd(
    port: int = typer.Option(8501, help="Port for the web interface."),
    browser: bool = typer.Option(True, help="Open the browser automatically."),
) -> None:
    """Open the graphical interface in the browser."""
    import os
    import subprocess
    import sys
    from importlib.util import find_spec

    if find_spec("streamlit") is None:
        fail("the GUI needs streamlit: pip install -e '.[gui]'")
    if not state.config_path.exists():
        fail(f"{state.config_path} not found. Run `lab init` or pass --config.")
    script = Path(__file__).with_name("gui.py")
    env = {**os.environ, "LAB_CONFIG": str(state.config_path.resolve())}
    cmd = [sys.executable, "-m", "streamlit", "run", str(script), "--server.port", str(port),
           "--server.headless", "false" if browser else "true", "--browser.gatherUsageStats", "false",
           "--client.toolbarMode", "minimal"]
    typer.echo(f"GUI on http://localhost:{port}  (Ctrl+C to stop)")
    try:
        subprocess.run(cmd, env=env, check=False)
    except KeyboardInterrupt:
        pass


@app.command("backup")
def backup_cmd() -> None:
    """Make a timestamped copy of the database now."""
    copy = db.backup(state.cfg.database, state.cfg.backup_dir)
    typer.echo(f"Backup: {copy}" if copy else "No database yet.")


def expand_multi(argv: list[str], flags: tuple[str, ...] = MULTI_VALUE_FLAGS) -> list[str]:
    """Let ``-m 1 2 3`` mean ``-m 1 -m 2 -m 3`` (click options take a fixed number of values).

    Values are collected until the next token that starts with ``-``. Only used for
    options of commands that take no positional arguments.
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        out.append(tok)
        i += 1
        if tok in flags:
            first = True
            while i < len(argv) and (first or not argv[i].startswith("-")):
                if not first:
                    out.append(tok)
                out.append(argv[i])
                i += 1
                first = False
        if tok == "--":
            out.extend(argv[i:])
            break
    return out


def run() -> None:
    """Console entry point."""
    import sys

    app(args=expand_multi(sys.argv[1:]), prog_name="lab")


if __name__ == "__main__":
    run()
