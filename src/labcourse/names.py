"""Name normalisation used when a source has no student id."""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = "'’‘`´ʼ"


def normalise(text: str) -> str:
    """Case-, accent-, apostrophe- and whitespace-insensitive key.

    >>> normalise("  D’Angelo  ") == normalise("d'angelo") == normalise("DANGELO")
    True
    >>> normalise("Nicolò") == normalise("Nicolo'")
    True
    """
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(c for c in text if c not in _APOSTROPHES)
    text = re.sub(r"[\s\-]+", " ", text).strip().casefold()
    return text.replace(" ", "")


def name_key(surname: str, name: str) -> tuple[str, str]:
    return normalise(surname), normalise(name)
