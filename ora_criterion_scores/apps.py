"""App configuration that registers this package as an Open edX LMS plugin."""

from django.apps import AppConfig


class OraCriterionScoresConfig(AppConfig):
    """
    Open edX plugin AppConfig.

    Registers the plugin's URLs (mounted at the site root so the full
    ``/courses/<course_id>/instructor/ora/<usage_id>/criterion_scores`` path
    resolves) and its settings hook (which wires the instructor-dashboard
    render filter). Uses raw string keys instead of the
    ``PluginURLs``/``PluginSettings`` constants so the package imports cleanly
    without a hard dependency on a specific edx-platform module path.
    """

    name = "ora_criterion_scores"
    verbose_name = "ORA Criterion Scores Report"

    plugin_app = {
        "url_config": {
            "lms.djangoapp": {
                "namespace": "ora_criterion_scores",
                "regex": r"",
                "relative_path": "urls",
            },
        },
        "settings_config": {
            "lms.djangoapp": {
                "common": {"relative_path": "settings.common"},
                "production": {"relative_path": "settings.common"},
                "devstack": {"relative_path": "settings.common"},
            },
        },
    }
