"""
Pure, dependency-free helpers for the criterion-scores report.

This module intentionally imports nothing from Django, edx-platform, or
edx-ora2 so the core logic (matrix assembly, launch-panel JS) can be unit
tested in isolation with only the standard library.
"""

import json

# Cell states consumed by the report template.
CELL_NO_SUBMISSION = "no_submission"   # learner never submitted -> em dash
CELL_UNGRADED = "ungraded"             # submitted, but no staff score on this criterion
CELL_DEMONSTRATED = "demonstrated"     # selected option has points > 0
CELL_NOT_YET = "not_yet"               # selected option has points == 0


def cell_for(selection):
    """
    Build a single cell from a selected option, or the ``ungraded`` cell when
    ``selection`` is ``None``.

    ``selection`` is ``{"label": str, "points": int}``.
    """
    if selection is None:
        return {"state": CELL_UNGRADED, "label": "", "points": None}
    points = selection["points"]
    state = CELL_DEMONSTRATED if points > 0 else CELL_NOT_YET
    return {"state": state, "label": selection["label"], "points": points}


def assemble_rows(criteria, learners, anon_id_to_submission, selected_options):
    """
    Build the report rows (the left-join of learners against their scores).

    Args:
        criteria: list of ``{"name", "label", "prompt"}`` in display order.
        learners: iterable of ``(anon_id, display_name, username)``.
        anon_id_to_submission: ``{anon_id: submission_uuid}``.
        selected_options: ``{submission_uuid: {criterion_name: {"label", "points"}}}``.

    Returns:
        list of ``{"name", "username", "cells": [cell, ...]}`` with one cell per
        criterion, in the same order as ``criteria``.
    """
    rows = []
    for anon_id, display_name, username in learners:
        submission_uuid = anon_id_to_submission.get(anon_id)
        if submission_uuid is None:
            cells = [
                {"state": CELL_NO_SUBMISSION, "label": "", "points": None}
                for _criterion in criteria
            ]
        else:
            selections = selected_options.get(submission_uuid, {})
            cells = [cell_for(selections.get(criterion["name"])) for criterion in criteria]
        rows.append({"name": display_name, "username": username, "cells": cells})
    return rows


def build_items(blocks, url_for):
    """
    Build the launch-panel item list from ORA blocks.

    Args:
        blocks: iterable of objects exposing ``display_name``, ``location``,
            and ``parent`` (orphaned blocks with ``parent is None`` are skipped).
        url_for: callable ``location -> report_url``.

    Returns:
        list of ``{"name", "url"}``.
    """
    items = []
    for block in blocks:
        if getattr(block, "parent", None) is None:
            continue
        items.append({
            "name": block.display_name or "Open Response Assessment",
            "url": url_for(block.location),
        })
    return items


# Client-side panel builder. Receives a JSON array of {name, url} and the id of
# the Open Responses section, and renders a links panel at the top of it. Uses
# inline styles (no stylesheet dependency) and is idempotent.
PANEL_JS_TEMPLATE = """
(function () {
  var items = %s;
  var sectionId = %s;
  function build() {
    var host = document.getElementById(sectionId);
    if (!host || host.querySelector('.ora-cs-panel')) { return; }
    var panel = document.createElement('div');
    panel.className = 'ora-cs-panel';
    panel.style.cssText = 'border:1px solid #c9d6e5;border-radius:8px;padding:16px 20px;margin:16px 0;background:#fff;';
    var title = document.createElement('div');
    title.textContent = 'Criterion score reports';
    title.style.cssText = 'font-size:16px;font-weight:600;margin-bottom:4px;';
    panel.appendChild(title);
    var sub = document.createElement('div');
    sub.textContent = 'Per-learner rubric breakdown for each assessment. Opens in a new tab.';
    sub.style.cssText = 'font-size:13px;color:#5f5f5f;margin-bottom:12px;';
    panel.appendChild(sub);
    items.forEach(function (it) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-top:1px solid #eee;';
      var name = document.createElement('span');
      name.textContent = it.name;
      name.style.cssText = 'font-size:14px;';
      var link = document.createElement('a');
      link.textContent = 'View criterion scores';
      link.href = it.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.style.cssText = 'font-size:13px;white-space:nowrap;';
      row.appendChild(name);
      row.appendChild(link);
      panel.appendChild(row);
    });
    var header = host.querySelector('h3');
    if (header && header.nextSibling) {
      host.insertBefore(panel, header.nextSibling);
    } else {
      host.appendChild(panel);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();
"""


def render_panel_js(items, section_id):
    """Render the launch-panel JavaScript for ``items`` targeting ``section_id``."""
    return PANEL_JS_TEMPLATE % (json.dumps(items), json.dumps(section_id))
