"""
Unit tests for the pure report logic in ``ora_criterion_scores._matrix``.

These run with only the standard library + pytest — no Django or edx-platform
required.
"""

import json

from ora_criterion_scores._matrix import (
    CELL_DEMONSTRATED,
    CELL_NO_SUBMISSION,
    CELL_NOT_YET,
    CELL_UNGRADED,
    assemble_rows,
    build_items,
    cell_for,
    render_panel_js,
)

CRITERIA = [
    {"name": "ideation", "label": "Ideation", "prompt": "Generates unique ideas"},
    {"name": "top", "label": "Top Options", "prompt": ""},
]


def test_cell_for_demonstrated():
    assert cell_for({"label": "Demonstrated", "points": 1}) == {
        "state": CELL_DEMONSTRATED,
        "label": "Demonstrated",
        "points": 1,
    }


def test_cell_for_not_yet_is_zero_points():
    cell = cell_for({"label": "Not yet", "points": 0})
    assert cell["state"] == CELL_NOT_YET
    assert cell["label"] == "Not yet"


def test_cell_for_multi_point_option_is_demonstrated():
    # Any option worth > 0 points counts as "demonstrated", not just 1.
    assert cell_for({"label": "Excellent", "points": 3})["state"] == CELL_DEMONSTRATED


def test_cell_for_none_is_ungraded():
    assert cell_for(None) == {"state": CELL_UNGRADED, "label": "", "points": None}


def test_assemble_rows_graded_learner():
    learners = [("anon-jordan", "Jordan Doe", "j.doe")]
    anon_to_sub = {"anon-jordan": "sub-1"}
    selected = {"sub-1": {
        "ideation": {"label": "Demonstrated", "points": 1},
        "top": {"label": "Not yet", "points": 0},
    }}

    rows = assemble_rows(CRITERIA, learners, anon_to_sub, selected)

    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Jordan Doe"
    assert row["username"] == "j.doe"
    assert [c["state"] for c in row["cells"]] == [CELL_DEMONSTRATED, CELL_NOT_YET]
    assert [c["label"] for c in row["cells"]] == ["Demonstrated", "Not yet"]


def test_assemble_rows_no_submission_is_all_dashes():
    learners = [("anon-lena", "Lena Novak", "l.novak")]
    rows = assemble_rows(CRITERIA, learners, anon_id_to_submission={}, selected_options={})

    cells = rows[0]["cells"]
    assert len(cells) == len(CRITERIA)
    assert all(c["state"] == CELL_NO_SUBMISSION for c in cells)


def test_assemble_rows_submitted_but_ungraded():
    # Learner has a submission, but no staff assessment recorded for it.
    learners = [("anon-simi", "Simi Okafor", "s.okafor")]
    anon_to_sub = {"anon-simi": "sub-2"}
    rows = assemble_rows(CRITERIA, learners, anon_to_sub, selected_options={})

    assert all(c["state"] == CELL_UNGRADED for c in rows[0]["cells"])


def test_assemble_rows_partial_criteria_graded():
    # Submission graded on one criterion only -> the other is ungraded, not a dash.
    learners = [("anon-mei", "Mei Chan", "m.chan")]
    anon_to_sub = {"anon-mei": "sub-3"}
    selected = {"sub-3": {"ideation": {"label": "Demonstrated", "points": 1}}}

    cells = assemble_rows(CRITERIA, learners, anon_to_sub, selected)[0]["cells"]
    assert cells[0]["state"] == CELL_DEMONSTRATED
    assert cells[1]["state"] == CELL_UNGRADED


def test_assemble_rows_preserves_criteria_order():
    reversed_criteria = list(reversed(CRITERIA))
    learners = [("a", "A", "a")]
    selected = {"s": {
        "ideation": {"label": "Demonstrated", "points": 1},
        "top": {"label": "Not yet", "points": 0},
    }}
    cells = assemble_rows(reversed_criteria, learners, {"a": "s"}, selected)[0]["cells"]
    # First column should now be "top" (Not yet), matching the passed order.
    assert cells[0]["label"] == "Not yet"
    assert cells[1]["label"] == "Demonstrated"


def test_assemble_rows_preserves_learner_order():
    learners = [("a1", "Aaron", "a1"), ("a2", "Zoe", "a2")]
    rows = assemble_rows(CRITERIA, learners, {}, {})
    assert [r["name"] for r in rows] == ["Aaron", "Zoe"]


class _FakeBlock:
    def __init__(self, display_name, location, parent="unit"):
        self.display_name = display_name
        self.location = location
        self.parent = parent


def test_build_items_maps_name_and_url():
    blocks = [_FakeBlock("Exercise A", "block-a")]
    items = build_items(blocks, url_for=lambda loc: f"/report/{loc}")
    assert items == [{"name": "Exercise A", "url": "/report/block-a"}]


def test_build_items_skips_orphaned_blocks():
    blocks = [_FakeBlock("Orphan", "block-x", parent=None), _FakeBlock("Kept", "block-y")]
    items = build_items(blocks, url_for=lambda loc: str(loc))
    assert [i["name"] for i in items] == ["Kept"]


def test_build_items_falls_back_when_no_display_name():
    blocks = [_FakeBlock("", "block-z")]
    assert build_items(blocks, url_for=lambda loc: "u")[0]["name"] == "Open Response Assessment"


def test_render_panel_js_embeds_items_and_section():
    items = [{"name": "Exercise A", "url": "/report/a"}]
    js = render_panel_js(items, "open_response_assessment")
    assert json.dumps(items) in js
    assert '"open_response_assessment"' in js
    assert "ora-cs-panel" in js            # idempotency guard present
    assert "View criterion scores" in js


def test_render_panel_js_escapes_section_id_as_json_string():
    # section id must be embedded as a quoted JS string, not a bare token.
    js = render_panel_js([], "sec")
    assert 'getElementById(sectionId)' in js
    assert 'var sectionId = "sec";' in js
