"""Every yes/no rule that can stop a candidate trade before it reaches a served deck.

Founders' review, use case 2 (docs/plans/founder-review/rule-waterfall-design.md). One ordered
list, in the order the engine applies the rules on the deck that serves today (owner bilateral
revision 2 built rules-first, ADR-030; revision 5 adds no rule of its own, see ``REVISION_5``).
``backend/rule_waterfall.py`` counts each candidate once, at the first of these it fails, and the
founder page shows one row per rule with its notes (``database.founder_rule_notes``).

Pure data: no imports from the engine, no I/O. The plain-language ``name`` and ``description``
are what a non-engineer reads; ``source`` and ``counted`` are for the engineer who answers the
founder's question. ``test_rule_catalog`` fails when the engine gains a rejection reason this
list does not name, and lints the plain-language fields.

Field meanings:
- ``key``: stable id; the engine's own reason string where one exists.
- ``stage``: one of ``STAGES``, in order.
- ``kind``: ``rule`` (removes candidates; a waterfall row), ``search_limit`` (removes candidates
  without judging them; a waterfall row, shown as such), ``scope`` (defines what the waterfall
  starts with), ``reorder`` (moves cards, removes none), ``addition`` (decides whether an extra
  card is ADDED to the deck; never removes a generated one), ``exception`` (puts a removed card
  back).
- ``live``: whether it can fire on today's production configuration for an organic deck (False:
  behind a flag that is off, or only on a pinned/targeted search).
- ``protects``: ``you``, ``the other manager``, ``both`` or ``deck quality``.
- ``question``: why the rule is flagged for the founder to question, or None.
"""
from __future__ import annotations

from dataclasses import dataclass

VERSION = "rule-catalog-1"

BUILDING = "candidate building"
BOTH_SIDES = "both-sides check"
DECK = "deck rules"
AFTER = "after the deck is built"
STAGES = (BUILDING, BOTH_SIDES, DECK, AFTER)
KINDS = ("rule", "search_limit", "scope", "reorder", "addition", "exception")
PROTECTS = ("you", "the other manager", "both", "deck quality")
WATERFALL_KINDS = ("rule", "search_limit")
# Revision 5 (the win-now season signal) adds no rejection reason: its season lineup changes the
# inputs of the two "good for" checks and its conflict demotion only reorders.
REVISION_5 = "no new rule; season points feed the two 'good for' checks"


@dataclass(frozen=True)
class Rule:
    key: str
    name: str
    description: str
    stage: str
    kind: str
    protects: str
    setting: str
    source: str
    counted: str
    live: bool = True
    question: str | None = None


_GEN = "trade_gen_owner.py"
_BIL = "trade_gen_bilateral.py"
_EVAL_COUNTED = ("Counted per reason in the generation report's rejections only when the gated "
                 "full solve runs (trade_fast_deck.gated_full); the page search that normally "
                 "serves keeps no per-reason count")

