"""
Tests for the data layer with fake platform modules.

``get_columns`` imports ``xmodule`` lazily, ``get_submissions`` calls the
submissions API and ``get_cells`` resolves effective scores through
``_effective_selections``. Each test monkeypatches the few calls it needs.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from django.conf import settings as django_settings

from ora_criterion_scores import data

BASE = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
BINARY = [{"label": "Not Demonstrated", "points": 0}, {"label": "Demonstrated", "points": 1}]
FOUR_LEVELS = [{"label": str(i), "points": i} for i in range(5)]


def _criterion(name, options, order=0, label=None):
    criterion = {"name": name, "order_num": order, "options": options, "prompt": ""}
    if label is not None:
        criterion["label"] = label
    return criterion


def _ora(location, name, criteria, steps=("staff-assessment",)):
    return SimpleNamespace(
        category="openassessment", location=location, display_name=name,
        rubric_criteria=criteria, assessment_steps=list(steps), get_children=lambda: [],
    )


def _course(name, children):
    return SimpleNamespace(
        category="course", location="course", display_name=name, get_children=lambda: list(children),
    )


def _store(monkeypatch, course):
    store = SimpleNamespace(get_course=lambda key, depth=None: course)
    monkeypatch.setattr("xmodule.modulestore.django.modulestore", lambda: store)


# --- get_columns -------------------------------------------------------------

def test_get_columns_follows_outline_order_across_blocks(monkeypatch):
    first = _ora("b1", "Reflection", [_criterion("c2", BINARY, order=2), _criterion("c1", BINARY, order=1)])
    second = _ora("b2", "Pitch", [_criterion("clarity", FOUR_LEVELS, label="Clarity")])
    vertical = SimpleNamespace(category="vertical", get_children=lambda: [second, first])
    # Outline order is tree order, not creation order: "second" comes first in the tree.
    course = _course("Course Title", [SimpleNamespace(category="chapter", get_children=lambda: [vertical])])
    _store(monkeypatch, course)

    columns, blocks_by_id = data.get_columns("course-key")

    assert [(c["assessment"], c["criterion"], c["criterion_name"], c["max_points"]) for c in columns] == [
        ("Pitch", "Clarity", "clarity", 4),
        ("Reflection", "c1", "c1", 1),
        ("Reflection", "c2", "c2", 1),
    ]
    assert [c["block_id"] for c in columns] == ["b2", "b1", "b1"]
    assert {c["competency"] for c in columns} == {"Course Title"}
    assert set(blocks_by_id) == {"b1", "b2"}


def test_get_columns_skips_feedback_only_criterion(monkeypatch):
    block = _ora("b1", "Reflection", [_criterion("c1", BINARY), _criterion("notes", [], order=1)])
    _store(monkeypatch, _course("Course", [block]))

    columns, _blocks = data.get_columns("course-key")

    assert [c["criterion_name"] for c in columns] == ["c1"]


def test_get_columns_label_and_name_fallbacks(monkeypatch):
    block = _ora("b1", "", [_criterion("c1", BINARY)])
    _store(monkeypatch, _course("", [block]))

    columns, _blocks = data.get_columns("course-key")

    assert columns[0]["criterion"] == "c1"
    assert columns[0]["assessment"] == "Open Response Assessment"
    assert columns[0]["competency"] == ""


def test_get_columns_max_points_is_highest_option(monkeypatch):
    block = _ora("b1", "A", [_criterion("c1", [{"label": "x", "points": 2}, {"label": "y", "points": 5}])])
    _store(monkeypatch, _course("Course", [block]))

    assert data.get_columns("course-key")[0][0]["max_points"] == 5


def test_get_columns_no_course(monkeypatch):
    _store(monkeypatch, None)
    assert data.get_columns("course-key") == ([], {})


def test_get_columns_course_without_ora(monkeypatch):
    _store(monkeypatch, _course("Course", []))
    assert data.get_columns("course-key") == ([], {})


# --- get_submissions ---------------------------------------------------------

def _submission(student_id, item_id, uuid, submitted_at):
    return (
        {"student_id": student_id, "item_id": item_id, "course_id": "c", "item_type": "openassessment"},
        {"uuid": uuid, "submitted_at": submitted_at},
        {},
    )


def _submissions_api(monkeypatch, rows):
    calls = []

    def api(course_id, item_type):
        calls.append((course_id, item_type))
        return iter(rows)

    monkeypatch.setattr(data.sub_api, "get_all_course_submission_information", api)
    return calls


def test_get_submissions_keeps_latest_per_learner_and_block(monkeypatch):
    calls = _submissions_api(monkeypatch, [
        _submission("anon-1", "b1", "old", BASE),
        _submission("anon-1", "b1", "new", BASE + timedelta(days=2)),
        _submission("anon-1", "b1", "older", BASE - timedelta(days=1)),
        _submission("anon-1", "b2", "other-block", BASE),
        _submission("anon-2", "b1", "second-learner", BASE),
        _submission("anon-3", "not-wanted", "ignored", BASE),
    ])

    result = data.get_submissions("course-key", {"b1", "b2"})

    assert calls == [("course-key", "openassessment")]
    assert result == {
        ("anon-1", "b1"): {"uuid": "new", "submitted_at": BASE + timedelta(days=2)},
        ("anon-1", "b2"): {"uuid": "other-block", "submitted_at": BASE},
        ("anon-2", "b1"): {"uuid": "second-learner", "submitted_at": BASE},
    }


# --- get_cells ---------------------------------------------------------------

def _users(*ids):
    return [SimpleNamespace(id=i) for i in ids]


def _columns(block_id="b1", assessment="Reflection", criteria=("c1", "c2"), max_points=1):
    return [
        {
            "competency": "Course", "block_id": block_id, "assessment": assessment, "criterion": name.upper(),
            "criterion_name": name, "max_points": max_points,
        }
        for name in criteria
    ]


def _selection(points, source):
    return {"label": "x", "points": points, "source": source}


@pytest.fixture
def cells_env(monkeypatch):
    """Patch anonymous ids, the submissions API and ``_effective_selections``."""
    env = SimpleNamespace(submissions=[], selected={}, calls=[])
    monkeypatch.setattr(data, "anonymous_id_for_user", lambda user, course_key: "anon-%s" % user.id)
    monkeypatch.setattr(
        data.sub_api, "get_all_course_submission_information", lambda course_id, item_type: iter(env.submissions),
    )

    def fake_effective(block, criteria, submission_uuids):
        env.calls.append((block.location, sorted(submission_uuids)))
        return {uuid: env.selected[uuid] for uuid in submission_uuids if uuid in env.selected}

    monkeypatch.setattr(data, "_effective_selections", fake_effective)
    env.blocks = {
        "b1": _ora("b1", "Reflection", [_criterion("c1", BINARY), _criterion("c2", BINARY, order=1)]),
        "b2": _ora("b2", "Pitch", [_criterion("c1", BINARY)]),
    }
    return env


def test_get_cells_staff_scored_learner(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE)]
    cells_env.selected = {"sub-1": {"c1": _selection(1, "staff"), "c2": _selection(0, "staff")}}

    cells, dates = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75)

    assert cells[1] == [{"percent": 100, "status": "demonstrated"}, {"percent": 0, "status": "not_demonstrated"}]
    assert dates[1] == {"b1": {"date": "10/20/2026", "note": "Staff score"}}


def test_get_cells_percent_uses_highest_option_points(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE)]
    cells_env.selected = {"sub-1": {"c1": _selection(2, "staff"), "c2": _selection(3, "staff")}}

    cells, _dates = data.get_cells(_columns(max_points=4), cells_env.blocks, _users(1), "course-key", 75)

    assert cells[1] == [{"percent": 50, "status": "not_demonstrated"}, {"percent": 75, "status": "demonstrated"}]


def test_get_cells_peer_only_learner(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE)]
    cells_env.selected = {"sub-1": {"c1": _selection(1.5, "peer"), "c2": _selection(1.5, "peer")}}

    cells, dates = data.get_cells(_columns(max_points=2), cells_env.blocks, _users(1), "course-key", 75)

    assert cells[1][0] == {"percent": 75, "status": "demonstrated"}
    assert dates[1]["b1"]["note"] == "Peer score"


def test_get_cells_self_only_learner(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE)]
    cells_env.selected = {"sub-1": {"c1": _selection(1, "self")}}

    cells, dates = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75)

    assert cells[1] == [{"percent": 100, "status": "demonstrated"}, None]
    assert dates[1]["b1"]["note"] == "Self score"


def test_get_cells_submitted_not_scored(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE)]
    cells_env.selected = {"sub-1": {}}   # for example a peer step still waiting for reviews

    cells, dates = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75)

    assert cells[1] == [None, None]
    assert dates[1] == {"b1": {"date": "10/20/2026", "note": "Awaiting grade"}}


def test_get_cells_submitted_with_no_selection_entry(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE)]   # uuid absent from the result

    cells, dates = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75)

    assert cells[1] == [None, None]
    assert dates[1]["b1"] == {"date": "10/20/2026", "note": "Awaiting grade"}


def test_get_cells_selection_without_points_is_no_score(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE)]
    cells_env.selected = {"sub-1": {"c1": _selection(None, "peer"), "c2": _selection(1, "peer")}}

    cells, _dates = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75)

    assert cells[1] == [None, {"percent": 100, "status": "demonstrated"}]


def test_get_cells_never_submitted(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE)]
    cells_env.selected = {"sub-1": {"c1": _selection(1, "staff")}}

    cells, dates = data.get_cells(_columns(), cells_env.blocks, _users(1, 2), "course-key", 75)

    assert cells[2] == [None, None]
    assert dates[2] == {}
    assert "b1" in dates[1]


def test_get_cells_writes_dates_in_the_browser_zone(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "sub-1", BASE.replace(hour=3))]
    cells_env.selected = {"sub-1": {"c1": _selection(1, "staff")}}

    _, utc_dates = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75)
    _, honolulu = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75, "Pacific/Honolulu")
    _, bad_zone = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75, "Nope/Nope")

    assert utc_dates[1]["b1"]["date"] == "10/20/2026"
    assert honolulu[1]["b1"]["date"] == "10/19/2026"
    assert bad_zone[1]["b1"]["date"] == "10/20/2026"


def test_get_cells_later_submission_wins(cells_env):
    cells_env.submissions = [
        _submission("anon-1", "b1", "later", BASE + timedelta(days=3)),
        _submission("anon-1", "b1", "earlier", BASE),
    ]
    cells_env.selected = {
        "later": {"c1": _selection(1, "staff"), "c2": _selection(1, "staff")},
        "earlier": {"c1": _selection(0, "staff"), "c2": _selection(0, "staff")},
    }

    cells, dates = data.get_cells(_columns(), cells_env.blocks, _users(1), "course-key", 75)

    assert cells[1][0] == {"percent": 100, "status": "demonstrated"}
    assert dates[1]["b1"]["date"] == "10/23/2026"
    assert cells_env.calls == [("b1", ["later"])]


def test_get_cells_effective_selections_once_per_block_for_page_uuids_only(cells_env):
    cells_env.submissions = [
        _submission("anon-1", "b1", "s-1-b1", BASE),
        _submission("anon-2", "b1", "s-2-b1", BASE),
        _submission("anon-3", "b1", "s-3-b1", BASE),   # learner 3 is not on this page
        _submission("anon-1", "b2", "s-1-b2", BASE),
        _submission("anon-2", "b2", "s-2-b2", BASE),
    ]
    columns = _columns("b1") + _columns("b2", "Pitch", ("c1",))

    data.get_cells(columns, cells_env.blocks, _users(1, 2), "course-key", 75)

    assert cells_env.calls == [("b1", ["s-1-b1", "s-2-b1"]), ("b2", ["s-1-b2", "s-2-b2"])]


def test_get_cells_skips_blocks_nobody_submitted(cells_env):
    cells_env.submissions = [_submission("anon-1", "b1", "s-1-b1", BASE)]
    columns = _columns("b1") + _columns("b2", "Pitch", ("c1",))

    cells, dates = data.get_cells(columns, cells_env.blocks, _users(1), "course-key", 75)

    assert [call[0] for call in cells_env.calls] == ["b1"]
    assert cells[1][2] is None
    assert list(dates[1]) == ["b1"]


def test_get_cells_no_columns_or_users(cells_env):
    assert data.get_cells([], cells_env.blocks, _users(1), "course-key", 75) == ({1: []}, {1: {}})
    assert data.get_cells(_columns(), cells_env.blocks, [], "course-key", 75) == ({}, {})
    assert cells_env.calls == []


# --- _effective_selections ---------------------------------------------------

def _patch_apis(monkeypatch, staff=None, peer=None, self_assessment=None):
    from openassessment.assessment.api import peer as peer_api
    from openassessment.assessment.api import self as self_api
    from openassessment.assessment.api import staff as staff_api

    monkeypatch.setattr(staff_api, "get_latest_staff_assessment", lambda uuid: (staff or {}).get(uuid))
    monkeypatch.setattr(
        peer_api, "get_assessment_scores_with_grading_strategy", lambda uuid, requirements: (peer or {}).get(uuid, {}),
    )
    monkeypatch.setattr(self_api, "get_assessment", lambda uuid: (self_assessment or {}).get(uuid))


def _assessment(**points_by_criterion):
    return {"parts": [
        {"criterion": {"name": name}, "option": {"label": "L%s" % points, "points": points}}
        for name, points in points_by_criterion.items()
    ]}


NORMALIZED = [
    {"name": "c1", "label": "C1", "prompt": "", "options": BINARY},
]


def test_effective_selections_staff_wins(monkeypatch):
    _patch_apis(
        monkeypatch, staff={"s1": _assessment(c1=1)}, peer={"s1": {"c1": 0}}, self_assessment={"s1": _assessment(c1=0)},
    )
    block = _ora("b1", "A", [], steps=("peer-assessment", "self-assessment", "staff-assessment"))

    result = data._effective_selections(block, NORMALIZED, ["s1"])  # pylint: disable=protected-access

    assert result == {"s1": {"c1": {"label": "L1", "points": 1, "source": "staff"}}}


def test_effective_selections_peer_median(monkeypatch):
    _patch_apis(monkeypatch, peer={"s1": {"c1": 1}})
    block = _ora("b1", "A", [], steps=("peer-assessment",))

    result = data._effective_selections(block, NORMALIZED, ["s1"])  # pylint: disable=protected-access

    assert result["s1"]["c1"]["source"] == "peer"
    assert result["s1"]["c1"]["points"] == 1


def test_effective_selections_peer_without_reviews_is_empty(monkeypatch):
    _patch_apis(monkeypatch)
    block = _ora("b1", "A", [], steps=("peer-assessment",))

    assert data._effective_selections(block, NORMALIZED, ["s1"]) == {"s1": {}}  # pylint: disable=protected-access


def test_effective_selections_self(monkeypatch):
    _patch_apis(monkeypatch, self_assessment={"s1": _assessment(c1=1)})
    block = _ora("b1", "A", [], steps=("self-assessment",))

    result = data._effective_selections(block, NORMALIZED, ["s1", "s2"])  # pylint: disable=protected-access

    assert result == {"s1": {"c1": {"label": "L1", "points": 1, "source": "self"}}}


# --- small helpers -----------------------------------------------------------

def test_learner_row_shape_and_name_fallback():
    dates = {"b1": {"date": "10/20/2026", "note": "Staff score"}}
    with_name = SimpleNamespace(username="u", email="e@x.com", profile=SimpleNamespace(name="Full Name"))
    no_name = SimpleNamespace(username="u2", email="e2@x.com", profile=SimpleNamespace(name=""))
    no_profile = SimpleNamespace(username="u3", email="e3@x.com")

    assert data.learner_row(with_name, [None], dates) == {
        "name": "Full Name", "username": "u", "email": "e@x.com", "cells": [None], "dates": dates,
    }
    assert data.learner_row(no_name, [], {})["name"] == "u2"
    assert data.learner_row(no_profile, [], {})["name"] == "u3"


def test_threshold_default_and_setting(monkeypatch):
    monkeypatch.delattr(django_settings, "EDL_AUTO_ASSESSMENT_THRESHOLD", raising=False)
    assert data.threshold() == 75
    monkeypatch.setattr(django_settings, "EDL_AUTO_ASSESSMENT_THRESHOLD", 60, raising=False)
    assert data.threshold() == 60


def test_build_report_collects_columns_and_all_learners(monkeypatch):
    users = [SimpleNamespace(id=1, username="a", email="a@x.com"), SimpleNamespace(id=2, username="b", email="b@x.com")]
    columns = _columns()
    monkeypatch.setattr(data, "get_columns", lambda key: (columns, {"b1": object()}))
    monkeypatch.setattr(data, "learners_queryset", lambda key: users)
    seen = {}

    def fake_cells(cols, blocks, page_users, key, threshold, tz=None):
        seen["args"] = (cols, blocks, [u.id for u in page_users], key, threshold, tz)
        return {1: [None, None], 2: [None, None]}, {1: {}, 2: {"b1": {"date": "10/20/2026", "note": ""}}}

    monkeypatch.setattr(data, "get_cells", fake_cells)

    report_data = data.build_report("course-key", "Asia/Karachi")

    assert seen["args"][2:] == ([1, 2], "course-key", 75, "Asia/Karachi")
    assert report_data["columns"] == columns
    assert [learner["username"] for learner in report_data["learners"]] == ["a", "b"]
    assert report_data["learners"][1]["dates"] == {"b1": {"date": "10/20/2026", "note": ""}}
