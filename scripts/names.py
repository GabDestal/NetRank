"""Player-name normalisation shared by both sources for entity resolution.

Sackmann gives first and last names ("Juan Martin", "del Potro"); tennis-data gives "Last F."
("Del Potro J.M."). Both are reduced to a key: folded last name + first initial ("del potro j").
"""

import re
import unicodedata

INITIALS = re.compile(r"^(?:[A-Za-z]{1,2}\.?-?)+$")


def fold(text: str) -> str:
    """Lowercase, strip accents, turn hyphens/apostrophes/dots into spaces, collapse spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[-'.`]", " ", ascii_only.lower())).strip()


def sackmann_key(first: str | None, last: str | None) -> str:
    """Key for a Sackmann player: folded last name + initial of the first name."""
    initial = fold(first or "")[:1]
    return f"{fold(last or '')} {initial}".strip()


def tennisdata_key(name: str) -> str:
    """Key for a tennis-data name like 'Del Potro J.M.' or 'Ramos-Vinolas A.'.

    The last token is read as initials when it is short and dotted or all-caps; otherwise the
    whole string is treated as the last name (no initial).
    """
    tokens = name.strip().split()
    if len(tokens) > 1 and INITIALS.match(tokens[-1]) and (tokens[-1].endswith(".") or tokens[-1].isupper()):
        return f"{fold(' '.join(tokens[:-1]))} {fold(tokens[-1])[:1]}"
    return fold(name)


def last_name(key: str) -> str:
    """The last-name part of a key (drops a trailing single-letter initial)."""
    parts = key.rsplit(" ", 1)
    return parts[0] if len(parts) == 2 and len(parts[1]) == 1 else key
