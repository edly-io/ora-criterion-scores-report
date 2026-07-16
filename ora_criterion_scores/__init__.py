"""
Open edX plugin: per-block ORA "Criterion scores" report.

Adds a standalone, staff-only report page that shows, for a single Open
Response Assessment, a matrix of enrolled learners against the rubric
criteria (the selected option per learner per criterion), plus a CSV export.
The report is launched from a small links panel injected into the Instructor
Dashboard "Open Responses" tab.
"""

__version__ = "0.2.0"

default_app_config = "ora_criterion_scores.apps.OraCriterionScoresConfig"
