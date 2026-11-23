ORA Criterion Scores Report
===========================

An Open edX plugin that adds a course-wide **Open response scores** table to the
Instructor Dashboard **Open Responses** tab, below the native list of open
response assessments (ORAs). The table shows every enrolled learner (rows)
against the rubric criteria of every ORA in the course (columns), as
percentages. A CSV export of the same table is included. No changes to
``edx-platform`` or ``edx-ora2`` are required.

What the table shows
--------------------

* A heading ``Open response scores for <course name>`` and one line saying what
  the table shows and the Demonstrated threshold.
* One group of columns per ORA, in course outline order. The first column of
  each group is an **Attempt date** column with the date the learner
  submitted (for example ``Oct 20, 2026``, in the viewer's browser time zone).
* Under the date, a note says where the score came from: ``Staff score``,
  ``Peer score`` or ``Self score``. A learner who submitted but has no score yet
  shows ``Awaiting grade`` under the date and one merged ``Awaiting grade`` cell
  across the criteria of that ORA. The note is on screen only and is not in the CSV.
* A learner who has not submitted an ORA gets one merged ``No attempt yet``
  cell across the whole group. Inside a graded ORA, a criterion without a score
  also says ``No attempt yet``.
* Each criterion cell is the percent of the highest option points of that
  criterion (a binary rubric gives 0% or 100%), with the same rounding as the
  Auto Assessments tab in ``tutor-contrib-edl``. **Demonstrated** (green) means
  the percent is at or above the threshold, **Not demonstrated** (orange) means
  below it.
* One toolbar row: search by name, username or email, an **Assessment**
  dropdown (``<name> (X of Y attempted)``, counted over every enrolled learner,
  not only the current page or search), and a **Download CSV** button. **Clear
  filters** shows while a search is active. A line shows ``Showing X of Y
  learners``, and a search without results shows ``No learners match``.
* Paging and page size. Inter is loaded from Google Fonts at runtime and falls
  back to the system font if it is blocked.

How it works
------------

* **Table** — an ``InstructorDashboardRenderStarted`` filter step
  (``ora_criterion_scores.pipeline.AddCriterionScoresPanel``) attaches
  ``static/ora_scores.css`` and ``static/ora_scores.js`` to the Open Responses
  section's fragment, which the dashboard template already emits. The script
  builds the table's host element at the end of the section and loads the data
  the first time the section is shown. It is only added to courses that have at
  least one ORA. Wired automatically by the plugin's settings.
* **Data URL** — staff-only JSON, one page of learners at a time:
  ``/courses/<course_id>/instructor/ora_scores/data`` with the query parameters
  ``page``, ``page_size`` (default 10, maximum 100), ``q`` and ``assessment``
  (a block id). Each ``assessments`` item has ``id``, ``name``, ``attempted``
  (learners with a live submission) and ``total`` (active enrollees), both over
  the whole course. Reverse name ``ora_criterion_scores:data``.
* **CSV URL** — staff-only download of every learner and every ORA (the
  ``tz`` parameter sets the time zone of the dates):
  ``/courses/<course_id>/instructor/ora_scores/csv``, file name
  ``ora_assessment_scores_<course key>_<YYYY-MM-DD>.csv``. Reverse name
  ``ora_criterion_scores:csv``.
* **Data** — enrolled learners come from ``CourseEnrollment``. Submission dates
  come from ``submissions.api.get_all_course_submission_information`` (the
  ``submitted_at`` of the learner's latest live submission for the ORA). The
  selected option per criterion comes from the learner's assessments in
  ``edx-ora2``, read through its public APIs.

CSV layout
----------

Row 1 is ``Competency`` (the course title), row 2 is ``Assessment Name``, row 3
is ``Learner, Username, Email`` followed by the criterion names. Each ORA group
starts with a ``Attempt Date`` column (rows 1 and 2 repeat the competency and the
assessment name above it). Then there is one row per learner. Score cells read
``75% (Demonstrated)``. The date cell is empty when the learner has not
submitted. Dates read like ``Oct 20, 2026`` and statuses like
``40% (Not demonstrated)``.

Settings
--------

``EDL_AUTO_ASSESSMENT_THRESHOLD`` is the percent at or above which a criterion
is Demonstrated. It is the same setting the Auto Assessments tab uses, so both
views agree. If it is absent, 75 is used.

Installation
------------

.. code-block:: bash

    pip install -e /path/to/ora-criterion-scores-report

Then restart the LMS. The plugin is auto-discovered via the ``lms.djangoapp``
entry point — no ``INSTALLED_APPS`` or settings edits needed. In Tutor, add it
to a ``requirements`` build or mount it and ``pip install -e`` in the ``lms``
container.

Tests
-----

The pure logic (``report.py``, the peer-median mapping in ``_matrix.py``) is
covered by dependency-free unit tests. The data, view and pipeline tests need
Django, ``openedx-filters`` and ``edx-opaque-keys``:

.. code-block:: bash

    pip install pytest django openedx-filters edx-opaque-keys
    pytest

``tests/conftest.py`` configures minimal Django settings and stubs the
edx-platform modules (``xmodule``, ``lms``, ``common``, ``submissions``,
``openassessment``, ``openedx.core``) when running outside edx-platform, so the
suite runs standalone.

Scope / assumptions
-------------------

* ``ora_criterion_scores/report.py`` is a copy of the helpers in
  ``tutor-contrib-edl`` (``edl_plugin/auto_assessment_scores/report.py``), and
  ``static/ora_scores.js`` and ``static/ora_scores.css`` are copies of that
  plugin's ``auto_assessments.js`` and ``auto_assessments.css`` with the CSS
  prefix ``edl-ora`` and the global ``EdlOraScores``. Keep the copies in sync.
* Scores reflect the **effective** assessment, mirroring the ORA grade page:
  a staff assessment (including a staff override) wins; otherwise the peer
  median mapped back to the authored option; otherwise the self assessment.
  Criteria with no score on the effective assessment (e.g. a peer step still
  awaiting reviews) show ``No attempt yet``.
* Criteria without options (feedback only) are not columns.
* Peer medians assume the default ``median`` grading strategy. If
  ``ENABLE_ORA_PEER_CONFIGURABLE_GRADING`` is on with a per-block strategy,
  extend ``_effective_selections`` to pass the block's peer requirements.
* Team ORAs are not handled specially: submissions are per team member, as
  returned by ``edx-submissions``.
* The CSV computes the effective scores for every learner, which takes several
  queries per submission.
* Access is limited to users with staff-level access to the course.
