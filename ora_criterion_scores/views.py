"""
Views for the per-block ORA criterion-scores report.

Renders a standalone, self-contained HTML page (no Mako / no LMS chrome) and a
CSV export of the same matrix. Access is restricted to course staff.
"""

import csv
from importlib.resources import files

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.template import Context, Template
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey

from lms.djangoapps.courseware.courses import get_course_with_access
from xmodule.modulestore.django import modulestore  # pylint: disable=wrong-import-order
from xmodule.modulestore.exceptions import ItemNotFoundError  # pylint: disable=wrong-import-order

from . import data as report_data

_REPORT_TEMPLATE = None


def _report_template():
    """Load and cache the packaged report template as a Django Template."""
    global _REPORT_TEMPLATE  # pylint: disable=global-statement
    if _REPORT_TEMPLATE is None:
        source = (
            files("ora_criterion_scores")
            .joinpath("templates/ora_criterion_scores/report.html")
            .read_text(encoding="utf-8")
        )
        _REPORT_TEMPLATE = Template(source)
    return _REPORT_TEMPLATE


def _get_ora_block(course_key, usage_id):
    """Load and validate the ORA block for ``usage_id`` within ``course_key``."""
    try:
        usage_key = UsageKey.from_string(usage_id).map_into_course(course_key)
    except InvalidKeyError as error:
        raise Http404() from error

    if usage_key.block_type != "openassessment":
        raise Http404()

    try:
        return modulestore().get_item(usage_key)
    except ItemNotFoundError as error:
        raise Http404() from error


def _csv_response(block, report):
    """Return the report matrix as a text/csv attachment."""
    response = HttpResponse(content_type="text/csv")
    filename = "ora_criterion_scores_{}.csv".format(slugify(block.display_name) or "report")
    response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)

    writer = csv.writer(response)
    writer.writerow([_("Learner"), _("Username")] + [c["label"] for c in report["criteria"]])
    for row in report["rows"]:
        cells = [
            "" if cell["state"] == report_data.CELL_NO_SUBMISSION else cell["label"]
            for cell in row["cells"]
        ]
        writer.writerow([row["name"], row["username"]] + cells)
    return response


@login_required
@cache_control(no_cache=True, no_store=True, must_revalidate=True)
def ora_criterion_scores(request, course_id, usage_id):
    """
    Render the criterion-scores report for a single ORA block, or its CSV
    export when ``?format=csv`` is supplied. Restricted to course staff.
    """
    try:
        course_key = CourseKey.from_string(course_id)
    except InvalidKeyError as error:
        raise Http404() from error

    # Raises for users without staff-level access to the course.
    get_course_with_access(request.user, "staff", course_key, depth=None)

    block = _get_ora_block(course_key, usage_id)
    report = report_data.build_report(course_key, block)

    if request.GET.get("format") == "csv":
        return _csv_response(block, report)

    context = Context({
        "block_name": block.display_name,
        "criteria": report["criteria"],
        "rows": report["rows"],
        "csv_download_url": "{}?format=csv".format(request.path),
        "no_submission_state": report_data.CELL_NO_SUBMISSION,
        "ungraded_state": report_data.CELL_UNGRADED,
    })
    return HttpResponse(_report_template().render(context))
