"""
Pure, dependency-free helpers for the criterion-scores report.

This module intentionally imports nothing from Django, edx-platform, or
edx-ora2 so the core logic (matrix assembly, peer-median mapping, launch-panel
JS) can be unit tested in isolation with only the standard library.
"""

import json

# Cell states consumed by the report template. Graded cells are colored by the
# assessment source that produced the score; the label text (always the authored
# option label) still conveys the actual level.
CELL_NO_SUBMISSION = "no_submission"   # learner never submitted -> em dash
CELL_UNGRADED = "ungraded"             # submitted, but no effective score yet -> en dash
CELL_STAFF = "staff"                   # scored by staff (incl. override)
CELL_PEER = "peer"                     # scored by peer median
CELL_SELF = "self"                     # scored by self assessment

_VALID_SOURCES = frozenset({CELL_STAFF, CELL_PEER, CELL_SELF})


def cell_for(selection):
    """
    Build a single cell from an effective selection, or the ``ungraded`` cell
    when ``selection`` is ``None`` (or carries no points, e.g. a peer step still
    awaiting reviews).

    ``selection`` is ``{"label": str, "points": number, "source": str}`` where
    ``source`` is one of ``staff`` / ``peer`` / ``self``.
    """
    if selection is None:
        return {"state": CELL_UNGRADED, "label": "", "points": None}
    if selection.get("points") is None:
        return {"state": CELL_UNGRADED, "label": selection.get("label", ""), "points": None}
    source = selection.get("source")
    state = source if source in _VALID_SOURCES else CELL_UNGRADED
    return {"state": state, "label": selection["label"], "points": selection["points"]}


def median_option(options, median_score):
    """
    Map a peer *median* score back to the authored rubric option(s).

    Faithful port of edx-ora2's ``grade_mixin._peer_median_option`` so the
    report shows exactly what the ORA grade page would: a single option's label
    when the median matches one option, or the slash-joined labels of the
    bracketing options when the median falls between them. Returns ``None`` when
    there is no median yet (e.g. too few peer reviews) so the cell reads as
    ungraded.

    ``options`` is ``[{"label", "points"}]``; ``median_score`` is a number or
    ``None``.
    """
    if median_score is None or not options:
        return None

    # Sort by label then points (stable), matching ORA, so equal-point options
    # order deterministically.
    ordered = sorted(sorted(options, key=lambda o: o["label"]), key=lambda o: o["points"])

    last_score = None
    collected = []
    for option in ordered:
        current = option["points"]
        if current != last_score:
            if last_score is not None and last_score >= median_score:
                break
            if current <= median_score:
                collected = []
            last_score = current
        collected.append(option)

    if not collected:
        return None
    if len(collected) == 1:
        return {"label": collected[0]["label"], "points": collected[0]["points"]}
    return {"label": " / ".join(o["label"] for o in collected), "points": median_score}


def assemble_rows(criteria, learners, anon_id_to_submission, selected_options):
    """
    Build the report rows (the left-join of learners against their scores).

    Args:
        criteria: list of ``{"name", "label", "prompt", "options"}`` in order.
        learners: iterable of ``(anon_id, display_name, username)``.
        anon_id_to_submission: ``{anon_id: submission_uuid}``.
        selected_options: ``{submission_uuid: {criterion_name: selection}}`` where
            selection is ``{"label", "points", "source"}``.

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


def build_items(blocks, url_for, unit_name_for):
    """
    Build the launch-panel item list from ORA blocks.

    Args:
        blocks: iterable of objects exposing ``display_name``, ``location``,
            and ``parent`` (orphaned blocks with ``parent is None`` are skipped).
        url_for: callable ``location -> report_url``.
        unit_name_for: callable ``block -> parent unit display name`` (may
            return an empty string).

    Returns:
        list of ``{"unit", "title", "url"}``.
    """
    items = []
    for block in blocks:
        if getattr(block, "parent", None) is None:
            continue
        items.append({
            "unit": unit_name_for(block) or "",
            "title": block.display_name or "Open Response Assessment",
            "url": url_for(block.location),
        })
    return items


# Client-side panel builder. Receives a JSON array of {unit, title, url} and the
# id of the Open Responses section, and renders a links panel at the top of it.
# Each row shows the unit name in bold followed by the ORA title. Uses inline
# styles (no stylesheet dependency), builds text via DOM (no HTML injection),
# and is idempotent.
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
      name.style.cssText = 'font-size:14px;';
      if (it.unit) {
        var unit = document.createElement('strong');
        unit.textContent = it.unit;
        name.appendChild(unit);
        name.appendChild(document.createTextNode(' \\u2013 ' + it.title));
      } else {
        name.textContent = it.title;
      }
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