RULES: tuple[Rule, ...] = (
    # ── candidate building ────────────────────────────────────────────────────────────────
    Rule("pool", "Players the search considers",
         "For each other team, the search only builds trades from 16 of your players and 16 of "
         "theirs, picked for interest, value spread and position mix. Players with no market "
         "value are never included. The waterfall starts with every 1-for-1, 2-for-1 and "
         "1-for-2 trade that can be built from those players.",
         BUILDING, "scope", "deck quality", "Fixed (16 per side per team)",
         f"{_GEN}:633-653 (pool), :231 and database.py owner_pool_size (16)",
         "Not counted; the waterfall reports the number of possible trades from full rosters for "
         "context",
         question="16 is a speed limit, not a judgement; a player outside the 16 never appears "
                  "in any trade with that team."),
    Rule("not_expanded", "Not worth adding a piece",
         "A 2-for-1 or 1-for-2 is only tried when its core 1-for-1 passed, or failed for a reason "
         "an extra piece could fix (price, fairness, or one side not gaining enough). If the core "
         "1-for-1 failed anything else, every larger version of it is skipped untested.",
         BUILDING, "search_limit", "deck quality", "Fixed",
         f"{_BIL}:377-381 (the list of fixable reasons; trade_first_page.py:162 repeats it)",
         "Not counted",
         question="A shortcut, not a proven rule: adding a player more valuable than the core "
                  "player changes which player counts as the main one, which can change the "
                  "outcome of the skipped checks."),
    Rule("search_budget", "Search time limit",
         "The full search stops after 4,096 trades per other team and 60,000 in total. On the "
         "deck served today the fast search does not stop there; the waterfall raises the limit "
         "to 120,000, so this only removes trades in leagues of about 30 teams or more.",
         BUILDING, "search_limit", "deck quality", "Fixed",
         f"{_GEN}:49-50, :751-757; database.py owner_pair_budget / owner_total_budget",
         "Generation report budget_exhausted (true/false), no count"),

    # ── both-sides check: the owner evaluator, in its order (trade_gen_owner.evaluate) ────
    Rule("invalid_fairness", "Fairness setting is usable",
         "If the fairness setting sent with the request is not a number between 0 and 1, every "
         "trade is rejected. A safety check; it should never fire.",
         BOTH_SIDES, "rule", "both", "Trade settings: fairness", f"{_GEN}:504-505",
         _EVAL_COUNTED),
    Rule("invalid_partner", "Partner is in your league",
         "The other team must be a different team in this league (and the chosen team, when you "
         "picked one). A safety check; it should never fire.",
         BOTH_SIDES, "rule", "both", "Fixed", f"{_GEN}:506-509", _EVAL_COUNTED),
    Rule("invalid_assets", "Trade pieces are valid",
         "Both sides must send at least one piece, no piece twice, no piece on both sides, and "
         "every piece must have a market value. A safety check.",
         BOTH_SIDES, "rule", "both", "Fixed", f"{_GEN}:510-513", _EVAL_COUNTED),
    Rule("assets_not_owned", "Pieces on the right rosters",
         "Everything you send must be on your roster and everything you get must be on theirs. "
         "A safety check against stale rosters.",
         BOTH_SIDES, "rule", "both", "Fixed", f"{_GEN}:514-517", _EVAL_COUNTED),
    Rule("exact_give_mismatch", "Sends exactly what you chose",
         "Only when you search with 'send exactly these players': the trade must send exactly "
         "that set.",
         BOTH_SIDES, "rule", "you", "Targeted search: send exactly", f"{_GEN}:518-519",
         _EVAL_COUNTED, live=False),
    Rule("selection_mismatch", "Includes the players you chose",
         "Only on a targeted search: the trade must include the players you picked to send or to "
         "get (or at least one of them on the 'closest alternative' pass).",
         BOTH_SIDES, "rule", "you", "Targeted search: chosen players", f"{_GEN}:520-523",
         _EVAL_COUNTED, live=False),
    Rule("avoided_position", "Avoids positions you avoid",
         "You never get a player at a position you marked as 'Avoiding'. The setting is hidden "
         "today (switched off), so this never fires.",
         BOTH_SIDES, "rule", "you", "Trade settings: Avoiding positions (switched off today)",
         f"{_GEN}:524-525; server.py _owner_generation_context avoid_positions; "
         "config/features.json trade.avoid_positions false",
         _EVAL_COUNTED, live=False),
    Rule("previous_disposition", "Not one you already answered",
         "A trade you passed on in the last 14 days, liked in the last 7, or that is waiting on "
         "the other manager or already agreed is not shown again.",
         BOTH_SIDES, "rule", "you", "Fixed (pass cooldown 14 days, like window 7 days)",
         f"{_GEN}:526-527; server.py _load_trade_disposition_keys, _load_presentment_exclusions; "
         "database.py pass_cooldown_days (14)",
         _EVAL_COUNTED),
    Rule("organic_shape", "Small trades only",
         "Suggested trades are 1-for-1, 2-for-1 or 1-for-2. Bigger trades appear only when you "
         "pick several players yourself.",
         BOTH_SIDES, "rule", "deck quality", "Fixed", f"{_GEN}:528-529", _EVAL_COUNTED),
    Rule("tier_direction", "Matches your requested move",
         "Only when you ask to move up, move down or stay level: your best incoming player must "
         "be in a higher, lower or the same tier as your best outgoing one on your own board "
         "(or 5% better or worse in the same tier).",
         BOTH_SIDES, "rule", "you", "Trade intent (move up / down / level)", f"{_GEN}:530-536",
         _EVAL_COUNTED, live=False),
    Rule("selected_position", "Gets the position you chose",
         "Only when you ask for a position swap: your best incoming player must play one of the "
         "positions you chose.",
         BOTH_SIDES, "rule", "you", "Trade intent (position swap)", f"{_GEN}:537-540",
         _EVAL_COUNTED, live=False),
    Rule("invalid_market_value", "Trade can be priced",
         "The market price of both sides must be computable. A safety check.",
         BOTH_SIDES, "rule", "both", "Fixed", f"{_GEN}:541-543", _EVAL_COUNTED),
    Rule("market_floor", "Fair by market value",
         "By consensus market value, the cheaper side must be worth at least 65% of the dearer "
         "side, or your fairness setting if it is stricter. This is the fairness check both "
         "managers rely on.",
         BOTH_SIDES, "rule", "both", "Trade settings: fairness (only above 65% has an effect)",
         f"{_GEN}:236 (floor), :551-552; database.py market_floor_absolute (0.65)",
         _EVAL_COUNTED,
         question="A fairness setting below 65% does nothing (the fixed 65% floor wins), and "
                  "between 65% and 75% it only matters for trades with a gap under 500 (see 'No "
                  "big overpay either way'). It removes about 87-92% of all candidates."),
    Rule("market_overpay", "No big overpay either way",
         "A trade is dropped when one side pays at least 500 more in market value and that gap "
         "is at least a quarter of the bigger side. This applies in both directions, including "
         "trades where you are the one being overpaid.",
         BOTH_SIDES, "rule", "both", "Fixed (not affected by the fairness setting)",
         f"{_GEN}:553-554; trade_service.py overpay_ok; database.py max_overpay_frac (0.25), "
         "max_overpay_min_value (500)",
         _EVAL_COUNTED,
         question="Overlaps 'Fair by market value': for gaps of 500 or more it acts as a 75% "
                  "floor. At the default fairness setting (75%) it removed nothing in any "
                  "measured league; below 75% it overrides the setting for every trade with a "
                  "gap of 500 or more. Two rules, two thresholds, one idea."),
    Rule("viewer_no_benefit", "Good for you",
         "Your fit score for the trade must be above 0.35, on a 0-to-1 scale where 0.5 is "
         "neutral. The score mixes how you rank the players (45%), market value (35%) and your "
         "team plan (20%).",
         BOTH_SIDES, "rule", "you", "Indirectly: your rankings and team outlook",
         f"{_GEN}:562-564; {_BIL}:23-24 (weights), :244 (score minus 0.35)",
         _EVAL_COUNTED,
         question="0.35 and the 45/35/20 weights are hand-set launch values, not calibrated on "
                  "accepted trades."),
    Rule("counterparty_no_benefit", "Good for them",
         "The other manager's fit score must also be above 0.35, judged from their rankings "
         "(or market value when they have none), market value and their team plan.",
         BOTH_SIDES, "rule", "the other manager", "Fixed", f"{_GEN}:562-564; {_BIL}:244",
         _EVAL_COUNTED),
    Rule("untouchable", "Keeps players marked Keep",
         "A suggested trade never sends a player either manager marked Keep (untouchable), "
         "unless you chose to send that player yourself.",
         BOTH_SIDES, "rule", "both", "Roster setup: Keep",
         f"{_GEN}:565-575; database.py owner_untouchable_hard (1 = hard rule)", _EVAL_COUNTED),
    Rule("untouchable_return", "Keep players need a premium",
         "Only if the hard Keep rule is switched off: a Keep player may leave only for more "
         "market value and a player at the same position coming back.",
         BOTH_SIDES, "rule", "both", "Roster setup: Keep (old rule, switched off)",
         f"{_GEN}:576-579; database.py owner_untouchable_hard", _EVAL_COUNTED, live=False),
    # Bilateral checks (trade_gen_bilateral._Search._decision). They run together after the
    # owner checks pass; when a trade fails several, the engine records the LAST one in this
    # order, so the waterfall counts it there.
    Rule("viewer_intent_unfulfilled", "Something you want",
         "The trade must match something you showed you want: a player you rank clearly above "
         "market coming in (or below market going out), a player or position you asked for, a "
         "player on your trade block, a stated team plan it helps, or, if you have not ranked "
         "players yet, a small market or plan gain.",
         BOTH_SIDES, "rule", "you", "Indirectly: your rankings, targets, trade block, outlook",
         f"{_BIL}:196-201, :271-272", _EVAL_COUNTED,
         question="The bar for 'rank clearly above market' is small (0.025 of a tier); in tests "
                  "most served cards qualify through it."),
    Rule("expired_draft_asset", "No used draft picks",
         "No trade may include a draft pick from a draft that has already happened.",
         BOTH_SIDES, "rule", "both", "Fixed", f"{_BIL}:277-278", _EVAL_COUNTED),
    Rule("known_preference_harm", "Not against their rankings",
         "If either manager's own rankings say the trade clearly moves them the wrong way "
         "(net lean below -0.15) and it does little for their team plan (plan gain under 0.20), "
         "it is dropped.",
         BOTH_SIDES, "rule", "both", "Indirectly: rankings", f"{_BIL}:279-280", _EVAL_COUNTED),
    Rule("tanking_own_next_draft_pick", "Tanking teams keep next pick",
         "A team marked Tanking never sends its own next-year draft pick, unless you chose to "
         "send it yourself.",
         BOTH_SIDES, "rule", "both", "Team outlook: Tanking", f"{_BIL}:281-284", _EVAL_COUNTED),
    Rule("tanking_rb_without_long_term_exception", "Tanking teams skip older RBs",
         "A team marked Tanking does not take on a running back unless it ranks him in its top "
         "three tiers, or he is 24 or younger, it rates him above market and it gains at least 5% "
         "in market value.",
         BOTH_SIDES, "rule", "both", "Team outlook: Tanking", f"{_BIL}:285-294", _EVAL_COUNTED),
    Rule("tanking_favored_young_asset", "Tanking teams keep young favourites",
         "A team marked Tanking does not give away a young QB (27 or under) or WR or TE (25 or "
         "under) it rates above market when the trade as a whole leans against its rankings.",
         BOTH_SIDES, "rule", "both", "Team outlook: Tanking", f"{_BIL}:295-302", _EVAL_COUNTED),
    Rule("unnecessary_compensation", "No needless extra pieces",
         "Revision 1 only (not served today): a 2-for-1 is dropped when the same trade without "
         "the extra piece is just as good for both managers.",
         BOTH_SIDES, "rule", "both", "Fixed", f"{_BIL}:308-334", _EVAL_COUNTED, live=False),
    Rule("duplicate", "Same trade listed once",
         "If the same two-sided trade with the same team turns up twice in the search, it is "
         "kept once.",
         BOTH_SIDES, "rule", "deck quality", "Fixed", f"{_BIL}:496-499", "Not counted"),

    # ── deck rules (deck_rules.DeckRules, in its order) ───────────────────────────────────
    Rule("significance", "Has a real centrepiece",
         "At least one player in the trade must be worth a second-round tier or better on your "
         "board or the consensus, or the trade must include a first-round pick. Several small "
         "pieces never add up to a centrepiece.",
         DECK, "rule", "deck quality", "Fixed",
         "deck_rules.py:58-59; server.py _evaluate_trade_significance; trade_significance.py; "
         "database.py significance_mode (2 = enforce in production), "
         "significance_player_min_tier (2 = second)",
         "Counted in the rules-first log line (rules_rejected) as distinct packages checked; "
         "downstream copy counted in the job's significance diagnostics",
         question="Code default is off (significance_mode 0); production enforces it. A "
                  "first-round pick always qualifies, any second-round pick never does."),
    Rule("breakup", "Keeps your best player",
         "The best player you get must be worth at least 70% of the best player you give. "
         "Stops trades that break up your top asset for lesser pieces.",
         DECK, "rule", "you", "Fixed",
         "deck_quality.py:49-54, :92-93; BREAKUP_MIN_RATIO (0.70) at :26",
         "rules_rejected in the rules-first log line; downstream copy in the deck quality filters "
         "log line"),
    Rule("filler", "No filler pieces",
         "Every piece in the trade must be worth at least 450, and at least a quarter of the "
         "trade's best player. Stops trades padded with bench players or late picks.",
         DECK, "rule", "deck quality", "Fixed",
         "deck_quality.py:57-63, :94-95; FILLER_FLOOR (450), FILLER_FRAC (0.25) at :27-28",
         "rules_rejected in the rules-first log line; downstream copy in the deck quality filters "
         "log line",
         question="The 450 floor is a hand-set number, and the likes-you path uses a different "
                  "filler rule (25% of the side's best player, plus its own floor)."),
    Rule("redundant", "No extra QB or TE",
         "Neither side gets a QB or TE when it already keeps as many comparable ones (worth at "
         "least 70% of the incoming player) as it has starting spots for that position. Skipped "
         "when the league's lineup is unknown.",
         DECK, "rule", "both", "Indirectly: your league's lineup",
         "deck_quality.py:66-80, :96-99; REDUNDANT_MIN_RATIO (0.70) at :29",
         "rules_rejected in the rules-first log line; downstream copy in the deck quality filters "
         "log line"),

    # ── after the deck is built (server._run_trade_job, in its order) ────────────────────
    Rule("likes_you_added", "Trades they already liked",
         "Up to 3 trades another manager already liked are added to the top of your deck, or "
         "flagged if already there. They skip the deck rules and must pass their own checks: "
         "still on both rosters, nothing you marked Keep or Not interested, you gain value, no "
         "overpay against you and no filler.",
         AFTER, "addition", "both", "Fixed (cap 3)",
         "server.py _inject_likes_you_cards_impl (gates), _LIKES_YOU_CAP (3); "
         "likes_you_gate_level (2)",
         "Log line 'liked cards proven/consensus/errors'",
         question="Liked trades bypass every deck rule and both-sides check by design; one the "
                  "engine finds unfair is still shown as a plain consensus card."),
    Rule("standing_offer_added", "Standing offers",
         "Standing offers from other managers can be added the same way, sharing the cap of 3.",
         AFTER, "addition", "both", "Fixed (shares the cap of 3)",
         "server.py _inject_likes_you_cards_impl standing-offer branch",
         "Cap drops counted in the likes-you log line"),
    Rule("decline_window", "Not like one you declined",
         "For 30 days after you decline a trade, near-copies are hidden: same main player, same "
         "shape and a package value within 10%. One near-copy may come back once the 30 days "
         "end, as a retest.",
         AFTER, "rule", "you", "Fixed (30 days, 10%)",
         "server.py _apply_deck_suppression; database.py fatigue_decline_suppress_days (30), "
         "fatigue_decline_value_band (0.10)",
         "Job suppression_note count (after the floor)"),
    Rule("decline_floor", "Never fewer than five",
         "If hiding near-copies of declined trades would leave fewer than 5 cards, the best "
         "hidden ones are put back until there are 5.",
         AFTER, "exception", "you", "Fixed (5)", "server.py _apply_deck_suppression floor; "
         "_DECK_MIN_CARDS (5)", "Warning log line 'suppression floor engaged'",
         question="With rules-first, the floor counts cards that already passed every rule, so "
                  "heavy decliners can see up to 5 near-copies of declined trades."),
    Rule("revised_offer_replaced", "Replaced by revised offer",
         "When one of your own declined offers has a revised version, it leads the deck (up to "
         "3) and any identical suggested trade is removed so it is not shown twice.",
         AFTER, "rule", "deck quality", "Fixed (cap 3)",
         "server.py _inject_revised_offer_cards; trade_revised_offers.py build",
         "Not counted"),
    Rule("revalidation", "Still valid at serve time",
         "Each suggested trade is checked again with the same evaluator just before it is "
         "served. It only fails if something changed while the deck was being built.",
         AFTER, "rule", "both", "Fixed", "server.py _owner_cards_valid", "Not counted"),
    Rule("roster_protection", "Roster stays legal",
         "Would check that both rosters stay legal and keep a full lineup after the trade. "
         "Switched off today.",
         AFTER, "rule", "both", "Fixed", "server.py _evaluate_deck_rosters; trade.roster_protection",
         "Job roster_evaluation diagnostics", live=False),
    Rule("market_policy", "Personal-market policy",
         "Would apply a second market-value floor and two-sided gain check. Switched off today.",
         AFTER, "rule", "both", "Fixed", "server.py _evaluate_deck_policy; "
         "trade.personal_market_policy_v1", "trade_policy_shadow rows", live=False),
    Rule("significance_recheck", "Centrepiece checked again",
         "The centrepiece rule runs again on the finished deck. On today's deck it removes "
         "nothing; a removal here would mean the two copies disagree.",
         AFTER, "rule", "deck quality", "Fixed", "server.py _run_trade_job significance block",
         "Warning log line 'rules-first guard' when it removes anything"),
    Rule("dispositions", "Not answered meanwhile",
         "Just before serving, trades you passed on in the meantime are removed, and liked "
         "trades whose like was withdrawn are removed.",
         AFTER, "rule", "you", "Fixed", "server.py _project_trade_dispositions", "Not counted"),
    Rule("quality_recheck", "Quality rules checked again",
         "The keeps-your-best-player, filler and extra-QB/TE rules run again on the finished "
         "deck. On today's deck they remove nothing.",
         AFTER, "rule", "deck quality", "Fixed", "server.py _run_trade_job quality block",
         "Deck quality filters log line; 'rules-first guard' warning"),
    Rule("repeat_cap", "Variety in the first 30",
         "No player appears in more than 5 of the first 30 cards; extra repeats move to just "
         "after card 30. Nothing is removed.",
         AFTER, "reorder", "deck quality", "Fixed (5 of 30)",
         "deck_quality.py:128-143; REPEAT_CAP (5), REPEAT_WINDOW (30) at :30-31",
         "Deck quality filters log line (deferred)",
         question="In 232 of 247 recorded decks the window never fills, so it pulls the "
                  "lowest-ranked distinct trades forward."),
)

BY_KEY = {rule.key: rule for rule in RULES}
# The reason strings the engine itself records for the rows above.
ENGINE_REASONS = frozenset(
    rule.key for rule in RULES if rule.stage in (BOTH_SIDES, DECK) and rule.key != "duplicate")


def waterfall_rules() -> tuple[Rule, ...]:
    """The rows of the decline waterfall, in order."""
    return tuple(rule for rule in RULES if rule.kind in WATERFALL_KINDS)


def is_known(key) -> bool:
    return isinstance(key, str) and key in BY_KEY


def as_rows() -> list[dict]:
    """The catalog as plain dicts (for the page and the design doc's table)."""
    return [{"key": r.key, "name": r.name, "description": r.description, "stage": r.stage,
             "kind": r.kind, "protects": r.protects, "setting": r.setting, "source": r.source,
             "counted": r.counted, "live": r.live, "question": r.question} for r in RULES]
