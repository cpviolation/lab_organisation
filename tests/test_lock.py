import json
from datetime import datetime, timedelta

from labcourse import lock
from labcourse.config import load_config
from labcourse.lock import Machine

A = Machine("a" * 32, "studio")
B = Machine("b" * 32, "casa")
T0 = datetime(2026, 11, 26, 9, 0)


def test_this_machine_is_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("LABCOURSE_HOME", str(tmp_path / "home"))
    first = lock.this_machine()
    assert first == lock.this_machine() and len(first.id) == 32 and first.name


def test_lock_between_two_computers(tmp_path):
    db = tmp_path / "lab.db"
    assert lock.other_user(db, A) is None
    lock.acquire(db, A, T0)
    assert lock.other_user(db, A, T0) is None                   # our own lock
    other = lock.other_user(db, B, T0 + timedelta(minutes=1))
    assert other is not None and other.machine_name == "studio"
    assert lock.other_user(db, B, T0 + lock.STALE_AFTER + timedelta(minutes=1)) is None  # stale

    # refreshing keeps "since" and is throttled
    lock.acquire(db, A, T0 + timedelta(minutes=1))
    assert lock.read(db).seen == T0.isoformat()
    lock.acquire(db, A, T0 + timedelta(minutes=10))
    assert lock.read(db).since == T0.isoformat() and lock.read(db).seen == (T0 + timedelta(minutes=10)).isoformat()

    # B takes over; A's release does not remove B's lock
    lock.acquire(db, B, T0 + timedelta(hours=1))
    assert lock.other_user(db, A, T0 + timedelta(hours=1)).machine_name == "casa"
    lock.release(db, A)
    assert lock.read(db).machine_id == B.id
    lock.release(db, B)
    assert not lock.lock_path(db).exists()


def test_unreadable_lock_is_ignored(tmp_path):
    db = tmp_path / "lab.db"
    lock.lock_path(db).write_text("not json")
    assert lock.other_user(db, A) is None
    lock.lock_path(db).write_text(json.dumps({"machine_id": "x"}))
    assert lock.other_user(db, A) is None


def test_config_paths_expand_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "me"))
    monkeypatch.setenv("LAB_DRIVE", str(tmp_path / "drive"))
    toml = tmp_path / "course.toml"
    toml.write_text('database = "~/Drive/lab/lab.db"\nbackup_dir = "$LAB_DRIVE/backups"\n')
    cfg = load_config(toml)
    assert cfg.database == tmp_path / "me" / "Drive" / "lab" / "lab.db"
    assert cfg.backup_dir == tmp_path / "drive" / "backups"
    assert cfg.output_dir == tmp_path / "output"   # relative paths: next to course.toml, as before


def test_cli_warns_when_in_use_elsewhere(tmp_path, monkeypatch, fx):
    import shutil

    from test_legacy_and_cli import ok
    from typer.testing import CliRunner
    from labcourse.cli import app
    monkeypatch.chdir(tmp_path)
    for f in fx.iterdir():
        shutil.copy(f, tmp_path / f.name)
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    ok(runner, "cohort", "import", "students_2025.json")
    assert "another computer" not in ok(runner, "students", "list")
    lock.acquire(load_config(tmp_path / "course.toml").database, B)
    assert "in use on another computer (casa" in ok(runner, "students", "list")
