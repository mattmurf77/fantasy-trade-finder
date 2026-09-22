"""Prepared inventory Lane B: real actors, fresh team identity and quiet reads.

All providers/clocks are injected; no server, sessions or production DB is used.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import socket

import pytest

from backend import prepared_trade_cohort as cohort


NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("unexpected network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def actor(uid, **extra):
    return dict(dict(sleeper_user_id=uid, verified_via="sleeper", signup_at="2020-01-01"), **extra)


def league(lid="10", platform="sleeper", **extra):
    return dict(sleeper_league_id=lid, platform=platform, season="2026",
                default_scoring="1qb_ppr", **extra)


def team(tid, owner, players, co_owners=()):
    return dict(team_id=tid, owner_id=owner, co_owners=list(co_owners),
                player_ids=list(players), name="Team")


def source(lid="10", platform="sleeper", teams=None, **extra):
    return dict(league_id=lid, platform=platform, season="2026",
                observed_at=NOW.isoformat(), teams=teams if teams is not None else [
                    team("1", "alice", ["a"], ["bob"]), team("2", "other", ["b"])],
                metadata={}, limitations=[], **extra)


def discover(users=None, leagues=None, members=(), accounts=(), bindings=(), reader=None):
    return cohort.discover_targets(users=users if users is not None else [actor("alice")],
        accounts=accounts, leagues=leagues if leagues is not None else [league()],
        members=members, bindings=bindings, read_source=reader or (lambda _: source()),
        season=2026, now=lambda: NOW)


def test_coowners_keep_personal_targets_and_exclude_same_team_once():
    calls = []
    def read(row):
        calls.append(row["sleeper_league_id"])
        return source()
    result = discover([actor("alice"), actor("bob")], reader=read)
    assert calls == ["10"]
    assert len(result["targets"]) == 2
    assert {t["user_id"] for t in result["targets"]} == {"alice", "bob"}
    assert {t["league_user_id"] for t in result["targets"]} == {"alice"}
    assert all(t["user_roster"] == ["a"] for t in result["targets"])
    assert all([o["user_id"] for o in t["opponents"]] == ["other"] for t in result["targets"])


def test_all_known_current_leagues_not_activity_or_disposition_selected():
    result = discover([actor("alice", last_active_at="2020-01-01")],
        leagues=[league("10"), league("20")], reader=lambda r: source(r["sleeper_league_id"]))
    assert {t["league_id"] for t in result["targets"]} == {"10", "20"}


@pytest.mark.parametrize("platform,field,tid", [("espn", "espn_my_team_id", 3),
    ("mfl", "platform_my_team", "0003"), ("fleaflicker", "platform_my_team", "3")])
def test_account_only_platform_binding_requires_actual_retained_own_member(platform, field, tid):
    uid = "acct_account"
    lg = league(platform=platform, user_id=uid, **{field: tid})
    rows = [dict(league_id="10", user_id=uid, player_ids=["old"])]
    fresh = source(platform=platform, teams=[team(str(tid), None, ["a"]), team("9", None, ["b"])])
    result = discover([actor(uid)], [lg], members=rows,
        accounts=[dict(account_id="account", sleeper_user_id=None)], reader=lambda _: fresh)
    assert len(result["targets"]) == 1
    assert result["targets"][0]["user_roster"] == ["a"]
    assert result["targets"][0]["league_user_id"] == uid
    assert result["targets"][0]["opponents"][0]["user_id"] != uid


def test_importer_last_team_mismatch_cannot_assign_another_accounts_team():
    lg = league(platform="espn", user_id="first", espn_my_team_id=2)
    result = discover([actor("first"), actor("second")], [lg],
        members=[dict(league_id="10", user_id="second", player_ids=["b"])],
        reader=lambda _: source(platform="espn", teams=[team("2", None, ["b"])]))
    assert result["targets"] == []
    assert any(c["reason"] == "missing_platform_binding" for c in result["coverage"])


def test_opponents_unverified_deleted_and_old_account_alias_do_not_create_targets():
    users = [actor("alice"), actor("acct_anchor"), actor("espn:10.t3"),
             dict(sleeper_user_id="bob", signup_at="2020", verified_via=None),
             actor("deleted", deleted=True)]
    result = discover(users, accounts=[dict(account_id="anchor", sleeper_user_id="alice")])
    assert [t["user_id"] for t in result["targets"]] == ["alice"]
    assert any(c["reason"] == "unverified_actor" for c in result["coverage"])
    assert any(c["reason"] == "deleted_actor" for c in result["coverage"])


def test_ambiguous_ownership_is_not_first_match_wins():
    fresh = source(teams=[team("1", "alice", ["a"]), team("2", "other", ["b"], ["alice"])])
    result = discover(reader=lambda _: fresh)
    assert result["targets"] == []
    assert any(c["reason"] == "ambiguous_team_binding" for c in result["coverage"])


def test_source_failure_and_valid_empty_are_distinct_and_quiet():
    def failed(_):
        raise cohort.SourceUnavailable("source_auth_failed")
    bad = discover(reader=failed)
    empty = discover(reader=lambda _: source(teams=[]))
    assert any(c["reason"] == "source_auth_failed" for c in bad["coverage"])
    assert any(c["reason"] == "empty_league" for c in empty["coverage"])
    assert bad["counts"]["discovery_complete"] is False
    assert "secret-cookie" not in json.dumps(bad)


def test_stale_foreign_and_malformed_sources_fail_closed():
    for change, reason in [({"observed_at": (NOW-timedelta(hours=1)).isoformat()}, "source_stale"),
                            ({"league_id": "foreign"}, "source_identity_mismatch"),
                            ({"teams": None}, "source_invalid")]:
        fresh = source(); fresh.update(change)
        result = discover(reader=lambda _: fresh)
        assert result["targets"] == []
        assert any(c["reason"] == reason for c in result["coverage"])


def test_inputs_and_returned_targets_are_detached():
    users, leagues, fresh = [actor("alice")], [league()], source()
    before = deepcopy((users, leagues, fresh))
    result = discover(users, leagues, reader=lambda _: fresh)
    result["targets"][0]["user_roster"].append("changed")
    assert (users, leagues, fresh) == before


def test_explicit_multiple_platform_bindings_not_shared_importer_attribution():
    lg = league(platform="mfl", user_id="importer", platform_my_team="0001")
    bindings = [dict(user_id=uid, league_id="10", platform="mfl", team_id=tid,
                     source="verified_import") for uid, tid in [("alice", "0001"), ("bob", "0002")]]
    result = discover([actor("alice"), actor("bob")], [lg], bindings=bindings,
        reader=lambda _: source(platform="mfl", teams=[team("0001", None, ["a"]), team("0002", None, ["b"])]))
    assert [(t["user_id"], t["user_roster"]) for t in result["targets"]] == [("alice", ["a"]), ("bob", ["b"])]
    assert [t["opponents"][0]["user_id"] for t in result["targets"]] == ["bob", "alice"]


def test_conflicting_explicit_and_legacy_binding_is_not_guessed():
    result = discover(leagues=[league(platform="espn", user_id="alice", espn_my_team_id=1)],
        members=[dict(league_id="10", user_id="alice")],
        bindings=[dict(user_id="alice", league_id="10", platform="espn", team_id="2", source="verified_import")],
        reader=lambda _: source(platform="espn", teams=[team("1", None, ["a"]), team("2", None, ["b"])]))
    assert not result["targets"]
    assert result["counts"]["by_reason"]["ambiguous_team_binding"] == 1


@pytest.mark.parametrize("change,reason", [({"season": "2025"}, "noncurrent_season"),
    ({"default_scoring": "unknown"}, "unsupported_format"), ({"platform": "unknown"}, "unsupported_platform")])
def test_unsupported_known_league_does_not_call_provider(change, reason):
    lg = league(); lg.update(change)
    def forbidden(_):
        raise AssertionError("provider read forbidden")
    result = discover(leagues=[lg], reader=forbidden)
    assert result["counts"]["source_reads"] == 0
    assert reason in result["counts"]["by_reason"]


@pytest.mark.parametrize("bad", [None, {}, [None], [team("1", "alice", ["a", "a"])],
    [team("1", "alice", ["a"]), team("1", "other", ["b"])],
    [dict(team("1", "alice", ["a"]), co_owners="bob")]])
def test_malformed_teams_never_report_ready(bad):
    fresh = source(); fresh["teams"] = bad
    result = discover(reader=lambda _: fresh)
    assert not result["targets"]
    assert result["counts"]["by_reason"] == {"no_known_linked_team": 1, "source_invalid": 1}


@pytest.mark.parametrize("teams,reason", [([team("1", None, ["a"], ["alice"])], "ownerless_team"),
    ([team("1", "alice", []), team("2", "other", ["b"])], "empty_roster"),
    ([team("1", "alice", ["a"])], "missing_opponents")])
def test_missing_roster_inputs_have_honest_status(teams, reason):
    result = discover(reader=lambda _: source(teams=teams))
    assert not result["targets"]
    assert reason in result["counts"]["by_reason"]


def test_no_provider_exception_message_or_credential_leaks():
    def bad(_):
        raise RuntimeError("secret-cookie=private-actor")
    result = discover(reader=bad)
    assert "secret-cookie" not in json.dumps(result)
    assert "private-actor" not in json.dumps(result["counts"])
    fresh = source(); fresh["metadata"] = {"nested": {"access_token": "secret"}}
    assert not discover(reader=lambda _: fresh)["targets"]


def test_source_fingerprint_changes_inputs_not_read_clock():
    first = discover()["targets"][0]["source"]
    changed = source(); changed["observed_at"] = (NOW-timedelta(seconds=1)).isoformat()
    second = discover(reader=lambda _: changed)["targets"][0]["source"]
    assert first["fingerprint"] == second["fingerprint"]
    changed["teams"][1]["player_ids"] = ["new"]
    assert first["fingerprint"] != discover(reader=lambda _: changed)["targets"][0]["source"]["fingerprint"]


def sleeper_reader(overrides=None):
    values = {"": {"league_id": "10", "season": "2026", "name": "League",
        "settings": {"draft_rounds": 3}, "scoring_settings": {"rec": 1},
        "roster_positions": ["QB", "RB", "WR", "FLEX"]},
        "/rosters": [{"roster_id": 1, "owner_id": "alice", "players": ["a"], "co_owners": ["bob"]},
                     {"roster_id": 2, "owner_id": "other", "players": ["b"]}],
        "/users": [{"user_id": "alice", "display_name": "Alice"},
                   {"user_id": "other", "username": "Other Manager"}],
        "/traded_picks": [], "/drafts": []}
    values.update(overrides or {})
    calls = []
    def read(url):
        calls.append(url)
        return deepcopy(values[url.removeprefix("https://api.sleeper.app/v1/league/10")])
    return read, calls


def test_quiet_sleeper_adapter_reads_only_known_league_and_keeps_fresh_pick_evidence():
    picks = [{"season": "2027", "round": 1, "roster_id": 1, "owner_id": 2}]
    read, calls = sleeper_reader({"/traded_picks": picks})
    result = cohort.read_league_source(league(), sleeper_get=read, now=lambda: NOW)
    assert len(calls) == 5
    assert result["traded_picks"] == picks
    assert result["drafts"] == []
    assert result["teams"][0]["co_owners"] == ["bob"]
    assert result["teams"][0]["name"] == "Alice"
    assert result["teams"][1]["name"] == "Other Manager"
    assert result["metadata"]["roster_positions"] == ["QB", "RB", "WR", "FLEX"]


@pytest.mark.parametrize("suffix,bad", [("", None), ("/rosters", None), ("/traded_picks", None),
    ("/drafts", {}), ("/users", None), ("", {"league_id": "elsewhere", "season": "2026"})])
def test_sleeper_adapter_never_turns_provider_failure_into_valid_empty(suffix, bad):
    read, _ = sleeper_reader({suffix: bad})
    with pytest.raises(cohort.SourceUnavailable):
        cohort.read_league_source(league(), sleeper_get=read, now=lambda: NOW)


def test_imported_adapter_uses_existing_secure_read_without_credential_echo(monkeypatch):
    from backend import espn_service
    from types import SimpleNamespace
    seen = []
    def fetch(*args, **kwargs):
        seen.append((args, kwargs))
        return {"teams": [], "settings": {"name": "League"}}
    monkeypatch.setattr(espn_service, "fetch_league", fetch)
    monkeypatch.setattr(espn_service, "parse_league", lambda _: dict(league_id="10", season=2026,
        name="League", teams=[SimpleNamespace(team_id=1, name="One"), SimpleNamespace(team_id=2, name="Two")]))
    monkeypatch.setattr(espn_service, "map_rosters", lambda *_: dict(rosters={1: ["a"], 2: ["b"]}, report={"unmatched": []}))
    lg = league(platform="espn", user_id="alice", espn_auth="cookie")
    result = cohort.read_league_source(lg, crosswalk=object(), now=lambda: NOW,
        credential_reader=lambda platform, uid: {"espn_s2_encrypted": "cipher", "swid": "private-swid"},
        decrypt_token=lambda cipher: "secret-cookie")
    assert seen[0][1]["espn_s2"] == "secret-cookie"
    assert seen[0][1]["swid"] == "private-swid"
    assert "secret-cookie" not in json.dumps(result) and "private-swid" not in json.dumps(result)
    assert result["limitations"] == ["platform_pick_ledger_not_provided"]


def test_provider_auth_failure_sanitized_without_reconnect_or_clear(monkeypatch):
    from backend import espn_service
    def failed(*args, **kwargs):
        raise espn_service.EspnAuthError("secret-cookie expired")
    monkeypatch.setattr(espn_service, "fetch_league", failed)
    with pytest.raises(cohort.SourceUnavailable, match="^source_auth_failed$"):
        cohort.read_league_source(league(platform="espn"), crosswalk=object(), now=lambda: NOW)


@pytest.mark.parametrize("platform", ["espn", "mfl", "fleaflicker"])
def test_missing_crosswalk_is_not_partial_roster_success(platform):
    with pytest.raises(cohort.SourceUnavailable, match="source_crosswalk_missing"):
        cohort.read_league_source(league(platform=platform), now=lambda: NOW)


def test_private_credentials_missing_does_not_try_anonymous_fallback():
    with pytest.raises(cohort.SourceUnavailable, match="source_credentials_missing"):
        cohort.read_league_source(league(platform="mfl", platform_auth="cookie"),
            crosswalk=object(), now=lambda: NOW)


def test_espn_fresh_owner_contradiction_revokes_retained_private_binding(monkeypatch):
    from backend import espn_service
    from types import SimpleNamespace
    monkeypatch.setattr(espn_service, "fetch_league", lambda *a, **k: {"teams": [], "settings": {}})
    monkeypatch.setattr(espn_service, "parse_league", lambda _: dict(league_id="10", season=2026,
        name="League", teams=[SimpleNamespace(team_id=1, name="One", owner_swid="someone-else")]))
    monkeypatch.setattr(espn_service, "map_rosters", lambda *_: dict(rosters={1: ["a"]}, report={"unmatched": []}))
    with pytest.raises(cohort.SourceUnavailable, match="source_identity_mismatch"):
        cohort.read_league_source(league(platform="espn", user_id="alice", espn_auth="cookie", espn_my_team_id=1),
            crosswalk=object(), now=lambda: NOW, credential_reader=lambda *_: {
                "espn_s2_encrypted": "cipher", "swid": "owner"}, decrypt_token=lambda _: "secret")


def test_missing_espn_roster_envelope_is_failure_not_valid_empty(monkeypatch):
    from backend import espn_service
    monkeypatch.setattr(espn_service, "fetch_league", lambda *a, **k: {"id": 10, "seasonId": 2026})
    monkeypatch.setattr(espn_service, "map_rosters", lambda *_: dict(rosters={}, report={"unmatched": []}))
    with pytest.raises(cohort.SourceUnavailable, match="source_invalid"):
        cohort.read_league_source(league(platform="espn"), crosswalk=object(), now=lambda: NOW)


def test_mfl_adapter_keeps_zero_padded_team_ids_and_live_future_pick_ledger(monkeypatch):
    from backend import mfl_service
    raw = {"league": {"league": {"id": "10", "name": "League", "franchises": {
        "count": "2", "franchise": [{"id": "0001", "name": "One"}, {"id": "0002", "name": "Two"}]}}},
        "rosters": {"rosters": {"franchise": []}},
        "futureDraftPicks": {"futureDraftPicks": {"franchise": [{"id": "0001", "futureDraftPick": [
            {"year": "2027", "round": "1", "originalPickFor": "0002"}]}]}}, "rules": {}}
    seen = []
    def fetch(*args, **kwargs):
        seen.append((args, kwargs)); return raw
    monkeypatch.setattr(mfl_service, "fetch_league_bundle", fetch)
    monkeypatch.setattr(mfl_service, "map_franchises", lambda *_: dict(rosters={"0001": ["a"], "0002": ["b"]}, report={"unmatched": []}))
    result = cohort.read_league_source(league(platform="mfl", platform_host="https://www49.myfantasyleague.com"),
        crosswalk=object(), now=lambda: NOW)
    assert seen[0][0] == ("10", 2026, "https://www49.myfantasyleague.com")
    assert result["teams"][0]["team_id"] == "0001"
    assert result["future_picks"] == [{"franchise_id": "0001", "year": "2027", "round": "1", "original_owner": "0002"}]


def test_fleaflicker_quiet_public_read_declares_horizon_and_pick_limits(monkeypatch):
    from backend import fleaflicker_service
    raw = {"standings": {"league": {"id": 10, "name": "League", "size": 2}},
        "rosters": {"rosters": [{"team": {"id": 1, "name": "One"}, "players": []},
                                  {"team": {"id": 2, "name": "Two"}, "players": []}]}}
    monkeypatch.setattr(fleaflicker_service, "fetch_league_bundle", lambda *a, **k: raw)
    monkeypatch.setattr(fleaflicker_service, "map_teams", lambda *_: dict(rosters={"1": ["a"], "2": ["b"]}, report={"unmatched": []}))
    result = cohort.read_league_source(league(platform="fleaflicker"), crosswalk=object(), now=lambda: NOW)
    assert result["teams"][1]["player_ids"] == ["b"]
    assert result["limitations"] == ["platform_pick_ledger_not_provided", "platform_season_not_attested"]


@pytest.mark.parametrize("platform", ["mfl", "fleaflicker"])
def test_imported_missing_envelope_is_not_zero_inventory(monkeypatch, platform):
    from backend import mfl_service, fleaflicker_service
    provider = mfl_service if platform == "mfl" else fleaflicker_service
    monkeypatch.setattr(provider, "fetch_league_bundle", lambda *a, **k: {})
    with pytest.raises(cohort.SourceUnavailable, match="source_invalid"):
        cohort.read_league_source(league(platform=platform, platform_host="https://www49.myfantasyleague.com"),
            crosswalk=object(), now=lambda: NOW)


def test_unmapped_skill_player_rejects_incomplete_roster(monkeypatch):
    from backend import espn_service
    monkeypatch.setattr(espn_service, "fetch_league", lambda *a, **k: {"id": 10, "seasonId": 2026, "teams": []})
    monkeypatch.setattr(espn_service, "map_rosters", lambda *_: dict(rosters={}, report={"unmatched": [{"name": "Unmapped"}]}))
    with pytest.raises(cohort.SourceUnavailable, match="source_unmapped_players"):
        cohort.read_league_source(league(platform="espn"), crosswalk=object(), now=lambda: NOW)


def test_duplicate_league_reads_once_and_targets_are_independently_owned():
    calls = []
    result = discover([actor("alice"), actor("bob")], [league(), league()],
        reader=lambda row: calls.append(row) or source())
    assert len(calls) == 1
    result["targets"][0]["source"]["teams"][0]["player_ids"].append("x")
    assert result["targets"][1]["source"]["teams"][0]["player_ids"] == ["a"]


def test_single_target_refresh_revalidates_current_binding_not_saved_snapshot():
    first = discover()["targets"][0]
    changed = source(); changed["teams"][0]["owner_id"] = "new-owner"
    second = discover(reader=lambda _: changed)
    assert first["user_id"] == "alice" and second["targets"] == []


def test_default_coverage_summary_contains_no_manager_identity():
    result = discover([actor("private-manager")], reader=lambda _: source(teams=[
        team("1", "private-manager", ["a"]), team("2", "opponent", ["b"])]))
    assert "private-manager" not in json.dumps(result["counts"])
    assert result["counts"]["resolved_targets"] == 1


def test_imported_opponent_ids_preserve_existing_platform_member_namespace(monkeypatch):
    from backend import espn_service
    from types import SimpleNamespace
    monkeypatch.setattr(espn_service, "fetch_league", lambda *a, **k: {"teams": []})
    monkeypatch.setattr(espn_service, "parse_league", lambda _: dict(league_id="10", season=2026,
        name="League", teams=[SimpleNamespace(team_id=1, name="One", owner_swid="owner-one", owner_display="First"),
                              SimpleNamespace(team_id=2, name="Two", owner_swid="owner-two", owner_display="Second")]))
    monkeypatch.setattr(espn_service, "map_rosters", lambda *_: dict(rosters={1: ["a"], 2: ["b"]}, report={"unmatched": []}))
    lg = league(platform="espn", user_id="alice", espn_my_team_id=1)
    fresh = cohort.read_league_source(lg, crosswalk=object(), now=lambda: NOW)
    result = discover(leagues=[lg], members=[dict(league_id="10", user_id="alice")], reader=lambda _: fresh)
    assert result["targets"][0]["opponents"][0]["user_id"] == "espn:owner-two"
    assert result["targets"][0]["opponents"][0]["name"] == "Second"


def test_fleaflicker_fallback_and_opponent_actor_exclusion_use_flea_prefix():
    result = discover([actor("alice"), actor("flea:10.t2")],
        [league(platform="fleaflicker", user_id="alice", platform_my_team="1")],
        members=[dict(league_id="10", user_id="alice")], reader=lambda _: source(platform="fleaflicker",
            teams=[team("1", None, ["a"]), team("2", None, ["b"])]))
    assert result["targets"][0]["opponents"][0]["user_id"] == "flea:10.t2"
    assert result["counts"]["eligible_actors"] == 1


def test_null_saved_scoring_uses_documented_native_default_not_skip():
    lg = league(); lg["default_scoring"] = None
    result = discover(leagues=[lg])
    assert result["targets"][0]["scoring_format"] == "1qb_ppr"
    assert result["targets"][0]["scoring_basis"] == "native_default"


@pytest.mark.parametrize("field", ["reserve", "taxi"])
def test_only_inactive_roster_assignment_changes_source_identity(field):
    read, _ = sleeper_reader()
    first = cohort.read_league_source(league(), sleeper_get=read, now=lambda: NOW)
    changed = [{"roster_id": 1, "owner_id": "alice", "players": ["a"], field: ["a"]},
               {"roster_id": 2, "owner_id": "other", "players": ["b"]}]
    read, _ = sleeper_reader({"/rosters": changed})
    second = cohort.read_league_source(league(), sleeper_get=read, now=lambda: NOW)
    # Isolate the one relevant source delta (coowners otherwise differ in fixture).
    first["teams"][0]["co_owners"] = []
    second["teams"][0]["co_owners"] = []
    first = discover(reader=lambda _: first)["targets"][0]["source"]
    second = discover(reader=lambda _: second)["targets"][0]["source"]
    assert first["teams"][0]["player_ids"] == second["teams"][0]["player_ids"]
    assert second["teams"][0][field] == ["a"]
    assert first["fingerprint"] != second["fingerprint"]


def test_legacy_normalized_source_missing_availability_remains_explicit_unknown():
    normalized = discover()["targets"][0]["source"]["teams"][0]
    assert normalized["reserve"] == normalized["taxi"] == []
    assert normalized["availability_source"] == "unknown"
