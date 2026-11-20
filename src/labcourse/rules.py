"""Course rules as pure functions: no database, easy to test."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .config import AttendanceRules, ExamRules
from .marks import Mark


@dataclass(frozen=True)
class SessionInfo:
    id: int
    date: str
    hours: float


def counted_hours(sessions: Iterable[SessionInfo], rules: AttendanceRules) -> float:
    """Hours the attendance fraction is computed against (capped)."""
    total = sum(s.hours for s in sessions)
    return min(total, rules.max_counted_hours)


def attended_hours(
    sessions: Iterable[SessionInfo], statuses: Mapping[int, str], rules: AttendanceRules
) -> float:
    return sum(s.hours for s in sessions if statuses.get(s.id, "A") in rules.present_codes)


def attendance_fraction(
    sessions: Iterable[SessionInfo], statuses: Mapping[int, str], rules: AttendanceRules
) -> float:
    """Fraction of counted hours attended, between 0 and 1.

    ``sessions`` are the sessions held so far; ``statuses`` maps session id to the
    student's status code. A missing status counts as absent.
    """
    sessions = list(sessions)
    total = counted_hours(sessions, rules)
    if total <= 0:
        return 0.0
    return min(attended_hours(sessions, statuses, rules) / total, 1.0)


def counting_written(attempts: Iterable[tuple[str, Mark]], rules: ExamRules) -> tuple[str, Mark] | None:
    """The written attempt that counts, according to ``rules.written_policy``.

    Attempts where the student was absent or withdrew are ignored.
    """
    sat = [(d, m) for d, m in attempts if m.sat]
    if not sat:
        return None
    if rules.written_policy == "latest":
        return max(sat, key=lambda dm: dm[0])
    # best mark; on ties the most recent
    return max(sat, key=lambda dm: (dm[1].numeric, dm[0]))


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    attendance: float
    written: tuple[str, Mark] | None
    reasons: tuple[str, ...] = field(default_factory=tuple)


def oral_eligibility(
    written_attempts: Iterable[tuple[str, Mark]],
    attendance: float,
    exam_rules: ExamRules,
    attendance_rules: AttendanceRules,
) -> Eligibility:
    written = counting_written(written_attempts, exam_rules)
    reasons = []
    if written is None:
        reasons.append("no written exam")
    elif not written[1].is_pass(exam_rules.written_pass):
        reasons.append(f"written {written[1]} < {exam_rules.written_pass}")
    if attendance < attendance_rules.min_fraction:
        reasons.append(f"attendance {attendance:.0%} < {attendance_rules.min_fraction:.0%}")
    return Eligibility(not reasons, attendance, written, tuple(reasons))


def report_score(grades: Iterable[str], exam_rules: ExamRules) -> int:
    """Sum of report points (one letter grade per experiment)."""
    return sum(exam_rules.report_scale.points(g) for g in grades)
