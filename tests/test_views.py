"""Tests for the staff-only data and CSV views, with data and access checks monkeypatched."""

import csv
import io
import json
from datetime import date
from types import SimpleNamespace

import pytest
from django.http import Http404
from django.test import RequestFactory

views = pytest.importorskip(
    "ora_criterion_scores.views",
    reason="requires Django and edx-opaque-keys",
)

COURSE_ID = "course-v1:Org+C+R"
COLUMNS = [
    {"competency": "Course Title", "block_id": "b1", "assessment": "Reflection", "criterion": "C1",
     "criterion_name": "c1", "max_points": 1},
    {"competency": "Course Title", "block_id": "b1", "assessment": "Reflection", "criterion": "C2",
     "criterion_name": "c2", "max_points": 1},
    {"competency": "Course Title", "block_id": "b2", "assessment": "Pitch", "criterion": "C3",
     "criterion_name": "c3", "max_points": 4},
]
REPORT = {
    "columns": [
        {"competency": "Course Title", "block_id": "b1", "assessment": "Reflection", "criterion": "Criterion 1"},
    ],
    "learners": [{
        "name": "=Evil", "username": "u1", "email": "u1@example.com",
        "cells": [{"percent": 100, "status": "demonstrated"}],
        "dates": {"b1": {"date": "10/20/2026", "note": "Staff score"}},
    }],
}


class _Users(list):
    """Minimal queryset: count and slicing."""

    def count(self):
        return len(self)

    def __getitem__(self, item):
        result = super().__getitem__(item)
        return _Users(result) if isinstance(item, slice) else result


def _user(i):
    return SimpleNamespace(id=i, username="u%02d" % i, email="u%02d@example.com" % i,
                           profile=SimpleNamespace(name="Learner %d" % i))


def _request(path="/data", **params):
    request = RequestFactory().get(path, params)
    request.user = SimpleNamespace(is_authenticated=True)
    return request


def _get(**params):
    response = views.ora_scores_data(_request(**params), COURSE_ID)
    return json.loads(response.content)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    calls = {}
    users = _Users([_user(i) for i in range(1, 24)])  # 23 learners

    def learners_queryset(course_key, query=None):
        calls["q"] = query
        return users

    def get_cells(columns, blocks_by_id, page_users, course_key, threshold, tz=None, submissions=None):
        calls["columns"] = columns
        calls["page_users"] = page_users
        calls["threshold"] = threshold
        cells = {u.id: [None] * len(columns) for u in page_users}
        dates = {u.id: {"b1": {"date": "10/20/2026", "note": "Staff score"}} if u.id % 2 else {}
                 for u in page_users}
        return cells, dates

    monkeypatch.setattr(views, "get_course_with_access", lambda *a, **k: None)
    monkeypatch.setattr(views.data, "get_columns", lambda key: (COLUMNS, {}))
    monkeypatch.setattr(views.data, "learners_queryset", learners_queryset)
    monkeypatch.setattr(views.data, "get_cells", get_cells)
    monkeypatch.setattr(views.data, "get_submissions", lambda course_key, block_ids: {})
    monkeypatch.setattr(views.data, "get_attempt_counts", lambda columns, course_key, submissions=None: ({}, 23))
    monkeypatch.setattr(views.data, "threshold", lambda: 75)
    monkeypatch.setattr(views.data, "build_report", lambda course_key, tz=None: REPORT)
    return calls


def test_first_page_defaults():
    body = _get()
    assert (body["page"], body["page_size"], body["total"], body["num_pages"]) == (1, 10, 23, 3)
    assert len(body["learners"]) == 10
    assert body["learners"][0]["username"] == "u01"
    assert body["threshold"] == 75
    assert len(body["columns"]) == 3
    assert set(body) == {"assessments", "columns", "learners", "page", "page_size", "total", "num_pages", "threshold"}
    assert set(body["columns"][0]) == {"competency", "block_id", "assessment", "criterion"}


def test_learners_carry_dates_for_submitted_blocks_only():
    learners = _get()["learners"]
    assert learners[0]["dates"] == {"b1": {"date": "10/20/2026", "note": "Staff score"}}   # u01 submitted
    assert learners[1]["dates"] == {}                                                       # u02 did not
    assert set(learners[0]) == {"name", "username", "email", "cells", "dates"}


