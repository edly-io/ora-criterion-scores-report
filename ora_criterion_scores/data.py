"""
Data assembly for the per-block ORA criterion-scores report.

Builds a matrix of enrolled learners (rows) against rubric criteria (columns),
where each cell reflects the option selected on the learner's *effective*
assessment for that criterion. "Effective" mirrors what the ORA grade page
shows: a staff assessment (including a staff override) wins; otherwise the peer
median (mapped back to the authored option label(s)); otherwise the self
assessment. Learners with no submission are marked as such; criteria with no
score on the effective assessment are left blank.
"""

import logging

from django.contrib.auth.models import User  # pylint: disable=imported-auth-user

from submissions import api as sub_api

from common.djangoapps.student.models import anonymous_id_for_user

from ._matrix import (  # noqa: F401  (CELL_* re-exported for views/tests)
    CELL_NO_SUBMISSION,
    CELL_PEER,
    CELL_SELF,
    CELL_STAFF,
    CELL_UNGRADED,
    assemble_rows,
    median_option,
)

log = logging.getLogger(__name__)


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

    normalized_criteria = [
        {
            "name": c["name"],
            "label": c.get("label") or c["name"],
            "prompt": c.get("prompt", ""),
            "options": [
                {"label": o.get("label", ""), "points": o.get("points")}
                for o in c.get("options", [])
            ],
        }
        for c in criteria
    ]

    selected_options = _effective_selections(
        block, normalized_criteria, anon_id_to_submission.values()
    )

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

    return {
        "criteria": normalized_criteria,
        "rows": assemble_rows(normalized_criteria, learners, anon_id_to_submission, selected_options),
    }
