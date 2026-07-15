ORA Criterion Scores Report
===========================

An Open edX plugin that adds a per-block **Criterion scores** report for Open
Response Assessments (ORAs). For a single ORA it shows a matrix of every
enrolled learner (rows) against the rubric criteria (columns), where each cell
is the rubric option selected on the learner's **staff** assessment
(e.g. *Demonstrated* / *Not yet*). Learners with no submission show an em dash.
A CSV export of the same matrix is included.

The report is launched from a small "Criterion score reports" links panel that
the plugin injects into the Instructor Dashboard **Open Responses** tab. No
changes to ``edx-platform`` or ``edx-ora2`` are required.

How it works
------------

* **Report page** — a standalone, staff-only Django view at
  ``/courses/<course_id>/instructor/ora/<usage_id>/criterion_scores``
  (append ``?format=csv`` for the download). Registered via the plugin's own
  ``urls.py`` (mounted at the site root).
* **Data** — enrolled learners come from ``CourseEnrollment``; the selected
  option per criterion comes from each learner's staff ``Assessment`` in
  ``edx-ora2`` (read through public ``openassessment`` / ``submissions`` APIs).
* **Launch panel** — an ``InstructorDashboardRenderStarted`` filter step
  (``ora_criterion_scores.pipeline.AddCriterionScoresPanel``) attaches a small
  JavaScript snippet to the Open Responses section's fragment, which renders the
  links panel client-side. Wired automatically by the plugin's settings.

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

The core logic (matrix assembly and launch-panel JS in ``_matrix.py``) is
covered by dependency-free unit tests that run with only pytest:

.. code-block:: bash

    pip install pytest
    pytest

The pipeline tests exercise the render-filter step with monkeypatched
dependencies; ``tests/conftest.py`` stubs ``xmodule`` when running outside
edx-platform so they run standalone too.

Scope / assumptions
-------------------

* Cells reflect the **staff** assessment. ORAs graded only by peer/self will
  show blank cells (no staff score). Effective-grade resolution
  (staff-override → staff → peer-median → self) is intentionally out of scope
  for this version.
* Access is limited to users with staff-level access to the course.
