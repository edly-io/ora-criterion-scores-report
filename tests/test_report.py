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
    assert report.cell_text(report.make_cell(2, 4, 75)) == "50% (Not demonstrated)"


def test_status_labels_are_sentence_case():
    assert report.STATUS_LABELS == {STATUS_DEMONSTRATED: "Demonstrated", STATUS_NOT_DEMONSTRATED: "Not demonstrated"}


def test_csv_cell_text_uses_sentence_case_label():
    assert report.cell_text({"percent": 40, "status": STATUS_NOT_DEMONSTRATED}) == "40% (Not demonstrated)"
    assert "Not Demonstrated" not in report.cell_text({"percent": 40, "status": STATUS_NOT_DEMONSTRATED})


def test_safe_prefixes_formula_characters():
    for char in ("=", "+", "-", "@", "\t", "\r"):
        assert report.safe(char + "cmd") == "'" + char + "cmd"
    assert report.safe("Ayesha") == "Ayesha"
    assert report.safe(None) == ""


def test_format_date_utc_aware():
    assert report.format_date(datetime(2026, 10, 14, 9, 30, tzinfo=timezone.utc)) == "Oct 14, 2026"


def test_format_date_converts_to_utc_across_midnight():
    minus_five = timezone(timedelta(hours=-5))
    assert report.format_date(datetime(2026, 10, 14, 23, 30, tzinfo=minus_five)) == "Oct 15, 2026"


def test_format_date_naive_is_treated_as_utc():
    assert report.format_date(datetime(2026, 1, 5, 0, 0)) == "Jan 5, 2026"


def test_format_date_in_browser_zone_moves_the_day():
    late_utc = datetime(2026, 10, 15, 3, 30, tzinfo=timezone.utc)
    assert report.format_date(late_utc, "UTC") == "Oct 15, 2026"
    assert report.format_date(late_utc, "Pacific/Honolulu") == "Oct 14, 2026"
    assert report.format_date(late_utc, "Asia/Karachi") == "Oct 15, 2026"
    assert report.format_date(datetime(2026, 10, 15, 20, 0, tzinfo=timezone.utc), "Asia/Karachi") == "Oct 16, 2026"


def test_format_date_naive_value_with_zone_is_read_as_utc():
    assert report.format_date(datetime(2026, 10, 15, 3, 30), "Pacific/Honolulu") == "Oct 14, 2026"


def test_format_date_unknown_or_empty_zone_falls_back_to_utc():
    value = datetime(2026, 10, 15, 3, 30, tzinfo=timezone.utc)
    for bad in (None, "", "Not/AZone", "../etc/passwd", "x" * 200, 5):
        assert report.format_date(value, bad) == "Oct 15, 2026"


def test_format_date_has_no_leading_zero_on_the_day():
    assert report.format_date(datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)) == "Oct 5, 2026"
    assert report.format_date(datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)) == "Oct 20, 2026"


def test_format_date_december_and_all_month_names():
    assert report.format_date(datetime(2026, 12, 31, 9, 0, tzinfo=timezone.utc)) == "Dec 31, 2026"
    names = [report.format_date(datetime(2026, month, 1, 12, 0, tzinfo=timezone.utc)).split()[0]
             for month in range(1, 13)]
    assert names == ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def test_format_date_zone_can_move_the_year():
    new_year_utc = datetime(2027, 1, 1, 2, 0, tzinfo=timezone.utc)
    assert report.format_date(new_year_utc, "Pacific/Honolulu") == "Dec 31, 2026"


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
        "Learner", "Username", "Email", "Attempt Date", "Criterion 1", "Criterion 2", "Attempt Date", "Clarity",
    ]
    assert rows[3] == [
        "Syed Sajjad", "sajjad", "s@example.com", "10/20/2026", "100% (Demonstrated)", "0% (Not demonstrated)", "", "",
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
    assert rows[2][3:] == ["Attempt Date", "'@C"]
    assert rows[3][0] == "'-Name"


def test_build_rows_without_columns_has_only_learner_headings():
    rows = report.build_rows({"columns": [], "learners": []})
    assert rows == [["Competency", "", ""], ["Assessment Name", "", ""], ["Learner", "Username", "Email"]]
