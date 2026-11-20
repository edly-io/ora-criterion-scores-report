"""
Test bootstrap.

The plugin imports edx-platform modules (``xmodule``, ``lms``, ``common``,
``submissions``, ``openassessment``, ``openedx.core.constants``) that only exist
inside the LMS. When they are absent (running the suite standalone) install
minimal stubs so the modules import and their logic can be exercised with
monkeypatched dependencies. Django is configured with minimal settings when no
settings are set. In the platform test environment the real modules and
settings are present and the stubs are never used.
"""

import sys
import types


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    parent, _, child = name.rpartition(".")
    if parent and parent in sys.modules:
        setattr(sys.modules[parent], child, module)
    return module


def _configure_django():
    try:
        from django.conf import settings
    except ImportError:
        return
    if settings.configured:
        return
    settings.configure(
        INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        SECRET_KEY="insecure-secret-key",
        USE_TZ=True,
        TIME_ZONE="UTC",
    )
    import django
    django.setup()


def _install_platform_stubs():
    try:
        import lms.djangoapps.courseware.courses  # noqa: F401  pylint: disable=unused-import
        return
    except Exception:  # pylint: disable=broad-except
        pass

    for name in (
        "xmodule", "xmodule.modulestore",
        "lms", "lms.djangoapps", "lms.djangoapps.courseware",
        "common", "common.djangoapps", "common.djangoapps.student",
        "openedx", "openedx.core",
        "openassessment", "openassessment.assessment", "openassessment.assessment.api",
    ):
        _stub(name)

    _stub("xmodule.modulestore.django", modulestore=lambda: None)  # overridden per test via monkeypatch
    _stub("lms.djangoapps.courseware.courses", get_course_with_access=lambda *args, **kwargs: None)
    _stub("common.djangoapps.student.models", anonymous_id_for_user=lambda user, course_key: "anon-%s" % user.id)
    _stub("submissions", api=_stub(
        "submissions.api", get_all_course_submission_information=lambda course_id, item_type: iter(()),
    ))
    _stub("openedx.core.constants", COURSE_ID_PATTERN=r"(?P<course_id>[^/+]+(/|\+)[^/+]+(/|\+)[^/?]+)")
    _stub("openassessment.assessment.api.staff", get_latest_staff_assessment=lambda submission_uuid: None)
    _stub(
        "openassessment.assessment.api.peer",
        get_assessment_scores_with_grading_strategy=lambda submission_uuid, requirements: {},
    )
    _stub("openassessment.assessment.api.self", get_assessment=lambda submission_uuid: None)


_configure_django()
_install_platform_stubs()
