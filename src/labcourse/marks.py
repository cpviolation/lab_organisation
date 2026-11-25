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
    aliases: tuple[tuple[str, str], ...] = ()  # (written form, canonical grade)

    def canonical(self, grade: str) -> str:
        """Normalised grade: upper case, no spaces, aliases applied.

        A grade not in the scale but written ``X/Y`` with X and Y in the scale
        (e.g. ``A/A-``) is accepted and worth the average of the two.
        """
        g = "".join(str(grade).split()).upper()
        g = dict(self.aliases).get(g, g)
        if g in self.grades:
            return g
        parts = g.split("/")
        if len(parts) == 2 and all(p in self.grades for p in parts):
            return g
        raise ValueError(f"Invalid report grade {grade!r}; expected one of {', '.join(self.grades)} "
                         "or two of them as X/Y")

    def points(self, grade: str) -> float:
        g = self.canonical(grade)
        if g in self.grades:
            return self.top_points - self.grades.index(g)
        a, b = g.split("/")
        return (self.points(a) + self.points(b)) / 2

    def validate(self, grade: str) -> str:
        return self.canonical(grade)

    def choices(self) -> list[str]:
        """Grades to offer when entering a mark: the scale plus the halfway grades
        ``X/Y`` between consecutive simple grades (e.g. ``A/A-``), best first."""
        simple = [g for g in self.grades if "/" not in g]
        options = set(self.grades) | {f"{a}/{b}" for a, b in zip(simple, simple[1:])}
        return sorted(options, key=lambda g: (-self.points(g), g))
