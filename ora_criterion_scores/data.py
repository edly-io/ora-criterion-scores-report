"""
Data assembly for the course-wide ORA scores table and CSV.

Builds a matrix of enrolled learners (rows) against the rubric criteria of every
Open Response Assessment in the course (columns). Each cell is the percent of
the highest option points, taken from the option selected on the learner's
*effective* assessment for that criterion. "Effective" mirrors what the ORA
grade page shows: a staff assessment (including a staff override) wins;
otherwise the peer median (mapped back to the authored option label(s));
otherwise the self assessment. Each assessment also carries the learner's
submission date and where the score came from.
"""

from django.conf import settings
from django.contrib.auth.models import User  # pylint: disable=imported-auth-user
from django.db.models import Q

from submissions import api as sub_api

from common.djangoapps.student.models import anonymous_id_for_user

from . import report
from ._matrix import CELL_PEER, CELL_SELF, CELL_STAFF, median_option

_NOTE_BY_SOURCE = {
    CELL_STAFF: report.NOTE_STAFF,
    CELL_PEER: report.NOTE_PEER,
    CELL_SELF: report.NOTE_SELF,
}


def threshold():
    """Return the Demonstrated threshold (percent), shared with the Auto Assessments tab."""
    return getattr(settings, "EDL_AUTO_ASSESSMENT_THRESHOLD", report.DEFAULT_THRESHOLD)


def rubric_criteria(block):
    """Return the block's rubric criteria as dicts sorted by ``order_num``."""
    return sorted(
        block.rubric_criteria or [],
        key=lambda criterion: criterion.get("order_num", 0),
    )


def _selection_from_parts(assessment, source):
    """
    Extract ``{criterion_name: {"label", "points", "source"}}`` from a serialized
    staff or self assessment dict (as returned by the ORA staff/self APIs).
    """
    selections = {}
    for part in assessment.get("parts", []):
        option = part.get("option")
        if not option:
            continue  # feedback-only criterion, no selectable option
        selections[part["criterion"]["name"]] = {
            "label": option.get("label", ""),
            "points": option.get("points"),
            "source": source,
        }
    return selections


def _effective_selections(block, criteria, submission_uuids):
    """
    For each submission uuid, resolve the effective per-criterion selection.

    Precedence per submission (mirrors ORA's grade display):
        staff assessment (incl. override) -> peer median -> self assessment.

    Returns ``{submission_uuid: {criterion_name: {"label", "points"}}}``.
    Submissions/criteria with no effective score are simply absent.
    """
    # Imported here (not at module load) to avoid pulling ORA assessment APIs
    # during Django app startup.
    from openassessment.assessment.api import peer as peer_api
    from openassessment.assessment.api import self as self_api
    from openassessment.assessment.api import staff as staff_api

    steps = block.assessment_steps
    has_peer = "peer-assessment" in steps
    has_self = "self-assessment" in steps

    selected = {}
    for submission_uuid in set(submission_uuids):
        staff_assessment = staff_api.get_latest_staff_assessment(submission_uuid)
        if staff_assessment:
            selected[submission_uuid] = _selection_from_parts(staff_assessment, CELL_STAFF)
            continue

        if has_peer:
            try:
                median_scores = peer_api.get_assessment_scores_with_grading_strategy(
                    submission_uuid, {}
                )
            except Exception:  # pylint: disable=broad-except
                median_scores = {}
            criteria_selections = {}
            for criterion in criteria:
                option = median_option(criterion["options"], median_scores.get(criterion["name"]))
                if option is not None:
                    option["source"] = CELL_PEER
                    criteria_selections[criterion["name"]] = option
            selected[submission_uuid] = criteria_selections
            continue

        if has_self:
            self_assessment = self_api.get_assessment(submission_uuid)
            if self_assessment:
                selected[submission_uuid] = _selection_from_parts(self_assessment, CELL_SELF)

    return selected


def _ora_blocks_in_outline_order(course):
    """Return the course's ``openassessment`` blocks in outline order (depth first)."""
    blocks = []

    def walk(block):
        if block.category == "openassessment":
            blocks.append(block)
        for child in block.get_children():
            walk(child)

    walk(course)
    return blocks


def _normalized_criteria(block):
    """Return the block's criteria as ``{"name", "label", "prompt", "options": [{"label", "points"}]}``."""
    return [
        {
            "name": c["name"],
            "label": c.get("label") or c["name"],
            "prompt": c.get("prompt", ""),
            "options": [
                {"label": o.get("label", ""), "points": o.get("points")}
                for o in c.get("options", [])
            ],
        }
        for c in rubric_criteria(block)
    ]


