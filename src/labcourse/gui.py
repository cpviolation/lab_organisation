"""Streamlit GUI for labcourse. Start it with ``lab gui``.

The page uses the same library functions as the ``lab`` command: every write is
previewed first (dry run), backed up and applied in one transaction.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from labcourse import analysis, db, importers, render, repo
from labcourse.cli import split_ids
from labcourse.config import Config, load_config
from labcourse.importers import ImportReport

st.set_page_config(page_title="Laboratorio", page_icon="🧪", layout="wide")


# ---------------------------------------------------------------- setup

def config_path() -> Path:
    return Path(os.environ.get("LAB_CONFIG", "course.toml")).resolve()


@st.cache_resource
def _load_config(path: str, mtime: float) -> Config:
    return load_config(path)


def get_config() -> Config:
    path = config_path()
    if not path.exists():
        st.error(f"File di configurazione non trovato: `{path}`. Esegui `lab init` nella cartella del corso.")
        st.stop()
    return _load_config(str(path), path.stat().st_mtime)


def connect(cfg: Config) -> sqlite3.Connection:
    return db.connect(cfg.database)


def slug(cohort: str) -> str:
    return cohort.replace("/", "_")


def download_buttons(records: list[dict], stem: str, key: str) -> None:
    """CSV and Excel download buttons for a table."""
    if not records:
        return
    c1, c2, _ = st.columns([1, 1, 2])
    with tempfile.TemporaryDirectory() as tmp:
        for col, ext, mime in ((c1, "csv", "text/csv"),
                               (c2, "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")):
            path = render.export(records, Path(tmp) / f"{stem}.{ext}")
            col.download_button(f"Scarica {ext.upper()}", path.read_bytes(), file_name=path.name,
                                mime=mime, key=f"{key}-{ext}", width="stretch")


def pdf_button(label: str, make_tex: Callable[[], str], out_dir: Path, stem: str, key: str) -> None:
    """Generate a PDF on click, save it in the output folder and offer it for download."""
    if st.button(label, key=key, type="primary"):
        try:
            with st.spinner("Compilo il PDF…"):
                pdf = render.compile_pdf(make_tex(), out_dir, stem)
        except RuntimeError as e:
            st.error(str(e))
            return
        st.session_state[f"{key}-pdf"] = str(pdf)
    saved = st.session_state.get(f"{key}-pdf")
    if saved and Path(saved).exists():
        st.success(f"Salvato in `{saved}`")
        st.download_button("Scarica PDF", Path(saved).read_bytes(), file_name=Path(saved).name,
                           mime="application/pdf", key=f"{key}-dl")


def show_report(rep: ImportReport) -> None:
    st.markdown(f"**{rep.title}**: {rep.summary()}")
    if rep.problems:
        with st.expander(f"⚠️ {len(rep.problems)} problemi", expanded=True):
            st.markdown("\n".join(f"- {p}" for p in rep.problems))
    if rep.changes:
        with st.expander(f"Modifiche ({len(rep.changes)})"):
            st.markdown("\n".join(f"- {c}" for c in rep.changes[:500]))
            if len(rep.changes) > 500:
                st.caption(f"… e altre {len(rep.changes) - 500}")


def run_write(cfg: Config, fn: Callable[[sqlite3.Connection], ImportReport | list[ImportReport]],
              dry_run: bool, strict: bool = False) -> bool:
    """Run an import; returns True if something was written."""
    backup = None
    if not dry_run:
        backup = db.backup(cfg.database, cfg.backup_dir)
    conn = connect(cfg)
    try:
        conn.execute("BEGIN")
        try:
            result = fn(conn)
        except (LookupError, ValueError, FileNotFoundError) as e:
            conn.rollback()
            st.error(str(e))
            return False
        reports = result if isinstance(result, list) else [result]
        for r in reports:
            show_report(r)
        problems = any(r.problems for r in reports)
        if dry_run:
            conn.rollback()
            st.info("Anteprima: nessuna modifica scritta.")
            return False
        if strict and problems:
            conn.rollback()
            st.error("Ci sono problemi e la modalità rigorosa è attiva: nessuna modifica scritta.")
            return False
        conn.commit()
        st.success("Modifiche salvate." + (f" Backup: `{backup}`" if backup else ""))
        return True
    finally:
        conn.close()


def save_upload(upload) -> Path:
    """Copy an uploaded file to a temporary path, keeping its extension."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="lab-upload-"))
    path = tmp_dir / Path(upload.name).name
    path.write_bytes(upload.getvalue())
    return path


# ---------------------------------------------------------------- pages

