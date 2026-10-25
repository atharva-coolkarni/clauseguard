from clauseguard.text import normalize


def test_collapses_whitespace():
    assert normalize("  The   rent\nis due\t monthly. ") == "The rent is due monthly."


def test_joins_hyphen_broken_across_lines():
    assert normalize("minor day-\nto-day repairs") == "minor day-to-day repairs"
    assert normalize("minor day-  \n   to-day repairs") == "minor day-to-day repairs"


def test_keeps_ordinary_hyphens_and_dashes():
    assert normalize("flat B-304 - Kochi") == "flat B-304 - Kochi"
