"""Unit tests for the cross-source player-name keys."""

import pytest

from scripts.names import fold, last_name, sackmann_key, tennisdata_key


@pytest.mark.parametrize(
    ("first", "last", "td_name"),
    [
        ("Roger", "Federer", "Federer R."),
        ("Juan Martin", "del Potro", "Del Potro J.M."),
        ("Albert", "Ramos", "Ramos-Vinolas A."),
        ("Felix", "Auger-Aliassime", "Auger-Aliassime F."),
        ("Stan", "Wawrinka", "Wawrinka S."),
        ("Gael", "Monfils", "Monfils G."),
        ("Andrey", "Kuznetsov", "Kuznetsov An."),
        ("Jo-Wilfried", "Tsonga", "Tsonga J.W."),
    ],
)
def test_keys_agree_on_first_initial(first, last, td_name):
    """Both sources reduce to the same initial; last names agree up to the known Ramos case."""
    s_key, t_key = sackmann_key(first, last), tennisdata_key(td_name)
    assert s_key[-1] == t_key[-1]
    assert last_name(t_key).startswith(last_name(s_key))


def test_fold_strips_accents_and_punctuation():
    """Accents, hyphens and apostrophes do not change the key."""
    assert fold("Núñez-O'Connell") == "nunez o connell"


def test_tennisdata_name_without_initial():
    """A name with no initials token is kept whole."""
    assert tennisdata_key("Nadal") == "nadal"


def test_tennisdata_handles_extra_spaces():
    """Stray whitespace in the source does not leak into the key."""
    assert tennisdata_key("  Federer   R. ") == "federer r"


def test_sackmann_key_tolerates_missing_parts():
    """Missing first or last names give a usable, trimmed key."""
    assert sackmann_key(None, "Federer") == "federer"
    assert sackmann_key("Roger", None) == "r"
    assert sackmann_key(float("nan"), "Federer") == "federer"  # pandas missing value


def test_last_name_drops_only_a_single_letter_initial():
    """'del potro j' -> 'del potro'; a key without initial is returned unchanged."""
    assert last_name("del potro j") == "del potro"
    assert last_name("nadal") == "nadal"
