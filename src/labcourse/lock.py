"""Which computer is using the database, for a database shared through a synced folder.

SQLite cannot merge changes made on two computers: when the database lives in a
folder synced by Google Drive (or similar), only one computer must use it at a time.
The GUI writes a small ``<database>.lock`` file next to the database saying which
computer is using it, and warns when another computer has used it recently.

This is advisory and depends on the sync: the lock file reaches the other computer
only after the folder has synced.
"""

from __future__ import annotations

import json
import os
import platform
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

STALE_AFTER = timedelta(hours=12)   # a lock not refreshed for this long is ignored
REFRESH_EVERY = timedelta(minutes=5)


@dataclass(frozen=True)
class Machine:
    id: str
    name: str


@dataclass(frozen=True)
class LockInfo:
    machine_id: str
    machine_name: str
    user: str
    since: str   # ISO timestamps, local time
    seen: str

    @property
    def seen_at(self) -> datetime:
        return datetime.fromisoformat(self.seen)

    @property
    def since_at(self) -> datetime:
        return datetime.fromisoformat(self.since)


def _machine_file() -> Path:
    base = os.environ.get("LABCOURSE_HOME") or Path.home() / ".config" / "labcourse"
    return Path(base) / "machine-id"


def this_machine() -> Machine:
    """A stable id for this computer (host names change with the network on macOS)."""
    path = _machine_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Machine(data["id"], data["name"])
    except (OSError, ValueError, KeyError):
        pass
    machine = Machine(uuid.uuid4().hex, platform.node().split(".")[0] or "computer")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(machine)), encoding="utf-8")
    return machine


def lock_path(database: str | Path) -> Path:
    database = Path(database)
    return database.with_name(database.name + ".lock")


def read(database: str | Path) -> LockInfo | None:
    try:
        return LockInfo(**json.loads(lock_path(database).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def other_user(database: str | Path, me: Machine | None = None, now: datetime | None = None) -> LockInfo | None:
    """The lock of another computer that used the database recently, if any."""
    info = read(database)
    if info is None:
        return None
    me = me or this_machine()
    now = now or datetime.now()
    if info.machine_id == me.id or now - info.seen_at > STALE_AFTER:
        return None
    return info


def acquire(database: str | Path, me: Machine | None = None, now: datetime | None = None) -> None:
    """Mark the database as used by this computer (refreshing an existing lock of ours
    at most every few minutes, to limit sync traffic)."""
    me = me or this_machine()
    now = (now or datetime.now()).replace(microsecond=0)
    info = read(database)
    if info and info.machine_id == me.id:
        if now - info.seen_at < REFRESH_EVERY:
            return
        since = info.since
    else:
        since = now.isoformat()
    lock = LockInfo(me.id, me.name, os.environ.get("USER", ""), since, now.isoformat())
    path = lock_path(database)
    if not path.parent.exists():
        return
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(asdict(lock)), encoding="utf-8")
    tmp.replace(path)


def release(database: str | Path, me: Machine | None = None) -> None:
    """Remove the lock if it is ours."""
    info = read(database)
    if info and info.machine_id == (me or this_machine()).id:
        lock_path(database).unlink(missing_ok=True)