def test_last_page_is_partial():
    body = _get(page=3)
    assert len(body["learners"]) == 3
    assert body["learners"][0]["username"] == "u21"


def test_page_past_end_is_clamped():
    assert _get(page=99)["page"] == 3


def test_page_size_capped_and_invalid_values_ignored():
    assert _get(page_size=1000)["page_size"] == 100
    assert _get(page_size="abc")["page_size"] == 10
    assert _get(page="abc")["page"] == 1
    assert _get(page=0)["page"] == 1


def test_assessment_filter_limits_columns_but_not_dropdown():
    body = _get(assessment="b2")
    assert [c["criterion"] for c in body["columns"]] == ["C3"]
    assert body["assessments"] == [
        {"id": "b1", "name": "Reflection", "attempted": 0, "total": 23},
        {"id": "b2", "name": "Pitch", "attempted": 0, "total": 23},
    ]


def _with_counts(monkeypatch, counts, total):
    monkeypatch.setattr(views.data, "get_attempt_counts",
                        lambda columns, course_key, submissions=None: (counts, total))


def test_assessments_carry_attempted_and_total(monkeypatch):
    _with_counts(monkeypatch, {"b1": 5, "b2": 0}, 23)
    assert _get()["assessments"] == [
        {"id": "b1", "name": "Reflection", "attempted": 5, "total": 23},
        {"id": "b2", "name": "Pitch", "attempted": 0, "total": 23},
    ]


def test_total_counts_all_enrolled_not_the_page_or_search(monkeypatch):
    _with_counts(monkeypatch, {"b1": 7}, 40)
    body = _get(q="u0", page_size=5)
    assert [a["total"] for a in body["assessments"]] == [40, 40]
    assert body["total"] == 23   # the search result size is separate


def test_counts_use_every_column_and_ignore_search_and_assessment(monkeypatch):
    seen = []

    def counts(columns, course_key, submissions=None):
        seen.append([c["block_id"] for c in columns])
        return {"b1": 4, "b2": 2}, 23

    monkeypatch.setattr(views.data, "get_attempt_counts", counts)
    body = _get(q="u01", assessment="b2")
    assert seen == [["b1", "b1", "b2"]]
    assert [(a["id"], a["attempted"]) for a in body["assessments"]] == [("b1", 4), ("b2", 2)]


def test_no_columns_gives_empty_assessments_and_no_submissions_call(monkeypatch):
    monkeypatch.setattr(views.data, "get_columns", lambda key: ([], {}))
    monkeypatch.setattr(views.data, "get_submissions", lambda *a: pytest.fail("no columns, no call"))
    body = _get()
    assert body["assessments"] == [] and body["columns"] == []


def test_same_submissions_are_passed_to_counts_and_cells(monkeypatch, _patch):
    shared = {("anon-1", "b1"): {"uuid": "s", "submitted_at": None}}
    monkeypatch.setattr(views.data, "get_submissions", lambda course_key, block_ids: shared)
    passed = {}

    def counts(columns, course_key, submissions=None):
        passed["counts"] = submissions
        return {}, 23

    def cells(columns, blocks_by_id, page_users, course_key, threshold, tz=None, submissions=None):
        passed["cells"] = submissions
        return {u.id: [None] * len(columns) for u in page_users}, {u.id: {} for u in page_users}

    monkeypatch.setattr(views.data, "get_attempt_counts", counts)
    monkeypatch.setattr(views.data, "get_cells", cells)
    _get()
    assert passed["counts"] is shared and passed["cells"] is shared


def test_submissions_requested_for_all_blocks_not_just_the_filtered_one(monkeypatch):
    wanted = []
    monkeypatch.setattr(views.data, "get_submissions", lambda course_key, block_ids: wanted.append(block_ids) or {})
    _get(assessment="b2")
    assert wanted == [{"b1", "b2"}]


