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


def frame(records: list[dict]) -> pd.DataFrame:
    """DataFrame for ``st.dataframe``, with mixed-type columns made Arrow-compatible.

    The render records use ``""`` for missing values next to numbers (e.g. ``gruppo``),
    which Arrow cannot serialise. Columns whose non-empty values are all numbers become
    nullable numeric columns; any other mixed column becomes text.
    """
    df = pd.DataFrame(records)
    for col in df.columns:
        if df[col].dtype != object:
            continue
        values = df[col][df[col].notna() & (df[col] != "")]
        types = {type(v) for v in values}
        if len(types) <= 1 and len(values) == df[col].notna().sum():
            continue
        if types and all(issubclass(t, (int, float)) and not issubclass(t, bool) for t in types):
            num = pd.to_numeric(df[col].replace("", None))
            df[col] = num.astype("Int64") if all(issubclass(t, int) for t in types) else num
        else:
            df[col] = df[col].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    return df


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
            st.dataframe(frame(records), hide_index=True, width="stretch")
            download_buttons(records, f"{slug(cohort)}_studenti", "students")
    with tab_search:
        c1, c2, c3 = st.columns(3)
        ids = c1.text_input("Matricole", placeholder="100001 100002 oppure 100001,100002")
        surname = c2.text_input("Cognome")
        name = c3.text_input("Nome")
        if ids or name or surname:
            rows = repo.search_students(conn, split_ids([ids]) if ids else None, name or None, surname or None)
            if rows:
                st.dataframe(frame(render.students_records(rows)), hide_index=True,
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
    df = frame(records)
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
    tab_el, tab_list = st.tabs(["Ammessi all'orale", "Esami e relazioni registrati"])
    cohorts = repo.list_cohorts(conn)
    with tab_el:
        ids_text = st.text_input("Matricole (facoltativo)", placeholder="incolla le matricole separate da spazi o virgole")
        ids = split_ids([ids_text]) if ids_text else []
        minimum = cfg.attendance.min_fraction
        c1, c2 = st.columns(2)
        all_cohorts = c1.toggle("Tutte le coorti", value=bool(ids))
        pending = c2.toggle("Solo chi non ha ancora l'orale")
        c3, c4 = st.columns(2)
        show_all = c3.toggle("Mostra anche i non ammessi", value=bool(ids),
                             help="Per esempio chi non ha superato lo scritto")
        show_low = c4.toggle(f"Mostra anche sotto il {minimum:.0%} di presenze", value=False,
                             help="Studenti che non hanno raggiunto la soglia minima di presenze")
        selected = cohorts if all_cohorts else ([cohort] if cohort else [])
        if not selected:
            st.info("Nessuna coorte.")
            return
        rows, warnings = analysis.exam_table_multi(conn, selected, cfg, matricole=ids or None)
        for w in warnings:
            st.warning(w)
        shown = rows if show_all else [r for r in rows if r.eligible]
        if not show_low:
            hidden = [r for r in shown if r.attendance < minimum]
            shown = [r for r in shown if r.attendance >= minimum]
            if hidden:
                st.caption(f"{len(hidden)} studenti nascosti perché sotto il {minimum:.0%} di presenze "
                           f"({', '.join(r.student.full_name for r in hidden[:5])}"
                           f"{', …' if len(hidden) > 5 else ''}).")
        if pending:
            shown = [r for r in shown if r.oral == "-"]
        m1, m2 = st.columns(2)
        m1.metric("Ammessi", sum(r.eligible for r in rows))
        m2.metric("Studenti considerati", len(rows))
        records = render.exam_records(shown, with_cohort=len(selected) > 1)
        df = frame(records)
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


def page_appelli(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    st.header("Appelli")
    appelli = repo.list_appelli(conn)
    labels = {r["date"]: f"{r['date'][8:]}/{r['date'][5:7]}/{r['date'][:4]} — {r['iscritti']} iscritti, "
                         f"{r['con_voto']} con voto" for r in appelli}
    tab_sum, tab_imp, tab_edit = st.tabs(["Iscritti e riepilogo", "Importa iscritti e voti", "Aggiungi o rimuovi"])

    with tab_imp:
        appello_import_tab(cfg)

    with tab_edit:
        c1, c2 = st.columns([1, 2])
        day = c1.date_input("Data dell'appello", value=date.today(), format="DD/MM/YYYY", key="edit-date")
        ids_text = c2.text_input("Matricole", placeholder="100001 100002 oppure 100001,100002", key="edit-ids")
        ids = split_ids([ids_text]) if ids_text else []
        b1, b2, _ = st.columns([1, 1, 2])
        if b1.button("Iscrivi", type="primary", disabled=not ids, width="stretch"):
            iso = day.isoformat()

            def add(c):
                rep = ImportReport(f"Appello {iso}")
                try:
                    aid = repo.appello_id(c, iso)
                except LookupError:
                    aid = repo.appello_id(c, iso, create=True)
                    rep.count("nuovo appello")
                for m in ids:
                    outcome, _ = repo.upsert_registration(c, aid, m)
                    rep.count("iscritti" if outcome == "new" else "già iscritti")
                    if repo.student_by_matricola(c, m) is None:
                        rep.problem(f"matricola {m} non presente nel database (iscritta comunque)")
                return rep

            run_write(cfg, add, dry_run=False)
        if b2.button("Rimuovi", disabled=not ids, width="stretch"):
            iso = day.isoformat()

            def remove(c):
                rep = ImportReport(f"Appello {iso}")
                aid = repo.appello_id(c, iso)
                for m in ids:
                    if repo.remove_registration(c, aid, m):
                        rep.count("rimossi")
                    else:
                        rep.problem(f"matricola {m} non iscritta")
                return rep

            run_write(cfg, remove, dry_run=False)

    with tab_sum:
        if not appelli:
            st.info("Nessun appello: importa la lista degli iscritti o i risultati dello scritto.")
            return
        dates = [r["date"] for r in reversed(appelli)]
        iso = st.selectbox("Appello", dates, format_func=labels.get, key="appello-date")
        rows = analysis.appello_table(conn, cfg, iso)
        admitted = [r for r in rows if r.eligible]
        unknown = [r for r in rows if r.exam is None]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Iscritti", len(rows))
        m2.metric("Con voto", sum(bool(r.appello_mark) for r in rows))
        m3.metric("Ammessi all'orale", len(admitted))
        m4.metric("Non nel database", len(unknown))
        only_admitted = st.toggle("Solo gli ammessi all'orale", key="appello-admitted")
        if unknown:
            st.caption("Studenti non presenti nel database (nessun dato su presenze e relazioni): "
                       + ", ".join(r.full_name if r.surname else r.matricola for r in unknown))
        shown = admitted if only_admitted else rows
        records = render.appello_records(shown)
        df = frame(records)
        if df.empty:
            st.info("Nessuno studente da mostrare.")
        else:
            st.dataframe(
                df.style.map(lambda v: "color: #1e8449; font-weight: 600" if v == "sì"
                             else ("color: #c0392b" if v == "no" else ""), subset=["ammesso"]),
                hide_index=True, width="stretch",
            )
        download_buttons(records, f"{iso}_appello", f"appello-{iso}")
        p1, p2 = st.columns(2)
        with p1:
            pdf_button("PDF riepilogo appello",
                       lambda: render.appello_tex(shown, cfg.title, iso, cfg.rows_per_table, oral=False),
                       cfg.output_dir, f"{iso}_appello", f"appello-pdf-{iso}")
        with p2:
            if admitted:
                pdf_button("PDF tabella per l'orale",
                           lambda: render.appello_tex(admitted, cfg.title, iso, cfg.rows_per_table, oral=True),
                           cfg.output_dir, f"{iso}_orali", f"orali-pdf-{iso}")


def appello_import_tab(cfg: Config) -> None:
    st.caption("Lista degli iscritti esportata da Esse3 o dall'e-learning (Excel o CSV, con o senza voti), "
               "oppure il JSON con i risultati dello scritto. Chi ha un voto ed è nel database lo riceve "
               "anche tra i risultati dello scritto, così conta per l'ammissione all'orale.")
    upload = st.file_uploader("File", type=["xlsx", "xls", "csv", "json"], key="appello-upload")
    if not upload:
        return
    path = save_upload(upload)
    try:
        _appello_import_form(cfg, upload, path)
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


def _appello_import_form(cfg: Config, upload, path: Path) -> None:
    sheet = None
    found = None
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            sheets = importers.excel_sheets(path)
            sheet = st.selectbox("Foglio", sheets) if len(sheets) > 1 else sheets[0]
        if path.suffix.lower() != ".json":
            rows, found, problems = importers.read_registration_table(path, sheet)
            st.caption(f"{len(rows)} studenti nel file, {sum(r.mark is not None for r in rows)} con voto"
                       + (f"; data trovata: {found}" if found else "; data non trovata nel file"))
    except ValueError as e:
        st.error(str(e))
        return
    if path.suffix.lower() == ".json":
        appello_date = None
        st.caption("Ogni data del file diventa un appello.")
    else:
        default = date.fromisoformat(found) if found else date.today()
        appello_date = st.date_input("Data dell'appello", value=default, format="DD/MM/YYYY",
                                     key=f"appello-import-date-{upload.name}-{sheet}").isoformat()
    strict = st.checkbox("Modalità rigorosa: non scrivere nulla se ci sono problemi", key="appello-strict")
    c1, c2, _ = st.columns([1, 1, 2])
    fn = lambda c: importers.import_appello(c, path, appello_date, sheet)  # noqa: E731
    if c1.button("Anteprima", width="stretch", key="appello-preview"):
        run_write(cfg, fn, dry_run=True)
    if c2.button("Importa", type="primary", width="stretch", key="appello-import"):
        if run_write(cfg, fn, dry_run=False, strict=strict):
            st.caption("Vai alla scheda *Iscritti e riepilogo* per vedere l'appello.")


COHORT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def _cohort_scale(all_cohorts: list[str]):
    """Fixed colour per cohort (by its position among all cohorts), so a filter never repaints."""
    import altair as alt

    return alt.Scale(domain=all_cohorts, range=COHORT_COLORS[:len(all_cohorts)] or COHORT_COLORS[:1])


def page_stats(cfg: Config, conn: sqlite3.Connection, cohort: str | None) -> None:
    import altair as alt

    from labcourse import stats

    st.header("Statistiche")
    all_cohorts = repo.list_cohorts(conn)
    if not all_cohorts:
        st.info("Nessun dato.")
        return
    chosen = st.multiselect("Coorti", all_cohorts, default=all_cohorts)
    if not chosen:
        return
    df = stats.results_frame(conn, cfg, chosen)
    color = alt.Color("cohort:N", title="Coorte", scale=_cohort_scale(all_cohorts))
    tab_dist, tab_app, tab_corr, tab_time = st.tabs(["Distribuzioni", "Appelli", "Correlazioni", "Tempi"])

    with tab_dist:
        st.dataframe(stats.summary(df), hide_index=True, width="stretch")
        st.caption("Scritto: voto con cui lo studente è stato ammesso (il migliore superato). 30L conta 30. "
                   "Relazioni: punti medi per esperienza.")
        measure = st.radio("Prova", ["written", "oral", "report_mean"], horizontal=True,
                           format_func={"written": "Scritto", "oral": "Orale", "report_mean": "Relazioni"}.get)
        sub = df[["cohort", measure]].dropna()
        if measure == "report_mean":
            sub = sub.assign(**{measure: sub[measure].round()})
        counts = sub.groupby(["cohort", measure]).size().reset_index(name="studenti")
        chart = alt.Chart(counts).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X(f"{measure}:O", title="Voto" if measure != "report_mean" else "Punti medi (arrotondati)"),
            xOffset="cohort:N",
            y=alt.Y("studenti:Q", title="Studenti"),
            color=color,
            tooltip=[alt.Tooltip("cohort:N", title="Coorte"), alt.Tooltip(f"{measure}:O", title="Voto"),
                     alt.Tooltip("studenti:Q", title="Studenti")],
        ).properties(height=320)
        st.altair_chart(chart, width="stretch")

    with tab_app:
        ap = stats.appelli_frame(conn, cfg, chosen)
        if ap.empty:
            st.info("Nessuno scritto registrato.")
        else:
            st.caption("Ogni punto è un appello scritto per una coorte; asse x: giorni dalla fine delle lezioni "
                       "di quella coorte (negativo = prima della fine). La dimensione è il numero di presenti.")
            base = alt.Chart(ap.dropna(subset=["days_after_lessons"])).encode(
                x=alt.X("days_after_lessons:Q", title="Giorni dalla fine delle lezioni"),
                color=color,
                tooltip=[alt.Tooltip("date:N", title="Appello"), alt.Tooltip("cohort:N", title="Coorte"),
                         alt.Tooltip("sat:Q", title="Presenti"), alt.Tooltip("passed:Q", title="Superati"),
                         alt.Tooltip("pass_rate:Q", title="% superati", format=".0%"),
                         alt.Tooltip("mean:Q", title="Media", format=".1f")],
            )
            c1, c2 = st.columns(2)
            c1.altair_chart(base.mark_circle(opacity=0.85, stroke="white", strokeWidth=2).encode(
                y=alt.Y("mean:Q", title="Voto medio", scale=alt.Scale(domain=[18, 30])),
                size=alt.Size("sat:Q", title="Presenti", scale=alt.Scale(range=[60, 600])),
            ).properties(height=300, title="Voto medio per appello"), width="stretch")
            c2.altair_chart(base.mark_circle(opacity=0.85, stroke="white", strokeWidth=2).encode(
                y=alt.Y("pass_rate:Q", title="% superati", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                size=alt.Size("sat:Q", title="Presenti", scale=alt.Scale(range=[60, 600])),
            ).properties(height=300, title="Percentuale di superati"), width="stretch")
            table = ap.assign(pass_rate=(ap["pass_rate"] * 100).round(0), mean=ap["mean"].round(1),
                              mean_passed=ap["mean_passed"].round(1))
            st.dataframe(table.rename(columns={
                "date": "appello", "cohort": "coorte", "registered": "voti registrati", "sat": "presenti",
                "absent": "assenti", "withdrawn": "ritirati", "passed": "superati", "pass_rate": "% superati",
                "mean": "media", "mean_passed": "media superati", "days_after_lessons": "giorni dopo le lezioni"}),
                hide_index=True, width="stretch")

    with tab_corr:
        st.dataframe(stats.correlations(df), hide_index=True, width="stretch")
        st.caption("rho di Spearman: +1 = stesso ordinamento, 0 = nessuna relazione, −1 = ordinamento opposto. "
                   "Con meno di 5 studenti non viene calcolato.")
        options = {"Scritto ↔ Orale": ("written", "oral"), "Relazioni ↔ Orale": ("report_mean", "oral"),
                   "Relazioni ↔ Scritto": ("report_mean", "written"), "Presenze ↔ Orale": ("attendance", "oral"),
                   "Presenze ↔ Scritto": ("attendance", "written")}
        label = st.selectbox("Grafico", list(options))
        xcol, ycol = options[label]
        names = {"written": "Scritto", "oral": "Orale", "report_mean": "Relazioni (punti medi)", "attendance": "Presenze"}
        pts = df[["cohort", xcol, ycol]].dropna()
        if xcol == "report_mean":
            pts = pts.assign(report_mean=pts["report_mean"].round(1))
        agg = pts.groupby(["cohort", xcol, ycol]).size().reset_index(name="studenti")
        scatter = alt.Chart(agg).mark_circle(opacity=0.8, stroke="white", strokeWidth=2).encode(
            x=alt.X(f"{xcol}:Q", title=names[xcol], scale=alt.Scale(zero=False),
                    axis=alt.Axis(format="%") if xcol == "attendance" else alt.Axis()),
            y=alt.Y(f"{ycol}:Q", title=names[ycol], scale=alt.Scale(zero=False)),
            size=alt.Size("studenti:Q", title="Studenti", scale=alt.Scale(range=[60, 500])),
            color=color,
            tooltip=["cohort:N", alt.Tooltip(f"{xcol}:Q", title=names[xcol]),
                     alt.Tooltip(f"{ycol}:Q", title=names[ycol]), "studenti:Q"],
        ).properties(height=380)
        st.altair_chart(scatter, width="stretch")
        d = df.dropna(subset=["oral", "written"])
        if len(d):
            m1, m2, m3 = st.columns(3)
            m1.metric("Orale − scritto (media)", f"{d['oral_minus_written'].mean():+.1f}")
            m2.metric("Orale più alto dello scritto", f"{(d['oral_minus_written'] > 0).mean():.0%}")
            m3.metric("Orale più basso", f"{(d['oral_minus_written'] < 0).mean():.0%}")

    with tab_time:
        st.caption("Attese misurate dalla fine delle lezioni della coorte dello studente.")
        med = df.groupby("cohort")[["days_end_to_written", "days_end_to_oral", "days_written_to_oral"]].median()
        st.dataframe(med.round(0).rename(columns={
            "days_end_to_written": "giorni fine corso → scritto (mediana)",
            "days_end_to_oral": "giorni fine corso → orale (mediana)",
            "days_written_to_oral": "giorni scritto → orale (mediana)"}).reset_index().rename(columns={"cohort": "coorte"}),
            hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        for col, (days, value, first, title) in zip((c1, c2), (
                ("days_end_to_written", "written", "prima della fine", "Scritto"),
                ("days_end_to_oral", "oral", "prima della fine", "Orale"))):
            w = stats.by_wait(df, days, value, first_label=first).dropna(subset=["media"])
            base = alt.Chart(w).encode(
                x=alt.X("attesa:N", sort=list(w["attesa"]), title="Sostenuto dopo la fine delle lezioni",
                        axis=alt.Axis(labelAngle=-30, labelLimit=160, labelOverlap=False)),
                y=alt.Y("media:Q", title="Voto medio", scale=alt.Scale(domain=[18, 30])),
                tooltip=[alt.Tooltip("attesa:N", title="Quando"), alt.Tooltip("media:Q", title="Media"),
                         alt.Tooltip("n:Q", title="Studenti")],
            )
            dots = base.mark_circle(size=140, color=COHORT_COLORS[0], opacity=1)
            labels = base.mark_text(dy=-14, color="#52514e", fontSize=11).encode(
                text=alt.Text("n:Q", format="d"))
            col.altair_chart((dots + labels).properties(height=300, title=f"{title}: voto medio"), width="stretch")
        st.caption("Il numero sopra ogni punto è quanti studenti ci sono in quel gruppo: "
                   "con pochi studenti la media è poco affidabile.")
        status = pd.DataFrame({
            "coorte": chosen,
            "iscritti": [int((df["cohort"] == c).sum()) for c in chosen],
            "senza scritto": [int(((df["cohort"] == c) & (df["written_attempts"] == 0)).sum()) for c in chosen],
            "scritto superato, orale mancante": [int(((df["cohort"] == c) & df["written_passed"] & df["oral"].isna()).sum())
                                                 for c in chosen],
            "con orale": [int(((df["cohort"] == c) & df["oral"].notna()).sum()) for c in chosen],
            "più tentativi allo scritto": [int(((df["cohort"] == c) & (df["written_attempts"] > 1)).sum()) for c in chosen],
        })
        st.subheader("A che punto sono gli studenti")
        st.dataframe(status, hide_index=True, width="stretch")


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
    "🗓️ Appelli": page_appelli,
    "📊 Statistiche": page_stats,
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
