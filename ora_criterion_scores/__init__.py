"""
Open edX plugin: course-wide ORA scores table.

Adds a staff-only table to the Instructor Dashboard "Open Responses" tab, below
the native list. It shows every enrolled learner against the rubric criteria of
every Open Response Assessment in the course, as percentages (Demonstrated or
Not Demonstrated) with the date each learner submitted, plus a CSV export. The
table is loaded from two staff-only JSON and CSV URLs registered by this plugin.
"""

__version__ = "0.3.0"

default_app_config = "ora_criterion_scores.apps.OraCriterionScoresConfig"
