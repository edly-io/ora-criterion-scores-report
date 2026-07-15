"""
Instructor-dashboard render filter step.

Injects a small "Criterion score reports" links panel into the Open Responses
tab. Implemented as an ``InstructorDashboardRenderStarted`` pipeline step so it
requires no changes to edx-platform or edx-ora2: it attaches JavaScript to the
Open Responses section's fragment, which the dashboard template already emits.
"""

import logging

from django.urls import reverse
from openedx_filters import PipelineStep

from xmodule.modulestore.django import modulestore

from ._matrix import build_items, render_panel_js

log = logging.getLogger(__name__)

ORA_SECTION_KEY = "open_response_assessment"


class AddCriterionScoresPanel(PipelineStep):
    """Attach the criterion-scores links panel to the Open Responses section."""

    def run_filter(self, context, template_name):  # pylint: disable=arguments-differ
        try:
            self._inject(context)
        except Exception:  # pylint: disable=broad-except
            # Never let this break the instructor dashboard.
            log.exception("Failed to inject ORA criterion-scores links panel")
        return {"context": context, "template_name": template_name}

    def _inject(self, context):
        sections = context.get("sections", []) or []
        section = next(
            (s for s in sections if s.get("section_key") == ORA_SECTION_KEY),
            None,
        )
        if not section or "fragment" not in section:
            return

        course = context.get("course")
        if course is None:
            return

        course_id = str(course.id)

        def url_for(location):
            return reverse(
                "ora_criterion_scores:report",
                kwargs={"course_id": course_id, "usage_id": str(location)},
            )

        blocks = modulestore().get_items(course.id, qualifiers={"category": "openassessment"})
        items = build_items(blocks, url_for)
        if not items:
            return

        section["fragment"].add_javascript(render_panel_js(items, ORA_SECTION_KEY))