def get_columns(course_key):
    """
    Return ``(columns, blocks_by_id)`` for the course.

    One column per rubric criterion of each ORA block, in outline order.
    Criteria without options (feedback only) are skipped. Every column carries
    the course display name as its ``competency``.

    ``columns`` is ``[{"competency", "block_id", "assessment", "criterion",
    "criterion_name", "max_points"}]`` where ``max_points`` is the highest
    option points of the criterion. ``blocks_by_id`` maps the block id to the
    block, because ``_effective_selections`` needs its assessment steps.
    """
    # Imported here so the module loads (and unit tests run) outside edx-platform.
    from xmodule.modulestore.django import modulestore  # pylint: disable=import-outside-toplevel

    course = modulestore().get_course(course_key, depth=None)
    if course is None:
        return [], {}

    competency = course.display_name or ""
    columns = []
    blocks_by_id = {}
    for block in _ora_blocks_in_outline_order(course):
        block_id = str(block.location)
        blocks_by_id[block_id] = block
        for criterion in rubric_criteria(block):
            options = criterion.get("options") or []
            if not options:
                continue
            columns.append({
                "competency": competency,
                "block_id": block_id,
                "assessment": block.display_name or "Open Response Assessment",
                "criterion": criterion.get("prompt") or criterion["name"],
                "criterion_name": criterion["name"],
                "max_points": max(option["points"] for option in options),
            })
    return columns, blocks_by_id


def learners_queryset(course_key, query=None):
    """Return active enrollees ordered by username, optionally filtered by name, username or email."""
    users = User.objects.filter(
        courseenrollment__course_id=course_key,
        courseenrollment__is_active=True,
    )
    if query:
        users = users.filter(
            Q(username__icontains=query) | Q(email__icontains=query) | Q(profile__name__icontains=query)
        )
    return users.order_by("username").select_related("profile").distinct()


def get_submissions(course_key, block_ids):
    """
    Return ``{(anonymous_id, block_id): {"uuid", "submitted_at"}}`` for the given ORA blocks.

    One course-wide call to the submissions API. It yields
    ``(student_item, submission, score)`` tuples and leaves out submissions that
    staff deleted ("delete learner state"). When a learner has several
    submissions for one block, the one with the latest ``submitted_at`` is kept.
    """
    latest = {}
    submissions = sub_api.get_all_course_submission_information(str(course_key), "openassessment")
    for student_item, submission, _score in submissions:
        block_id = student_item["item_id"]
        if block_id not in block_ids:
            continue
        key = (student_item["student_id"], block_id)
        if key not in latest or submission["submitted_at"] > latest[key]["submitted_at"]:
            latest[key] = {"uuid": submission["uuid"], "submitted_at": submission["submitted_at"]}
    return latest


def _note_for(selections):
    """Return the note under an assessment date: where the score came from, or awaiting grade."""
    if not selections:
        return report.NOTE_AWAITING
    # All selections of one submission share one source.
    return _NOTE_BY_SOURCE.get(next(iter(selections.values()))["source"], "")


def get_cells(columns, blocks_by_id, users, course_key, current_threshold, tz=None):
    """
    Return ``(cells, dates)`` for ``users``.

    ``cells`` is ``{user.id: [cell | None, ...]}`` with one cell per column
    (``None`` when the learner did not submit or the criterion has no score).
    ``dates`` is ``{user.id: {block_id: {"date", "note"}}}``, with a key only for
    blocks the learner submitted. Effective scores are resolved once per block
    and only for the submissions of ``users``.
    """
    users = list(users)
    cells = {user.id: [None] * len(columns) for user in users}
    dates = {user.id: {} for user in users}
    if not columns or not users:
        return cells, dates

    anon_by_user = {user.id: anonymous_id_for_user(user, course_key) for user in users}
    block_ids = {column["block_id"] for column in columns}
    submissions = get_submissions(course_key, block_ids)

    for block_id in dict.fromkeys(column["block_id"] for column in columns):
        block_submissions = {
            user.id: submissions[(anon_by_user[user.id], block_id)]
            for user in users
            if (anon_by_user[user.id], block_id) in submissions
        }
        if not block_submissions:
            continue
        selected = _effective_selections(
            blocks_by_id[block_id],
            _normalized_criteria(blocks_by_id[block_id]),
            [submission["uuid"] for submission in block_submissions.values()],
        )
        for user_id, submission in block_submissions.items():
            selections = selected.get(submission["uuid"], {})
            dates[user_id][block_id] = report.date_entry(
                report.format_date(submission["submitted_at"], tz), _note_for(selections)
            )
            for index, column in enumerate(columns):
                if column["block_id"] != block_id:
                    continue
                selection = selections.get(column["criterion_name"])
                if selection is None or selection["points"] is None:
                    continue
                cells[user_id][index] = report.make_cell(
                    selection["points"], column["max_points"], current_threshold
                )
    return cells, dates


def learner_row(user, cells, dates):
    """Return the report row for ``user``: ``{"name", "username", "email", "cells", "dates"}``."""
    profile = getattr(user, "profile", None)
    name = profile.name if profile is not None and profile.name else user.username
    return {"name": name, "username": user.username, "email": user.email, "cells": cells, "dates": dates}


def build_report(course_key, tz=None):
    """Return ``{"columns": [...], "learners": [...]}`` for every active enrollee (used by the CSV)."""
    columns, blocks_by_id = get_columns(course_key)
    users = list(learners_queryset(course_key))
    cells, dates = get_cells(columns, blocks_by_id, users, course_key, threshold(), tz)
    return {
        "columns": columns,
        "learners": [learner_row(user, cells[user.id], dates[user.id]) for user in users],
    }
