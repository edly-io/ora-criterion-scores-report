"""URL routing for the ORA scores table data and CSV (mounted at the site root)."""

from django.urls import re_path

from openedx.core.constants import COURSE_ID_PATTERN

from . import views

app_name = "ora_criterion_scores"

urlpatterns = [
    re_path(
        r"^courses/{course_id}/instructor/ora_scores/data$".format(course_id=COURSE_ID_PATTERN),
        views.ora_scores_data,
        name="data",
    ),
    re_path(
        r"^courses/{course_id}/instructor/ora_scores/csv$".format(course_id=COURSE_ID_PATTERN),
        views.ora_scores_csv,
        name="csv",
    ),
]
