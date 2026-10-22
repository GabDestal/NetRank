"""Text normalisation shared by the API (search) and the data scripts (entity resolution)."""

import re
import unicodedata


def fold(text: str) -> str:
    """Lowercase, strip accents, turn hyphens/apostrophes/dots into spaces, collapse spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[-'.`]", " ", ascii_only.lower())).strip()
