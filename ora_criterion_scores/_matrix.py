"""
Pure, dependency-free helpers for the ORA scores report.

This module intentionally imports nothing from Django, edx-platform, or
edx-ora2 so the peer-median mapping can be unit tested in isolation with only
the standard library.
"""

# Which assessment produced an effective selection (see ``data._effective_selections``).
CELL_STAFF = "staff"   # scored by staff (incl. override)
CELL_PEER = "peer"     # scored by peer median
CELL_SELF = "self"     # scored by self assessment


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
