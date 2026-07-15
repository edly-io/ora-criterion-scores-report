"""
Plugin settings.

Wires the ``AddCriterionScoresPanel`` step into the instructor-dashboard render
filter without clobbering any pipeline steps other plugins may have registered
for the same filter.
"""

INSTRUCTOR_DASHBOARD_RENDER_FILTER = "org.openedx.learning.instructor.dashboard.render.started.v1"
PIPELINE_STEP = "ora_criterion_scores.pipeline.AddCriterionScoresPanel"


def plugin_settings(settings):
    """Register the render-filter pipeline step (idempotent, merge-safe)."""
    filters_config = dict(getattr(settings, "OPEN_EDX_FILTERS_CONFIG", {}) or {})
    existing = dict(filters_config.get(INSTRUCTOR_DASHBOARD_RENDER_FILTER, {}))

    pipeline = list(existing.get("pipeline", []))
    if PIPELINE_STEP not in pipeline:
        pipeline.append(PIPELINE_STEP)

    filters_config[INSTRUCTOR_DASHBOARD_RENDER_FILTER] = {
        "fail_silently": existing.get("fail_silently", True),
        "pipeline": pipeline,
    }
    settings.OPEN_EDX_FILTERS_CONFIG = filters_config
