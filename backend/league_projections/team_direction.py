"""The Home playoff card's `team_direction` block (flag `league.direction_card`).

Spec: docs/plans/league-projections/direction-pages/spec.md §5, §7 (D-265,
D-270). Composed on the forecast read from figures the saved run already
holds and from the two feature blocks the same read serves (`max_pf_moves`,
`playoff_targets`). Nothing is saved and the weekly job does no extra work.
Pure: callers check the flags and pass them in; nothing here reads a flag,
the database or the network.

The rule the app follows everywhere: the server decides, the app shows what
it is given. The band, the leading direction and whether each direction is
offered are decided here, never on the device.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import pick_projection, pick_slots

VERSION = 1

# The same file `batch.settings()` reads, under its own key; not imported from
# batch so this module stays free of database and flag imports.
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "league_projections.json"
SETTINGS_KEYS = ("middle_min", "middle_max")

# The stored draft-order answers under which the forecast's max-PF pick order
# is wrong for the league (spec H-5): the projected pick is not served.
NOT_MAXPF = frozenset({"reverse_standings", "lottery_or_other"})
# Saved outlooks that lean to the draft pick whatever the playoff chance (§5.4).
DRAFT_PICK_OUTLOOKS = frozenset({"rebuilder", "jets"})


def parse_settings(raw):
    """Validated `team_direction` settings: 0 < middle_min < middle_max < 1.
    Raises ValueError on a missing, unknown or out-of-range key (booleans are
    never numbers here)."""
    if not isinstance(raw, dict) or set(raw) != set(SETTINGS_KEYS):
        raise ValueError("invalid_team_direction_configuration")
    low, high = raw["middle_min"], raw["middle_max"]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (low, high)) or not 0 < low < high < 1:
        raise ValueError("invalid_team_direction_configuration")
    return {"middle_min": float(low), "middle_max": float(high)}


def settings():
    """The `team_direction` object of `config/league_projections.json`. Read
    only while `league.direction_card` is on; `batch.settings()` never looks
    at it."""
    return parse_settings(json.loads(CONFIG_PATH.read_text()).get("team_direction"))


def band(probability, cuts):
    """§5.2 on the unrounded probability: low below middle_min, middle from
    middle_min up to (not including) middle_max, high from middle_max."""
    if probability < cuts["middle_min"]:
        return "low"
    if probability < cuts["middle_max"]:
        return "middle"
    return "high"


def lean(probability, saved_outlook):
    """§5.4: the draft pick at REBUILDING_MAX (45%) or lower, or with a saved
    Rebuilding / Tanking outlook; otherwise the playoffs. The rule that
    decides which of the two Standings sections starts open."""
    from .recommendation import REBUILDING_MAX
    if probability <= REBUILDING_MAX or saved_outlook in DRAFT_PICK_OUTLOOKS:
        return "draft_pick"
    return "playoffs"


def _option(offered, reason=None):
    return {"offered": bool(offered), "reason": None if offered else reason}


def draft_pick_option(flag_on, block):
    """§5.3 / §7.3 for the draft pick, read from the served `max_pf_moves`
    block. Precedence follows that block's own state order, with ownership
    of the pick placed after the draft-order check (a league that does not
    draft by max PF is the more basic reason)."""
    if not flag_on:
        return _option(False, "feature_off")
    if not isinstance(block, dict):
        return _option(False, "unavailable")
    state = block.get("state")
    if state == "unavailable":
        return _option(False, "unavailable")
    if state in ("season_over", "after_trade_deadline", "draft_order_not_maxpf"):
        return _option(False, state)
    if (block.get("pick_owner") or {}).get("owns_own_pick") is False:
        return _option(False, "pick_owned_elsewhere")
    if state == "no_miss":
        return _option(False, "no_miss")
    if state == "no_moves":
        return _option(False, "none_found")
    if state == "ready":
        return _option(True)
    # An open set: a state this server does not know is passed through, and
    # the app's line for an unknown reason is "Not available right now."
    return _option(False, state if isinstance(state, str) and state else "unavailable")


def playoffs_option(flag_on, block):
    """§5.3 / §7.3 for the playoffs, read from the served `playoff_targets` block."""
    if not flag_on:
        return _option(False, "feature_off")
    if not isinstance(block, dict):
        return _option(False, "unavailable")
    state = block.get("state")
    if state == "unavailable":
        return _option(False, "unavailable")
    if state in ("season_over", "after_trade_deadline", "clinched", "eliminated", "near_certain", "no_sellers"):
        return _option(False, state)
    if state == "no_targets":
        return _option(False, "none_found")
    if state == "ready":
        return _option(True)
    return _option(False, state if isinstance(state, str) and state else "unavailable")


def projected_pick(saved, viewer, team, draft_order):
    """The D-257 label for the viewer's own next-year 1st, over this run: the
    computation behind `max_pf_moves.baseline.label` (`pick_projection.compact`
    → `slot_ranks`, then `pick_slots.slot_suffix`). None when the stored draft
    order is not max PF, or when the run cannot be ranked."""
    if (draft_order or {}).get("rule") in NOT_MAXPF:
        return None
    summary = pick_projection.compact(saved, run_id="team_direction", created_at="")
    slot = summary.slots.get(str(viewer)) if summary else None
    if not slot:
        return None
    owner = team.get("pick_owner_roster_id", viewer)
    names = {t.get("roster_id"): t.get("name") for t in saved.get("teams") or []}
    return {"label": pick_slots.slot_suffix((saved.get("config") or {}).get("draft_round", 1), slot),
            "slot": slot, "owns_own_pick": owner == viewer,
            "owner_name": names.get(owner) or f"Team {owner}"}


def compose(view_state, saved, *, failure_reason=None, saved_outlook=None, draft_order=None,
            cuts=None, max_pf_on=False, max_pf_block=None, targets_on=False, targets_block=None):
    """The `team_direction` block served on the forecast read (spec §7.2).

    view_state      the read's forecast state (`batch.view` after the model check)
    saved           the saved run's parsed `result_json`, or None
    failure_reason  the last attempt's reason (as `recommendation.unusable_reason` takes it)
    saved_outlook   the viewer's saved outlook id, or None
    draft_order     {"rule", "set_at"} from the league row
    cuts            `settings()`
    max_pf_on / targets_on        the two feature flags
    max_pf_block / targets_block  the blocks this same read serves (None when off)
    """
    from . import recommendation
    block = {"version": VERSION, "state": "unavailable", "reason": None, "captured_at": None,
             "playoff_probability": None, "playoff_clinched": False, "playoff_eliminated": False,
             "projected_pick": None, "band": None, "primary": None,
             "options": {"playoffs": playoffs_option(targets_on, targets_block),
                         "draft_pick": draft_pick_option(max_pf_on, max_pf_block)}}
    if view_state == "unsupported_policy":
        saved = None
    team = None
    if isinstance(saved, dict):
        viewer = saved.get("viewer_roster_id")
        team = next((t for t in saved.get("teams") or [] if viewer is not None and t.get("roster_id") == viewer), None)
        block["captured_at"] = saved.get("captured_at")
        if team is not None and recommendation.valid_probability(team.get("playoff_probability")):
            # Served for a run that is not current too: the card shows both
            # figures as "last saved".
            block.update(playoff_probability=team["playoff_probability"],
                         playoff_clinched=bool(team.get("playoff_clinched")),
                         playoff_eliminated=bool(team.get("playoff_eliminated")),
                         projected_pick=projected_pick(saved, viewer, team, draft_order))
    reason = recommendation.unusable_reason(view_state, saved, failure_reason=failure_reason)
    if reason is None and block["playoff_probability"] is None:
        reason = "team_not_found"
    if reason is not None:
        return {**block, "reason": reason}
    probability = block["playoff_probability"]
    options = block["options"]
    first = lean(probability, saved_outlook)
    second = "playoffs" if first == "draft_pick" else "draft_pick"
    primary = first if options[first]["offered"] else second if options[second]["offered"] else None
    return {**block, "state": "ready", "band": band(probability, cuts), "primary": primary}


def read_failed(max_pf_on, targets_on):
    """The block when the read itself failed: unavailable, no figures."""
    return {**compose("no_run", None, max_pf_on=max_pf_on, targets_on=targets_on), "reason": "read_failed"}
