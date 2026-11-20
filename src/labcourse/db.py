"""SQLite storage: one database file, a normalised schema and numbered migrations.

All queries elsewhere use ``?`` placeholders; no SQL is built from user data.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE cohort (
        id   INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE student (
        id        INTEGER PRIMARY KEY,
        matricola TEXT UNIQUE NOT NULL,
        surname   TEXT NOT NULL,
        name      TEXT NOT NULL,
        email     TEXT
    );
    CREATE TABLE enrolment (
        student_id INTEGER NOT NULL REFERENCES student(id) ON DELETE CASCADE,
        cohort_id  INTEGER NOT NULL REFERENCES cohort(id) ON DELETE CASCADE,
        lab_group  INTEGER,
        PRIMARY KEY (student_id, cohort_id)
    );
    CREATE TABLE session (
        id        INTEGER PRIMARY KEY,
        cohort_id INTEGER NOT NULL REFERENCES cohort(id) ON DELETE CASCADE,
        date      TEXT NOT NULL,
        hours     REAL NOT NULL CHECK (hours > 0),
        UNIQUE (cohort_id, date)
    );
    CREATE TABLE attendance (
        session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
        student_id INTEGER NOT NULL REFERENCES student(id) ON DELETE CASCADE,
        status     TEXT NOT NULL CHECK (status IN ('P','A','R','G')),
        PRIMARY KEY (session_id, student_id)
    );
    CREATE TABLE assessment (
        id        INTEGER PRIMARY KEY,
        cohort_id INTEGER NOT NULL REFERENCES cohort(id) ON DELETE CASCADE,
        kind      TEXT NOT NULL CHECK (kind IN ('written','report','oral')),
        date      TEXT NOT NULL,
        label     TEXT NOT NULL DEFAULT '',
        UNIQUE (cohort_id, kind, date, label)
    );
    CREATE TABLE result (
        assessment_id INTEGER NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
        student_id    INTEGER NOT NULL REFERENCES student(id) ON DELETE CASCADE,
        raw_mark      TEXT NOT NULL,
        PRIMARY KEY (assessment_id, student_id)
    );
    """,
    # 2: exam sessions (appelli) and the students registered for them.
    # Registrations are keyed by matricola so that students who are not in the
    # database (other turni, other years) can be registered too.
    """
    CREATE TABLE appello (
        id   INTEGER PRIMARY KEY,
        kind TEXT NOT NULL DEFAULT 'written' CHECK (kind IN ('written','oral')),
        date TEXT NOT NULL,
        UNIQUE (kind, date)
    );
    CREATE TABLE registration (
        appello_id INTEGER NOT NULL REFERENCES appello(id) ON DELETE CASCADE,
        matricola  TEXT NOT NULL,
        surname    TEXT,
        name       TEXT,
        email      TEXT,
        mark       TEXT,
        PRIMARY KEY (appello_id, matricola)
    );
    """,
]


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the database and bring the schema up to date."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # explicit transactions only
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def migrate(conn: sqlite3.Connection) -> None:
    current = schema_version(conn)
    for version, script in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        conn.executescript(
            f"BEGIN; {script}; INSERT INTO schema_version (version) VALUES ({int(version)}); COMMIT;"
        )


@contextmanager
def transaction(conn: sqlite3.Connection, dry_run: bool = False) -> Iterator[sqlite3.Connection]:
    """Run a block atomically; roll back on error or when ``dry_run`` is set."""
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    if dry_run:
        conn.rollback()
    else:
        conn.commit()


def backup(db_path: str | Path, backup_dir: str | Path) -> Path | None:
    """Copy the database to a timestamped file. Returns the copy, or None if no db yet."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = backup_dir / f"{db_path.stem}-{stamp}{db_path.suffix}"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return target

