"""
Tests for the instructor-dashboard render-filter step.

Importing ``pipeline`` pulls in Django, openedx-filters, and xmodule, so these
tests skip automatically in an environment without those deps (they run inside
the edx-platform test environment). The step's dependencies (modulestore,
reverse) are monkeypatched so no real course/DB is needed.
"""

import pytest

pipeline = pytest.importorskip(
    "ora_criterion_scores.pipeline",
    reason="requires Django/openedx-filters/xmodule (edx-platform environment)",
)


class _FakeFragment:
    def __init__(self):
        self.scripts = []

    def add_javascript(self, js):
        self.scripts.append(js)


class _FakeBlock:
    def __init__(self, display_name, location, parent="unit"):
        self.display_name = display_name
        self.location = location
        self.parent = parent


class _FakeCourse:
    def __init__(self, course_id="course-v1:Org+C+R"):
        self.id = course_id


def _patch_modulestore(monkeypatch, blocks):
    class _Store:
        def get_items(self, _course_id, qualifiers=None):  # noqa: ARG002
            return blocks
    monkeypatch.setattr(pipeline, "modulestore", lambda: _Store())


def _patch_reverse(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "reverse",
        lambda name, kwargs=None: f"/{name}/{kwargs['usage_id']}",
    )


def _run(context):
    step = pipeline.AddCriterionScoresPanel(
        filter_type="org.openedx.learning.instructor.dashboard.render.started.v1",
        running_pipeline=[],
    )
    return step.run_filter(context=context, template_name="tpl.html")


def test_injects_script_into_ora_section(monkeypatch):
    _patch_modulestore(monkeypatch, [_FakeBlock("Exercise A", "block-a")])
    _patch_reverse(monkeypatch)
    fragment = _FakeFragment()
    context = {
        "course": _FakeCourse(),
        "sections": [{"section_key": "open_response_assessment", "fragment": fragment}],
    }

    result = _run(context)

    assert result["template_name"] == "tpl.html"
    assert len(fragment.scripts) == 1
    assert "Exercise A" in fragment.scripts[0]
    assert "/ora_criterion_scores:report/block-a" in fragment.scripts[0]


def test_noop_when_no_ora_section(monkeypatch):
    _patch_modulestore(monkeypatch, [_FakeBlock("Exercise A", "block-a")])
    _patch_reverse(monkeypatch)
    context = {"course": _FakeCourse(), "sections": [{"section_key": "membership"}]}

    # Should not raise and should leave context untouched.
    result = _run(context)
    assert result["context"] is context


def test_noop_when_no_ora_blocks(monkeypatch):
    _patch_modulestore(monkeypatch, [])
    _patch_reverse(monkeypatch)
    fragment = _FakeFragment()
    context = {
        "course": _FakeCourse(),
        "sections": [{"section_key": "open_response_assessment", "fragment": fragment}],
    }

    _run(context)
    assert fragment.scripts == []


def test_orphaned_blocks_excluded(monkeypatch):
    _patch_modulestore(monkeypatch, [_FakeBlock("Orphan", "block-x", parent=None)])
    _patch_reverse(monkeypatch)
    fragment = _FakeFragment()
    context = {
        "course": _FakeCourse(),
        "sections": [{"section_key": "open_response_assessment", "fragment": fragment}],
    }

    _run(context)
    # Only orphaned blocks -> no items -> no script injected.
    assert fragment.scripts == []


def test_never_raises_on_internal_error(monkeypatch):
    # If modulestore blows up, the dashboard render must still proceed.
    def _boom():
        raise RuntimeError("modulestore down")
    monkeypatch.setattr(pipeline, "modulestore", _boom)
    fragment = _FakeFragment()
    context = {
        "course": _FakeCourse(),
        "sections": [{"section_key": "open_response_assessment", "fragment": fragment}],
    }

    result = _run(context)  # must not raise
    assert result["context"] is context
    assert fragment.scripts == []
