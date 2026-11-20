"""Parsing of exam and report marks.

Marks are stored in the database exactly as written (``'27'``, ``'30L'``, ``'A'``,
``'B+'``) and interpreted only here.
"""

from __future__ import annotations

from dataclasses import dataclass

ABSENT = "A"      # assente
WITHDRAWN = "R"   # ritirato
FAILED = "I"      # insufficiente
CUM_LAUDE = "30L"


@dataclass(frozen=True)
class Mark:
    """A numeric exam mark (written or oral) on the Italian /30 scale."""

    raw: str

    @classmethod
    def parse(cls, value: object) -> "Mark":
        raw = str(value).strip().upper()
        if raw.endswith(".0"):  # Excel/JSON numbers like 27.0
            raw = raw[:-2]
        if raw in ("30 L", "30 E LODE", "30LODE", "30E LODE"):
            raw = CUM_LAUDE
        if raw not in (ABSENT, WITHDRAWN, FAILED, CUM_LAUDE):
            try:
                n = int(raw)
            except ValueError:
                raise ValueError(f"Invalid mark: {value!r}") from None
            if not 0 <= n <= 30:
                raise ValueError(f"Mark out of range 0-30: {value!r}")
            raw = str(n)
        return cls(raw)

    @property
    def is_absent(self) -> bool:
        return self.raw == ABSENT

    @property
    def is_withdrawn(self) -> bool:
        return self.raw == WITHDRAWN

    @property
    def sat(self) -> bool:
        """True when the student actually handed in a graded paper."""
        return self.raw not in (ABSENT, WITHDRAWN)

    @property
    def is_cum_laude(self) -> bool:
        return self.raw == CUM_LAUDE

    @property
    def numeric(self) -> int | None:
        """30L counts as 31; failed counts as 0; absent/withdrawn have no value."""
        if self.raw == CUM_LAUDE:
            return 31
        if self.raw == FAILED:
            return 0
        if not self.sat:
            return None
        return int(self.raw)

    def is_pass(self, threshold: int = 18) -> bool:
        n = self.numeric
        return n is not None and n >= threshold

    def __str__(self) -> str:
        return self.raw


@dataclass(frozen=True)
class ReportScale:
    """Ordered letter grades for lab reports; the first grade is worth ``top_points``."""

    grades: tuple[str, ...]
    top_points: int = 31

    def points(self, grade: str) -> int:
        g = str(grade).strip().upper()
        if g not in self.grades:
            raise ValueError(f"Invalid report grade {grade!r}; expected one of {', '.join(self.grades)}")
        return self.top_points - self.grades.index(g)

    def validate(self, grade: str) -> str:
        self.points(grade)
        return str(grade).strip().upper()