def page_students(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    st.header("Studenti")
    tab_list, tab_search = st.tabs(["Coorte", "Cerca in tutte le coorti"])
    with tab_list:
        if not cohort:
            st.info("Nessuna coorte: importa prima gli studenti.")
        else:
            students = repo.cohort_students(conn, repo.cohort_id(conn, cohort), order="group")
            groups = sorted({s.lab_group for s in students if s.lab_group is not None})
            c1, c2 = st.columns([1, 3])
            group = c1.selectbox("Gruppo", ["Tutti", "Senza gruppo", *groups])
            if group == "Senza gruppo":
                students = [s for s in students if s.lab_group is None]
            elif group != "Tutti":
                students = [s for s in students if s.lab_group == group]
            records = render.students_records(students)
            c2.metric("Studenti", len(records))
            st.dataframe(pd.DataFrame(records), hide_index=True, width="stretch")
            download_buttons(records, f"{slug(cohort)}_studenti", "students")
    with tab_search:
        c1, c2, c3 = st.columns(3)
        ids = c1.text_input("Matricole", placeholder="100001 100002 oppure 100001,100002")
        surname = c2.text_input("Cognome")
        name = c3.text_input("Nome")
        if ids or name or surname:
            rows = repo.search_students(conn, split_ids([ids]) if ids else None, name or None, surname or None)
            if rows:
                st.dataframe(pd.DataFrame(render.students_records(rows)), hide_index=True,
                             width="stretch")
            else:
                st.warning("Nessuno studente trovato.")
            if ids:
                found = {r.matricola for r in rows}
                missing = [m for m in split_ids([ids]) if m not in found]
                if missing:
                    st.warning("Non presenti nel database: " + ", ".join(missing))
        else:
            st.caption("Cerca per matricola o per nome (senza distinguere maiuscole, accenti e apostrofi).")


IMPORT_KINDS = {
    "Studenti (export e-learning)": ("students", ["json", "csv", "xlsx"],
                                     "JSON/CSV/XLSX con `nome`, `cognome`, `matricola`, `indirizzoemail`."),
    "Gruppi": ("groups", ["json", "csv", "xlsx"],
               "Righe con `gruppo` e `matricola` oppure `nome` + `cognome`."),
    "Date delle lezioni": ("sessions", ["json", "csv", "xlsx"],
                           'JSON `{"2025-10-01": 4, …}` oppure CSV/XLSX con `date`, `hours`.'),
    "Presenze": ("attendance", ["xlsx", "xls", "json"],
                 "Registro Excel (una colonna per data, valori P/A/R/G) oppure JSON."),
    "Voti scritto": ("written", ["json"], '`{"2026-01-20": {"<matricola>": "27", …}}` — A assente, R ritirato, 30L lode.'),
    "Voti orale": ("oral", ["json"], '`{"2026-02-10": {"<matricola>": "28", …}}`'),
    "Voti relazioni": ("report", ["json"], '`{"2025-12-01": {"<gruppo>": {"<esperienza>": "B+"}}}`'),
}


def page_import(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    st.header("Importa dati")
    kind_label = st.selectbox("Cosa vuoi importare?", list(IMPORT_KINDS))
    kind, types, help_text = IMPORT_KINDS[kind_label]
    st.caption(help_text)

    cohorts = repo.list_cohorts(conn)
    if kind == "students":
        target = st.text_input("Coorte", value=cohort or cfg.default_cohort or "",
                               help="Viene creata se non esiste, es. 2025/26").strip()
    else:
        if not cohorts:
            st.info("Importa prima gli studenti.")
            return
        target = st.selectbox("Coorte", cohorts, index=cohorts.index(cohort) if cohort in cohorts else 0)

    hours = None
    if kind == "attendance":
        if st.checkbox("Crea le lezioni mancanti", help="Se nel file c'è una data non registrata"):
            hours = st.number_input("Ore per le lezioni create", min_value=0.5, value=4.0, step=0.5)

    upload = st.file_uploader("File", type=types, key=f"upload-{kind}")
    strict = st.checkbox("Modalità rigorosa: non scrivere nulla se ci sono problemi")
    if not upload or not target:
        return

    def fn(c: sqlite3.Connection):
        path = save_upload(upload)
        try:
            return do_import(c, path)
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def do_import(c: sqlite3.Connection, path: Path):
        if kind == "students":
            return importers.import_students(c, path, target)
        if kind == "groups":
            return importers.import_groups(c, path, target)
        if kind == "sessions":
            return importers.import_sessions(c, path, target)
        if kind == "attendance":
            return importers.import_attendance(c, path, target, cfg, hours)
        if kind == "report":
            return importers.import_reports(c, path, target, cfg)
        return importers.import_marks(c, path, target, kind)

    c1, c2, _ = st.columns([1, 1, 4])
    preview = c1.button("Anteprima", width="stretch")
    apply = c2.button("Importa", type="primary", width="stretch")
    if preview:
        run_write(cfg, fn, dry_run=True)
    if apply:
        run_write(cfg, fn, dry_run=False, strict=strict)


def page_sessions(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    st.header("Lezioni")
    if not cohort:
        st.info("Nessuna coorte.")
        return
    cid = repo.cohort_id(conn, cohort)
    codes = cfg.attendance.present_codes
    rows = conn.execute(
        "SELECT s.date AS data, s.hours AS ore, COUNT(a.student_id) AS registrati, "
        f"COALESCE(SUM(a.status IN ({','.join('?' for _ in codes)})), 0) AS presenti FROM session s "
        "LEFT JOIN attendance a ON a.session_id = s.id WHERE s.cohort_id = ? GROUP BY s.id ORDER BY s.date",
        (*codes, cid),
    ).fetchall()
    total = sum(r["ore"] for r in rows)
    c1, c2, c3 = st.columns(3)
    c1.metric("Lezioni", len(rows))
    c2.metric("Ore totali", f"{total:g}")
    c3.metric("Ore conteggiate", f"{min(total, cfg.attendance.max_counted_hours):g}")
    st.dataframe(pd.DataFrame([dict(r) for r in rows]), hide_index=True, width="stretch")

    st.subheader("Aggiungi o modifica una lezione")
    with st.form("add-session", clear_on_submit=False):
        c1, c2 = st.columns(2)
        day = c1.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        hours = c2.number_input("Ore", min_value=0.5, value=4.0, step=0.5)
        if st.form_submit_button("Salva lezione", type="primary"):
            iso = day.isoformat()

            def fn(c):
                rep = ImportReport(f"Lezione {iso}")
                _, outcome = repo.upsert_session(c, cid, iso, float(hours))
                rep.count({"new": "lezione aggiunta", "updated": "ore aggiornate", "same": "invariata"}[outcome])
                return rep

            if run_write(cfg, fn, dry_run=False):
                st.rerun()


def page_attendance(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    st.header("Presenze")
    if not cohort:
        st.info("Nessuna coorte.")
        return
    order = st.radio("Ordina per", ["name", "group", "matricola"], horizontal=True,
                     format_func={"name": "Cognome", "group": "Gruppo", "matricola": "Matricola"}.get)
    sessions, rows = analysis.attendance_table(conn, cohort, cfg, order=order)
    minimum = cfg.attendance.min_fraction
    below = [r for r in rows if r.fraction < minimum]
    c1, c2, c3 = st.columns(3)
    c1.metric("Studenti", len(rows))
    c2.metric("Lezioni svolte", len(sessions))
    c3.metric(f"Sotto il {minimum:.0%}", len(below))
    only_below = st.toggle(f"Mostra solo chi è sotto il {minimum:.0%}")
    shown = below if only_below else rows
    records = render.attendance_records(sessions, shown)
    df = pd.DataFrame(records)
    if not df.empty:
        styled = df.style.apply(
            lambda col: ["background-color: rgba(255, 80, 80, .25)" if v < minimum * 100 else "" for v in col],
            subset=["%"],
        ).map(lambda v: "color: #c0392b; font-weight: 600" if v == "A" else "",
              subset=[s.date for s in sessions]).format({"ore": "{:g}"})
        st.dataframe(styled, hide_index=True, width="stretch")
    else:
        st.info("Nessuno studente.")
    download_buttons(records, f"{slug(cohort)}_presenze", "attendance")
    pdf_button(
        "Genera PDF delle presenze",
        lambda: render.attendance_tex(sessions, rows, cfg.title, cohort, minimum, cfg.rows_per_table),
        cfg.output_dir, f"{slug(cohort)}_attendance", "attendance-pdf",
    )


def page_signature(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    st.header("Foglio firme")
    if not cohort:
        st.info("Nessuna coorte.")
        return
    students = repo.cohort_students(conn, repo.cohort_id(conn, cohort), order="group")
    groups = sorted({s.lab_group for s in students if s.lab_group is not None})
    c1, c2 = st.columns([1, 2])
    day = c1.date_input("Data della lezione", value=date.today(), format="DD/MM/YYYY")
    chosen = c2.multiselect("Gruppi (vuoto = tutti)", groups)
    if chosen:
        students = [s for s in students if s.lab_group in chosen]
    n_groups = len({s.lab_group for s in students if s.lab_group is not None})
    no_group = sum(s.lab_group is None for s in students)
    st.caption(f"{len(students)} studenti in {n_groups} gruppi"
               + (f" ({no_group} senza gruppo)" if no_group else ""))
    if not students:
        return
    pdf_button(
        "Genera foglio firme",
        lambda: render.signature_tex(students, cfg.title, day.isoformat(), cfg.rows_per_table),
        cfg.output_dir, f"{day.isoformat()}_signature", "signature-pdf",
    )


def page_exams(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    st.header("Esami")
    tab_el, tab_list = st.tabs(["Ammessi all'orale", "Appelli e relazioni"])
    cohorts = repo.list_cohorts(conn)
    with tab_el:
        ids_text = st.text_input("Matricole (facoltativo)", placeholder="incolla le matricole separate da spazi o virgole")
        ids = split_ids([ids_text]) if ids_text else []
        c1, c2, c3 = st.columns(3)
        all_cohorts = c1.toggle("Tutte le coorti", value=bool(ids))
        show_all = c2.toggle("Mostra anche i non ammessi", value=bool(ids))
        pending = c3.toggle("Solo chi non ha ancora l'orale")
        selected = cohorts if all_cohorts else ([cohort] if cohort else [])
        if not selected:
            st.info("Nessuna coorte.")
            return
        rows, warnings = analysis.exam_table_multi(conn, selected, cfg, matricole=ids or None)
        for w in warnings:
            st.warning(w)
        shown = rows if show_all else [r for r in rows if r.eligible]
        if pending:
            shown = [r for r in shown if r.oral == "-"]
        m1, m2 = st.columns(2)
        m1.metric("Ammessi", sum(r.eligible for r in rows))
        m2.metric("Studenti considerati", len(rows))
        records = render.exam_records(shown, with_cohort=len(selected) > 1)
        df = pd.DataFrame(records)
        if df.empty:
            st.info("Nessuno studente da mostrare.")
        else:
            st.dataframe(
                df.style.map(lambda v: "color: #1e8449; font-weight: 600" if v == "sì"
                             else ("color: #c0392b" if v == "no" else ""), subset=["ammesso"]),
                hide_index=True, width="stretch",
            )
        stem = "tutte_esami" if len(selected) > 1 else f"{slug(selected[0])}_esami"
        download_buttons(records, stem, "exams")
    with tab_list:
        if not cohort:
            st.info("Nessuna coorte.")
        else:
            rows = repo.list_assessments(conn, repo.cohort_id(conn, cohort))
            kinds = {"written": "scritto", "oral": "orale", "report": "relazione"}
            st.dataframe(pd.DataFrame([{"tipo": kinds.get(r["kind"], r["kind"]), "data": r["date"],
                                        "esperienza": r["label"], "voti": r["n"]} for r in rows]),
                         hide_index=True, width="stretch")


def page_settings(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    st.header("Impostazioni")
    st.markdown(f"""
| | |
|---|---|
| Configurazione | `{config_path()}` |
| Database | `{cfg.database}` |
| Cartella output | `{cfg.output_dir}` |
| Backup | `{cfg.backup_dir}` |
| Presenza minima | {cfg.attendance.min_fraction:.0%} |
| Ore massime conteggiate | {cfg.attendance.max_counted_hours:g} |
| Codici di presenza | {", ".join(cfg.attendance.present_codes)} |
| Sufficienza scritto | {cfg.exams.written_pass} |
| Scritto che conta | {"il migliore" if cfg.exams.written_policy == "best" else "l'ultimo consegnato"} |
""")
    st.caption("Per cambiare queste regole modifica `course.toml`; la pagina si aggiorna da sola.")
    if st.button("Fai un backup adesso"):
        copy = db.backup(cfg.database, cfg.backup_dir)
        st.success(f"Backup: `{copy}`" if copy else "Il database non esiste ancora.")
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("cohort", "student", "enrolment", "session", "attendance", "assessment", "result")}
    st.subheader("Contenuto del database")
    st.dataframe(pd.DataFrame([counts]), hide_index=True)


PAGES = {
    "👩‍🎓 Studenti": page_students,
    "📥 Importa": page_import,
    "📅 Lezioni": page_sessions,
    "✅ Presenze": page_attendance,
    "✍️ Foglio firme": page_signature,
    "📝 Esami": page_exams,
    "⚙️ Impostazioni": page_settings,
}


def main() -> None:
    cfg = get_config()
    conn = connect(cfg)
    try:
        with st.sidebar:
            st.title(cfg.title)
            cohorts = repo.list_cohorts(conn)
            cohort = None
            if cohorts:
                default = cfg.default_cohort if cfg.default_cohort in cohorts else cohorts[-1]
                cohort = st.selectbox("Coorte", cohorts, index=cohorts.index(default))
            else:
                st.info("Database vuoto: inizia da **Importa**.")
            page = st.radio("Sezione", list(PAGES), label_visibility="collapsed")
        PAGES[page](cfg, conn, cohort)
    finally:
        conn.close()


main()
