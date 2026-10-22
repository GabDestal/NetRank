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
    """Key for a Sackmann player: folded last name + initial of the first name.

    Missing parts (None, or NaN as read by pandas) count as empty.
    """
    first = first if isinstance(first, str) else ""
    last = last if isinstance(last, str) else ""
    return f"{fold(last)} {fold(first)[:1]}".strip()


def is_initials(token: str) -> bool:
    """'R.', 'J.M.', 'An.', 'JP' are initials; 'Nadal' or 'Ze' are not."""
    return bool(INITIALS.match(token)) and (token.endswith(".") or token.isupper())


def tennisdata_key(name: str) -> str:
    """Key for a tennis-data name like 'Del Potro J.M.', 'Varillas J. P.' or 'Ramos-Vinolas A.'.

    Trailing initials tokens are stripped; the first of them gives the initial. A name with no
    initials is treated as a bare last name.
    """
    tokens = name.strip().split()
    split = len(tokens)
    while split > 1 and is_initials(tokens[split - 1]):
        split -= 1
    if split == len(tokens):
        return fold(name)
    return f"{fold(' '.join(tokens[:split]))} {fold(tokens[split])[:1]}"


def surname_variants(key: str) -> set[str]:
    """Looser forms of a key for compound or joined surnames, initial kept.

    'ramos vinolas a' -> {'ramos a', 'ramosvinolas a'}; 'o connell c' -> {'o c', 'oconnell c'}.
    """
    surname, _, initial = key.rpartition(" ") if " " in key else (key, "", "")
    if len(initial) != 1:
        surname, initial = key, ""
    tokens = surname.split()
    return {f"{form} {initial}".strip() for form in (tokens[0], "".join(tokens))} if tokens else set()


def last_name(key: str) -> str:
    """The last-name part of a key (drops a trailing single-letter initial)."""
    parts = key.rsplit(" ", 1)
    return parts[0] if len(parts) == 2 and len(parts[1]) == 1 else key
