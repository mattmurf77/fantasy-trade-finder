"""Private, paired owner generation. No sessions, organic jobs or exposure writes.

Provider ownership is resolved once. Both models consume that same detached input
and the same captured publication gates; only the version selector differs.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from .blind_grading import Catalog, GradingError

VERSIONS = ("owner-v2-bilateral-2", "owner-v2-bilateral-3")
@lru_cache(maxsize=1)
def code_revision():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted([*root.rglob("*.py"), root / "tier_config.json"]):
        if "tests" not in path.relative_to(root).parts:
            digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _semantic_rows(rows):
    return [{k: v for k, v in row.items() if k not in
             {"synced_at", "updated_at", "created_at", "id"}} for row in
            sorted(rows, key=lambda r: str(r.get("pick_id") or ""))]


def _json(value):
    from .server import _owner_canonical
    return json.loads(json.dumps(_owner_canonical(value), sort_keys=True, default=str))


def _hash(value):
    return hashlib.sha256(json.dumps(_json(value), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _input_identity(user_id, league_id, captured_metadata_ids=()):
    """Persisted/cache-only freshness check; never fetch a provider on an open."""
    from . import server as s, database as db, trade_service as ts
    fmt = db.get_league_scoring(league_id)
    members = db.load_league_members(league_id)
    ids = sorted({user_id, *(str(m["user_id"]) for m in members)})
    pool = s.g_universal_by_format.get(fmt) or {}
    # Hash the actual pool facts, not an object address or a process-local token.
    players = pool.get("players") or []
    if isinstance(players, dict):
        players = players.values()
    facts = [{k: getattr(p, k, None) for k in
              ("id", "age", "position", "team", "search_rank", "pick_value", "injury_status")}
             for p in players]
    metadata = s._load_sleeper_cache() or {}
    held = {str(pid) for member in members for pid in member.get("player_ids", [])}
    held.update(map(str, captured_metadata_ids))
    evidence = pool.get("input_evidence")
    player_map = {p.id: p for p in players}
    provenance = evidence.capture(player_map).as_dict(player_map) if evidence else None
    state = db.get_league_roster_state(league_id) or {}
    member_facts = sorted(({"user_id": str(m["user_id"]),
                           "roster": sorted(map(str, m.get("player_ids") or []))}
                          for m in members), key=lambda m: m["user_id"])
    from .calibration_provider_capture import binding_identity
    return _hash(dict(code_revision=code_revision(), format=fmt, members=member_facts,
        provider_binding=binding_identity(user_id, league_id),
        roster_state={k: state.get(k) for k in ("roster_fp", "status")},
        availability={p: {k: (metadata.get(p) or {}).get(k) for k in
                          ("injury_status", "fantasy_positions", "position", "player_id", "active")} for p in held | set(player_map)},
        slot_order=s._league_slot_order(league_id), provenance=provenance,
        prefs=s.load_league_preferences_bulk(ids, league_id),
        asset_prefs={u: s.load_asset_preferences(user_id=u, league_id=league_id) for u in ids},
        rankings=s.load_member_rankings(league_id, exclude_user_id=user_id, scoring_format=fmt),
        overrides=s.load_tier_overrides(user_id=user_id, scoring_format=fmt),
        override_stamps=s.load_tier_override_stamps(user_id=user_id, scoring_format=fmt),
        swipes=s.load_swipe_decisions(user_id=user_id, scoring_format=fmt),
        picks=_semantic_rows(s.load_draft_picks(league_id=league_id, source=s._pick_read_source())),
        suppressions=_suppression_state(s, user_id, league_id, include_clock=False),
        draft=s.get_league_draft_context(league_id),
        dispositions=s._load_trade_disposition_keys(user_id, league_id),
        exclusions=s._load_presentment_exclusions(user_id, league_id),
        config=dict(ts._cfg), flags=_flags(s), players=sorted(facts, key=lambda p: p["id"]),
        seed=pool.get("seed") or pool.get("seed_ratings") or {}))


def _flags(s):
    return {name: bool(getattr(s.FLAGS, name, False)) for name in
            ("trade_preference_lists", "trade_avoid_positions", "trade_presentment_rules",
             "trade_picks_in_pool", "trade_outlook_seed", "deck_quality_filters",
             "deck_fatigue", "trade_roster_protection", "trade_mutual_benefit_v1", "picks_slot_labels")}


def is_current(source, *, user_id, league_user_id, league_id):
    try:
        from . import server as s
        # A restart clears process pools; warm before comparing semantic
        # inputs instead of retiring every durable prepared exercise as stale.
        from . import database as db
        fmt = db.get_league_scoring(league_id)
        if not (s.g_universal_by_format.get(fmt) or {}).get("players"):
            pool, seed = s._get_universal_pool(fmt)
            if not pool or not seed:
                raise GradingError("comparison_inputs_unavailable", 503)
        # Cache absence after a restart is not a changed provider rule.
        # Compare a known observation to the actual captured rules, rather
        # than hashing whether a process happened to have warmed its cache.
        hit = s._FA_LEAGUE_META_CACHE.get(league_id)
        if (source.get("platform", "sleeper") == "sleeper" and hit and hit[0] > datetime.fromisoformat(source["captured_at"]).timestamp()
                and source.get("provider_rules") is not None):
            if _provider_rules(hit[1]) != source["provider_rules"]:
                return False
        return (source["account_user_id"] == user_id
                and source["league_user_id"] == league_user_id
                and source["league_id"] == league_id
                and source["input_identity"] == _input_identity(user_id, league_id, source.get("captured_metadata_ids") or ()))
    except (KeyError, TypeError, ValueError):
        return False


def _provider_rules(meta):
    return _json({k: meta.get(k) for k in
                  ("roster_positions", "settings", "scoring_settings", "season", "total_rosters")})


def _suppression_state(s, user_id, league_id, *, include_clock=True):
    rows = s.load_deck_suppressions(user_id, league_id)
    passed = {str(r["id"]): s.load_deck_pass_after(user_id, league_id,
              r["retest_trade_hash"], r["retested_at"]) for r in rows
              if r.get("retested_at") and r.get("retest_trade_hash")}
    return {"rows": rows, "passed_at": passed,
            "band": s._deck_cfg("fatigue_decline_value_band", .10),
            "window_days": s._deck_cfg("fatigue_decline_suppress_days", 30),
            **({"now": datetime.now(timezone.utc).isoformat()} if include_clock else {})}


@dataclass
class CapturedComparison:
    owner_context: dict
    catalog: Catalog
    source: dict
    roster_context: object
    significance: tuple
    quality_enabled: bool

    def run_arm(self, version):
        from . import server as s, trade_service as ts, bakeoff_runner as bakeoff
        from . import trade_bilateral_presentment, deck_quality
        if version not in VERSIONS:
            raise ValueError("unsupported calibration version")
        context = copy.deepcopy(self.owner_context)
        context["config"]["owner_outlook_evidence_enabled"] = float(version == VERSIONS[1])
        if version == VERSIONS[0]:
            context.pop("input_evidence", None)
        with ts._cfg_override(context["config"]):
            cards, report = bakeoff.owner_generator(context["config"])(**context)
            native = len(cards)
            from .calibration_fixed_lineup import validate_legs, annotate as annotate_fixed
            fixed_lineup = self.source.get("fixed_lineup") or {}
            validate_legs(cards, fixed_lineup, self.roster_context)
            suppression = self.source.get("suppression")
            if suppression is not None:
                cards, _, _ = s._apply_deck_suppression(cards,
                    user_id=self.source["account_user_id"], league_id=self.source["league_id"],
                    seed_map=context["seed_elo"], mutation_sink=[], frozen_state=suppression)
            suppressed = len(cards)
            cards = s._owner_cards_valid(cards, context)
            validated = len(cards)
            # The shared roster gate sorts; restore the native order before
            # owner presentment just as the production owner pipeline does.
            original = list(cards)
            cards, _, roster_diag = s._evaluate_deck_rosters(
                cards, copy.deepcopy(self.roster_context), enforce=True, require_mutual=False)
            retained = {id(card) for card in cards}
            cards = [card for card in original if id(card) in retained]
            del original, retained
            from .calibration_roster_coverage import annotate_coverage
            annotate_coverage(cards, self.source.get("unpriced_occupancy") or {}, self.roster_context)
            annotate_fixed(cards, fixed_lineup, self.roster_context.viewer_id)
            roster_count = len(cards)
            cards, _, significance_diag = s._evaluate_trade_significance(
                cards, capture=self.significance, players=context["players"],
                user_elo=context["user_elo"], seed_elo=context["seed_elo"],
                scoring_format=context["scoring_format"], user_sources=context["user_sources"])
            significant = len(cards)
            pass_keys = {(frozenset(g), frozenset(r)) for g, r in self.source.get("pass_keys", [])}
            cards = [c for c in cards if (frozenset(c.give_player_ids),
                     frozenset(c.receive_player_ids)) not in pass_keys]
            cards, presentment = trade_bilateral_presentment.present(cards, generator_version=version)
            quality_diag = {}
            if self.quality_enabled:
                rosters = {m.user_id: list(m.roster) for m in context["league"].members}
                rosters[context["user_id"]] = list(context["user_roster"])
                seed, players = context["seed_elo"], context["players"]
                from .calibration_native_lineup import max_positions
                cards, quality_diag = deck_quality.filter_deck(cards,
                    viewer_id=context["user_id"],
                    market=lambda pid: ts.elo_to_value(seed[pid]) if pid in seed else None,
                    position=lambda pid: getattr(players.get(pid), "position", None),
                    rosters=rosters, lineup_slots=list(self.roster_context.rules.slots),
                    native_caps=({p:n for p,n in max_positions(self.roster_context.rules.native_bounds, len(self.roster_context.rules.slots)).items() if p in ('QB','TE')}
                                 if getattr(self.roster_context.rules,'native_bounds',()) else None))
            return cards, {"model_version": version, "native_count": native,
                "post_suppression_count": suppressed, "validated_count": validated, "roster_count": roster_count,
                "significant_count": significant, "final_count": len(cards),
                "generator": report.as_dict(), "roster": roster_diag,
                "significance": significance_diag, "presentment": presentment,
                "quality": quality_diag}


def capture(*, user_id, league_user_id, league_id):
    from . import server as s, database as db, trade_service as ts
    from .session_input import resolve_session_input, SessionInputError
    from .trade_input_evidence import request_evidence
    from .trade_gen_outlook_evidence import INPUT_VERSION
    from .trade_roster_adapter import build_context
    from .trade_roster import Asset

    raw = {}
    linked = None
    if db.is_linked_platform_league(league_id):
        # An imported flat member cache can be stale. The linked reader first
        # validates the account's persisted binding, then its fresh native seat.
        from .calibration_provider_capture import capture_linked
        linked = capture_linked(user_id=user_id, league_id=league_id)
        resolved = linked.resolved
        raw["rosters"] = linked.rosters
    else:
        try:
            resolved = resolve_session_input({"user_id": user_id, "verified": True},
                {"user_id": user_id, "league_id": league_id}, s._sleeper_get, raw=raw)
        except SessionInputError as exc:
            raise GradingError(exc.error, exc.status) from exc
    seat = str(resolved["league_user_id"])
    if (league_user_id is not None and seat != str(league_user_id)
            and not (linked and linked.platform == 'mfl' and str(league_user_id) == str(user_id)
                     and linked.provenance.get('ownership_basis') == 'current_provider_owner')):
        raise GradingError("league_seat_changed", 409)
    # Observe registered identities BEFORE any private board/preferences read.
    # Persistence locks these accounts and rejects deletion/re-creation; league
    # opponents who never had a Fleeced account remain valid public members.
    participant_ids = {str(user_id), seat, *(str(m["user_id"]) for m in resolved["opponent_rosters"])}
    with db.engine.connect() as conn:
        registered = dict(conn.execute(db.select(db.users_table.c.sleeper_user_id,
            db.users_table.c.created_at).where(db.users_table.c.sleeper_user_id.in_(participant_ids))).tuples().all())
    slots = linked.slots if linked else raw["meta"].get("roster_positions") or []
    starters = [slot for slot in slots if slot not in ("BN", "IR", "TAXI")]
    if not starters:
        raise GradingError("lineup_unavailable", 409)
    fmt = db.get_league_scoring(league_id)
    # Refresh pick ownership from the SAME provider roster snapshot. No
    # synthetic picks and no organic jobs/session tokens are created here.
    refreshed_picks = None
    include_picks = bool(s.FLAGS.trade_picks_in_pool)
    if linked and linked.platform == "espn":
        from types import SimpleNamespace
        include_picks = s._owned_picks_available(league_id, SimpleNamespace(platform="espn"))
    if include_picks and linked and linked.platform == "mfl":
        refreshed_picks = s._sync_mfl_owned_picks(league_id, source_picks=linked.future_picks,
            expected_binding=linked.provenance["binding"]["binding"])
    if include_picks and not linked:
        names = {str(m["user_id"]): m.get("username") or "" for m in resolved["opponent_rosters"]}
        # A co-owner's display name must not overwrite the primary owner's.
        names.update({str(m["user_id"]): m.get("username") or m.get("display_name") or ""
                      for m in db.load_league_members(league_id) if str(m["user_id"]) == seat})
        traded = s._sleeper_get(f"https://api.sleeper.app/v1/league/{league_id}/traded_picks")
        drafts = s._sleeper_get(f"https://api.sleeper.app/v1/league/{league_id}/drafts")
        if not isinstance(traded, list) or not isinstance(drafts, list) or not drafts:
            raise GradingError("pick_ownership_unavailable", 409)
        refreshed_picks = s._sync_sleeper_owned_picks(league_id, names, fmt,
                rosters=raw["rosters"], meta=raw["meta"], traded_picks=traded, drafts=drafts)
        if refreshed_picks is None:
            raise GradingError("pick_ownership_unavailable", 409)
    s._get_universal_pool(fmt)  # Warm before the consistency window.
    captured_metadata_ids = sorted({str(pid) for row in raw["rosters"] for pid in row.get("players") or []})
    identity_before = _input_identity(user_id, league_id, captured_metadata_ids)
    fmt = db.get_league_scoring(league_id)
    pool, seed = s._get_universal_pool(fmt)
    service = s._extension_ranking_services(user_id, strict=True)[fmt]
    seed = dict(seed)
    players = {p.id: p for p in pool}
    user_elo = {r.player.id: r.elo for r in service.get_rankings(position=None).rankings}
    members = [ts.LeagueMember(user_id=str(m["user_id"]), username="",
                roster=list(m["player_ids"]), elo_ratings={}) for m in resolved["opponent_rosters"]]
    league = ts.League(league_id=league_id, name="", platform=resolved["platform"], members=members)
    roster = list(resolved["user_player_ids"])
    if not roster or not members:
        raise GradingError("league_rosters_unavailable", 409)
    cfg, flags = dict(ts._cfg), _flags(s)
    cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.,
               owner_outlook_evidence_enabled=1.)
    # Read inside the checked window. A concurrent sync must not attach a
    # new revision to the earlier refresh return value.
    pick_source = "platform" if linked and linked.platform == "mfl" else s._pick_read_source()
    picks = (s.load_draft_picks(league_id=league_id, source=pick_source) or []) if (not linked or include_picks) else []
    if not linked and include_picks:
        from .calibration_provider_capture import pick_ownership
        platform_rows = [p for p in picks if s._pick_provenance(p) == "platform"]
        if pick_ownership(platform_rows) != pick_ownership(refreshed_picks):
            raise GradingError("provider_pick_ownership_changed", 409)
    if linked and linked.platform == "mfl" and include_picks:
        # Compare actual ownership to the same raw provider bundle, even if
        # a concurrent writer changed the cache before identity_before.
        linked.validate_owned_picks(picks)
    if linked and linked.platform == "espn":
        picks = [p for p in picks if s._pick_provenance(p) == "user"]
    draft = s.get_league_draft_context(league_id) or {}
    with ts._cfg_override(cfg):
        if include_picks:
            seed, roster, _ = s._inject_owned_picks(league_id=league_id, scoring_format=fmt,
                trade_service=ts.TradeService(players=dict(players)), players_dict=players,
                seed_map=seed, user_elo=user_elo, user_id=seat, user_roster=roster,
                league=league, picks=picks)
        prefs = dict(s.load_league_preference(user_id=user_id, league_id=league_id) or {})
        if flags["trade_preference_lists"]:
            prefs.update(s.load_asset_preferences(user_id=user_id, league_id=league_id))
        prefs["avoid_positions"] = (prefs.get("avoid_positions") or []) if flags["trade_avoid_positions"] else []
        prefs["acquire_positions"] = [p for p in (prefs.get("acquire_positions") or [])
                                       if p not in prefs["avoid_positions"]]
        sess = {"user_id": user_id, "league_user_id": seat, "user_roster": roster, "players": pool}
        if not prefs.get("team_outlook"):
            prefs["inferred_outlook"] = s._infer_user_outlook(seat, league_id, sess, league, picks)[0]
        context = s._owner_generation_context(sess=sess, service=service, league=league,
            players=players, seed_map=seed, user_elo=user_elo, user_roster=roster,
            scoring_format=fmt, fairness_threshold=.75, captured_config=cfg,
            viewer_preferences=prefs, job_draft_picks=lambda: picks, job_draft_context=lambda: draft,
            pinned_give_players=None, pinned_receive_players=None, opponent_user_id=None, trade_intent=None)
        # Rankings/preferences are account scoped; ownership is seat scoped.
        # Do not substitute the primary owner's private board for a co-owner's.
        context["user_id"] = seat
        context["manager_preferences"][seat] = context["manager_preferences"].pop(user_id)
        if user_id in context["inferred_outlooks"]:
            context["inferred_outlooks"][seat] = context["inferred_outlooks"].pop(user_id)
        capacity = linked.capacity if linked else sum(slot not in ("IR", "TAXI") for slot in slots)
        for uid, pref in context["manager_preferences"].items():
            pref.update(starter_slots=starters, lineup_source="observed", roster_capacity=capacity)
            if linked and linked.native_bounds:
                from .calibration_native_lineup import templates
                pref['starter_slots'] = list(templates(linked.native_bounds, sum(s in ('QB','RB','WR','TE') for s in starters))[0])
                pref['calibration_native_bounds'] = linked.native_bounds
                raw_team = next(r for r in linked.rosters if str(r['owner_id']) == str(uid))
                pref['inactive_ids'] = sorted(set(raw_team.get('reserve',()) + raw_team.get('taxi',())))
            year = pref.get("next_draft_year")
            pref["own_next_draft_pick_ids"] = [str(p["pick_id"]) for p in picks
                if year is not None and str(p.get("season")) == str(year)
                and str(p.get("original_user_id")) == uid]
        context["input_evidence"] = request_evidence(context)
        context["input_evidence"].update(schema_version=INPUT_VERSION, used_in_model=True,
                                          age_use="diagnostic_only_not_production_fit")
        metadata = s._load_sleeper_cache() or {}
        cache_age = s._players_cache_age_seconds()
        if cache_age is None or cache_age > 48 * 3600:
            raise GradingError("player_availability_stale", 409)
        if linked:
            metadata = linked.normalized_metadata(players, metadata)
        owned = {}
        for pick in picks:
            owned.setdefault(str(pick.get("owner_user_id")), []).append(str(pick["pick_id"]))
        roster_kwargs = dict(viewer_id=seat, league=context["league"], players=context["players"],
            consensus_value=ts.make_consensus_value_fn(seed, players),
            startable=ts._startable_ok_fn(players, fmt), player_metadata=metadata,
            outlooks={**context["opponent_outlooks"], seat: prefs.get("team_outlook") or prefs.get("inferred_outlook") or "balanced"},
            owned_picks=owned, viewer_roster=roster, availability_fresh=True)
        roster_ctx = (linked.roster_context(**roster_kwargs) if linked else
            build_context(**roster_kwargs, slots=starters, platform="sleeper",
                          raw_rosters=raw["rosters"], capacity=capacity))
        order = s._league_slot_order(league_id)
        for pick in picks:
            pid = str(pick["pick_id"])
            if pid not in roster_ctx.assets:
                roster_ctx.assets[pid] = Asset(pid, frozenset(),
                    float(s._priced_pick_value(pick, order, fmt)), is_pick=True)
        from .calibration_roster_coverage import add_unranked_occupancy
        unpriced_occupancy = add_unranked_occupancy(roster_ctx, metadata)
        from .calibration_fixed_lineup import prepare as prepare_fixed_lineup
        fixed_lineup = prepare_fixed_lineup(roster_ctx, metadata, fixed_bounds=linked.fixed_bounds if linked else ())
        unpriced_occupancy.update(fixed_lineup["assets"])
        for uid, team in roster_ctx.teams.items():
            roster_ctx.utility_inputs[uid] = {"explicit_outlook": prefs.get("team_outlook") if uid == seat else context["opponent_outlooks"].get(uid),
                "inferred_outlook": prefs.get("inferred_outlook") if uid == seat else None,
                "inference_fresh": team.availability_known}
    significance = s._capture_trade_significance()
    assignment = s._owner_selected_assignment(context, "calibration", serve=True, exclusive=True)
    source = {"schema": "outlook-calibration-capture-1", "account_user_id": user_id,
        "league_user_id": seat, "league_id": league_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "input": assignment["input"], "input_evidence": assignment["input_evidence"],
        "roster_context": {k: v for k, v in asdict(roster_ctx).items() if k not in {"cache", "_assignments"}},
        "flags": flags, "significance": significance, "unpriced_occupancy": unpriced_occupancy,
        "fixed_lineup": fixed_lineup,
        "captured_metadata_ids": captured_metadata_ids,
        "code_revision": code_revision(), "platform": resolved["platform"],
        "provider_rules": linked.provenance["rules"] if linked else _provider_rules(raw["meta"]),
        "provider_provenance": linked.provenance if linked else None,
        "picks_included": include_picks,
        "registered_participants": sorted(registered), "registered_participant_revisions": registered,
        "suppression": _suppression_state(s, user_id, league_id) if flags["deck_fatigue"] else None,
        "pass_keys": s._load_trade_disposition_keys(user_id, league_id)[1],
        "roster_policy": "required_structural_safety_for_both_calibration_arms",
        "fairness_basis": "fixed_discovery_default_0.75"}
    source = _json(source)
    identity_after = _input_identity(user_id, league_id, captured_metadata_ids)
    with db.engine.connect() as conn:
        registered_after = dict(conn.execute(db.select(db.users_table.c.sleeper_user_id,
            db.users_table.c.created_at).where(db.users_table.c.sleeper_user_id.in_(participant_ids))).tuples().all())
    from .calibration_provider_capture import binding_identity
    if linked and linked.provenance["binding"] != binding_identity(user_id, league_id):
        raise GradingError("inputs_changed_during_capture", 409)
    if identity_before != identity_after or registered != registered_after:
        raise GradingError("inputs_changed_during_capture", 409)
    source["input_identity"] = identity_after
    source["freshness_policy"] = "frozen_asof_comparison_known_changes_retire_unanswered"
    source["source_hash"] = _hash(source)
    holdings = {uid: frozenset(team.roster) for uid, team in roster_ctx.teams.items()}
    assets = {pid: {"name": getattr(players.get(pid), "name", pid),
              "position": getattr(players.get(pid), "position", "PICK" if asset.is_pick else None),
              "nfl_team": getattr(players.get(pid), "team", None),
              "age": (context["input_evidence"].get("age", {}).get(pid, {}).get("age")
                      if context["input_evidence"].get("age", {}).get(pid, {}).get("state") == "observed"
                      else None), "value": None if pid in unpriced_occupancy else round(asset.value)}
              for pid, asset in roster_ctx.assets.items()}
    names = {str(m["user_id"]): m.get("username") or "League manager" for m in resolved["opponent_rosters"]}
    return CapturedComparison(context, Catalog(assets, names, holdings), source,
                              roster_ctx, significance, flags["deck_quality_filters"])
