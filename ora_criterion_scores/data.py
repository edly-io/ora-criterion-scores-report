"""
Data assembly for the per-block ORA criterion-scores report.

Builds a matrix of enrolled learners (rows) against rubric criteria (columns),
where each cell reflects the option selected on the learner's *staff*
assessment for that criterion. Learners with no submission are marked as such;
submissions with no staff score on a given criterion are left blank.
"""

from django.contrib.auth.models import User  # pylint: disable=imported-auth-user

from openassessment.assessment.models import Assessment
from openassessment.assessment.score_type_constants import STAFF_TYPE
from submissions import api as sub_api

from common.djangoapps.student.models import anonymous_id_for_user

from ._matrix import (  # noqa: F401  (CELL_* re-exported for views/tests)
    CELL_DEMONSTRATED,
    CELL_NO_SUBMISSION,
    CELL_NOT_YET,
    CELL_UNGRADED,
    assemble_rows,
)


def rubric_criteria(block):
    """Return the block's rubric criteria as dicts sorted by ``order_num``."""
    return sorted(
        block.rubric_criteria or [],
        key=lambda criterion: criterion.get("order_num", 0),
    )


def _selected_options_by_submission(submission_uuids):
    """
    Map each submission uuid to its staff assessment's selected options:

        {submission_uuid: {criterion_name: {"label": str, "points": int}}}

    The most recent staff assessment wins if more than one exists. Submissions
    with no staff assessment are absent from the mapping.
    """
    submission_uuids = list(submission_uuids)
    if not submission_uuids:
        return {}

    # Oldest first so the newest assessment overwrites older entries below.
    assessments = Assessment.objects.filter(
        submission_uuid__in=submission_uuids,
        score_type=STAFF_TYPE,
    ).prefetch_related(
        "parts__criterion",
        "parts__option",
    ).order_by("scored_at")

    selected = {}
    for assessment in assessments:
        criteria = {}
        for part in assessment.parts.all():
            if part.option is None:
                continue  # feedback-only criterion, no selectable option
            criteria[part.criterion.name] = {
                "label": part.option.label,
                "points": part.option.points,
            }
        selected[assessment.submission_uuid] = criteria
    return selected


def build_report(course_key, block):
    """
    Assemble the criterion-scores matrix for ``block``.

    Returns::

        {
            "criteria": [{"name", "label", "prompt"}],
            "rows": [{"name", "username", "cells": [{"state", "label", "points"}]}],
        }
    """
    block_id = str(block.location)
    criteria = rubric_criteria(block)

    # Map every submission in this block to the submitting learner's anon id.
    # get_all_course_submission_information is course-wide; filter to this block.
    anon_id_to_submission = {}
    all_submissions = sub_api.get_all_course_submission_information(str(course_key), "openassessment")
    for student_item, submission, _score in all_submissions:
        if student_item["item_id"] == block_id:
            anon_id_to_submission[student_item["student_id"]] = submission["uuid"]

    selected_options = _selected_options_by_submission(anon_id_to_submission.values())

    enrolled_students = User.objects.filter(
        courseenrollment__course_id=course_key,
        courseenrollment__is_active=1,
    ).order_by("username").select_related("profile")

    learners = []
    for student in enrolled_students:
        anon_id = anonymous_id_for_user(student, course_key)
        profile = getattr(student, "profile", None)
        display_name = profile.name if profile and profile.name else student.username
        learners.append((anon_id, display_name, student.username))

    normalized_criteria = [
        {"name": c["name"], "label": c.get("label") or c["name"], "prompt": c.get("prompt", "")}
        for c in criteria
    ]

    return {
        "criteria": normalized_criteria,
        "rows": assemble_rows(normalized_criteria, learners, anon_id_to_submission, selected_options),
    }
