"""Tests for the pure report helpers (a copy of the Auto Assessments ones)."""

from datetime import datetime, timedelta, timezone

from ora_criterion_scores import report
from ora_criterion_scores.report import STATUS_DEMONSTRATED, STATUS_NOT_DEMONSTRATED


def test_percent_binary():
    assert report.percent(1, 1) == 100
    assert report.percent(0, 1) == 0
    assert isinstance(report.percent(1, 1), int)


def test_percent_multi_level():
    assert report.percent(2, 4) == 50
    assert report.percent(2, 3) == 66.67


def test_percent_peer_median_between_options():
    assert report.percent(1.5, 2) == 75
    assert report.status(report.percent(1.5, 2), 75) == STATUS_DEMONSTRATED


def test_percent_none_when_maximum_is_zero_or_missing():
    assert report.percent(0, 0) is None
    assert report.percent(1, None) is None
    assert report.percent(None, 1) is None
    assert report.percent(5, -1) is None


def test_percent_caps_at_100():
    assert report.percent(120, 100) == 100


def test_status_boundary():
    assert report.status(75, 75) == STATUS_DEMONSTRATED
    assert report.status(74.99, 75) == STATUS_NOT_DEMONSTRATED


def test_make_cell_and_cell_text():
    assert report.make_cell(1, 1, 75) == {"percent": 100, "status": STATUS_DEMONSTRATED}
    assert report.make_cell(0, 1, 75) == {"percent": 0, "status": STATUS_NOT_DEMONSTRATED}
    assert report.make_cell(1, 0, 75) is None
    assert report.cell_text(None) == ""
    assert report.cell_text(report.make_cell(3, 4, 75)) == "75% (Demonstrated)"
    assert report.cell_text(report.make_cell(2, 4, 75)) == "50% (Not Demonstrated)"


def test_safe_prefixes_formula_characters():
    for char in ("=", "+", "-", "@", "\t", "\r"):
        assert report.safe(char + "cmd") == "'" + char + "cmd"
    assert report.safe("Ayesha") == "Ayesha"
    assert report.safe(None) == ""


def test_format_date_utc_aware():
    assert report.format_date(datetime(2026, 10, 14, 9, 30, tzinfo=timezone.utc)) == "10/14/2026"


def test_format_date_converts_to_utc_across_midnight():
    minus_five = timezone(timedelta(hours=-5))
    assert report.format_date(datetime(2026, 10, 14, 23, 30, tzinfo=minus_five)) == "10/15/2026"


def test_format_date_naive_is_treated_as_utc():
    assert report.format_date(datetime(2026, 1, 5, 0, 0)) == "01/05/2026"


def test_format_date_none_is_empty():
    assert report.format_date(None) == ""


def test_date_entry():
    assert report.date_entry("10/14/2026") == {"date": "10/14/2026", "note": ""}
    assert report.date_entry("10/14/2026", report.NOTE_PEER) == {"date": "10/14/2026", "note": "Peer score"}


def test_note_constants():
    assert (report.NOTE_STAFF, report.NOTE_PEER, report.NOTE_SELF, report.NOTE_AWAITING) == (
        "Staff score", "Peer score", "Self score", "Awaiting grade",
    )
    assert report.DEFAULT_THRESHOLD == 75


def test_build_rows_two_assessments():
    data = {
        "columns": [
            {"competency": "Course", "block_id": "b1", "assessment": "Reflection", "criterion": "Criterion 1"},
            {"competency": "Course", "block_id": "b1", "assessment": "Reflection", "criterion": "Criterion 2"},
            {"competency": "Course", "block_id": "b2", "assessment": "Pitch", "criterion": "Clarity"},
        ],
        "learners": [
            {
                "name": "Syed Sajjad", "username": "sajjad", "email": "s@example.com",
                "cells": [
                    {"percent": 100, "status": STATUS_DEMONSTRATED},
                    {"percent": 0, "status": STATUS_NOT_DEMONSTRATED},
                    None,
                ],
                "dates": {"b1": {"date": "10/20/2026", "note": "Staff score"}},
            },
            {
                "name": "Sidra", "username": "sidra", "email": "sidra@example.com",
                "cells": [None, None, None],
                "dates": {"b2": {"date": "10/23/2026", "note": "Awaiting grade"}},
            },
            {
                "name": "admin", "username": "admin", "email": "admin@example.com",
                "cells": [None, None, None],
                "dates": {},
            },
        ],
    }
    rows = report.build_rows(data)
    assert rows[0] == ["Competency", "", "", "Course", "Course", "Course", "Course", "Course"]
    assert rows[1] == [
        "Assessment Name", "", "", "Reflection", "Reflection", "Reflection", "Pitch", "Pitch",
    ]
    assert rows[2] == [
        "Learner", "Username", "Email", "Date taken", "Criterion 1", "Criterion 2", "Date taken", "Clarity",
    ]
    assert rows[3] == [
        "Syed Sajjad", "sajjad", "s@example.com", "10/20/2026", "100% (Demonstrated)", "0% (Not Demonstrated)", "", "",
    ]
    assert rows[4] == ["Sidra", "sidra", "sidra@example.com", "", "", "", "10/23/2026", ""]
    assert rows[5] == ["admin", "admin", "admin@example.com", "", "", "", "", ""]
    assert len(rows) == 6
    # Notes are on screen only.
    assert not any(note in str(cell) for row in rows for cell in row for note in (
        "Staff score", "Awaiting grade", "Peer score", "Self score",
    ))


def test_build_rows_escapes_formula_characters():
    data = {
        "columns": [{"competency": "=Course", "block_id": "b1", "assessment": "+A", "criterion": "@C"}],
        "learners": [{
            "name": "-Name", "username": "u", "email": "e@x.com", "cells": [None], "dates": {},
        }],
    }
    rows = report.build_rows(data)
    assert rows[0][3:] == ["'=Course", "'=Course"]
    assert rows[1][3:] == ["'+A", "'+A"]
    assert rows[2][3:] == ["Date taken", "'@C"]
    assert rows[3][0] == "'-Name"


def test_build_rows_without_columns_has_only_learner_headings():
    rows = report.build_rows({"columns": [], "learners": []})
    assert rows == [["Competency", "", ""], ["Assessment Name", "", ""], ["Learner", "Username", "Email"]]
