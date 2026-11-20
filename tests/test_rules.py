import pytest

from labcourse.config import AttendanceRules, ExamRules
from labcourse.marks import Mark
from labcourse.names import normalise
from labcourse.rules import (
    SessionInfo, attendance_fraction, counting_written, oral_eligibility, report_score,
)

RULES = AttendanceRules(min_fraction=0.75, max_counted_hours=56, present_codes=("P", "R", "G"))


# ---------------------------------------------------------------- marks

@pytest.mark.parametrize("raw,numeric,passes", [
    ("27", 27, True), (27, 27, True), ("18", 18, True), ("17", 17, False),
    ("30L", 31, True), ("30 e lode", 31, True), ("27.0", 27, True),
    ("A", None, False), ("R", None, False), ("I", 0, False),
])
def test_mark_parse(raw, numeric, passes):
    m = Mark.parse(raw)
    assert m.numeric == numeric
    assert m.is_pass(18) is passes


@pytest.mark.parametrize("raw", ["31", "-1", "abc", ""])
def test_mark_invalid(raw):
    with pytest.raises(ValueError):
        Mark.parse(raw)


def test_absent_and_withdrawn_did_not_sit():
    assert not Mark.parse("A").sat and Mark.parse("A").is_absent
    assert not Mark.parse("R").sat and Mark.parse("R").is_withdrawn
    assert Mark.parse("12").sat


def test_report_scale():
    scale = ExamRules().report_scale
    assert scale.points("A+") == 31
    assert scale.points("b+") == 27
    assert scale.points("E") == 16
    with pytest.raises(ValueError):
        scale.points("F")
    assert report_score(["A+", "B+"], ExamRules()) == 58


# ---------------------------------------------------------------- names

def test_normalise_names():
    assert normalise("D’Angelo") == normalise("d'angelo") == normalise(" DANGELO ")
    assert normalise("Nicolò") == normalise("NICOLO'")
    assert normalise("De  Luca") == normalise("de luca")
    assert normalise("Rossi") != normalise("Rosso")


# ---------------------------------------------------------------- attendance

def sessions(*hours):
    return [SessionInfo(i, f"2025-10-{i:02d}", h) for i, h in enumerate(hours, start=1)]


def test_attendance_fraction_basic():
    s = sessions(4, 4, 4, 4)
    assert attendance_fraction(s, {1: "P", 2: "P", 3: "A", 4: "R"}, RULES) == pytest.approx(0.75)


def test_missing_record_counts_as_absent_and_g_counts_as_present():
    s = sessions(4, 4)
    assert attendance_fraction(s, {1: "G"}, RULES) == pytest.approx(0.5)


def test_hours_are_capped():
    s = sessions(*([4] * 16))  # 64 h held, counted 56
    statuses = {i: "P" for i in range(1, 15)}  # 56 h attended
    assert attendance_fraction(s, statuses, RULES) == 1.0
    statuses = {i: "P" for i in range(1, 11)}  # 40 h
    assert attendance_fraction(s, statuses, RULES) == pytest.approx(40 / 56)


def test_no_sessions():
    assert attendance_fraction([], {}, RULES) == 0.0


# ---------------------------------------------------------------- written exam and eligibility

ATTEMPTS = [("2026-01-10", Mark.parse("24")), ("2026-02-10", Mark.parse("19")),
            ("2026-03-10", Mark.parse("A"))]


def test_best_policy_ignores_order_and_absences():
    assert counting_written(ATTEMPTS, ExamRules(written_policy="best"))[1].raw == "24"


def test_latest_policy_uses_last_paper_handed_in():
    assert counting_written(ATTEMPTS, ExamRules(written_policy="latest"))[1].raw == "19"


def test_counting_written_none_when_never_sat():
    assert counting_written([("2026-01-10", Mark.parse("A"))], ExamRules()) is None


def test_eligibility():
    rules = ExamRules()
    ok = oral_eligibility(ATTEMPTS, 0.8, rules, RULES)
    assert ok.eligible and ok.reasons == ()
    low_att = oral_eligibility(ATTEMPTS, 0.5, rules, RULES)
    assert not low_att.eligible and "attendance" in low_att.reasons[0]
    failed = oral_eligibility([("2026-01-10", Mark.parse("17"))], 0.9, rules, RULES)
    assert not failed.eligible and failed.reasons == ("written 17 < 18",)
    none = oral_eligibility([], 0.9, rules, RULES)
    assert none.reasons == ("no written exam",)
