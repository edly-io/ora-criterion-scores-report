"""URL routing for the ORA criterion-scores report (mounted at the site root)."""

from django.conf import settings
from django.urls import re_path

from openedx.core.constants import COURSE_ID_PATTERN

from . import views

app_name = "ora_criterion_scores"

urlpatterns = [
    re_path(
        r"^courses/{course_id}/instructor/ora/{usage_id}/criterion_scores$".format(
            course_id=COURSE_ID_PATTERN,
            usage_id=settings.USAGE_ID_PATTERN,
        ),
        views.ora_criterion_scores,
        name="report",
    ),
]
