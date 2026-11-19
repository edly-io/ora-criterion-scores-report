"""
Unit tests for the pure peer-median mapping in ``ora_criterion_scores._matrix``.

These run with only the standard library + pytest — no Django or edx-platform
required.
"""

from ora_criterion_scores._matrix import CELL_PEER, CELL_SELF, CELL_STAFF, median_option

# --- peer median -> authored option(s), faithful to ORA ----------------------

BINARY = [{"label": "Not yet", "points": 0}, {"label": "Demonstrated", "points": 1}]
SPREAD = [{"label": "A", "points": 1}, {"label": "B", "points": 3}, {"label": "C", "points": 5}]


def test_median_option_exact_match_returns_single_label():
    assert median_option(SPREAD, 3) == {"label": "B", "points": 3}


def test_median_option_between_options_joins_authored_labels():
    # Median 4 sits between B(3) and C(5) -> "B / C", never a hardcoded string.
    result = median_option(SPREAD, 4)
    assert result["label"] == "B / C"
    assert result["points"] == 4


def test_median_option_none_when_no_reviews():
    assert median_option(BINARY, None) is None


def test_median_option_ties_collapse_to_joined_labels():
    tied = [{"label": "A", "points": 1}, {"label": "B", "points": 1}, {"label": "C", "points": 3}]
    assert median_option(tied, 1)["label"] == "A / B"


def test_median_option_binary_matches_authored_label():
    assert median_option(BINARY, 1) == {"label": "Demonstrated", "points": 1}
    assert median_option(BINARY, 0) == {"label": "Not yet", "points": 0}


def test_source_constants():
    assert (CELL_STAFF, CELL_PEER, CELL_SELF) == ("staff", "peer", "self")