def test_one_course_wide_submissions_call_per_data_request(monkeypatch):
    """Real get_submissions, get_attempt_counts and get_cells: the platform API is hit once."""
    from types import SimpleNamespace

    models = pytest.importorskip("common.djangoapps.student.models")
    api_calls = []
    rows = [
        ({"student_id": "anon-1", "item_id": "b1"}, {"uuid": "s1", "submitted_at": None}, {}),
        ({"student_id": "anon-2", "item_id": "b2"}, {"uuid": "s2", "submitted_at": None}, {}),
    ]

    def api(course_id, item_type):
        api_calls.append((course_id, item_type))
        return iter(rows)

    class _Manager:
        def filter(self, **kwargs):
            return SimpleNamespace(values_list=lambda *a, **k: iter(["anon-1", "anon-2"]))

    monkeypatch.undo()   # drop the autouse stubs, then install only what this test needs
    monkeypatch.setattr(views, "get_course_with_access", lambda *a, **k: None)
    monkeypatch.setattr(views.data, "get_columns", lambda key: (COLUMNS, {"b1": object(), "b2": object()}))
    monkeypatch.setattr(views.data, "threshold", lambda: 75)
    monkeypatch.setattr(views.data, "learners_queryset",
                        lambda course_key, query=None: _Users([_user(1), _user(2)]))
    monkeypatch.setattr(views.data, "anonymous_id_for_user", lambda user, key: "anon-%s" % user.id)
    monkeypatch.setattr(views.data, "_normalized_criteria", lambda block: [])
    monkeypatch.setattr(views.data, "_effective_selections", lambda *a, **k: {})
    monkeypatch.setattr(views.data.sub_api, "get_all_course_submission_information", api)
    monkeypatch.setattr(models, "AnonymousUserId", SimpleNamespace(objects=_Manager()), raising=False)

    body = _get(q="u", assessment="b1")

    assert len(api_calls) == 1
    assert [(a["id"], a["attempted"], a["total"]) for a in body["assessments"]] == [
        ("b1", 1, 2), ("b2", 1, 2),
    ]


def test_csv_ignores_q_and_assessment_and_forwards_tz(monkeypatch):
    seen = {}
    monkeypatch.setattr(views.data, "build_report", lambda course_key, tz=None: seen.update(tz=tz) or REPORT)
    response = views.ora_scores_csv(_request("/csv", q="x", assessment="b1", tz="Asia/Karachi"), COURSE_ID)
    assert response.status_code == 200
    assert seen == {"tz": "Asia/Karachi"}


def test_query_is_passed_through(_patch):
    _get(q="  ayesha ")
    assert _patch["q"] == "ayesha"


def test_scores_requested_only_for_page_users_and_filtered_columns(_patch):
    _get(page=2, page_size=5, assessment="b1")
    assert [u.id for u in _patch["page_users"]] == [6, 7, 8, 9, 10]
    assert [c["criterion"] for c in _patch["columns"]] == ["C1", "C2"]
    assert _patch["threshold"] == 75


def test_data_rejects_non_staff(monkeypatch):
    def _deny(*args, **kwargs):
        raise Http404()
    monkeypatch.setattr(views, "get_course_with_access", _deny)
    with pytest.raises(Http404):
        _get()


def test_data_invalid_course_id_is_404():
    with pytest.raises(Http404):
        views.ora_scores_data(_request(), "not-a-course-id")


def test_data_response_is_not_cached():
    response = views.ora_scores_data(_request(), COURSE_ID)
    assert "no-store" in response["Cache-Control"]


def test_csv_download():
    response = views.ora_scores_csv(_request("/csv"), COURSE_ID)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert response["Content-Disposition"].startswith('attachment; filename="ora_assessment_scores_')
    assert "course-v1org" in response["Content-Disposition"]
    assert response["Content-Disposition"].endswith('.csv"')
    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows[0] == ["Competency", "", "", "Course Title", "Course Title"]
    assert rows[1] == ["Assessment Name", "", "", "Reflection", "Reflection"]
    assert rows[2] == ["Learner", "Username", "Email", "Attempt Date", "Criterion 1"]
    assert rows[3] == ["'=Evil", "u1", "u1@example.com", "10/20/2026", "100% (Demonstrated)"]
    assert len(rows) == 4


def test_csv_filename_has_today_date():
    response = views.ora_scores_csv(_request("/csv"), COURSE_ID)
    assert response["Content-Disposition"].endswith("_{}.csv\"".format(date.today().isoformat()))


def test_csv_rejects_non_staff(monkeypatch):
    def _deny(*args, **kwargs):
        raise Http404()
    monkeypatch.setattr(views, "get_course_with_access", _deny)
    with pytest.raises(Http404):
        views.ora_scores_csv(_request("/csv"), COURSE_ID)


def test_csv_invalid_course_id_is_404():
    with pytest.raises(Http404):
        views.ora_scores_csv(_request("/csv"), "not-a-course-id")
