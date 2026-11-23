"""
Tests for the instructor-dashboard render-filter step.

Importing ``pipeline`` pulls in Django, openedx-filters, and xmodule, so these
tests skip automatically in an environment without those deps (they run inside
the edx-platform test environment). The step's dependencies (modulestore,
reverse, the static reader) are monkeypatched so no real course/DB is needed.
"""

import json

import pytest

pipeline = pytest.importorskip(
    "ora_criterion_scores.pipeline",
    reason="requires Django/openedx-filters/xmodule (edx-platform environment)",
)


_REAL_READ_STATIC = pipeline._read_static  # pylint: disable=protected-access


class _FakeFragment:
    def __init__(self):
        self.css = []
        self.scripts = []

    def add_css(self, css):
        self.css.append(css)

    def add_javascript(self, js):
        self.scripts.append(js)


class _FakeCourse:
    def __init__(self, course_id="course-v1:Org+C+R"):
        self.id = course_id


def _patch_modulestore(monkeypatch, blocks):
    class _Store:
        def get_items(self, _course_id, qualifiers=None):
            assert qualifiers == {"category": "openassessment"}
            return blocks
    monkeypatch.setattr(pipeline, "modulestore", lambda: _Store())


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(
        pipeline, "reverse", lambda name, kwargs=None: "/{}/{}".format(name, kwargs["course_id"]),
    )
    monkeypatch.setattr(pipeline, "_read_static", lambda name: "/* {} */".format(name))
    monkeypatch.setattr(pipeline.data, "threshold", lambda: 75)


def _run(context):
    step = pipeline.AddCriterionScoresPanel(
        filter_type="org.openedx.learning.instructor.dashboard.render.started.v1",
        running_pipeline=[],
    )
    return step.run_filter(context=context, template_name="tpl.html")


def _context(fragment):
    return {
        "course": _FakeCourse(),
        "sections": [{"section_key": "open_response_assessment", "fragment": fragment}],
    }


def test_injects_css_config_and_script_into_ora_section(monkeypatch):
    _patch_modulestore(monkeypatch, [object()])
    fragment = _FakeFragment()

    result = _run(_context(fragment))

    assert result["template_name"] == "tpl.html"
    assert fragment.css == ["/* ora_scores.css */"]
    assert len(fragment.scripts) == 2
    prefix = "window.EdlOraScoresConfig = "
    assert fragment.scripts[0].startswith(prefix) and fragment.scripts[0].endswith(";")
    assert json.loads(fragment.scripts[0][len(prefix):-1]) == {
        "dataUrl": "/ora_criterion_scores:data/course-v1:Org+C+R",
        "csvUrl": "/ora_criterion_scores:csv/course-v1:Org+C+R",
        "threshold": 75,
    }
    assert fragment.scripts[1] == "/* ora_scores.js */"


def test_config_script_comes_before_table_script(monkeypatch):
    _patch_modulestore(monkeypatch, [object()])
    fragment = _FakeFragment()

    _run(_context(fragment))

    assert fragment.scripts[0].startswith("window.EdlOraScoresConfig")
    assert fragment.scripts[1] == "/* ora_scores.js */"


def test_noop_when_no_ora_section(monkeypatch):
    _patch_modulestore(monkeypatch, [object()])
    context = {"course": _FakeCourse(), "sections": [{"section_key": "membership"}]}

    result = _run(context)  # must not raise

    assert result["context"] is context


def test_noop_when_section_has_no_fragment(monkeypatch):
    _patch_modulestore(monkeypatch, [object()])
    context = {"course": _FakeCourse(), "sections": [{"section_key": "open_response_assessment"}]}

    result = _run(context)

    assert result["context"] is context


def test_noop_without_course(monkeypatch):
    _patch_modulestore(monkeypatch, [object()])
    fragment = _FakeFragment()

    _run({"sections": [{"section_key": "open_response_assessment", "fragment": fragment}]})

    assert fragment.css == [] and fragment.scripts == []


def test_noop_when_no_ora_blocks(monkeypatch):
    _patch_modulestore(monkeypatch, [])
    fragment = _FakeFragment()

    _run(_context(fragment))

    assert fragment.css == [] and fragment.scripts == []


def test_never_raises_on_internal_error(monkeypatch):
    # If modulestore blows up, the dashboard render must still proceed.
    def _boom():
        raise RuntimeError("modulestore down")
    monkeypatch.setattr(pipeline, "modulestore", _boom)
    fragment = _FakeFragment()
    context = _context(fragment)

    result = _run(context)  # must not raise

    assert result["context"] is context
    assert fragment.css == [] and fragment.scripts == []


def test_read_static_reads_packaged_files():
    assert "EdlOraScores" in _REAL_READ_STATIC("ora_scores.js")
    assert ".edl-ora" in _REAL_READ_STATIC("ora_scores.css")
