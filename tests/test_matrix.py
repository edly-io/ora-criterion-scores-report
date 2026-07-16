"""
Unit tests for the pure report logic in ``ora_criterion_scores._matrix``.

These run with only the standard library + pytest — no Django or edx-platform
required.
"""

import json

from ora_criterion_scores._matrix import (
    CELL_NO_SUBMISSION,
    CELL_PEER,
    CELL_SELF,
    CELL_STAFF,
    CELL_UNGRADED,
    assemble_rows,
    build_items,
    cell_for,
    median_option,
    render_panel_js,
)

CRITERIA = [
    {"name": "ideation", "label": "Ideation", "prompt": "Generates unique ideas", "options": []},
    {"name": "top", "label": "Top Options", "prompt": "", "options": []},
]


# --- cell_for: color follows the assessment source, text is the label --------

def test_cell_for_staff_source():
    assert cell_for({"label": "Demonstrated", "points": 1, "source": CELL_STAFF}) == {
        "state": CELL_STAFF,
        "label": "Demonstrated",
        "points": 1,
    }


def test_cell_for_peer_source():
    assert cell_for({"label": "Not yet", "points": 0, "source": CELL_PEER})["state"] == CELL_PEER


def test_cell_for_self_source():
    assert cell_for({"label": "Exemplary", "points": 3, "source": CELL_SELF})["state"] == CELL_SELF


def test_cell_for_none_is_ungraded():
    assert cell_for(None) == {"state": CELL_UNGRADED, "label": "", "points": None}


def test_cell_for_none_points_is_ungraded():
    # e.g. a peer step still awaiting reviews.
    assert cell_for({"label": "", "points": None, "source": CELL_PEER})["state"] == CELL_UNGRADED


def test_cell_for_unknown_source_falls_back_to_ungraded():
    assert cell_for({"label": "x", "points": 1, "source": "bogus"})["state"] == CELL_UNGRADED


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


# --- assemble_rows -----------------------------------------------------------

def test_assemble_rows_graded_learner_keeps_source_and_label():
    learners = [("anon-jordan", "Jordan Doe", "j.doe")]
    anon_to_sub = {"anon-jordan": "sub-1"}
    selected = {"sub-1": {
        "ideation": {"label": "Demonstrated", "points": 1, "source": CELL_PEER},
        "top": {"label": "Not yet", "points": 0, "source": CELL_PEER},
    }}

    row = assemble_rows(CRITERIA, learners, anon_to_sub, selected)[0]

    assert row["name"] == "Jordan Doe"
    assert [c["state"] for c in row["cells"]] == [CELL_PEER, CELL_PEER]
    assert [c["label"] for c in row["cells"]] == ["Demonstrated", "Not yet"]


def test_assemble_rows_no_submission_is_all_dashes():
    learners = [("anon-lena", "Lena Novak", "l.novak")]
    rows = assemble_rows(CRITERIA, learners, anon_id_to_submission={}, selected_options={})
    cells = rows[0]["cells"]
    assert len(cells) == len(CRITERIA)
    assert all(c["state"] == CELL_NO_SUBMISSION for c in cells)


def test_assemble_rows_submitted_but_ungraded():
    learners = [("anon-simi", "Simi Okafor", "s.okafor")]
    anon_to_sub = {"anon-simi": "sub-2"}
    rows = assemble_rows(CRITERIA, learners, anon_to_sub, selected_options={})
    assert all(c["state"] == CELL_UNGRADED for c in rows[0]["cells"])


def test_assemble_rows_partial_criteria_graded():
    learners = [("anon-mei", "Mei Chan", "m.chan")]
    anon_to_sub = {"anon-mei": "sub-3"}
    selected = {"sub-3": {"ideation": {"label": "Demonstrated", "points": 1, "source": CELL_SELF}}}

    cells = assemble_rows(CRITERIA, learners, anon_to_sub, selected)[0]["cells"]
    assert cells[0]["state"] == CELL_SELF
    assert cells[1]["state"] == CELL_UNGRADED


def test_assemble_rows_preserves_learner_order():
    learners = [("a1", "Aaron", "a1"), ("a2", "Zoe", "a2")]
    rows = assemble_rows(CRITERIA, learners, {}, {})
    assert [r["name"] for r in rows] == ["Aaron", "Zoe"]


# --- build_items: unit (bold) + ORA title ------------------------------------

class _FakeBlock:
    def __init__(self, display_name, location, parent="unit"):
        self.display_name = display_name
        self.location = location
        self.parent = parent


def test_build_items_carries_unit_title_and_url():
    blocks = [_FakeBlock("ASSESS: Stories", "block-a")]
    items = build_items(
        blocks,
        url_for=lambda loc: f"/report/{loc}",
        unit_name_for=lambda b: "PRACTICE: Stories",
    )
    assert items == [{
        "unit": "PRACTICE: Stories",
        "title": "ASSESS: Stories",
        "url": "/report/block-a",
    }]


def test_build_items_skips_orphaned_blocks():
    blocks = [_FakeBlock("Orphan", "block-x", parent=None), _FakeBlock("Kept", "block-y")]
    items = build_items(blocks, url_for=lambda loc: str(loc), unit_name_for=lambda b: "U")
    assert [i["title"] for i in items] == ["Kept"]


def test_build_items_title_fallback_and_empty_unit():
    blocks = [_FakeBlock("", "block-z")]
    item = build_items(blocks, url_for=lambda loc: "u", unit_name_for=lambda b: "")[0]
    assert item["title"] == "Open Response Assessment"
    assert item["unit"] == ""


# --- panel JS ----------------------------------------------------------------

def test_render_panel_js_embeds_items_and_section():
    items = [{"unit": "PRACTICE: A", "title": "ASSESS: A", "url": "/report/a"}]
    js = render_panel_js(items, "open_response_assessment")
    assert json.dumps(items) in js
    assert '"open_response_assessment"' in js
    assert "ora-cs-panel" in js            # idempotency guard present
    assert "View criterion scores" in js
    assert "createElement('strong')" in js  # unit rendered bold


def test_render_panel_js_escapes_section_id_as_json_string():
    js = render_panel_js([], "sec")
    assert "getElementById(sectionId)" in js
    assert 'var sectionId = "sec";' in js
