## 2026-10-31 — Deletion scrub stage 2: packs through the codec, the cached writer state, the page store (legal R28.22, G-a1 to G-a3)

Gates: the scope block `scope-deletion-scrub.md` §0.3 (head-eng's ruling 2, 10-31); `SCRUB_VERSION` 2. No schema change past stage 1's table, no flag, no event, no route contract change; one serve rule (a redacted page card is withdrawn). D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **`backend/tests/test_deletion_scrub_packs.py`, 12 tests:**
  - **Packs:**
    - a pack is rewritten through the codec with exactly the four changes;
    - non-redacted cards are bit-identical, directly and through `eval.data.load_decks` (G-a2);
    - a pack in a league the person left is found by the scan;
    - a second run changes nothing;
    - a pack that names nobody deleted is byte-identical;
    - a concurrent header update makes the scrub redo on the new row, keeping that update.
  - **The cached writer state:**
    - a writer's commit after a scrub keeps the scrub, and the pack still unpacks;
    - a stale cached state reloads once, and a plain header update doesn't reload it;
    - a held row's upgrade takes the pack's token.
  - **The page store:**
    - its cards and evidence are redacted, and `stored_bytes` is recomputed;
    - a page row in a left league is found by the scan;
    - a redacted card never serves and leaves as a withdrawal.
- **Sabotages, 16/16 red:**
  - the commit ignores the scrub;
  - the state never reloads;
  - the held row isn't redacted;
  - the old card index is kept;
  - `likes_you`, the scores, `qb_te`, `protected` or `redacted_at` kept in packs (one sabotage each);
  - no pack CAS;
  - no pack scan;
  - page cards kept;
  - a token card served;
  - blob rows kept;
  - blob `trade_impressions` kept;
  - no page scan.
- **Suites:**
  - stage 1's `test_deletion_scrub.py` still passes;
  - every pack-writer and page-store suite (17 files): 898 passed;
  - **the full backend suite** at `3e7dcf3e`: 10,207 passed, 2 skipped, 0 failed;
  - after stage 1's `bakeoff_runs` update was merged in (`77d55a47`): both scrub files (36) and every evidence, page-store and deletion suite, 1,442 passed.

## 2026-10-31 — Deletion scrub: #557 QA (NO-GO, 3 P1s) answered

Gates: release-lead's #557 QA @ `cbbb80f3`. No new table, flag, event or route change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **P1-1, owner_v2_bilateral's valuation:**
  - every id in `valuation_json` takes the token (it was only pruned);
  - a redacted card loses `bilateral`: `total_support` and `preference_fulfillment` sum both sides and `weaker_support` mins them, with the viewer's side kept, so they solve back (scope §1.3);
  - it loses `term_efficiency` (each companion classed by its recipient's preference-derived `benefits`) and assets' `counterparty_preference`.
- **P1-2:** owner-selected bakeoff runs' top-level `input` loses the person's board, sources, preferences and outlooks.
- **P1-3:** bakeoff `arms_json`, `agreement_json` and `groups_json` take the token, and an owner arm's `diagnostics.pools[<person>]` goes.
- **P2:**
  - the lease is renewed by CAS on every scan page and league store, and every write of a run is conditioned on it, so a runner that outlasted its lease writes nothing;
  - a runner claims one job at a time;
  - bakeoff pages are 200 rows (reads of 20), and bakeoff has no unbounded league pass (the scan covers it).
- **P3:**
  - a poison row is counted, the pass isn't marked done, and it's retried after a 1 h backoff;
  - a version bump re-runs the model store;
  - the route's kick and the cleanup step never raise, and log the class only (tested);
  - doc drift fixed (ten steps, `steps=10`, the scope's `last_error`);
  - a config-reference row for `FTF_DISABLE_DELETION_SCRUB_KICK`.
- **Not fixed here, named:** `prepared_runtime.owner_evaluation.snapshot_json` is latent while `prepared_trade_inventory_enabled` is 0, and goes with the prepared-adoption work. `notifications` and `user_events.props.partner_user_id` went to head-eng and legal.
- **Tests:** `test_deletion_scrub.py`, 32 passed.
- **Sabotages, 11/11 red:**
  - bilateral kept;
  - `counterparty_preference` kept;
  - valuation ids kept;
  - the top-level input kept;
  - pools kept;
  - arms not tokenized;
  - writes not on the lease;
  - claiming every job;
  - poison ignored;
  - the model store not re-run;
  - the route's kick unguarded.

## 2026-10-31 — Deletion scrub stage 1: the job, the hook, the tick step, rows, candidate sets, side tables (legal R28.20 (ii), R28.22)

Gates: the scope block `docs/plans/trade-time-to-suggestion/scope-deletion-scrub.md` (no waivers but analytics, a log-only job). Schema: the new table `deletion_scrub_jobs`. No flag; no event; a route's counts and the daily tick's steps change (api-reference). D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **`backend/tests/test_deletion_scrub.py`, 24 tests:**
  - **The job:**
    - written in the deletion transaction with a random token, the ids and the leagues, captured before `league_members` goes;
    - none on a rollback;
    - the lease's CAS, tested with a stale read;
    - a failed pass records the class only and is retried;
    - the 6 h grace pass scrubs a row an in-flight deck wrote later;
    - **a partner who left a league before deleting is still scrubbed from its decks:** rows and candidate sets, found by the fallback scan (head-eng 10-31);
    - the scan is bounded per run and resumes from its cursor;
    - **legal f's trace (10-31):**
      - another partner's card loses the person's owner inputs (outlooks, sources, preferences, board);
      - other users' `bakeoff_runs` keep the owner engine's full frozen input, and it loses the person's account fields, in the league and through the scan;
    - no id in any log line;
    - **CI fix (10-31):** the route's kicked thread never starts in the suite (`FTF_DISABLE_DELETION_SCRUB_KICK`, set in conftest like `FTF_DISABLE_CLEANUP_LOOP`). It outlived a route test's engine and raised "Set changed size during iteration" in the pool's dispose. A test pins both behaviors.
  - **Stores:**
    - a redacted card takes the token, loses `likes_you`, `standing_offer(_reason)`, `breaker(_shadow)`, `negmem.exempt` and the partner's sides of `fit` / `fit_diag` / `roster_evaluation` / the owner request, and its blended scores are nulled;
    - a plain card of the same partner is scrubbed the same way (uniformity);
    - another partner's card and a deck served past the cutoff are byte-identical;
    - candidate members take the token through the codec and in JSON, and the other member is bit-identical;
    - taste aliases merge;
    - standing offers take the token;
    - `match_valuation_json` is cleared on either side.
  - **The tick:**
    - the step sits right before `value_model_refit`;
    - the model store is redacted once, with every id mapped to its token;
    - a raise keeps the job;
    - a finished job is deleted only once `COMPLETE`;
    - the 24 h ERROR line carries counts only;
    - the tick never raises an error's text.
- **Sabotages, 18 run, 17 red and 1 green by design:**
  - no taste rename;
  - no standing-offer token;
  - the match valuation kept;
  - `surplus_margin` kept;
  - `likes_you` kept;
  - scores kept;
  - valuation kept;
  - the packed candidate path skipped;
  - no lease CAS;
  - the step after the refit;
  - no cutoff;
  - no grace pass;
  - an error's text logged;
  - no fallback scan;
  - the scan cursor not kept;
  - owner inputs redacted only on the person's own cards;
  - outlooks kept;
  - no `bakeoff_runs` scan.
  - **Green, by design:** removing `bakeoff_runs`' league pass. The fallback scan covers every row the league pass does, so each league pass is a fast path, never the only one.
- **Updated tests:**
  - `test_daily_tick_route.py`: ten steps.
  - `test_purge_entry_users.py`: `user_taste.attr`, the derived `partner:<id>` key, listed as not a user column.
- **Suites:** every test touching deletion, export or the tick (17 files): 909 passed before those two updates, and both pass after them (68). **The full backend suite at `671dd526`** (main `fabfe92c` merged): 10,195 passed, 2 skipped, 0 failed.

## 2026-10-31 — #551's flags-on failures: two tests pin their flags, a stored-path twin for the paged withhold

Gates: release-lead's flags-on run of #551 (`ops/200ms-flip`, both `trade.first_page_store` and `trade.packed_evidence` on) failed 3 tests. Failure 1 (the packed-evidence mirror pin) is fixed on `ops/200ms-flip` itself. This entry covers 2 and 3. Tests only: no app code, route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **2, `test_control_a_normal_job_does_write_impressions`:** with packed evidence on, an organic job defers its impressions to delivery (#370), so the control wrote none. It now pins both flags off rather than reading `features.json`.
- **3, `test_paged_withhold_holds_the_cursor`:** with the store on, `/status?cursor=0` reads the stored deck, which is the job's real cards (g1→r1, g2→r1, g1→r2, g2→r2), not the `CARDS` the test swaps into the in-memory job. Only g2→r2 passes I-1 on the stored rosters, and that one card is what served. So this was a fixture artifact, not an I-1 gap. The test now pins both flags off.
- **The flags-on twin:** `test_trade_page_store.py::test_a_paged_withhold_on_the_stored_deck_holds_the_cursor_then_serves_i1s_survivors`, with the page-store fixture (both flags on) and the real stored deck.
  - A stale roster past its bound withholds the page on `/status?cursor=0` with the cursor held: `([], 0, 0, "roster_check")`.
  - Once fresh, exactly the stored cards that pass I-1 serve. The test computes them from the stored rosters and picks, independent of the server.
  - The deck must have a card for I-1 to drop.
- **Sabotages, 2/2 red:** I-1's drops ignored on the page path; the withhold ignored on the page path.
- **Suites:** force-supersede, I-1 serve filter, page store and packed evidence: 317 passed on main and 317 passed on a flags-on copy of `ops/200ms-flip` (with failure 1's fix).
- **Full backend suite, flags on** (`ops/200ms-flip` @ `8080663e` plus this branch's three test files): 10,055 passed, 2 skipped, 0 failed.

## 2026-10-31 — #544 QA round 3: the X3 coverage hole closed; T-10 resolves namespace lookups; the residual documented by class

Gates: release-lead's #544 round-3 re-QA (one small round to merge): P2-1 must-fix, plus the ruling on the 14 forms. Still dark. No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **P2-1 (X3):** `test_account_deletion_coverage::test_new_private_rows_and_aliases_removed_counterparty_kept` compares the counterparty's rows **column for column** before and after, for every private table. It used to check only which `user_id`s were left.
  - **X3** (`_delete_user_data` UPDATEs every user's `receipts_grades` through the exempt name loop) now fails it on `[receipts_grades]`.
  - T-10 stays green on X3, since that loop is exempt by design; the coverage test is what catches it. The test also hardens account deletion for every other private table.
- **T-10, the five static-string lookups (optional, taken):** `globals()[...]`, `vars(m)[...]`, `m.__dict__[...]` / `.get(...)`, `operator.attrgetter(...)(m)` and `m.__getattribute__(...)` resolve to a receipts table when the name is static, then the allowlist governs. 5 new cases, all caught.
- **The residual, documented by class** in the test docstring, `docs/plans/receipts/LLD.md` (§3 and T-10) and the data dictionary (release-lead's ruling: T-10 catches accidents, not deliberate evasion):
  - run-time-computed names and runtime table searches;
  - back-references from an allowed use (`t.c.<col>.table`, `insert(t).table`, `get_final_froms()`);
  - SQL text built with `%(…)s` dicts, `.format_map`, `string.Template`, `bytes.decode` or `list.append` + `join`;
  - `exec`/`eval` or a file run;
  - the ORM.
- **Suites:** T-10 108 passed; account deletion coverage 52 passed. False-positive rescan with the new lookup rules: main `98b9291f` (every file) 0 findings; 101 open PRs (their 141 changed backend/scripts files; an unchanged file scans as on main) 0 findings.

## 2026-10-31 — Calibration's lock order: answer_grading_card locks the session first (the deadlock fixed, not documented)

Gates: the operator's "fix the deadlock" (#544 QA round 2 P3-1, documented on 10-29 as a must-fix before the cap). On #544. No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest plus a local Postgres 18 race.

- **The cause:** `answer_grading_card` updated the card, then the session. Every other grading writer takes the session first: the prune (sessions, then cards), `fold_grading_cards`, `finish_grading_session_build` and `insert_grading_session`.
- **The fix:** the answer reads its card's session id, then locks the session row (`SELECT … FOR UPDATE`) and reads its status under the lock, before it touches the card. If the session is gone by then (the prune), it returns `None`, which is the route's 404.
- **Proof on Postgres 18** (a throwaway local cluster; release-lead's `test_qa544_race.py` plus a new fold-versus-answer race; each interleaving forced with statement hooks):
  - **Before:** the prune against an answer deadlocked in both interleavings, killing the prune in one and the answer in the other. A fold re-numbering the card being answered deadlocked against it in both interleavings too, and that one is live on main today.
  - **After, 3 runs:** no deadlock in any of the 6 races. In the answer-first race, the prune waits, then deletes the session and its cards. In the prune-first race, the answer waits, then finds the session gone and returns `None`. The fold backs out (`False`) when its card got answered. Nothing is left partial.
- **CI** (`backend/tests/test_grading_lock_order.py`, 3 tests; CI has no Postgres, so the order is pinned on the source):
  - every function in `database.py` that writes or locks a card and touches the session table takes the session first, the five known ones included, and any new one is covered;
  - the answer's first operation is the session `FOR UPDATE`;
  - an answer to a session deleted between its read and its lock returns `None` and writes nothing.
- **Sabotages, 5/5 red:** no `FOR UPDATE`; the card updated before the lock; a vanished session not handled; the prune deleting cards first; the fold touching a card first.
- **Docs:** the prune's comment and the cap knob in `config-reference.md` no longer carry the "before the cap" caveat.
- **Suites:** lock order, T-10, retention, receipts, blind grading (all `test_blind_grading*`): 308 passed.

## 2026-10-31 — S1–S8 package follow-ups: S1 (b) in packed mode, C1 for a refused pack, S7 and U6 docs, ADR-025's title

Gates: the S1–S8 evidence package (`trades-eng-s1-s8-package.md` in the group notes folder, against main `63e373e2`), §7 items 1–4: trades-eng's small closers before models-lead's sign-off. Tests and docs only: no app code, route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **S1 (b) in packed mode:** `test_s1b_a_truncated_lost_job_deck_is_written_as_a_partial_run` is parametrized over `packed`. In both modes a truncated lost-job deck writes only `partial_run` rows, and never a pack.
- **S8 C1 when `pack_run` refuses a deck:** `test_c1_a_deck_that_wont_pack_gets_no_row_past_30_and_eval_reads_a_lost_pack`.
  - At every delivery there's no pack and no row past the first 30, so never a `full_interim` one.
  - The refusal is logged at ERROR, and each serve's withdrawals are still recorded (one served-before, one W0).
  - Eval reads the deck as `in_flight` at +1 h and `incomplete_deck` at +26 h, a lost pack, never a complete 30-card deck (`PACK_REQUIRED_SINCE` is set on main).
- **Sabotages, 4/4 red:** the refusal records no withdrawals; the refusal logged at WARNING; `PACK_REQUIRED_SINCE = None`; a partial run allowed to write a pack.
- **Docs:**
  - **S7:** the `evidence_tier` comment lists `viewed`, and "No row is deleted" now names the dark retention cap and account deletion (`database.py`, `data-dictionary.md`).
  - **U6:** the receipts LLD cites analytics-lead's and trades-eng's acceptances on main.
  - **ADR-025:** retitled to "write full rows only for viewed cards (and the first 30)".
- **Suites:** deferred evidence, packed evidence, eval withdrawals and paging: 306 passed.

## 2026-10-29 — #544 QA round 2: T-10 as an allowlist of uses; SQL normalised; the Calibration deadlock documented

Gates: release-lead's #544 delta re-QA (everything passes but T-10: 22 of 39 new forms outside the documented residual got through). P1-1 (narrowed) and P3-1. Still dark. No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **T-10, round 3** (`backend/tests/test_receipts_append_only.py`): an allowlist of USES, not a deny-list of writes.
  - **What it allows:** a receipts table, or a name bound to one, may appear only:
    - as the subject of `select` / `select_from` / `join` / `outerjoin` / `insert` / `_dialect_insert` / `exists`, or `.c` / `.insert()` / `.join()` / `.select()` / `.alias()`;
    - as `.name` in SQL text;
    - bound to a local name;
    - in `_delete_deck`'s two pinned statements.
  - **What it flags:** passing it on, returning or yielding it, storing it (tuple, dict, attribute, class body, global, module alias), a default, a star, or any other method (`.delete`, `.drop`, `getattr(t, …)`, `Delete(t)`, `drop_all(tables=[t])`).
  - **Name strings:**
    - Constants, `+`, `%`, `.format`, `.join`, names bound to static strings, and loop variables over name tuples all make `metadata.tables[...]`, `.get`, `getattr`, `Table`/`table` lookups references.
    - This replaces the bare-name rule, which flagged QA's admin-counts read.
  - **SQL text:** comments and identifier quotes are stripped; `ONLY`, a schema and `MERGE … THEN DELETE/UPDATE` are covered. `.sql` files are read too.
  - **Pins:** the bindings of `g`, `i`, `contract_ids`, `row_ids` in `_delete_deck` are pinned. No scope nested in it may rebind them (a walrus).
  - **Scoping as Python does it:** comprehensions are their own scope, and a name bound in a function is local to it.
  - **Account deletion:** `accounts._delete_user_data` loops over every private table by name (`receipts_grades` among them) and reuses its loop variables, so name lookups there aren't resolved. A direct reference is still checked, and a test pins `receipts_grades` on `_ADDITIONAL_PRIVATE_TABLES`.
  - **Residual, documented** in the test, `docs/plans/receipts/LLD.md` (T-10 and §3) and the data dictionary:
    - a table reached through a value computed at run time across functions;
    - a runtime `metadata.sorted_tables` search;
    - `exec`/`eval` or a file read and executed;
    - the ORM (waived: none in the codebase).
- **Tests:** 103.
  - **Caught (89 cases):** the clean tree; QA's 27 round-1 and 37 round-2 cases (the ORM pair waived); 25 more of ours (walrus in `_delete_deck`, global, module alias, yield, `.append`, `conn.info[...]`, `.join` SQL, a `--` comment, `UPDATE ONLY`, a second accounts `_del`, …). Each is caught by its intended rule.
  - **Left alone (8):** QA's 6 false positives plus 2 of ours.
  - **Also:** the SQL normaliser; the accounts rights path; the file inventory.
- **0 false positives across all 60 open PRs and main** (each tree scanned).
- **P3-1 (the Calibration deadlock), documented, to fix before the cap goes above 0:**
  - On Postgres the session prune can deadlock with `answer_grading_card` (card, then session). Postgres aborts one side; nothing is left partial.
  - No prune order avoids it: `fold_grading_cards` locks session, then cards. The fix is one order for the two.
  - Written in the prune's comment and in `config-reference.md` on the cap knob.
- **Sabotages:** the 14 deletion sabotages are still 14/14 red.
- **Suites:** T-10, retention, receipts, blind-grading DB, deletion coverage: 265 passed.

## 2026-10-29 — #544 QA: T-10 rebuilt on the syntax tree; grades pinned in the deck's transaction; Calibration at cap 0; sessions before cards

Gates: release-lead's #544 QA (deletion code correct; NOT ready on the guard). P1-1, P2-1, P2-2 and both P3s, on #544. Still dark (cap 0). No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **P1-1, T-10 (receipts' append-only guard):** QA injected 27 non-retention writes, and 21 passed the line-regex over two files. It's now `backend/tests/test_receipts_append_only.py`.
  - **What it reads:** every non-test `.py` under `backend/` and `scripts/`, parsed. In each function and at module level, the names bound to a receipts table are followed through assignments, annotations, walruses, tuple unpacking, loops, comprehensions, `.alias()`, `metadata.tables[...]` / `.get(...)` and `getattr`.
  - **What it flags:**
    - **W:** `delete`/`update` of one (any import alias, `table=` too), `.delete()`/`.update()` on one, an upsert or an `OR REPLACE` prefix on a statement built from one (a statement held in a variable included);
    - **S:** SQL text that writes one (case, whitespace, f-strings, `+` and `%` resolved: delete/update/replace/truncate/drop/alter/upsert);
    - **N:** a receipts table's bare name as a string outside two sites (`_delete_deck`'s count label, accounts' `_ADDITIONAL_PRIVATE_TABLES`);
    - **P:** the retention delete referenced, imported or called outside its chain.
  - **The exemption is the statement, not the place:** `_delete_deck`'s two grade deletes, exactly (by contract ids, by row ids). They were rewritten as their own statements for that, so a "correction" inside `_delete_deck` is caught.
  - **The callers are pinned:** `_delete_deck` only from `purge_deck_evidence`, which only from `server._prune_deck_evidence`, never with `now=` or `**`. The test also asserts both sanctioned statements and both calls are really there.
  - **Scanner tests:** QA's 27 cases plus 22 more (loops over table tuples, a module tuple, `getattr` with a concatenated name, `tables.get`, a `.alias()`, an upsert through a statement variable, `table=`, `sa.delete`, `%` SQL, TRUNCATE, SQL upsert, REPLACE INTO, a name list, a by-reference or imported `_delete_deck`, `**` kwargs, a lambda inside `_delete_deck`, a scripts file). All 49 caught, each by its intended rule. Reads and `on_conflict_do_nothing` inserts stay allowed.
  - **Residual, documented:** a table reached only through a name computed at run time across statements.
- **P2-1:** `test_receipts_grades_go_in_the_decks_own_transaction`. A statement failing after the grade deletes leaves the deck whole and its grades in place. QA's Q6 (own transaction) and Q6b (second connection) are red.
- **P2-2:** the off test and a real-loop-step test (knobs at their defaults, cap 0) seed a Calibration session past 365 days, one dated 2001 (past any clock's cap), and old grades; nothing goes. QA's Q8 and Q8b are red.
- **P3:**
  - Stale "never DELETEd" comments are corrected (`database.py`'s two receipts comments, `docs/plans/receipts/LLD.md` §3 and T-10, the data dictionary's claim).
  - `_delete_old_grading_sessions` deletes sessions before their cards. `fold_grading_cards` first updates its session row, so a racing fold either waits and finds the session gone, or commits first and its cards are caught. A test pins the order.
- **Sabotages, 14/14 red** (the three PR test files): QA's T1–T5, Q6, Q6b, Q7a–c, Q8, Q8b (adapted to the new statement layout), plus cards-before-sessions and the tick passing `now=`.
- **Suites:** the full backend suite: 10047 passed, 2 skipped.

## 2026-10-29 — Retention cap: receipts grades and Calibration's grading tables (head-eng's ruling)

Gates: head-eng's ruling on the c3 list (2026-10-29): `receipts_grades`, `grading_cards` and `grading_sessions` go under the 365-day cap, with no exception named to legal. A follow-up to #523 (#523 itself is unchanged), and still dark: the cap knob is 0. No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **`receipts_grades`:** deleted in the deck's own transaction (`_delete_deck`), by contract ids and by row ids, like outcomes and pass reasons.
  - A packed deck's grades outlive its rows (deleted at 90 days) and go at the cap.
  - The receipts queue ("no grade row yet") reads the rows, which are gone first, so nothing re-grades a deleted deck.
- **Calibration:** `grading_sessions` created before the cap, and their `grading_cards` (the shown trades), go by `created_at`, oldest first, in bounded batches. It's a side step like the page store's, isolated.
- **T-10 (receipts' append-only guard):** it now also catches a write through an alias of a receipts table, so the exception can't hide behind a rename. The one sanctioned exception is the retention delete in `_delete_deck`. The data dictionary says so.
- **Tests:**
  - grades of a packed deck (contract ids) and a pack-less deck (row ids) go at the cap, and a recent deck's stay;
  - a row-less packed card's grade is counted in the deck's transaction;
  - Calibration sessions and cards past the cap go, newer ones stay;
  - the side-step isolation includes grading.
- **Sabotages:** 5/5 red (contract-id grades kept, row grades kept, grading skipped, no cutoff, cards kept). T-10 is red on an aliased delete and on a tuple-alias update outside `_delete_deck`.


## 2026-10-29 — #537 QA P3s: the doc count, QA's drain tests ported, the ceiling line honest, a failed batch's count logged

Gates: release-lead's #537 QA (GO, SQLite + PG 18 in 3 collations), P3-1 to P3-3, taken on #537 before the operator's go. P3-4 (verify `ix_deck_diagnostic_snapshots_created_at` on prod) is release-lead's read-only check. No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **P3-1:** `docs/config-reference.md` § Deck diagnostic retention said "Up to 500 nodes … per tick". It now says 10,000 (20 batches of 500, each its own transaction, oldest first, stopping at a short batch) and quotes the ceiling line.
- **P3-3, the ceiling line:** `server.py` multiplied by a hard-coded 500, and "a backlog remains" was wrong when exactly 10,000 were all there was. Now:
  - `_DIAG_PURGE_BATCH = 500` is passed as `batch_size`;
  - the line says "(the tick's ceiling: more may remain)". A tick can't tell; the next one says.
- **P3-3, a mid-tick failure:** `purge_deck_diagnostics` logs "deck diagnostics purge: N expired snapshots deleted before a batch failed" (the earlier batches stay committed), then re-raises to the loop's handler.
- **P3-2, QA's tests ported:** `backend/tests/test_deck_diagnostics_drain.py`, 10 tests (SQLite; QA ran the correctness half on PG):
  - exact deletion at the cutoff (18 stamp shapes);
  - NULL `created_at` rejected by the schema;
  - the 20 × 500 ceiling oldest-first with fresh rows untouched (20 reads, 20 deletes, 20 commits; then 6/5; then 1/0);
  - a short batch stops the call;
  - one transaction per batch, and the failure's count log;
  - the one-batch default; degenerate args;
  - one real `_cleanup_loop` tick (10,000 + the ceiling line, then 2,500, then nothing);
  - exactly 10,000 says "more may remain";
  - a failing purge never stops the loop.
- **Sabotages, 12/12 red:**
  - QA's S1–S7 (S7 on the new wording), including the four that survived the first 13 tests: one transaction for all batches; stop only on an empty batch; the cutoff via `str()` / `isoformat(sep='t')`; the ceiling log dropped;
  - new: no failure-count log; "a backlog remains"; `>` for `>=`; a failure swallowed.
- **Suites:** every test touching the cleanup loop or the purge: 344 passed.

## 2026-10-29 — Diagnostics expiry drains up to 20 batches a tick (head-eng check 3)

Gates: head-eng's check 3, from release-lead's prod sweep: "Purged 500 expired deck diagnostic snapshots" every 5 minutes, always at the 500 cap, so expired rows may be backing up past the 30 days the c3 list promises. No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **`purge_deck_diagnostics(days, batch_size, max_batches=1)`:** up to `max_batches` bounded batches of the oldest. Each is its own transaction: the ids are read through the `created_at` index, then deleted by primary key. It stops at the first short batch.
  - The default of 1 keeps the old one-batch call.
  - The cleanup loop passes `_DIAG_PURGE_MAX_BATCHES` = 20: 10,000 rows a tick, 2.88M a day, against 144k before.
  - It logs "(the tick's ceiling: a backlog remains)" when it hits the ceiling, so the prod read shows whether it caught up.
- **The backlog's size and age** need a read-only prod query (release-lead): the oldest `created_at`, the count past 14 and past 30 days, and rows written a day.
- **Tests:** `test_deck_diagnostics.py`. A call drains up to `max_batches` and stops at a short batch (one read, counted); the loop passes the ceiling.
- **Sabotages:** 3/3 red (one batch only, no short-batch stop, the loop without the ceiling).
## 2026-10-29 — Mobile async guards fail when a check hangs (check-win-now-recovery passed 7 of 39 silently)

Gates: engagement-eng's report (release-lead's #488 QA found it). Test harness only: no app code, route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is the suites themselves.

- **The defect:** `mobile/tests/check-win-now-recovery.js` sets `process.exitCode` only when `main()` completes. An `await` that never settles drained the event loop, and node exited 0 after 7 checks.
  - On main all 39 run (8 runs, two `node_modules` installs). On #488's head (`5031fb40`) T3 hangs, so #488's break looked green.
- **The fix:** the guard `check-device-first-page.js` and `check-gate-miss.js` already use: `finished`, a `process.on('exit')` that fails an unfinished run, and `finished = true` before the summary. It's now in the six other trades-owned async suites: `check-win-now-recovery`, `check-win-now`, `check-trade-pages`, `check-trade-disposition`, `check-owner-offer-signals`, `check-fairness-default`.
- **`mobile/tests/README.md` § Writing one:** an async guard must fail if it never finishes.
- **Proof:**
  - **6/6:** a `new Promise(() => {})` injected before each suite's finish now exits 1 with "did not finish". Without the guard (the control) each exits 0.
  - **#488's tree:** the guarded recovery suite exits 1 instead of 0.
  - **All 126 `mobile/tests/check-*.js`** pass on the branch.
- **T3's hang on #488 (diagnosis, handed to engagement-eng):**
  - The cause: `apiRequest`'s catch now `return`s the async `_afterGateFailure(...)` instead of `throw err`. With the gate off, that adds microtask hops before the 409 retry schedules its backoff timer. The harness's `flush()` drains 80 ticks, so the timer is scheduled after `advance()` has moved the clock past it, and it never fires.
  - Deepening `flush` to 400 completes T3. Throwing synchronously when the gate is off (`if (opts.background || !_gateIsOn()) throw err;`) runs #488's own test file 39/39.
- **Not touched (other teams' async suites, no guard; routed to head-eng):** `check-apple-revoke-on-delete`, `check-espn-cookies`, `check-league-picker-recovery`, `check-send-timeout`, `check-sleeper-ownership`, `check-vault-subsumes-legacy`.

## 2026-10-29 — G3-e: `deck_outcomes.user_id`; account deletion and export also match an outcome by its owner

Gates: full (an additive schema change). Scope block: `docs/plans/trade-time-to-suggestion/scope-outcome-owner.md`. head-eng's R28.22 routing, item G3-e. Docs: `data-dictionary.md` § `deck_outcomes`, and `api-reference.md`'s `DELETE /api/account` and `GET /api/account/export` rows. No flag, event or client change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **The change:** `deck_outcomes.user_id` (nullable) plus `ix_deck_outcomes_user`.
  - Written by `save_deck_outcome` from `acting_user_id`.
  - Deletion deletes by it after today's row path, under its own count, `deck_outcomes_by_owner_deleted`. Export adds by it, deduped and in id order.
  - `scripts/purge_entry_users.py`'s `DELETION_ONLY_KEYS` gains the column.
  - The index is **never built at boot** (revised after release-lead's question, same day). A plain `CREATE INDEX` blocks every outcome write for its scan. A fresh DB gets it from the declaration. On prod it's built by `scripts/create_outcome_owner_index.py` (`CONCURRENTLY`, 5 s `lock_timeout`, autocommit, an INVALID leftover rebuilt), run once after the deploy on the operator's word. Until then deletion and export scan. No backfill.
- **Code walk (the gap is latent, not live):** `save_deck_outcome` is the only outcome writer, and its insert requires an owned `deck_impressions` row (`owner.exists()`). So a #535 deck (no rows, no pack) gets no outcome today: the write is dropped as an `unknown` reject. The column makes the owner a property of the outcome itself, whatever later prunes or never wrote its row.
- **Tests:** `backend/tests/test_deck_outcome_owner.py`, 7:
  - the write and the session path stamp the owner;
  - deletion reaches a column-only outcome (an alias's too), with the right counts and the others kept;
  - export has each row once, in id order;
  - boot on the old table adds the column and never the index, idempotent, no backfill; a fresh DB gets the index;
  - the script builds it on an existing table, `--check` writes nothing, idempotent;
  - the script's Postgres build pinned (`CONCURRENTLY`, autocommit, `lock_timeout`, INVALID dropped).
- **Sabotages, 16/16 red** (the new file, `test_purge_entry_users.py`, `test_account_deletion_coverage.py`):
  - a NULL owner;
  - the deletion: no owner delete; owner delete moved first;
  - the export: no owner match; no dedupe; no sort;
  - the migration: no column; the index built at boot; no metadata index;
  - the script: not `CONCURRENTLY`; not autocommit; no `lock_timeout`; INVALID not dropped; `--check` builds; the wrong column;
  - the purge key missing.
- **Suites:** the full backend suite on the first version: 9831 passed, 2 skipped. On the revision: 9832 passed, 2 skipped.
- **The #523 resync (2026-10-29, after #523 merged as `f7b6ec4d`):**
  - The export block keeps all three paths: #523's rows plus pack contract ids (chunked), then G3-e's owner select, deduped by id, sorted once.
  - Added QA's `test_three_paths_one_run` (onboarding-eng's ask): one outcome reachable only by its row, one only by a pack contract id, one only by `user_id`. Each is exported once, all are deleted in one run, and another user's outcome past the pack's `card_count` stays.
  - 4/4 sabotages fail it: either path dropped from export or from deletion.
  - The 39 test files touching `deck_outcomes`, retention, purge and deletion coverage: 1555 passed.
## 2026-10-29 — Exit guards on three async mobile check suites (platforms-eng; head-eng ask from trades-eng's #546 finding)

Test-only (`mobile/tests/`), no app code. D-056 posture. `check-espn-cookies.js`, `check-send-timeout.js` and `check-vault-subsumes-legacy.js` had no exit guard: an `await` that never settles, or an early `return`, let the event loop drain and node exit 0 mid-run, so a green run wasn't evidence.

- **Change:** each gets `check-device-first-page`'s pattern (mobile/tests/README.md § Writing one): `let finished = false;` + `process.on('exit')` that sets `exitCode = 1` and prints "did not finish" when the run never reached its end; `finished = true` just before the final report. 12 lines each.
- **Sabotage, each run with and without the guard, then restored (byte-identical, clean run exit 0):**

| Suite | early `return` | hung `await` | `throw` |
|---|---|---|---|
| check-espn-cookies | guard 1 / none 0 | guard 1 / none 0 | 1 / 1 |
| check-send-timeout | guard 1 / none 0 | guard 1 / none 0 | 1 / 1 |
| check-vault-subsumes-legacy | guard 1 / none 0 | guard 1 / none 0 | 1 / 1 |

  (A throw already exits 1 via the unhandled rejection; the guard is what catches the return and the hang.)
- **Not here:** #539's new `check-send-registry.js` has the same gap; it gets the guard on #539 or right after it merges (release-lead's call).
## 2026-10-29 — Exit guards on three async mobile suites (head-eng's ask, from trades-eng's #546 finding)

Test-only: no app code, no user-visible change. D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **The gap:** `check-apple-revoke-on-delete.js` (#446), `check-league-picker-recovery.js` (the 10-17 incident) and `check-sleeper-ownership.js` (#279) are async and had no exit guard. A run that returned early or awaited something that never settled let node exit 0 mid-run, so a green run there wasn't evidence.
- **The fix:** `check-device-first-page`'s pattern in each: `let finished = false` with an `exit` hook that fails an unfinished run (`process.exitCode = 1` plus a "did not finish" line), and `finished = true` right before the summary.
- **Sabotage, before the last check, guarded vs `origin/main`'s unguarded copy:**

  | suite | early return | throw | hang (a never-settling await) |
  |---|---|---|---|
  | guarded (all three) | exit 1 | exit 1 | exit 1 |
  | unguarded on main (all three) | **exit 0** | exit 1 | **exit 0** |

  Restored byte-identical. A throw already failed (an unhandled rejection, or the suite's own `.catch`). The guard is what catches the other two.
- **Runs:** each suite passes, exit 0; the full `check-*.js` loop is run on the PR.

## 2026-10-29 — The model-store hook hardened (#542 QA P3s)

Gates: eval code only (`backend/eval/redaction.py`) plus the runbook. No route, schema, event, flag, knob or engine-module change. The hook stays dark until trades-eng's scrub calls it.

- **The token map is validated** (`redaction.check_tokens`). Every value must start with `redacted:` and must not itself be a key of the map. Otherwise it raises `ValueError`, naming a count and never an id. A map like `{"u7": "u70"}` would otherwise re-key a deleted user's pairs onto a live user.
- **A symlinked store path** resolves to its target (`os.path.realpath`), so the id can't survive there.
- **The temp file** is `fchmod`ed inside its `fdopen`, so no fd leaks when `fchmod` fails, and it's fsynced before the replace.
- **QA's four store cases are ported:**
  - prefix-sharing ids (deleting u7 or acct_1 leaves u70, u700 and acct_12 alone);
  - any store mode kept (0600, 0640, 0664);
  - a failure at any step (`mkstemp`, `fchmod`, `fsync`, `replace`, an interrupt at `replace`) leaves the store's bytes, inode, mtime, mode and open fds untouched, with no temp file;
  - a concurrent reader sees only whole states, and each rewrite is a new inode.
- **Runbook:** never run `python3 -m backend.value_model --refit` while the daily tick runs. The scrub retries the hook when it raises.
- **Tests:** `test_eval_redaction_model_store.py`: 25 (+14).
- **Correction to #542's entry:** that PR added +2 tests to this file, not +3. The entry stands as written; the ledger is append-only.
- **Sabotage, each red then restored (3):** no map check; no `realpath`; `fchmod` before `fdopen`. The fsync is durability-only, so no test can show it.
- **Suites:** all `test_eval_*` plus `test_evidence_pack.py` and `test_deck_value_model.py`, on main @ `7edc9e74`: 485 passed.

## 2026-10-29 — The model-store hook under legal R28.22; #529 QA P3s

Gates: eval code only (`backend/eval/{redaction,data,flip_read,scorers,bdk_audit}.py`) plus docs. No route, schema, event, flag, knob or engine-module change. The hook is still dark until trades-eng's scrub calls it, in the daily tick before `nightly_refit`.

- **R28.22 (legal f, c3 #14):** `redact_model_store` now handles the two kinds of key differently:
  - a `partner_rates` key whose **viewer** is a deleted user, meaning their own rates, is **deleted**;
  - a key whose **partner** is a deleted user takes the token.
  - Until now both sides took the token.
- **#529 QA P3s:**
  - **Collision:** a re-keyed pair already present under the token keeps the token's rate, in either key order.
  - **File mode:** the rewrite keeps the store's file mode; `mkstemp`'s default is 0600.
  - **G1:** the whole-header move check reads each deck's W0 indexes. A later move naming a never-delivered card now fails G1 at once, just as the loader fails a delivered one.
  - **Doc fixes:** the logged-key contract (`position`, F2), `EXCLUSION_RULE_VERSION` 6 in the runbook, the scorers' honesty rule, F1's non-canonical-key wording, and B-DK-6's served-cards scope.
  - **E-b3's wording** follows models-lead's addendum G.
- **Tests:**
  - `test_eval_redaction_model_store.py`: 11 (+3, and the first test rewritten for R28.22).
  - `test_eval_display_moves.py`: +4 (the G1 W0 move, ×2; a pack with no deliveries, ×2).
- **Sabotage, each red then restored (4):**
  - viewer keys kept;
  - an overwrite on collision;
  - no `fchmod`;
  - G1 without the W0 check.
- **Suites:** all `test_eval_*` plus `test_evidence_pack.py` and `test_deck_value_model.py`: 471 passed on main @ `9370670e`.

## 2026-10-28 — Eval follow-ups: models-lead's F1–F4, E-b5 and the E-b3 hook; #501 and #503 QA P3s; #515's `market_coerced`

Gates: eval code only (`backend/eval/{data,replay,scorers,contract,persistence,flip_read,bdk_audit}.py`, the new `backend/eval/redaction.py`), plus the runbook and evidence-contract lines. No route, schema, event, flag, knob or engine-module change: `value_model.py` is untouched, and the hook lives in eval. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **F1 (re-read stability):**
  - The loader checks only `display_moves` delivered as of the read. A malformed later move leaves a same-as_of re-read stable, and a read past that delivery is `pack_integrity`.
  - G1 also checks every pack's whole move record (`data.display_moves_problem`), past `as_of` included, so the writer is flagged at once (`display_moves_malformed`).
- **F2:**
  - `EXCLUSION_RULE_VERSION` goes from 5 to 6.
  - `LoggedOrderScorer` ranks by displayed position: `card_dict` gains the logged `position`, which the contract grants only to `logged`.
- **F3:** B-DK-4..6 exemptions are split by deck (`protected_by_deck`: recorded / no record) and printed.
- **F4:** "B-DK-7 after-cut: not checked (n)". n counts the live-evidence (no-pack) Trades decks with a never-delivered withdrawal inside their first `REPEAT_WINDOW` cards.
- **E-b5:** `EvalRun.redacted_partners` is the distinct `redacted:` tokens among the window's partners, rows and packed cards alike. It's persisted and printed, a count only.
- **E-b3:** `backend/eval/redaction.redact_model_store(tokens)`, the deletion scrub's hook.
  - It rewrites every value-model record's `partner_rates` keys naming a deleted user, as viewer or as partner, to that user's token. Rates are kept.
  - The write is atomic; a re-run with the same map is a no-op; the serve cache reloads.
  - If the store keeps changing under it, it raises so the scrub retries.
  - **Added 2026-10-29 (head-eng's check, (a) and (b)):**
    - A torn line that may hold a deleted id is dropped and counted; that covers a whole id and a line cut off mid-id. The loader skips such lines, so serving is unchanged.
    - The window is documented: no lock exists to share, so the scrub must call the hook before `nightly_refit` in the daily tick.
- **Redacted partners in the B-DK audit (head-eng, 2026-10-29):** a card whose partner is a `redacted:` token is not auditable for B-DK-4..7, because the scrub removes its protection and the partner's `qb_te`. Its deck counts as incomplete for B-DK-7. The count is `redacted_cards`, printed.
  - `_short_deck` is unchanged: a scrubbed protection can only break the fixed point, never make one.
  - Tests: +2 audit tests (3 cases), +4 model-store cases.
  - Sabotage, each red then restored (6): the card loop's redaction check; the repeat check; never dropping a torn line; no mid-id tail match; no render line; a substring match on the prefix.
  - All `test_eval_*` plus `test_deck_value_model.py`: 415 passed.
- **#529 QA (release-lead, NO-GO on CI only), 2026-10-29:** F2's logged `position` failed four `test_evidence_pack.py` guards. None of my suite lists ran that file.
  - The codec is unchanged (PACK_VERSION 1 is frozen). `position` is rebuilt by the reader, like `impression_id`: the two contract tests exempt both (`REBUILT`), and the golden's scorer check (c) re-adds `position` to the round-tripped cards.
  - `test_evidence_pack.py`: 50 passed. **Full `pytest backend/tests`: 9741 passed, 2 skipped.**
- **#501 QA P3s:**
  - An anchor not after its card is rejected.
  - Ghost and null cases are pinned (QA's probes).
  - G7 leaves a `pack_integrity` deck's upgrade misses to G1, as row gone already did.
  - The `pack_integrity` doc line now says a moves-integrity pack keeps its cards merged.
- **#503 QA P3s:**
  - A record whose market value is neither null nor a number (or whose `market_coerced` isn't a list of str) is `record_failed`.
  - The position half of coverage is pinned.
  - The B-DK-7 scope line is corrected.
- **#515's `market_coerced`:** a card holding a listed asset is not auditable for breakup and filler. B-DK-6 still checks it.
- **Tests:**
  - `test_eval_display_moves.py`: 33 (+7: two undelivered malformed records left to G1, F1's re-read, two ghost cases, null, the logged scorer, G7).
  - `test_eval_bdk_audit.py`: 77 (+8: coerced, four malformed records, position coverage, F3, F4).
  - `test_eval_redaction.py`: 3. `test_eval_redaction_model_store.py`: 5.
  - The version pins moved to 6, and the G1 and report version strings changed.
- **Sabotage, each red then restored (11):**
  - F1 validating every move (4 red);
  - no anchor-after check;
  - no G1 whole-header check (3);
  - G7 counting `pack_integrity` decks;
  - the logged scorer by `card_index`;
  - `market_coerced` ignored;
  - no market-value check (2);
  - F3 always "recorded";
  - F4 without the window bound;
  - E-b5 matching a substring;
  - the redaction on the viewer side only (2).
  - The clean run: 205.
- **Eval-related suites** (`test_eval_*`, `test_value_model*`, packed and deferred evidence, blind grade, scorecard, the new redaction tests): 811 passed.
- **B-DK-6 with a coerced ±inf** (release-lead's #515 QA): it stays audited. The null can only lower the audit's count below the filter's, so a served card's verdict can't flip; QA saw mismatches on dropped cards only.
## 2026-10-29 — #525 re-QA: a new search answered with inputs_changed is read afresh (P1-1r); checklist paths

Gates: release-lead's #525 re-QA at `2546963b`. Every earlier fix was verified by their harness; this is the one residual, plus the checklist. Same PR (11-06 binary). D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **P1-1r:**
  - **The case:** a Try again (N3), or a tap while a re-search is pending (N3b), whose own answer is `inputs_changed`, on a deck already holding a revoked job. Its answer reset the budget, but the error mirror and the auto re-search effect keyed only on `job?.status` and `job?.error`, which were unchanged. So nothing re-read the error: `('idle', 'inputs_changed')` hid it with nothing pending.
  - **The fix:** both effects now depend on `job?.job_id` too (release-lead's harness-verified fix). The new search gets its one re-search, then the error card.
  - **Checks:** executed 11p (from `used` and from `pending`); 11q pins both dependency lists.
- **Checklist (P2):**
  - a GET-side-only player or Specific Team with an empty canvas (a give-side pin runs the fair sweep, which never sees `inputs_changed`);
  - the end card's real copy, "You've seen every trade for now.";
  - Pass, not Like (a Like may reach a real leaguemate);
  - step 5 needs a cold search with a visible wait.
- **Stale §10 references:** fixed in the scope and LLD (the section is §11).
- **P3s accepted, not changed:**
  - **N4:** a re-search may fire alongside a tap's own request: one extra generate, rare. The server joins the same-key job. Guarding it would reopen an empty-slot path when the tap's request fails.
  - **N2:** Retry while offline shows the error card, and two generates run on reconnect. The mutations are paused offline, so this is pre-existing offline behaviour.
- **Checks:** `check-trade-first-card-events` (11a–11q) and the related suites pass; `tsc` is clean.

## 2026-10-29 — #525: R2 names the re-search's response, not the revoked one (analytics-lead)

Gates: analytics-lead's ask after release-lead's #525 QA P3: R2's `job_id` named the revoked job, which broke R2-to-deck joins, and its `serve_source` was misattributed. No taxonomy change and no new prop. Mobile only. D-056: `FTF_SKIP_SIM_GATE=1` posture; the evidence is the check suite and tsc.

- **The change:** `noteFirstResponse(searchId, first, { replace })`. The automatic re-search's answer passes `replace: !!vars.research` and overwrites the open trace's `job_id`, `serve_source` and `freshness_state`.
  - Every other response stays first-wins, and a settled trace never changes.
  - Timing still runs from the original tap, and R2 fires once.
- **Checks:** `check-trade-first-card-events` §11 (ii) is extended. 11m: R2 carries the rebuilt response's three fields. 11n: an ordinary later response doesn't overwrite, and a settled trace doesn't change. 11o: only the re-search's answer passes `replace`.
- **Sabotages:** 5/5 red (never replace, always replace, replace a settled trace, the screen never or always replacing).
- **Other evidence:** the five related suites and `tsc` are green.

## 2026-10-29 — #525 QA (NO-GO at `05fee1fa`), fixed: no endless empty slot; the re-search paged; the offline card; checklist

Gates: release-lead's #525 QA, P1-1, P2-1 to P2-3 and P3s. Same PR (11-06 binary). No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture; the evidence is the check suites, tsc, and the TestFlight checklist in the scope block.

- **P1-1, the endless empty slot:**
  - **Before:** Try again reset the re-search budget at dispatch. When its request failed, the revoked job stayed, `('idle', 'inputs_changed')` hid the error, and nothing re-ran.
  - **Now:** only a new search's *answer* resets it (`autoResearchAfterAnswer` in `onSuccess`), and the hide holds only while the re-search itself is in flight (`generateMutation.variables.research`).
  - **Check:** executed case 11l (c2).
- **P2-1, the un-paged re-search:** `generateTrades(request, { searchId: vars.searchId })`. Every dispatch sends `page: 1`, plus `search_id` only when it has one, so the re-search after R2 is paged. `check-trade-pages` 5a pins it (its regex used to pin the un-paged line).
- **P2-2, with #488:**
  - the re-search carries `research: true` on the mutation's variables, so #488's D2 can treat it as background, like `vars.auto`;
  - the after-402 end state is agreed with engagement-eng (whoever merges second wires it);
  - this section is now §11, ahead of #488's §10, which ends in an async exit.
- **P2-3:** the TestFlight checklist is rewritten:
  - a pinned cold search, with the change made while the deck builds;
  - "the end card means it didn't trigger: redo";
  - safety notes (the board edit, never Send/Propose, no Sleeper roster move);
  - which decks pass the error through after the flip;
  - `testing.timing_readout`.
- **P3s:**
  - offline while recovering shows the Offline card, not an empty slot;
  - `trades_generated` carries no search_id (the scope's wording fixed);
  - the R2 `serve_source` skew is flagged to analytics-lead.
- **Checks:** `check-trade-first-card-events` (all, with 11a–11l) and `check-trade-pages` pass, and `tsc --noEmit` is clean.

## 2026-10-28 — The automatic re-search on `inputs_changed` (analytics-lead's option (a); for the 11-06 binary)

Gates: release-lead's #470 QA P2-1 follow-up; analytics-lead's grant of option (a) with conditions (2026-10-28, cc head-eng and head-product); head-eng: build once that answer came. The scope block is `docs/plans/trade-time-to-suggestion/scope-auto-research.md`. Mobile only; no event, value, flag, route or schema change. D-056: the evidence is the structural check, a code-walk and a TestFlight checklist.

- **The change:** a deck the server revoked for an input change (`status: 'error'`, `error: 'inputs_changed'`) re-searches once, by itself, when the user has no card left, instead of "Couldn't load more trades."
  - No R1, and no new search_id: the open trace's id, else none.
  - No R2b: no deckFailure.
  - At most once per search.
  - The error card is hidden at render while it recovers.
- **`check-trade-first-card-events.js` §10** (10a–10k, all pass):
  - analytics-lead's four cases, executed against `utils/tradePages.ts` and the real `state/tradeSearchTrace.ts`;
  - the TradesScreen wiring, by shape.
- **Census counts updated for the 8th dispatch site:** `check-canvas-results` 12a, `check-inline-home` 7f, `check-results-push` 4f, `check-offer-prefill-330` S-2 and `check-trade-pages` 5a (its shape).
  - All five passed on main and failed after the change until updated: they caught the new dispatch site, as designed.
  - Every `mobile/tests/check-*.js` passes. `tsc --noEmit` is clean; testid-lint is OK.
- **Sabotage, each red then restored (6):**
  - the recovery removed (10g);
  - a minted id for the re-search (4a, 10i);
  - the id sent when the trace has settled (10a);
  - a second re-search allowed (10f);
  - the error card not hidden (10j);
  - the re-search through a tap path (10h).
- **TestFlight:** the scope's §3 checklist (6 steps, two devices), for the operator on the 11-06 build. Not yet run.

## 2026-10-28 — Paywall price rise moves to 2027-01-02 04:00 UTC (App Store Connect's US start for a Jan-2 schedule; follow-up to #494)

Gates: a value change to the merged #494 (`bef9f5db`), as its own PR off main (`fix/paywall-rise-jan2`), requested by monetization-pm (head-product authorized; the operator approved scheduling both App Store price changes for 2027-01-02 on 2026-10-28). release-lead delta-QAs it. Still dark (`monetize.paywall`). D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **Change:** `_PAYWALL_PRICE_RISE_AT` = `datetime(2027, 1, 2, 4, 0, tzinfo=utc)` (was 2027-01-01 08:00Z, LA midnight). Per monetization-pm, citing Apple's start-times table, a change scheduled for 2027-01-01 starts in the US at 2027-01-01 04:00Z (11 pm ET on Dec 31), which breaks Terms §14.8; a 2027-01-02 schedule starts at 2027-01-02 04:00Z (11 pm ET / 8 pm PT on Jan 1). Apple's table renders its times client-side, so the 04:00Z figure is not independently checked here; monetization-pm's setup §3d records the time App Store Connect shows, and the constant moves if it differs. The comment block, api-reference row and cross-client-invariants SKU rows + fallback bullet say the same.
- **Tests (`test_paywall_config.py`, 43):** both sides of the new instant (`2027-01-02T03:59:59Z` old, `04:00:00Z` new); the Jan-1 schedule's US start (`2027-01-01T04:00Z`) and the previous LA-midnight instant (`2027-01-01T08:00Z`) now serve the old prices; the constant equals 23:00 Jan 1 New York and 20:00 Jan 1 Los Angeles via `zoneinfo`, and the last second of Dec 31 in Honolulu is before it; time-zone instants (NY 23:00 Dec 31 old, LA midnight Jan 1 old, NY 22:59:59 Jan 1 old, NY 23:00 Jan 1 new, LA 20:00 Jan 1 new, Paris 00:30 Jan 1 old). 43 passed.
- **Sabotage, each red then restored:** the old 2027-01-01 08:00Z instant → 6 red; a Jan-1 schedule's 2027-01-01 04:00Z → 9 red.
## 2026-10-29 — #521 QA P3s: the drafted-league retry, the retry lock-free, no retry on a pool timeout; deck pipeline v8

Gates: release-lead's #521 QA (GO-with-notes), P3-1 to P3-3. Follows #521. P3-4 (the PR body) is fixed on #521 itself. No route, schema, flag or event change. Deck pipeline v8, digest `f7ed33e6ab94af03`; models-eng classifies. Only stored pages carry the version, and `trade.first_page_store` is off in prod, so nothing is invalidated there. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **P3-1:** `test_a_draft_read_retried_once_keeps_the_drafted_context`. With a drafted leagues row (2026, high), a draft read that fails once leaves the owner context `drafted` with next draft year 2027, and the stamp is kept. Before, the fixture had no leagues row, so `{}` read the same either way.
- **P3-2:** `test_the_retry_runs_with_no_registry_lock_held`, for both reads. Owner-tracking proxies on `_trade_jobs_lock` and `_sessions_lock` show neither attempt holds either lock.
- **P3-3, code:** a pool checkout timeout (`sqlalchemy.exc.TimeoutError`, `_is_pool_timeout`) is never retried at once. The pool is exhausted, and a retry would only wait again and add to it. The read fails as before v7.
  - `_is_pool_timeout` is classified in `DECK_PIPELINE_FUNCTIONS`, since it decides whether the owner arm forfeits.
  - Pipeline v8.
  - **Test:** `test_a_pool_timeout_is_not_retried` (one call; the owner arm forfeits).
- **Sabotages, 7/7 red:**
  - QA's Q3d (the draft retry's result dropped), Q3b (the failure from the failed attempt kept), Q1a and Q1b (a retry under either lock);
  - the timeout retried (draft / picks);
  - `_is_pool_timeout` always False.
- **Suites:** freshness-roster, digest, page store, p2, filter inputs, deferred evidence: 437 passed.
## 2026-10-29 — #523 QA: account rights reach pruned decks' outcomes; id-bounded legacy delete; P3s

Gates: release-lead's #523 QA (GO-with-notes to merge dark; "fix two things in this PR"). Same PR, still dark (cap 0). No route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **P1-1, flip-blocking:** account export and deletion found a user's `deck_outcomes` only through their `deck_impressions` rows. After the full-row bound deletes a packed deck's rows, its outcomes (kept by contract id) were exported never (0 of 24) and deleted never (24 left forever).
  - Now `accounts` also matches the user's packs' contract ids (`database.deck_pack_contract_ids`, in 500-id chunks), for outcomes, the export and the `suggestion_trade_links` unlinking.
  - This also closes E-b4: a packed card's outcome that never had a row.
- **P2-1:** `_delete_old_trade_impressions` used an IN over a LIMIT subquery, a Postgres semi join over the whole table every tick (2.9 s cold at 2M rows). It now takes an id bound, `id <= the limit-th id (else max) AND shown_at < cap`, a primary-key range.
- **P3s:**
  - tests for exact ids (decks `abc`, `abc:1`, `abcd`) and for the first-delivery clock (re-served rows), packed and pack-less;
  - `counts["decks"]` counts only decks deleted;
  - a non-finite or over-36,500 bound is refused, and every refusal is logged once per value, not every tick (NaN, inf and 1e9 raised a traceback each tick);
  - the served index is checked again hourly, so a dropped index stops the pack-less scan.
  - A full-row knob is validated before it's compared with the cap.
- **Tests:** `test_deck_evidence_retention.py` 41 (was 29):
  - export and deletion with and without a full-row prune;
  - `deck_pack_contract_ids`;
  - exact ids; the clock ×2; the id-bounded batches;
  - refused bounds ×4; the index recheck.
- **Sabotages, 43/43 red:**
  - QA's list: my 24 and their X1a/b, X2a/b/c, X3a/b, X4, X5; T01, T15, T16 and X4 re-expressed where the code moved;
  - 7 on the fixes;
  - 3 on `accounts.py`: deletion, links and export by rows only.
- **QA's files on SQLite:** `test_qa523_rights` documented the gap, and its "pruned" asserts now flip. `test_qa523_correct` passes 13/14; the one red asserts the old "decks counts attempts", which P3-2 changed.
- **Suites:** retention, the four account suites, model_config log, packed and deferred evidence, digest, eval pack reader: 406 passed.

## 2026-10-28 — Deck-evidence retention prune, legal R28.20 (iii) final, dark until the cap is set

**Gates:**
- **The rules:** legal's R28.20 (iii) bounds (365 days for every deck-evidence store, 90 for full rows) and models-lead's addendum E (E-a1 deck-atomic, E-c1/E-c2 full rows of packed decks, ghosts included; E-a3 pack-less decks keep their rows under the cap), relayed by head-eng.
- **Full gates:** the scope block is `docs/plans/trade-time-to-suggestion/scope-evidence-retention.md`.
- **What changes:** two new `model_config` keys and one index. No route, flag, event or column change.
- **Evidence:** backend only. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

**The prune:** `database.purge_deck_evidence`, run by the cleanup loop's `_prune_deck_evidence` once per five-minute tick, measured from first delivery.
- **The cap (`deck_evidence_retention_days`, 365):** up to 200 decks per tick, each in one transaction. Every store goes at once: outcomes and pass reasons (a packed card's by exact contract ids from the pack's `card_count`, a row's by its id), rows, withdrawals, the candidate set, `bakeoff_runs`, `trade_policy_shadow` and the pack. Legacy `trade_impressions` and `trade_page_store` rows past the cap go too (the page store's own eviction runs only while it's on).
- **Full rows (`deck_evidence_full_row_days`, 90):** a packed deck's rows go, in 500-pack chunks resumed from an in-memory cursor. Pack-less decks keep their rows until the cap.
- **Off at a cap of 0** (the default). Either bound under 56 days is refused and logged.
- **Replaced from the first cut:** the 2027-01-01 date floor is gone (with 90/365 final it never binds). Outcomes and `bakeoff_runs` used to be kept; they now go with the deck.

**The index:** `ix_deck_impressions_served` is declared (fresh DBs get it), but on prod it's built off the boot path by `scripts/create_evidence_retention_index.py` (`CONCURRENTLY`, a 5 s `lock_timeout`, rebuilds an INVALID leftover).
- Until it exists, the cap skips pack-less decks and logs once. Packed decks use `ix_deck_evidence_packs_served`.
- My first cut built it in `init_db`, against the data dictionary's rule (a plain index on prod's `deck_impressions` can outlast the 120 s boot timeout); caught before push.
- **Outcome matching** is by exact ids, never a LIKE or a string range. Under prod's default collation, punctuation sorts at a lower collation level, so neither is a plain index range.

**Backend:** `test_deck_evidence_retention.py`, 29 tests:
- **Off:** off at 0, full rows included; both 56-day floors.
- **The cap:**
  - every store of a packed and of a pack-less deck goes at once, including a like and a pass reason on a packed card with no row;
  - no other deck's outcomes go;
  - a 1,200-card pack loses every outcome;
  - the pack-less scan never takes a deck whose pack is inside the cap.
- **Full rows:**
  - they go at 90 and everything else stays (the outcome count is unchanged);
  - pack-less decks keep their rows;
  - rows follow the cap with the bound at 0, 365 or 400;
  - chunks resume from the cursor;
  - a failed chunk keeps the cursor.
- **Bounds and batching:** both bounds are measured from the first delivery; one bounded batch per call; a failing deck is left whole; a failing `trade_impressions` or page-store step never stops the others; `trade_impressions` and page-store rows past the cap go (page rows with the store's flag off).
- **The loop step:** reads both knobs, its defaults match `model_config`'s, never raises, and the loop runs it.
- **The index and script:** pack-less decks wait for the index (logged once); the index is never built by `init_db`; the script builds it, is idempotent, and `--check` writes nothing.

**Sabotages:** 24 of 24 mutations turn the suite red:
- the floor;
- each store kept: contract outcomes, row outcomes, contract pass reasons, row pass reasons, `bakeoff_runs`, `trade_policy_shadow`, withdrawals, candidate sets;
- only the first 500 contract ids;
- the pack-less scan taking a packed deck;
- full rows deleted for any deck;
- no cursor advance; the cursor advancing on a failed chunk;
- `trade_impressions` with no cutoff, skipped, or not isolated; the page store with no cutoff or skipped;
- no batch bound;
- the loop skipping the step, or ignoring the full-row knob.

## 2026-10-28 — A live stamp on a deck with no evidence is logged (#517 QA P3-2, models-eng)

Gates: #517 QA P3-2 and models-eng's ask for a server-side count of decks eval can't see. A diagnostic log line only; no route, schema, flag, event or behaviour change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **The case:** a deferred deck whose page row was stored without its evidence blob and that has no pack. After its job leaves, its deliveries take the live-stamp path, which stamps and withdraws only rows that exist. So its cards reach eval nowhere, and an outcome on one is a G3 orphan.
- **What the common P3-2 shape does instead:** a first delivery after the job left on a truncated stored deck is an S1b partial run (rows and withdrawals, no pack, by design). Eval sees it.
- **The signal:**
  - `database.stamp_live_deliveries` now returns False when it delivered cards of a deck with no row at all: one indexed `LIMIT 1` probe, and only when there are cards.
  - `_deck_live_stamp` logs it at ERROR: `deck-evidence <deck_job_id>: n delivered cards of a deck with no evidence (no rows, no pack); eval can't see them`. It carries no user id.
- **Tests:** in `test_packed_evidence.py`, the return value (a deck with rows, one with none, no cards) and the ERROR line (logged only with no rows, with no user id). 3 sabotages red: always True, the empty-delivery guard dropped, the check inverted. Packed, deferred and page-store suites: 349 passed.

## 2026-10-28 — #530 QA P3s: the failed-read path's signature, "missing" read and running None stamp pinned; docstring

Gates: release-lead's #530 QA (GO-with-notes), three P3 test gaps and a docstring nit. Follows #530. Tests and one docstring; no behaviour, route, schema, flag or knob change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **(b) the "missing" read:** the failed-read tests are parametrized over a failed read (no snapshot) and a real "missing" one (the league's member rows deleted; the test asserts that status). Before, all six used `current=None`.
- **(a) the request signature:** a job for another request signature, complete or running, is never followed on either read.
- **(c) a running None-stamp job:** never followed on either read. The refusal is asserted by its kick, because a running job's kick may join that same job, so its `deck_id` alone proves nothing.
- **Docstring:** `_trade_rebase_job_current` no longer says P1 rejects a None stamp "on any read". The head is stricter than P1: `_trade_fingerprints_match` keeps a running None-stamp job on a failed read, and at mode 0. Here it kicks.
- **Sabotages:** QA's Q1 (None guard on complete jobs only), Q5 (signature dropped on the failed path), Q6 (missing keeps the old shortcut) and Q7 (missing compared as an ok read) are now red in the suite (2, 4, 6 and 4 tests). The original four (TE1–TE4) are still red.
- **Evidence:** `test_trade_pages_p2.py` (128), `test_trade_page_store.py`, `test_trade_freshness_roster.py` and the digest: 314 passed.
## 2026-10-28 — The repeat cap re-applied to the displayed order at a serve (models-lead addendum D3)

Gates: models-lead's ruling D3 (a disposition cut that pulls a deferred card into the displayed first 30 counts as a B-DK-7 violation; the fix is to re-apply the cap after serve-time withdrawals, cuts and I-1 at mode 2), via head-eng ("build it now", after #489 and #492). Not flip-gating; due before the launch-week freeze. It adds one optional run key to the pack header, `display_moves`, agreed with models-eng. models-eng's #501 is the reader, and either PR can merge first. No route, schema, flag, knob or event change. No pipeline bump: it is a serve-time order, `deck_quality.py` is untouched, and the digest test passes unchanged. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **#517 QA (release-lead, NO-GO at `f5ddc026`), fixed:**
  - **P1-1:** after the job left, the window's prior was the earlier cards less every withdrawal. Eval keeps a delivered-then-withdrawn card (W1) in place, so the window reached further than eval's and X landed 4× in its first 30. The after-left path now reads what `_served_cap` reads, from the pack:
    - the delivered cards (`_deck_stored_delivered`: at or under the last delivery boundary, less the `served_before` 0 withdrawals);
    - the recorded moves;
    - this response's delivered cards it no longer sends.
  - **P2-1:** `_deck_note_moves` takes `first(index)` and refuses (logs) a move for a card an earlier response delivered: in process, a card not new to this delivery; stored, a card under the last boundary.
  - **P3-1:** the off-scope test (filters off, unpacked, no withdrawal) runs on the job view and both stored paths, in process and after the job left.
  - **New tests (9 cases):**
    - the W1-then-page-2 repro, in process and after the job left;
    - a re-serve after the job left records no move for an earlier delivery's card, and eval's order is the client's;
    - no W0 means no move after the job left;
    - recorded moves are re-applied after the job left;
    - a card delivered unmoved holds its place at a later serve, in process and after left;
    - both writers refuse a stale move (the cap stubbed);
    - `_deck_note_moves`'s refusal.
  - **Sabotages, 9 of 9 red:**
    - the old after-left path;
    - every withdrawal read as W0;
    - no `delivered` (after left / in process);
    - no recorded moves;
    - an unpacked deck capped after left;
    - the refusal dropped;
    - each writer's `first` forced true.
  - **QA's probes:** 18 of 20 green. The two red ones are P3-2's (a deck first delivered after its job left never gets a pack), pre-existing and raised with models-eng.
  - **P1-2:** raised with models-eng and models-lead.
- **Backend:** `test_served_repeat_cap.py`, 90 tests (74 before QA).
  - **`_served_repeat_cap`, pure:**
    - a pulled card moves behind the next clean one;
    - a later page counts the cards earlier responses displayed;
    - a full window moves nothing;
    - protected and delivered cards hold, and count;
    - a delivered card withdrawn since holds its slot, unsent;
    - nothing moves without contract ids in build order;
    - recorded moves are re-applied and never recorded twice;
    - the anchor is always a card the response sends first (a delivered or withheld last card, or a recorded move, moves nothing);
    - a response with no clean card keeps its order;
    - 40 seeded decks order exactly as `deck_quality._repeat_cap`, and eval's display key reproduces each order.
  - **Serve paths,** each with a disposition cut (a real pass elsewhere) and with I-1 at mode 2:
    - a later page through the stored view, the job view, and after the job left the process;
    - the legacy body, with a repeat poll keeping the order;
    - a replace serve after a never-delivered withdrawal (moves);
    - a replace serve after a delivered card's withdrawal (nothing moves).
    - Each case asserts the served order, the pack header's `display_moves`, and that the order eval derives from the pack alone (#501's rule) puts X in exactly 3 of the first 30.
  - **What never moves:** flag off, an unpacked deck, no withdrawal.
  - **Header:** the CAS merge keeps a card's first move.
- **Regression:** the serve, evidence and eval suites (`test_deck_pipeline_digest`, `test_deck_quality`, `test_eval_bdk_audit`, `test_eval_withdrawals_and_paging`, `test_i1_serve_filter`, `test_packed_evidence`, `test_trade_page_store`): 458 passed on the first version.
- **Full suite:** `pytest backend/tests`, 9,424 passed and 2 skipped at `1cb381b6`. After resyncing onto main `66e50a35` (#489, #492, #452) the evidence suites passed again: 312 (`test_served_repeat_cap`, `test_evidence_cleanup`, both filter-inputs files, the digest, `test_packed_evidence`, `test_i1_serve_filter`).
- **Cross-check:** models-eng ran #501's reader on this branch's real packs (all 6 cut/i1 × stored/job_view/left_process cases). `load_decks` gave the same displayed order as `displayed()`, and the suite passed with #501's `data.py` overlaid (80).
- **Sabotage, each red then restored (11):**
  - no cap in the job view;
  - no cap in the stored view;
  - moves not noted in process;
  - moves not noted after a restart;
  - the header flush dropping moves;
  - the merge letting ours win;
  - withheld cards ignored;
  - moves on an unpacked deck;
  - the flag ignored;
  - prior pages ignored;
  - no anchor guard.
- **History:** the first version also carried the loader. models-eng took that side as #501, so it was removed here, along with its tests and sabotages, and the anchor guard was added for #501's same-delivery integrity rule. A display-key self-check in the first version was dropped: the guard makes it unreachable (its sabotage stayed green until a test reached it, and with the guard nothing does).

## 2026-10-28 — #519 QA P3s: the in-flight kickoff attribution, the burst test's race, docs

Gates: release-lead's #519 QA (GO-with-notes at `8af4189a`), P3-1 to P3-3. Follows #519. Tests and docs, and one docstring; no behaviour, route, schema, flag or knob change. D-056: `FTF_SKIP_SIM_GATE=1` posture; the evidence is pytest.

- **P3-1 (#487 QA P3-1 closed):** the kickoff attribution test is parametrized over the session's roster refresh: idle, and in flight (`roster_fetch_started_at=READ_NOW`, `roster_read_rows=MEMBERS_NOW`), which is the only path where the kickoff takes an expected fp. The in-flight case asserts the job really took one. This is release-lead's variant.
  - **Sabotage T5** (a separate picks read while in flight): the in-flight case is red. The idle case stays green, as QA found.
- **P3-2:** `test_a_burst_s_tail_is_logged_once_the_drops_stop` waits on the warning record, not on the drop counter. The worker zeroes the counter under the lock and logs after releasing it.
  - **Shown:** with that gap widened to 150 ms, the old wait fails and the new one passes. With no warning, it's red.
  - **Repeats:** 8 of 8 green.
- **P3-3, docs:**
  - #519's ledger entry is corrected in place, dated (it had said "no server code" and "3.12 may refuse");
  - the exit drain's docstring now says the guard is defensive;
  - LLD's `deck_i1_check` line names the exit drain's restart and the refusal path;
  - #519's PR body is fixed (44 tests, the guard commit).

## 2026-10-28 — Send pre-flight budget: no ESPN/MFL write starts after 30 s (release-lead QA P1-A on #527)

Full gates, platforms-eng (release-lead's P1-A, due before the 11-06 iOS binary). Server only, branch `fix/send-preflight-budget`, stacked on `fix/espn-mfl-send-failures` (#513). No new code, copy, schema, flag or event. An existing 502 gains one more cause. D-056: `FTF_SKIP_SIM_GATE=1` posture, the evidence is pytest.
- **Change:**
  - `_SEND_PREFLIGHT_BUDGET_S = 30`, with an injectable `_send_clock`.
  - `_mfl_propose_core` / `_espn_propose_core` take `t0` at entry. Immediately before the write, a core past the budget skips it and answers its existing R3 502 (`mfl_unavailable` / `espn_unavailable`, `kind: "network"`, I-2's copy). It also logs one WARNING line.
  - Scope: [docs/plans/c10-send-failures/scope.md](../docs/plans/c10-send-failures/scope.md) § Pre-flight budget.
- **Tests (`backend/tests/test_send_preflight_budget.py`, 6 new):**
  - A pin: budget + write timeout + MFL spacing < 60, for both platforms.
  - MFL and ESPN: the mocked live read advances the injected clock. At budget + 0.01 s, the response is the unavailable code with the R3 copy word for word and `detail` == `message`. The write mock is never called, there is no `trade_sent` row, and one budget WARNING line is logged. At budget − 0.01 s, the write runs (200).
  - Overhaul through the real MFL core: every offer past its budget becomes 5 `send_failed` attempts (never `outcome_unknown`) with `mfl_unavailable` and the R3 copy. Reservations are released and nothing is written.
- **Sabotage, each red then restored byte-identical (`cmp`, run with `python3 -B` per G-060):**
  - MFL guard removed → 2 red;
  - both guards moved after the write → 3 red;
  - budget raised to 50 → 1 red (the pin).
- **Targeted:** 366 passed in 15 files. They are the new file, `test_c10_send_failures`, `test_espn_propose_route`, `test_mfl_propose_route`, `test_espn_write`, `test_mfl_write`, `test_i2_espn_ownership`, `test_i2_mfl_ownership`, `test_i2_overhaul`, `test_i2_sleeper_ownership`, `test_overhaul_api`, `test_overhaul_service`, `test_overhaul_store`, `test_bilateral_overhaul` and `test_mfl_trade_lifecycle`.
- **Not run:** the full backend suite (CI runs it); live ESPN/MFL (all mocked); `tsc` / testid-lint (no mobile change). The 60 s iOS timeout is static evidence. Release-lead's TestFlight step confirms it: Network Link Conditioner, a custom 100% loss profile, then read the alert time (~60 s confirms, ~91 s refutes).

## 2026-10-27 — ESPN/MFL send failures: plain copy, raw provider bodies to logs only, outcome-unknown on post-send timeouts (C10)

Full gates, platforms-eng lead (head-eng pre-launch triage C10, "the only C item that prevents a real-money-adjacent harm"). Server only. API surface: new 502 `espn_outcome_unknown` / `mfl_outcome_unknown`, and `detail`/`message` are now plain placeholder copy on propose-espn, propose-mfl and respond-mfl; no schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture, the evidence is pytest. Branch `fix/espn-mfl-send-failures`.

- **Scope:** [docs/plans/c10-send-failures/scope.md](../docs/plans/c10-send-failures/scope.md) covers the problem, behavior, the before/after-send rule, the analytics (b) answer, the docs table and the mobile follow-ups. Copy is a placeholder, pending marketing via head-eng.
- **Tests (`backend/tests/test_c10_send_failures.py`, 70 new):**
  - Adapters, through the real `propose_trade` with an injected opener: 4 before-send cases → `network`; 13 after-send cases (read/socket timeout, reset, `RemoteDisconnected`, `BadStatusLine`, body-read timeout, `IncompleteRead`, `URLError` timeout/reset, HTTP 500/502/503/504) → `outcome_unknown`, for each platform; unreadable 2xx/200 → `outcome_unknown`; ESPN 4xx and MFL `<error>`/4xx → `error`; MFL 429 → `network`.
  - Propose routes: an HTML and a JSON ESPN rejection, an HTML 400 and an `<error>` 200 MFL rejection → code unchanged, marker absent from the response, logged once, truncated, SWID and cookie masked. A timeout/reset/5xx/`IncompleteRead` after send → `*_outcome_unknown` with the copy; DNS / refused before send → `*_write_failed` with the rejection copy. Unknown fires no `trade_sent`. Auth rejections (ESPN 401, MFL 403) return no raw body.
  - respond-mfl (review follow-up): an HTML 400 and an `<error>` 200 rejection → `mfl_write_failed` with the "this response … nothing changed" copy, never returned, logged once and masked; timeout / reset / 504 → `mfl_outcome_unknown`; refused → `mfl_write_failed` (`network`); the auth body is not returned.
  - Overhaul, through the real cores: ESPN tie A times out → two `outcome_unknown` attempts with the copy, A still reserved; B rejected → `send_failed` with the plain copy, released; C/D proposed; `GET /api/overhauls/{id}` shows the same. MFL reset on every offer → 5 `outcome_unknown`, all reserved.
- **Sabotage, each red then restored byte-identical (5):**
  - raw `detail` returned again (propose ESPN + MFL, respond-mfl) → 24 red;
  - the adapters' after-send branch classified `network` → 13 red;
  - every `URLError` treated as not sent → 4 red;
  - the routes ignoring `outcome_unknown` → 13 red;
  - overhaul recording the codes as `send_failed` → 2 red.
- **Targeted (after merging `origin/main` @ `052c9746`):** 530 passed in 22 files. They are the C10 file, `test_espn_propose_route`, `test_mfl_propose_route`, `test_espn_write`, `test_mfl_write`, `test_i2_espn_ownership`, `test_i2_mfl_ownership`, `test_i2_overhaul`, `test_i2_sleeper_ownership`, `test_overhaul_api`, `test_overhaul_service`, `test_overhaul_store`, `test_bilateral_overhaul`, `test_mfl_trade_lifecycle` (respond-mfl), `test_api_observability` and `test_sleeper_write_route`, plus six other suites that import the changed modules. The same 22 files were 523/523 before the respond-mfl follow-up. On the base commit before C10, the 10 propose / write / I-2 / overhaul-api / lifecycle files ran 235 passed.
- **Not run:** the full backend suite (CI runs it; the local machine is overloaded); live ESPN/MFL writes (all mocked); `tsc` and testid-lint (no mobile change).
- **2026-10-28, final copy (marketing addendum 10, 8a–8h + the optional ESPN auth line):**
  - The placeholders are replaced word for word, with straight apostrophes.
  - `_send_write_failed` now picks the `*_write_failed` line by `kind`: `network` → 8c/8d ("Couldn't reach … Try again in a moment.", including MFL's 429); `error` / `input` → 8a/8b. respond-mfl uses 8g for its `network` case too, since addendum 10 has no separate line for it.
  - The C10 file is 89 tests (19 new): pins for each string, a banned-word sweep of every C10 copy constant, the kind split, and MFL 429 → 8d. The overhaul unknown attempts carry 8e/8f.
  - New sabotages, each red then restored: `network` falls back to the rejected line → 7 red; a curly apostrophe → 10; "failed" in a constant → 14. The earlier five re-run at 25 / 13 / 4 / 15 / 2.
  - Targeted rerun, on the same 22 files at `1a92a7ab` plus this change: 549 passed (530 + the 19 new).

## 2026-10-29 — ESPN/MFL send registry: a remount keeps "Sending…", no second send of the same trade, a reminder after an unknown outcome (#527 QA P2-A)

Full gates, platforms-eng worker (head-eng YES for the 11-06 binary if it is in release-lead's queue by 11-03). Mobile only: no route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture. Branch `fix/send-registry`, cut from `fix/espn-mfl-client-send-timeout` (#527, `3ad01072`, untouched). Scope addendum: [docs/plans/client-send-timeout/scope-send-registry.md](../docs/plans/client-send-timeout/scope-send-registry.md).

- **#539 QA P3s (same day, after #539 passed release-lead's QA).** P3-1, a stale queued confirm dialog sends nothing: each dialog captures the trade's state and sends only if it is unchanged, and if the trade has since turned unknown the dialog reopens with 8e/8f. P3-3, eviction drops `sent` first, then `unknown`, never `in_flight`. P3-5, the suite shims #379's `utils/openExternal`. P3-6, TestFlight wording and the `sent`-lock limit line.
  - `check-send-registry.js`: **35/35** (R2d is P3-1's exact scenario, one POST plus the reopened dialog with the reminder; R2e pins the comparison; R6a pins the eviction order).
  - Sabotage, each red then restored: the comparison removed, ESPN → 2 red (R2d, R2e); the same on MFL → 2 red; evict `in_flight` first → 1 red (R6a). Re-run on the revised code, (a)–(d2) stay red: 5 / 5 / 7 / 4 / 4 / 6, plus C4 and C5.
  - #379 dry-run (`git merge-tree` with `origin/build/open-external-helper` `b362b4f8`, not pushed): conflicts only on the buttons' first two import lines. Resolved, the merge passes `check-send-registry` 35/35, `check-send-timeout` 24/24, `check-send-button-platform`, `check-external-links` and tsc (exit 0). Without the shim it fails `check-send-registry` (23 red).
  - All `check-*.js` 122/122; `npx tsc --noEmit` exit 0; testid-lint exit 0.
- **#539 delta QA P3s (same day, after the delta re-QA was GO; branch head `c326e1ea` with main merged in):**
  - ABA: a dialog now compares the registry **record object**, not its state. So "already unknown → double tap → dialog 1 sends and times out again → dialog 2" sends nothing and reopens with the reminder.
  - Eviction skips the entry just written, so a send that settles while the map is over the cap (everything else in flight) is not forgotten at once.
  - TestFlight step 2 now says the confirm dialog takes about 30 s to appear with the conditioner on.
  - `check-send-registry.js`: **37/37** (R2f is the ABA scenario per button, with 2 POSTs before the stale press, still 2 after, and the reopened dialog with the reminder; R2e pins the record comparison; R6a pins the skip).
  - Sabotage, each red then restored:
    - compare state only, ESPN → 2 red (R2e, R2f);
    - the same on MFL → 2 red;
    - the just-written skip dropped → 1 red (R6a).
  - `check-send-timeout.js` 24/24; all `check-*.js` 126/126 (main brought new suites); `npx tsc --noEmit` exit 0; testid-lint exit 0.

- **What it pins:**
  - `mobile/src/api/sendRegistry.ts` keeps each ESPN/MFL trade's send state as module state, in memory per app run. It survives a remount, not a restart, and is capped at 50 entries.
  - The key is platform + league + counterparty + sorted give / receive asset ids, the propose payload's own identifiers.
  - `in_flight` is set synchronously before the request. Success records `sent`; an unknown outcome records `unknown` with its time; a definitive not-sent answer clears the entry.
  - Both buttons read the registry with `useSyncExternalStore`, so a remount shows Sending… / Proposal sent.
  - `doPropose` starts with `if (!beginSend(sendKey)) return;`, so a second send of the same trade makes no request.
  - After an unknown outcome, the confirm dialog (and the warnings dialog) starts with marketing's 8e/8f line, `sendOutcomeUnknownMessage`. There is no new copy.
  - Exactly one result alert after a remount: the `doPropose` call that sent owns it, `Alert.alert` is global, and a remount never alerts.
- **`node mobile/tests/check-send-registry.js` (new, `npm run test:send-registry`): 31/31, exit 0.**
  - It executes the real registry and both real buttons under a minimal hooks shim, with a fake Alert and a scripted propose, plus the real `ApiError`, `sendOutcome.ts` and `sendOutcomeCopy.ts`.
  - R1, the key: order-insensitive, scoped, no collisions; the buttons key on the payload's own identifiers.
  - R2: `in_flight` is set before the request. A same-frame double press, two queued dialogs (pressed in flight and after a confirmed send) and a second mount each send one POST.
  - R3: a remount shows Sending…, disabled and inert.
  - R4: send, unmount, remount, then success / timeout / `write_failed` gives exactly one result alert, and the remount is notified.
  - R5: 5 unknown answers record `unknown`, and the dialog body is the 8e/8f line word for word plus the unchanged text. Success is `sent`. 5 not-sent answers clear the entry.
  - R6: bounded, no imports, out of the Sleeper button and the overhaul.
- **Sabotage, each red, then restored from a copy (working tree diff back to the intended change), 6 runs:**
  - (a) `in_flight` set after the await, ESPN → 4 red (R2a, R2b, R2c, R3);
  - (a) the same on MFL → 4 red;
  - (b) the button ignores the registry (`useState` in place of `useSyncExternalStore`) → 7 red (R2b, R3, R4 ×3, R5c, R5e);
  - (c) unknown not recorded → 3 red (R5a, R5b, R5d);
  - (d) the reminder altered in the button → 3 red (R5a, R5b, R5d);
  - (d2) the 8e/8f line altered in `sendOutcomeCopy.ts` → 4 red here (R5a, R5b, both platforms), plus `check-send-timeout.js` C4, C5.
- **All suites:** `for f in tests/check-*.js` → 122/122 pass, including `check-send-timeout.js` 24/24 and `check-send-button-platform.js`.
- **`npx tsc --noEmit` (mobile): exit 0**, on the final tree. **`mobile/scripts/testid-lint.sh`: exit 0** ("testid-lint OK"; no testID added).
- **Backend:** not run. Nothing in the backend changed.
- **Manual TestFlight checklist:** addendum §3, nine steps:
  - a remount under 100% loss shows Sending…;
  - one alert;
  - the reminder in the confirm dialog, then Cancel;
  - check and revoke after 5 minutes offline;
  - the reminder gone after a restart;
  - a double tap on a normal network sends one offer, and a reopen shows Proposal sent;
  - ESPN repeat;
  - a Not-sent regression.

  Sandbox league with a test counterparty only. **Unrun.** Every send needs the operator's go at action time.

## 2026-10-28 — ESPN/MFL client send timeout: wait the server's worst case, "couldn't confirm" instead of "try again" (C10 client half)

Full gates, platforms-eng worker (head-eng GO 2026-10-28, for the 11-06 iOS binary). Mobile only: no route, schema, flag or event change. D-056: `FTF_SKIP_SIM_GATE=1` posture; the evidence is an executed structural suite, a code walk and a TestFlight checklist. Branch `fix/espn-mfl-client-send-timeout`, scope [docs/plans/client-send-timeout/scope.md](../docs/plans/client-send-timeout/scope.md).

- **What it pins:** propose-espn / propose-mfl wait 91 s (`PLATFORM_SEND_TIMEOUT_MS`, `mobile/src/api/sendOutcome.ts`: the server's worst case for one propose, MFL 76 s = crosswalk 15 + resolve_host 15 + rosters 15 + futureDraftPicks 15 + spacing 1 + write 15, ESPN 45 s, plus a 15 s margin). The overhaul send waits (min(n × 76, 120) + 15) s: 91 s for one offer, 135 s for two or more. The cap is `GUNICORN_TIMEOUT_S` = gunicorn's `--timeout 120` (`render.yaml:16`), a review change added the same day. Every other call is unchanged. A timeout, no answer, `*_outcome_unknown`, `internal_error` or a code-less 5xx shows `Check before resending` with OK / Open ESPN-MFL only, never "try again" or a Retry; the overhaul re-reads its attempts on the plan.
- **Final copy (review change, same day):** marketing-lead addendum 10 items 8a/8b/8e/8f/8i, word for word with straight apostrophes, in `utils/sendOutcomeCopy.ts`:
  - outcome-unknown body: the server's `detail` for its own code, else `Couldn't confirm whether this trade reached ESPN. Check your league's pending trades on ESPN before you send it again.` (MFL likewise);
  - `*_write_failed`: title `Not sent`, body `detail` alone with the "rejected the request:" prefix dropped, and the 8a/8b line as the no-detail fallback;
  - the overhaul summary line is not in marketing's set: kept, marked PENDING MARKETING.
- **`node mobile/tests/check-send-timeout.js` (new, `npm run test:send-timeout`): 24/24, exit 0** (19 at first, 20 with the cap, 24 with the final copy). It executes the real `api/client.ts`, `sendOutcome.ts`, `sendInEspn.ts`, `sendInMfl.ts`, `overhaul.ts` and `sendOutcomeCopy.ts` under a fake clock with a scripted `fetch`:
  - the constant equals the server sum, with every term parsed from `backend/{espn,mfl}_write.py`, `mfl_service.py` and `espn_service.py`;
  - each propose core in `server.py` makes exactly the counted provider calls on their default timeouts;
  - `GUNICORN_TIMEOUT_S` equals the web service's `--timeout` parsed from `render.yaml`, one propose (76 s) fits under it uncapped, and `overhaulSendTimeoutMs(10)` = 135 s, the cap;
  - each send is still waiting at 15 s and times out at its long timeout; GETs, prepare-send, refresh and a plain POST still time out at 15 s;
  - 18 server answers are classified through the real client;
  - every final string is pinned word for word (C4); the body takes the server's `detail` only for its own outcome-unknown code (C5, 8 cases);
  - a sweep of the copy module (C6): no "failed" or "error" in any literal or output, and no "nothing was sent", "try again" or "retry" in the outcome-unknown copy;
  - the AST shows both buttons and the overhaul summary branch on the unknown case first, with no resend and buttons exactly OK + Open ESPN/MFL (so "Couldn’t send" never shows for it); `*_write_failed` → `Not sent` + `detail || sendNotSentFallback(...)`, with the old prefix gone;
  - no POST is retried on 502/503/504/network drop (a GET control is); `session_not_initialized` is the only POST replay.
- **Sabotage, each red then restored byte-identical (file restored from a copy or checked out again, working tree diff clean), 12 runs:**
  - (a) the long timeout removed from propose-mfl → 1 red (B propose-mfl);
  - (b1) a timeout classified as not-unknown → 1 red (C1);
  - (b2) the ESPN button skips the unknown branch, so a timeout falls to the generic "Please try again" → 1 red (D ESPN);
  - (c) gateway/network auto-retry enabled for POST → 4 red (C2, C3, E1, E3);
  - (d) server drift, `mfl_write._HTTP_TIMEOUT` 15 → 20 → 1 red (A3);
  - (e) server drift, a second provider read in `_espn_propose_core` → 1 red (A2);
  - (f) the overhaul cap removed, back to (n × 76 + 15) s → 1 red (A6);
  - (g) server drift, `render.yaml` `--timeout 120` → 90 → 1 red (A5);
  - (h) ESPN `write_failed` "ESPN rejected the request:" prefix restored → 1 red (D ESPN write_failed);
  - (i) a Retry button (re-calling `doPropose`) added on MFL outcome-unknown → 1 red (D MFL unknown);
  - (j) "failed" slipped into the not-sent fallback → 2 red (C4, C6);
  - (k) the 8e/8f body back to the curly placeholder → 2 red (C4, C5).
- **Worker class, for the record:** with `--threads 4` (#398, 2026-10-25), gunicorn runs gthread. Its `--timeout` is a heartbeat: the gthread run loop calls `notify()` every second whatever the request threads are doing; gunicorn's config doc says that for non-sync workers it "is not tied to the length of time required to handle a single request". So today the 120 s kill only applies under the sync-worker rollback. The cap stands either way, because attempts are persisted before the first provider call and the plan shows them. The scope's known limits cover both cases.
- **All suites (after the final copy):** `for f in tests/check-*.js` → 121/121 pass, including the new one, `check-send-button-platform`, `check-team-overhaul`, `check-apple-revoke-on-delete` (its `timeoutForRequest` probe still works) and `check-win-now-recovery` (39/39).
- **`npx tsc --noEmit` (mobile): exit 0, after the final copy.** **`mobile/scripts/testid-lint.sh`: exit 0** ("testid-lint OK"; no testIDs added).
- **Backend:** not run, because nothing in the backend changed. The server half (`*_outcome_unknown`) is #513's `test_c10_send_failures.py`.
- **Manual TestFlight checklist:** scope §3, nine steps (Network Link Conditioner on an MFL and an ESPN test league, airplane mode after send, normal send, regressions, and the overhaul if it is re-enabled). **Unrun.** Every real-league send needs the operator's go at action time.

## 2026-10-28 — QA P3 follow-ups: #489 (docs claim, LLD guard counts, deadlock-safe lock test), #487 (read pins, docstring), #485 (exit-drain restart, after-write flush)

Gates: release-lead's #489 delta QA, P3-1 to P3-3. Tests, docs and three small server changes (a docstring, the exit drain's worker restart and its shutdown guard); no route, schema, flag or knob change. (Corrected 2026-10-28, #519 QA P3-3: this line first said "no server code".)
- **P3-1:** #489's ledger entry said its docs included the data dictionary (the ERROR-line note). They didn't: the note from `85286cf7` already held. The entry is corrected in place, dated. Commit `7d5d0edb`'s message keeps the wrong claim; it can't be rewritten (no force-push).
- **P3-2:** LLD's guard-count list now includes `f5=` (printed when nonzero), beside `held=` and `evicted=`.
- **P3-3:** `test_evidence_cleanup`'s `_OrderedLock` takes a blocking lock with a 5 s timeout. A self-deadlock now fails the test with "lock not acquired" instead of hanging until the runner's timeout.
- **Evidence:**
  - `test_evidence_cleanup.py`: 38 passed.
  - **Sabotage:** the F5 drop's ledger lock nested inside itself. Before: the test hung (QA's Y1, caught only by the runner's timeout). Now: it's red in 17 s, then restored.
- **#487 QA (release-lead, 2026-10-27):**
  - **P3-1:** a kickoff test attributes every `draft_picks` and `leagues` statement to the one fingerprint read (`snapshot_ids`: one picks read, one drafted read) or to the preferences' pick share. An expected fp taken from a separate read fails it; the old spy counted only `snapshot_ids` calls.
  - **P3-2:** the worker spy now also asserts exactly one `get_league_draft_context` per job.
  - **P3-5:** `_trade_fingerprints_match`'s docstring now lists every None-stamp source: a failed kickoff read, other picks, a flipped verdict, a failed picks or draft read.
  - **P3-3, for models-eng:** owner-exclusive forfeits on a transient first picks-read failure (0 owner cards; main re-read and served). It's conservative and consistent; models-eng was told.
  - **P3-4, accepted:** a failed draft read unstamps drafted-league jobs on non-owner paths. It needs a DB error, and serving is unaffected. The +1 leagues lookup per non-owner job is the verdict the stamp's key holds since #487.
- **#485 QA (release-lead, 2026-10-27):**
  - **The exit drain:** it now starts a worker first when the current one died with writes queued behind it (`_i1_event_ensure_worker`, split from the enqueue), so those writes land instead of being lost.
  - **A test pins the after-write drop flush:** by the call on the test's own queue, since the drop counter is module-wide and another test's idle worker may log it.
  - **The death backoff:** informational; none added. The worker dies only on a BaseException, and each restart waits for the next enqueue or the exit drain.
  - **Shutdown guard (release-lead's #519 question):** defensive. Should an interpreter ever refuse a new thread at shutdown ("can't create new thread at interpreter shutdown", gh-104690), the exit drain logs the stranded writes with their count and returns at once. It never raises, and never waits on a queue nothing serves. (Corrected 2026-10-28, #519 QA P3-3: this said CPython 3.12 "may refuse". QA's real exits on 3.12.3, 3.12.15 and 3.14 restart the worker and the writes land.)
    - On 3.14 (local) the restart works at exit: the stranded write lands.
    - 3.12 isn't installed locally, so a child-interpreter test runs the real exit, normally and via a SIGTERM-to-exit handler (gunicorn's shape), on CI's 3.12. It asserts exit 0, no traceback, and the write either landed or logged.
- **Evidence:** `test_trade_freshness_roster.py`, `test_deck_i1_check.py` (44, with the refused-thread test and the child-interpreter exit ×2), `test_evidence_cleanup.py` and the digest all passed.
- **Sabotage, each red then restored (5):**
  - the exit drain's start unguarded (the refused-thread test raises);
  - a separate kickoff picks read;
  - a second worker draft read;
  - the exit drain without a restart;
  - no after-write flush. Its first form, a log assertion, stayed green in the full file because another test's idle worker logged the shared counter; it's now pinned by the call on the test's own queue.
## 2026-10-28 — Rebase case 2's failed-read path runs every other check (#520 QA P3s)

Gates: release-lead's #520 QA, P3-1 to P3-3, on main after #520 merged (flag-dark behind `trade.first_page_store`). No route, schema, flag or knob change; serve path only, no pipeline change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **P3-1:** `_trade_rebase_job_current` used to return True on a failed or missing snapshot before any check. Now only the fingerprint compare is skipped: the job's own stamp stands in for the read, and the policy, TTL, request signature and session-read checks P1's backing makes all still run.
  - A None stamp is never followed on that path, since P1 rejects it on any read.
- **P3-2, accepted, not changed:** when only the vsn read fails, `_trade_current_snapshot` returns None and the page view reads the roster again. That's 2 roster reads per poll, on that failure path only. Keeping the roster snapshot would change `_trade_current_snapshot`'s None-means-failed contract for all its callers, for a flag-dark failure path.
- **P3-3:** `test_trade_pages_p2.py`, 6 new tests (116 in the file):
  - a failed read follows a current newer job, complete and running, with no kick;
  - a failed read plus a revoked input epoch: no follow;
  - a failed read never follows a None-stamp job, one past the reuse TTL, or one built on a read the session replaced.
- **Sabotage, each red then restored (4):**
  - the old shortcut (3 red);
  - a failed read kicking (2 red);
  - no None-stamp guard;
  - the epoch check after the shortcut (4 red; one of QA's two green probes).
## 2026-10-28 — One retry inside the job's picks and draft-context reads (#487 QA P3-3, models-eng); deck pipeline v7

Gates: release-lead's #487 QA P3-3 (owner-exclusive forfeits on a transient first picks-read failure: 0 owner cards, where main re-read and served 348), and models-eng's ruling and v7 shape. Stacked on #515 (v6). No route, schema, flag or knob change. `DECK_PIPELINE_VERSION` 6 → 7 (`facf9a9f34b7529a`): only `_run_trade_job`'s two memos changed. models-eng reviews. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **The change:** inside `_job_draft_picks` and `_job_draft_context`, a raising read is retried once, immediately, with no lock held.
  - Either attempt's success is memoized. The read is marked failed only when both raise.
  - `_note_job_picks_read` runs after the retry, so the stamp check and the owner path see one, and the same, read.
  - A persistent failure behaves as before: the owner arm forfeits, and other readers degrade to empty. The success path is unchanged.
- **Backend:** `test_trade_freshness_roster.py`, 4 new tests (2 reads × 2):
  - a read that fails once is retried (2 calls in all, 1 note, the stamp kept) and the owner context builds;
  - a read that fails twice forfeits, as before.
  - The existing persistent-failure tests (`test_a_failed_read_still_forfeits_the_owner_arm`) still pass.
- **Regression:** the digest, `test_trade_freshness_roster`, both filter-inputs files and `test_bakeoff_serving`: 128 passed.
- **Sabotage, each red then restored (3):**
  - no picks retry;
  - no draft retry;
  - a second retry (the fails-twice test catches it).

## 2026-10-28 — Account-only sessions get `verification` (head-eng; for the 11-06 binary)

Full gates (scope `docs/plans/prelaunch-onboarding/scope-account-only-verification.md`). Server and mobile; D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **The change:**
  - `GET /api/session/ping` returns session/init's additive `verification` object, via `_session_verification(sess)`.
  - Mobile `refreshVerification()` pings and records it only for the same, still-signed-in user.
  - It's called from `revalidateSession`'s `NO_LEAGUE_ID` branch and after the account-only Apple sign-in.
  - The result: an Apple-first account with no league now reads `session_verified: true`.
- **Release-lead #524 QA (NO-GO, P1), fixed:** an unverified or demo session (session/init's 403 cases) now gets the constant unverified answer, with no lookup. Before the fix, ping told anyone who could name a user_id whether that account existed and which provider proved it (legal R28.9 row 4 / R28.14).
  - Also from QA: the sentinel ping is no longer awaited (P3-2).
  - `setUser` resets `verification` to null on any user_id change (an expiry then another user's sign-in).
- **Backend:** `test_session_ping_verification.py`, 24 tests:
  - the squatter test flipped to the constant;
  - the exact key sets for 7 session types;
  - 0 SQL for anonymous, unknown-token and unverified pings, with a positive control;
  - a foreign `user_id` / `X-User-Id` ignored;
  - a verified session reads the user row, not its own stamp.
  - **Sabotage 11/11 red:** QA's P1 reverted, demo looked up, an extra top-level key, an extra key in the unverified answer, the query user_id answered, X-User-Id looked up, a 401-path probe, plus round 1's 4 re-run.
- **Mobile:** `check-account-only-verification.js`, 5 AST pins (pin 3 is now unawaited; pin 5 is the `setUser` reset). **Sabotage:** 7/7 red in round 1, and 5/5 on the new and changed pins. tsc clean; `check-win-now-recovery` passes.
- **Runs:** see the PR (the full `check-*.js` loop, testid-lint, backend suites).
## 2026-10-28 — Settings tip row: hidden unless the cached paywall config offers tips (B8 gate, off main)

Gates: head-eng's extraction of #495's B8 tip-row gate after release-lead's #494 QA (with `monetize.paywall` on, a binary without the gate shows "Support Fleeced · Tip jar", which opens an empty sheet now that the server serves `tips: []`). Branch `fix/settings-tip-row-gate`. User-visible (a row hides); no route, schema, flag or analytics change. D-056: `FTF_SKIP_SIM_GATE=1` posture; the evidence is the structural suite, an executed check, a sabotage pass, tsc, testid-lint and a code walk.

- **The change:** new `mobile/src/state/useTipsOffered.ts`, byte-identical to the brief and to the file the paywall stack (#495) carries. `tipsOffered(config)` is true only for a non-empty `tips` array. `useTipsOffered()` subscribes to `['paywall-config','ios']` with `enabled: false`, so it never fetches. Both settings surfaces call it at the top level and render `settings-tip-row` only when the flag is on AND tips are offered. The "Fleeced Pro" row and the TipJar route are unchanged.
- **Code walk:**
  - Flag on, `tips: []` (`backend/server.py:36105`): `useTipsOffered.ts:14` → false, so the hub's `{tipsOffered ? (` (`SettingsHubScreen.tsx:320`) and the flat screen's (`SettingsScreen.tsx:1075`) render null. The Pro row still renders.
  - Flag on, cached config with tips: the same lines are true, and the row renders at `SettingsHubScreen.tsx:322` / `SettingsScreen.tsx:1077`. Only `PaywallScreen.tsx:132` fills that cache on this binary, so the row comes back after the paywall config has been fetched this launch.
  - Flag off: `paywallOn ? (` (`SettingsHubScreen.tsx:307`) and `paywallEnabled ? (` (`SettingsScreen.tsx:1051`) render null, as before.
- **`check-tipjar.js` now has 11 assertions (was 9):**
  - §8 pins the row inside the flag gate AND the `tipsOffered` gate on both surfaces, with the hook imported and called at the top level.
  - §8b executes `tipsOffered` on the hook file, transpiled with stubs: undefined, null, `{}` and `{tips: []}` give false; `{tips: [tip]}` gives true.
  - §8c executes `useTipsOffered` with a stubbed `useQuery`: key `['paywall-config','ios']`, `enabled: false`.
- **Sabotage (5), each red and then restored byte-identical:** the hub's tips gate removed (§8 red), the flat screen's tips gate removed (§8 red), the hub hook called conditionally (§8 red), `length >= 0` (§8b red), `enabled: true` (§8c red). After the restore: 11/11.
- **Results:**
  - `check-tipjar` 11/11, `check-paywall` 11/11, and green on `check-settings-ia`, `check-settings-testids`, `check-settings-nav`, `check-feedback-public`, `check-mascot-ram` and `check-signin-identity-labels` (every check that names a Settings screen).
  - All 120 `mobile/tests/check-*.js`: 0 red.
  - `tsc --noEmit`: exit 0, clean.
  - `testid-lint OK`.
- **TestFlight (operator):** with `monetize.paywall` on and the server serving `tips: []`, open Settings. Neither the hub (`account.settings_hub` on) nor the flat Settings (off) shows a "Support Fleeced" row, and "Fleeced Pro" still shows on both. Older installed builds without this gate still show the empty sheet (accepted by head-eng).
## 2026-10-28 — B5 launch copy, trades-eng's items 1, 3, 4 (marketing-lead addendum 10)

**Gates:**
- **Full gates.** The scope block is `docs/plans/launch-copy-b5-trades-2026-10-28.md`.
- **What changes:** copy plus one navigation link; no route, schema, flag or event change.
- **D-056:** `FTF_SKIP_SIM_GATE=1` posture. The evidence is the structural suite, tsc, and the TestFlight checklist in the scope block.

**The changes:**
- **Item 1:** Win Now's uncalibrated receipt says `Uncalibrated estimate` (mobile `utils/winNow.ts`, web `js/win-now.js`).
- **Item 3:** the calculator's ESPN note.
  - It reads `No draft picks are set up for this ESPN league yet.` and links `Set up picks →` to PickAssignment on the root stack.
  - It shows only while both `picks.assign` and `picks.assign_tradeable` are on (draft-eng's gates) and `picks_supported` is false. Under those flags that's the server's data test (`has_assigned_picks`).
  - Either flag off keeps today's line.
- **Item 4:**
  - the shop button reads `Show it to @{name}`, with VoiceOver `Show this offer to @{name} in their Fleeced deck`;
  - the queue toasts read `It's waiting in @{name}'s Fleeced deck.` and `It's already in @{name}'s Fleeced deck.`, for both of `queueCalcTrade`'s hosts.

**Mobile:** `check-b5-copy.js`, 9 checks:
- every string pinned word for word, with the old ones gone;
- item 3's gates: both flags (with no short-circuited hook), the server line, and today's line with a flag off;
- item 4's `testID`;
- no banned words.

**#531 QA (release-lead, NO-GO at `05c153e5`), fixed:**
- **P1-1:** saving picks left the calculator's ESPN note and pickers stale for up to 5 minutes. `PickAssignmentScreen`'s assign and seed `onSuccess` now invalidate `['league-picks', leagueId]`.
- **P3s:** the toast ternary, the shop name's normalizer and the hooks' order are pinned. The banned-words check reads the strings from the source.
- **P2-1:** the TestFlight checklist is rewritten: real-data warnings, preconditions and paths; 4b not run; the web half goes live at merge.
- `check-b5-copy.js` is now 12 checks.

**Sabotages:** 20 of 20 red. `check-win-now.js`'s two pins were updated, and its executable web test renders the new label. The 23 suites that read the edited files all pass, and `tsc --noEmit` is clean.

## 2026-10-27 — Paywall config: price rise at 2027-01-01 00:00 America/Los_Angeles; `tips: []` (#494 follow-up)

Gates: head-eng's two additions to #494 (`fix/paywall-fallback-prices`), values confirmed by monetization-pm. Same route, still dark (`monetize.paywall`). No route, schema, event, flag or knob change. Server and docs only; mobile untouched. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest, a sabotage pass and a code walk of TipJarScreen. Full suite not re-run (CI runs it).

- **The rise is an instant, not a UTC date (`backend/server.py`):**
  - `_PAYWALL_PRICE_RISE_DATE = date(2027, 1, 1)` compared on the UTC date, so the fallback flipped to $6.99 / $34.99 at 7 pm ET on Dec 31. Terms §14.8 promises the Founder price to anyone subscribing "by December 31, 2026".
  - It is now `_PAYWALL_PRICE_RISE_AT = datetime(2027, 1, 1, 8, 0, tzinfo=timezone.utc)`, which is 2027-01-01 00:00 America/Los_Angeles (PST, UTC-8). `_paywall_products` compares `now >= _PAYWALL_PRICE_RISE_AT`, and a naive `now` raises `TypeError`.
  - The comment says it is fallback-only (StoreKit is authoritative) and that monetization-pm checks it against the App Store Connect scheduled change; if the two differ, the constant moves.
  - The now-unused `date` import is reverted.
- **Tips:** the route serves `tips: []`, as #465 does, because the tip SKUs are not submitted to App Store Connect. `_PAYWALL_TIPS` stays as the list to restore. A tip still grants no entitlement (`entitlements.is_tip_product`, unchanged).
- **TipJarScreen with an empty list (code walk, `mobile/src/screens/TipJarScreen.tsx`):**
  - `:80` gives `tips = []`;
  - `:85` disables the StoreKit product fetch (`tips.length > 0`);
  - `options` is empty, so `:193-195` render "Tips aren’t available right now." No crash and no purchase row.
  - Hiding the Settings tip row is engagement-eng's client work, routed separately.
- **Backend:** `test_paywall_config.py` is now 36 tests (was 30):
  - both sides of the instant: `2027-01-01T07:59:59Z` old, `08:00:00Z` new; `2027-01-01T00:00Z` (4 pm Dec 31 in LA) is pinned old;
  - the constant equals 08:00 UTC and LA midnight via `zoneinfo`;
  - the UTC-date tests are replaced with instant tests. New York 20:00 Dec 31 now gets the **old** prices, and so does LA 23:59:59. LA 00:00 Jan 1 and New York 03:00 Jan 1 get the new ones. Paris 00:30 Jan 1 is old;
  - a naive `now` raises;
  - `tips == []` with no `ftf_tip` in the payload;
  - the restorable `_PAYWALL_TIPS` SKUs are all `is_tip_product` and claim no entitlement fields.
- **Targeted, with its own log:** `test_paywall_config.py`, `test_entitlements.py`, `test_analytics_p0.py`, `test_api_observability.py` → 136 passed, exit 0. `node mobile/tests/check-paywall.js` 11/11 and `check-tipjar.js` 9/9. check-tipjar is structural, so the empty list doesn't touch it.
- **Sabotage, each red then restored byte-identical (5):**
  - back to the UTC-date comparison (6 red);
  - the rise at UTC midnight (6 red);
  - `>` for `>=`, off by one second (3 red);
  - tips non-empty again (1 red);
  - `trial_days` back on annual (6 red).
- **Docs:** `docs/api-reference.md`, the `/api/paywall/config` row (the rise instant, empty tips). `docs/cross-client-invariants.md` § Monetization SKU ids: the SKU rows, the tip row and the fallback-prices bullet.

## 2026-10-27 — Paywall config fallback prices: $4.99 / $24.99 (→ $6.99 / $34.99 for new subs from 2027-01-01), no `trial_days`

Gates: a values fix to `GET /api/paywall/config` (flag `monetize.paywall`, still dark) flagged by marketing-lead via head-eng. The response loses the `trial_days` key and its prices follow #393's approved plan (operator 2026-10-25). No route, schema, event, flag or knob change. Server and docs only; mobile untouched. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest, a sabotage pass and a code walk of the old client.

- **The fix (`backend/server.py`):**
  - `_PAYWALL_PRODUCTS` drops `trial_days` (was 14 monthly, 30 annual) and carries no prices.
  - `_PAYWALL_PRICES` holds (before, from) pairs, switched by `_PAYWALL_PRICE_RISE_DATE = date(2027, 1, 1)`, judged in UTC: monthly $4.99 → $6.99, annual $24.99 / $2.09 → $34.99 / $2.92.
  - `_paywall_products(now)` is pure; the route passes it `_paywall_now()`, the clock tests patch.
  - `per_month_equiv` is the annual price / 12 rounded **up**: $2.09, matching legal's #393 R28.8 #2 copy, not the $2.08 a round-to-nearest gives.
- **Old-client render (code walk, main `mobile/src/screens/PaywallScreen.tsx:172-176`):**
  - the trial line is `trialEligible && p.trial_days > 0 ? … : null`, and `undefined > 0` is false, so it is null;
  - with no trial line, :360 renders nothing, the CTA at :383 reads "Continue", and the a11y label at :333 adds nothing;
  - the plans render "$4.99/month" and "$24.99/year" plus "$2.09/month, billed yearly" when StoreKit is unavailable (otherwise StoreKit's `priceString` wins).
  - A node emulation of that logic against the new payload printed exactly that.
- **Backend:** `test_paywall_config.py` is now 30 tests (was 15):
  - `test_products_shape` pins the exact key sets (no `trial_days`) at a frozen 2026-10-27;
  - the route on both sides of the rise (today, 2026-12-31T23:59:59Z, 2027-01-01T00:00:00Z, 2027-06-01);
  - no `trial_days` anywhere in the response, at all four instants;
  - the switch is judged in UTC (New York Dec 31 20:00 is risen; Paris Jan 1 00:30 is not);
  - the function is pure and leaves the module tables untouched;
  - `per_month_equiv` equals the ceil of price / 12 on both sides;
  - the default clock is the real aware UTC now.
- **Targeted:** `test_paywall_config.py`, `test_entitlements.py`, `test_analytics_p0.py`, `test_api_observability.py`, `test_account_deletion_coverage.py` → 166 passed. `node mobile/tests/check-paywall.js` 11/11 and `check-tipjar.js` 9/9 (mobile untouched).
- **Full suite** on the branch's working tree (`7b085e2d` plus this diff): `pytest backend/tests -q` → 9346 passed, 2 skipped, 0 failed, exit 0 (21m46s). Its own log, with junit confirming 9348 tests, 0 failures, 0 errors. A first run was discarded: another agent's suite wrote to the same scratch log.
- **Sabotage, each red then restored byte-identical (6):**
  - `trial_days: 30` back on annual (5 red);
  - the switch never fires (4 red);
  - `>` for `>=`, off by one day (2 red);
  - the date judged in the caller's tz, not UTC (2 red);
  - the route ignores the clock (2 red);
  - `per_month_equiv` rounded down to $2.08 (4 red).
- **Docs:** `docs/api-reference.md` (the `/api/paywall/config` row; plus the `/api/me/entitlements` row's drift fix: `/api/extension/auth` never carried `pro`, intentionally, legal R28.17); `docs/cross-client-invariants.md` § Monetization SKU ids (prices, the rise date, no `trial_days`). `docs/config-reference.md` n/a: the date is a code constant, not config.
- **Not covered:**
  - tsc not run here (no `mobile/` change; `billing.ts` still types `trial_days: number`, harmless at runtime, and the #393 M1 branch drops it);
  - `docs/plans/monetization/pro-subscription/lld.md` §3 JSON and `iap-enablement/sandbox-test-checklist.md` P2 still carry the old prices and trial lengths (history and ASC setup, left for the #393 owners).

## 2026-10-28 — Rebase case 2 follows the scope's newer job only while it's current (#484 QA P3-2)

Gates: release-lead's #484 QA P3-2, open since 10-27. It's flag-dark behind `trade.first_page_store` and must land before the ~11-04 flip. No route, schema, flag or knob change; the API reference's rebase case 3 wording is updated. No pipeline change: only serve-path code changed. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **The fix:** `_trade_deck_rebase`'s case 2 (the scope's newest job in this process) now uses P1's backing check (`_trade_rebase_job_current`), the one `_serve_trade_page_for` applies.
  - No input epoch may be revoked since the request.
  - The job must be fresh (`_trade_job_is_fresh`) or a matching running one (`_trade_running_matches`), against the same roster snapshot and the session's read.
  - A stale job falls through to the end or the kick, so the rebuild starts, as a fresh tap would.
- **Unchanged cases:** with no snapshot (a failed read, or `trade_i1_mode` 0), or one with no stored rows (`status` "missing", whose fp says nothing about the job's rosters), nothing proves the job stale (A2). It's followed as before, and the page view's own checks and S0's rules still decide what it sends.
- **One snapshot per poll is kept:** the rebase reads P1's serve snapshot once (lazily, shared by cases 1 and 2), and the job page view takes it (`_trade_job_page_view` / `_trade_job_public_view` `snap=`) for S0's serve rules. `test_each_deck_serve_reads_one_roster_snapshot` holds.
- **One test changed by design:** the C-e deck-path test edits the stored rows after building the newer job. On the rebased-job path it now re-stamps that job to the edited rows, so it still tests the C-e serve rule.
- **Backend:** `test_trade_pages_p2.py` (110):
  - a newer job whose rosters moved isn't followed, and the rebuild is kicked;
  - a matching running job is followed with no kick;
  - an input change means no follow;
  - both checks get the session's read.
- **Regression:** `test_trade_pages_p2`, `test_trade_page_store`, `test_trade_freshness_roster`, `test_i1_serve_filter`, `test_deck_i1_check` and the digest: 394 passed.
- **Sabotage, each red then restored (5):**
  - no check;
  - no session read;
  - input epochs ignored;
  - a fresh-only check, so the running job is lost;
  - a second snapshot read, which turns the one-snapshot test red.
  - Two of these stayed green on the first try (the session read was None; a kick joining the same running job looked like a follow); the tests were tightened.

## 2026-10-28 — #492 QA follow-ups and `repeat_head` (models-eng #503); deck pipeline v6

Gates: release-lead's #492 QA P3s, and models-eng's short-deck ask (`repeat_head`, agreed 10-28; #503 reads it). No route, schema, flag, knob or event change. `DECK_PIPELINE_VERSION` 5 → 6 (`d5176ae18c66d208`): `_run_trade_job` gates the record and passes the filter's `deferred` count. The deck's shape doesn't change; models-eng reviews the bump. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **P3-1:** the record is built only when the job holds deferred evidence. Before, it was computed and thrown away on every other deck, at 0.1–5 ms each.
- **P3-4:** a market value is a plain float, or null when it isn't a finite number. A bool is null and a numpy float becomes a float, so the header stays strict JSON.
- **P3-3:** QA's probes, ported to the real-worker harness. Its markets are all unseeded, so the probe asserts identity instead: the record gets the filter's returned cards (in order), its very callables and rosters, its viewer and its `deferred` count. It also asserts coverage equality and value equality. A cap-1 variant makes the filter reorder, so a record from the pre-filter cards fails here.
- **`repeat_head`:** the cap's kept trade_hashes when its head is shorter than 30, else null.
- **P3-5:** the data dictionary's "absent" now also covers a run revoked or timed out before the record was set.
- **#503 QA P2 (release-lead; agreed with models-eng):** a non-finite market's null is listed in `market_coerced` (sorted ids, absent when none), so #503's audit never reads it as an unseeded asset. A NaN first on a card had made a false filler FAIL; such a card is now not auditable for breakup and filler (models-eng's side, a follow-up after #501 and #503). A bool is now its 1.0 or 0.0, as the filter compared it. The unit tests cover both. `_quality_filter_inputs` is IGNORED, so the v6 pin is unchanged.
- **P3-2 (size):** no code change. For U8: the header is +9 to +12 KB per deck and rewritten 5–11 times per deck, and `evidence_blob` carries the record (+4 to +5 KB against the 250 MB cap). `repeat_head` adds at most 29 hashes (under 600 B) and only on a short cap. Release-lead's option (keep the record out of `base_run`'s deepcopy) is held for U8's numbers.
- **Backend:** `test_filter_inputs.py` (11: plus 5 `repeat_head` cases and the value coercion) and `test_filter_inputs_pack.py` (11: plus the no-deferred-evidence skip, the identity probe ×2 and `repeat_head` on the real cap ×2). 22 + the digest test passed.
- **Regression:** `test_bakeoff_serving` (the flag-off golden that pins the job's keys), `test_deck_quality`, `test_deck_pipeline_digest`, `test_packed_evidence`, `test_deferred_evidence` and both filter-inputs files: 304 passed.
- **Sabotage, each red then restored (7):**
  - the record built without deferred evidence;
  - no value coercion;
  - NaN kept as a float;
  - `repeat_head` always written;
  - the worker passing no deferred count;
  - the record from the pre-filter cards;
  - another market callable.

## 2026-10-27 — The quality filter's inputs, frozen per run (models-lead addendum D2); deck pipeline v5

Gates: models-lead's ruling D2 (B-DK-4..6 provenance), via head-eng. Field names agreed with models-eng (their changes: `viewer_team`; null, not absent, for an unseeded asset or a None position; coverage = the returned cards' assets plus the holdings; the optional `protected` included). It adds one per-run key to the pack's run header; no route, schema, flag or knob change. `DECK_PIPELINE_VERSION` 4 → 5 (stacked on #487's v4): `_run_trade_job` records the inputs, and `_quality_filter_inputs` is in `DECK_PIPELINE_IGNORED`. The deck's shape doesn't change. models-eng reviews the bump. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **CI fix (`backend-tests` at `c2253799`):** recording on the job broke `test_bakeoff_serving`'s flag-off golden, which pins the job's keys. The record now lives on the deck's evidence (`ev.filter_inputs`), and v5 is re-pinned in place (`99d62fcaf7ad01ef`).
- **Backend:** `test_filter_inputs.py` (5, unit) and `test_filter_inputs_pack.py` (6, real organic jobs with deferred evidence, and a real packed job for the header):
  - the record holds what the filter read (nulls, coverage, `qb_te` for the viewer and counterparties only, `protected`);
  - the lineup recorded as read (null / empty / list);
  - not a frozen input;
  - the real worker's record reproduces the filter: every kept card passes breakup and filler on it;
  - flag off, or a failed filter → `filter_ran` false;
  - a failed record never unfilters the deck;
  - the pack's run header carries it; a deck with no record has none.
- `test_deck_pipeline_digest.py`: v5 added to FROZEN_PINS.
- **Sabotage, each red then restored (8):**
  - job done dropping it;
  - the worker never setting it;
  - recording it on the job too (the golden goes red);
  - a record failure unfiltering the deck;
  - an unseeded asset absent instead of null;
  - `qb_te` for every team;
  - no record with the flag off;
  - no `protected`.
- **Size:** about 8.4 KB of JSON for a synthetic 120-card, 12-team deck (190 market entries; up to 121 QB/TE holdings with random positions, about 72 with real ones). It sits in the run header, which is rewritten on every header update. U8's re-measure takes the real number.
- **Full suite:** `pytest backend/tests`, 9,351 passed at `63638007` (merged with main at `0fa614d5`). After resyncing onto `190ce568` (#460; a ledger-only conflict), the targeted suites passed.

## 2026-10-26 — Settings labels ESPN/MFL sign-in identities (the onboarding-eng side of platforms-eng's ESPN/MFL sign-in)

Full gates, not express (scope: platforms-eng's ESPN/MFL sign-in, the onboarding-eng side; MUST 2 of onboarding-eng's design review). Mobile only; D-056: no simulator, `FTF_SKIP_SIM_GATE=1` posture. Frozen values (platforms-eng, 2026-10-26): identity provider `espn` / `mfl`, `verified_via` `espn` / `mfl_login`.

- **Change (`87011998`):**
  - a new shared map, `screens/settings/identityLabels.ts`: apple/google/espn/mfl → "Signed in with Apple/Google/ESPN/MFL"; `identityLabel()` returns null for any other provider;
  - `AccountIdentitySection` and the flag-off flat `SettingsScreen` render `identityLabel(ident.provider)` and **no row** for an unknown provider. Before this, every non-Apple identity read "Signed in with Google";
  - `SettingsHubScreen`: the provider type gains `espn` / `mfl`; the `verified_via` fallback maps `espn` and `mfl_login`; the labels are "ESPN" / "MFL". The Sleeper and demo branches are unchanged;
  - `AccountInfo` identities' provider type gains `'espn' | 'mfl'`.
  - Not touched: `SignInScreen.tsx`, the link sheets and `platformEntry.ts`. The `handleEntrySession` pass-through is platforms-eng's, on #443.
- **New guard `check-signin-identity-labels.js`** (`npm run test:signin-identity-labels`), 4 pins:
  1. the map labels `apple`, `google`, `espn` and `mfl` exactly, and an unknown provider gets null (executed);
  2. no `: 'Signed in with …'` fallback anywhere in `mobile/src`, and no "Signed in with …" literal outside the map;
  3. both row renderers take the label from `identityLabel()` and return null without one;
  4. the hub's own `verifiedVia` / `provider` / `signInLabel` declarations, executed: espn/mfl identities and `verified_via` `espn` / `mfl_login` give "ESPN" / "MFL"; Apple, Google, Sleeper and demo are unchanged.
- **Changed pin:** `check-settings-ia.js`'s identity-row marker moves from the literal `Signed in with Apple` to the `identityLabel(ident.provider)` call that renders it.
- **Sabotage: 21/21 red,** each restored byte-identical. That includes the moved settings-ia marker and the whole change reverted to `origin/main`.
- **Local runs:** `tsc --noEmit` clean; testid-lint OK; 118/118 `check-*.js`.
- **Operator TestFlight check,** once a build has the ESPN/MFL sign-in (platforms-eng's #443):
  1. Sign in with ESPN. Settings › Account shows "Signed in with ESPN", and the hub's account row reads "Signed in with ESPN" ("ESPN" in its preview).
  2. Sign in with MFL. The same rows read "Signed in with MFL" / "MFL".
  3. Apple and Google sign-ins are unchanged: "Signed in with Apple" / "Signed in with Google", and "Apple" / "Google" on the hub.
- **release-lead QA fixes (`63603e47`, `d10046a0`):** the hub maps `mfl_login` → "MFL" only on an account-only session; `/api/mfl/auth-link` also writes `mfl_login` for a Sleeper user who connects MFL, who stays "Sleeper" (P2). `espn` stays unguarded. Pin 4 gains release-lead's case (a Sleeper user verified by MFL auth-link → "Sleeper"); it fails on `40da9bc0`. **Sabotage 3/3 red.** `AccountInfo.verified_via` admits `mfl_login` / `espn` (P3). Runs: tsc clean; testid-lint OK; 118/118 `check-*.js`. Operator step 4: a Sleeper user who connected MFL by password still reads "Signed in with Sleeper" on the hub.

## 2026-10-27 — F5's drop is an eviction: `evicted_split`, and the `f5_past_stored` anomaly (models-lead addendum D1)

Gates: models-lead's ruling, D1 (`leads/models-lead-launch.md` addendum D), via head-eng. It changes one evidence cause (`restart_split` → `evicted_split` for an F5-dropped deck) and adds one ERROR log line. No route, schema, flag or knob change. It's not flip-gating; it must land before the first weekly ceiling read. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **The change:**
  - At F5's drop, the deck goes into `_deck_evicted_at` (kept ≥ 24 h, C3 (c2)) and a new `_deck_f5_dropped` ledger. This replaces #457's removal from `_deck_held`; it isn't added to it.
  - C3 (c1) is unchanged: below the effective stored count, a miss is `other`.
  - The anomaly (`_f5_past_stored`): an F5-evicted miss at or past the pack-recorded stored count logs `[evidence] f5_past_stored …` at ERROR, apart. The cause stays `evicted_split`.
- **Backend:** `test_evidence_cleanup.py`. The F5 repro is now `…_reads_evicted_split_…` (×6: both row-gone ways × F5 only, F5 then the job evicted, a real restart = `restart_split`), with the held entry kept. 3 new tests:
  - below / past the effective stored count;
  - `_f5_past_stored` only for an F5-evicted miss at or past the recorded count;
  - the anomaly line logged once, with the cause kept.
- **Run:** `test_evidence_cleanup.py` + `test_u4_ruled.py`, 52 passed. On the first cut, the evidence suites (cleanup, deferred, U4 ruled, upgrade-miss cards, pipeline digest) passed 165.
- **#489 QA (NO-GO, P1-1), option (a), pending models-lead's reading of D1:**
  - The P1: kept in `_deck_held`, an F5 deck read `other` (a false G7 FAIL) once its evicted entry aged out.
  - The fix: F5's drop now also pops `_deck_held`, like any eviction, so the late view reads `restart_split`.
  - New tests: the eviction aging out → `restart_split`; the anomaly on the kept cause; no anomaly on a real F5 row-gone miss; a bool count refused; the jobs → ledger lock order; the guard's `f5=`.
  - Sabotage (7, each red then restored): no held pop; the anomaly on the local cause; the anomaly on the effective count; a bool count; a reverse lock on the read path; the guard dropping `f5=`; f5 trims counted as held.
  - Docs: the contract sentence and LLD. (Corrected 2026-10-28, #489 QA P3-1: the data dictionary wasn't changed. Its ERROR-line note from `85286cf7` already held. Commit `7d5d0edb`'s message says otherwise.)
- **Sabotage, each red then restored (5):**
  - F5 also leaving the held ledger (#457's way: superseded by option (a) above);
  - F5 not an eviction;
  - the anomaly on any eviction;
  - the anomaly strictly past;
  - the anomaly not logged.

## 2026-10-29 — D-13 P2-2 (legal R28.22, MUST for 11-06): the notice is never marked seen at sign-in; B7 removed

Full gates (head-eng's routing of legal R28.22, Product agrees; scope `docs/plans/prelaunch-onboarding/scope-b7-d13-fresh-install.md`, § P2-2). Mobile only. D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **The change:** B7 is removed. `useWhatsNew` no longer reads a boot fact, writes the seen key at boot, or hides the entry for a signed-out boot. `useSession` drops `bootSignedIn` (back to the branch base). The only seen-mark is the tip's own tap (`dismiss`), so every signed-in user, a fresh sign-in included, gets the D-13 tip once. No copy change; the pinned sign-in line stays.
- **Guard** `check-whats-new.js` pin 8 rewritten (the seen key written once, in dismiss, and nowhere else in `src/`; no in-memory mark elsewhere; no session read; the exact entry condition; no `bootSignedIn`). **Sabotage 7/7 red**, restored byte-identical; a comment-only control stays green.
- **TestFlight:** the scope's 6-step P2-2 checklist replaces B7's 3 steps.
- **2026-10-29, release-lead delta QA @ `d318d180`: GO-with-notes.** An executed harness across 21 states shows the tip until its own tap (the same harness fails 17/21 on B7). **P2 (doc), fixed:** the checklist now says "the League tab, then League home" (LeagueHome sub-route), names both Apple entries (#507's button or the text link), and step 4 needs a device that never ran 1.22.0. The P3s (pin 8's indirect writes; no crediting the device ack to the first signed-in account) go to P2-3.
- **Runs:** see the PR.

## 2026-10-27 — Session-init trade capture skips linked-platform leagues (G-030)

Full gates, platforms-eng lead (platforms-pm audit F5). Server only, no API or schema change; D-056: `FTF_SKIP_SIM_GATE=1` posture, the evidence is pytest. Branch `fix/trade-capture-platform-guard`.

- **Defect:** the `market.trade_capture` block in `session_init`'s background daemon gated on `str(league_id).isdigit()` alone. ESPN, MFL and Fleaflicker native ids are numeric, so every init on a linked league sent Sleeper `GET /league/<id>/transactions/<week>` reads with a platform-native id. A league with no captured rows is re-backfilled each time (`sweep_weeks` returns 1..18 until `has_sleeper_trades`), and a linked league never captures any, so that was 18 reads per init.
- **Fix (`backend/server.py`, the `market.trade_capture` block):** added `and not _platform_linked`, the `is_linked_platform_league(league_id)` result the daemon already reads once at its top (the same guard the roster-history snapshot beside it uses). Sleeper leagues are unchanged.
- **Tests (`test_session_init_sleeper_calls.py`, 7 tests):**
  - The old MFL test tolerated `transactions` as a "known, pre-existing" Sleeper call. It is now `test_numeric_mfl_league_makes_no_sleeper_calls` and asserts `calls == {}`.
  - New `test_numeric_espn_league_makes_no_sleeper_calls` (a numeric ESPN-linked league, same assertion).
  - New `test_sleeper_league_still_captures_trades` (a Sleeper league with no captured rows makes exactly 18 `transactions` reads).
- **Sabotage, red then restored:** the `and not _platform_linked` line removed → the MFL and ESPN tests red (`assert {'transactions': 18} == {}`); the other 5 stay green.
- **Targeted:** `test_session_init_sleeper_calls`, `test_session_init_single_flight`, `test_market_data_readiness`, `test_co_owner_rosters`, `test_roster_refresh_state`, `test_players_refresh`, `test_account_only_harness`, `test_verified_sessions`, `test_trade_fingerprint_reads_unlocked`, `test_prepared_trade_runtime` → 162 passed.
- **Not run:** the full suite (CI runs it); no live Sleeper calls (every fetch is mocked).

## 2026-10-27 — B-DK audit reads the quality filter's own inputs (models-lead addendum D2, #492)

Gates: eval-side only (`backend/eval/bdk_audit.py`, its tests, the runbook § B-DK audit and the evidence-contract lines). It's stacked on the display-moves loader PR. No route, schema, event, flag, knob or engine-module change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **What changed** (release-lead's #492 QA notes, all taken):
  - B-DK-4..6 now read the pack's `run["filter_inputs"]` (v1), with null and NaN markets passed to the rules as the filter saw them.
  - An asset absent from the record makes its card not auditable.
  - Protection is the record's trade_hashes.
  - `position_caps(lineup_slots)` None means the filter skipped B-DK-6: a pass.
  - B-DK-6 reads the viewer's and the counterparty's (`str(partner_user_id)`) QB/TE holdings; an absent team holds nothing.
  - `filter_ran: false` decks are skipped (`filter_not_run`).
  - Decks without a record are counted by state (`record_failed`, `pack_without_record`, `no_pack`), and they're not auditable for 4..6.
  - `valuation_json` is no longer read, which removes the owner-deck false FAILs (D2 (c)).
  - B-DK-7 is unchanged except that a recorded deck's protection now comes from the record.
- **Tests:** `test_eval_bdk_audit.py`, 69 tests:
  - the value rules on the record;
  - the record read, never `valuation_json`;
  - record protection versus a row flag;
  - row flags still protecting without a record;
  - B-DK-6 on the viewer's and counterparty's holdings;
  - B-DK-6 reproducing `filter_deck` on full rosters over a grid;
  - an unknown lineup as a pass;
  - nine record states;
  - filter_not_run skipped;
  - an unseen asset;
  - a null or NaN market (the header's NaN token read);
  - str ids.
  - Together with `test_eval_display_moves.py`: 90 passed. Flip-read and blind-grade suites: 212 passed.
- **Sabotage, each red then restored (8):**
  - protection always from the row;
  - no counterparty side;
  - the viewer's holdings for both sides;
  - an unknown lineup not auditable;
  - no coverage check;
  - filter_not_run decks audited;
  - a bool version accepted;
  - decks without a record audited anyway (27 red).
- **B-DK-7 short caps (agreed with trades-eng; their v6 writes it):**
  - The record's `repeat_head` holds the trade_hashes of the cards the cap kept, only when it kept fewer than W.
  - A breach is explained when every unprotected over-cap card is outside it, so no rows past the window are needed.
  - A list naming one of them is a violation, even where a re-run would explain it.
  - Without the field, the re-run applies as before.
  - Tests: 5 (deferred / kept / absent; protected cards in the head; the record outranks a re-run).
  - Sabotage, 3 red: the head ignored; protected not skipped; a fall-back to the re-run.
- **Checked on trades-eng's D3 writer packs** (`feat/trades-serve-repeat-cap` @ `1cb381b6`, `test_a_later_page_moves_the_pulled_card_and_records_it`, all 6 cut/i1 × stored/job_view/left_process cases):
  - #501's loader order equals their `displayed()` ([29, 32, 30, 31, 33] around the move), with dense positions;
  - their suite passes with #501's `data.py` (80).
- **Not covered:**
  - whether live-evidence decks' not-auditable B-DK-4..6 blocks certification is models-lead's call.

## 2026-10-27 — Eval loader reads serve-time display moves (models-lead addendum D3)

Gates: eval-side only (`backend/eval/data.py`, a doc line in `bdk_audit.py`). It reads the pack header field `run["display_moves"]`, agreed with trades-eng, whose serve side writes it. No route, schema, event, flag, knob or engine-module change; an absent field changes nothing, so this merges before or after the writer. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **Why:**
  - D3's fix re-applies the repeat cap at serve time.
  - When a never-delivered withdrawal pulls a deferred card into the first 30, the server shows that card later in the same response.
  - The loader's position was card_index less the W0s below it, so it put the card back inside the window: a false B-DK-7 FAIL and a shifted e(k).
- **The rule:**
  - The kept non-ghost cards' positions are handed out in display order, `(anchor, 1, card_index)` for a moved card and `(card_index, 0, card_index)` otherwise.
  - A move counts once its response is delivered as of the read, so a re-read at the same as_of is stable.
  - A record breaking the writer's contract makes the deck `pack_integrity` (ahead of `withdrawal_conflict`): a malformed key or value, an anchor that is itself moved, a self-anchor, a ghost, missing or W0 card, or a move spanning two responses.
- **Tests:** `test_eval_display_moves.py`, 26 tests:
  - no moves;
  - one move; two behind one anchor;
  - moves after a W0;
  - as_of stability;
  - 16 malformed records;
  - a valid later-response move;
  - precedence;
  - B-DK-7 end to end (the moved deck passes; without the record the same deck is the false FAIL).
- **Sabotage, 8 of 9 red then restored:**
  - moves ignored (6 red);
  - no as_of guard (1);
  - moved card before its anchor (6);
  - no same-response check (1);
  - chained anchors allowed (1);
  - W0 allowed (2);
  - lenient keys (1);
  - integrity after the conflict check (1).
  - The ninth, a plain dense rank in place of the W0-adjusted slots, stays green as expected: the two are equal on every deck the loader doesn't exclude (an unexplained gap is `incomplete_deck`).
- **Eval, value-model and evidence suites:** `test_eval_*`, `test_value_model*`, `test_packed_evidence`, `test_deferred_evidence`: 578 passed.

## 2026-10-27 — B2: the launched onboarding flags in first-paint defaults (Product's pre-launch review)

Full gates (head-eng's ask; scope `docs/plans/prelaunch-onboarding/scope-b2-flag-defaults.md`). Mobile only; no flag value changes; D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **The change:** `LAUNCHED_FLAG_DEFAULTS` gains five flags, each `true` as in `config/features.json`:
  - `onboarding.v2`, `onboarding.landing`, `landing.platform_options`, `mfl.link`, `account.settings_hub`.
  - `espn.signin` waits for ask 15.
- **New guard `check-onboarding-flag-defaults.js`** (`npm run test:onboarding-flag-defaults`), dependency-free:
  - each key is baked, with `features.json`'s value;
  - `espn.signin` is baked only once `features.json` carries it true.
  - **Sabotage 6/6 red,** restored byte-identical.
- **Runs:** see the PR (tsc, the full `check-*.js` loop, testid-lint).
- **Operator TestFlight check** (11-06 build):
  1. a fresh install opened offline paints the username landing with the platform chips;
  2. after going back online, the same landing shows;
  3. Settings is the hub.
- **2026-10-28, release-lead QA @ `6b0c3b8f`: NO-GO on P1-1 → fixed:**
  - **P1-1:** `landing.platform_options` is no longer baked. A baked `true` painted chips that dead-end while the server holds the flag off (the purge window). It's baked with ask 16. Guard pin 4 keeps it out.
  - **P2-1:** the defaults' comment no longer contains the ESPN sign-in flag's literal, which had turned #443's `check-espn-signin-flag` pins 4/6 red.
  - **P3-1:** pin 5, "a server or cached false wins": the store starts from the defaults, a cached map spreads over them, and a fetch replaces the whole map. **Sabotage 4/4 red**, covering QA's three surviving wiring cases plus the chips flag baked again.
  - **2026-10-29, CI after merging main (#404, B8's update gate):** B8 widened the post-fetch `set({ flags, loaded: true })` to also set `appMinVersion` / `appStoreLive`, so pin 5c's exact-text match went red in `mobile-typecheck`. Pin 5c now matches a `set({ flags, loaded: true, …` that takes `flags` whole, still with no `LAUNCHED_FLAG_DEFAULTS` in the revalidate. **Sabotage 3/3 red** on the new shape (defaults merged under the fetch; the fetched map not set; defaults spread into it); a comment-only control stays green. tsc clean, 124/124, testid-lint OK.
  - **P3-4:** the TestFlight checklist is rewritten to 6 steps: online, offline, warm, server-false, Settings, kill switch. The offline step now expects **no** chips.
  - **Not taken:**
    - P3-2: the s0.1 guide intro is latent until `onboarding.guided_avatar` goes on;
    - P3-3: the entry sheet should close when the chips flag is withdrawn.
    - Both are in `SignInScreen.tsx`, which #443 and #507 are changing, so they're logged for that stack.

## 2026-10-27 — S0 picks-read follow-ups: draft verdict in the key, owner path on the job's reads (#486 QA P3s); deck pipeline v4

Gates: QA follow-ups to #486 (stacked on it). No route, schema, event, flag or knob change. `DECK_PIPELINE_VERSION` 3 → 4:
- `_run_trade_job` gains `_job_draft_context` (one memoized draft-verdict read);
- `_job_draft_picks` notes the picks with that verdict;
- the worker hands both reads to `_owner_generation_context` (new `job_draft_picks` / `job_draft_context` params; other entrances read their own).

The values are the same, so the deck's shape doesn't change. models-eng reviews the bump. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **Covered:**
  - P3-1: the owner path's second picks read is gone for trade jobs.
  - P3-2: the match docstring states the A2 rule for None stamps.
  - P3-3: spy tests for "one kickoff read" and "every worker picks read is noted", with the owner path on.
  - P3-4: a key that can't be computed unstamps.
  - P3-5: the picks key covers the draft verdict (kickoff and worker).
- **Backend:** `test_trade_freshness_roster.py` is now 49 tests (6 new):
  - a draft-verdict flip unstamps;
  - an unchanged verdict keeps the stamp;
  - a failed key unstamps;
  - one kickoff read;
  - every worker picks read noted;
  - the owner context uses the job's reads.
- `test_deck_pipeline_digest.py` (v4 in FROZEN_PINS) and `test_pick_assignment.py` pass, 44 together.
- **Sabotage, each red then restored (10):**
  - the owner path reading its own picks (QA's T5);
  - the inject path reading its own (`picks=None`);
  - the opponent shares reading their own;
  - the owner path ignoring the job's picks, or its draft;
  - the kickoff key without the verdict;
  - the note without the verdict;
  - a failed key keeping the stamp;
  - the kickoff reading twice.
  - Green by design: the seeded-outlook site (`_infer_user_outlook(..., _job_draft_picks())`) runs only without `prefs_preload`, which a kickoff always supplies.
- **models-eng's review: OK on the success path, one objection, fixed.**
  - **The objection:** the shared memos turned a failed read into an owner arm serving cards with no draft protection. Before, the owner path's own read raised, its context capture failed and the arm forfeited.
  - **The fix:** the memos remember the failure, and the owner path gets views that re-raise it. The stamp check keeps its degrade-to-empty.
  - **v4 is re-pinned in place** (`864cf30974da20ea`, in DECK_PIPELINE_PINS and FROZEN_PINS), since v4 was never on main.
  - **Tests (3 new):** the owner context builds from the job's reads; a raising picks read forfeits the owner arm; a raising draft read forfeits it.
  - **Sabotage, each red then restored (4):** the owner path given each degrading memo; each view never raising. QA's T5 is still red on the new call site.
  - **Full suite** on `54e42967`: 9340 passed, 2 skipped, 0 failed (12m12s). An earlier run on `56d395d0` is discarded: its 15 failures were source-reading tests that saw `server.py` mid-edit, and they pass on this head.
  - **models-eng OK at `54e42967` (2026-10-27).** The objection is resolved and the pin reproduces. Their stricter-edge note: an earlier failed read in the same job now forfeits the owner arm, where its own re-read might have succeeded. That fails closed, by design.

## 2026-10-27 — Web gate: the web's ESPN/MFL chips are hard-off (before ask 16)

Full gates (head-eng's ask, item 3; scope: [scope-web-gate.md](../docs/plans/landing-platform-options/scope-web-gate.md)). Web only; D-056: `FTF_SKIP_SIM_GATE=1` posture, no mobile change.

- **Change:** `web/js/app.js` `const WEB_PLATFORM_ENTRY = false` replaces both reads of `landing.platform_options` (the chip reveal and `selectEntryPlatform`). It's declared above `_applyLandingFlags()`, which runs the reveal at once (no TDZ).
- **Pin `GATE-web-espn-mfl-off[index.html]`** (`qa/web/check_web_structure.py`):
  - no web script or page reads the flag;
  - exactly one `const WEB_PLATFORM_ENTRY = false;`;
  - the reveal and the handler both go through it;
  - the row and both chips ship `hidden`.
  - **Sabotage 8/8 red,** each restored byte-identical.
- **Runtime (local static serve):** every flag forced on and `ftf:flags-ready` fired leaves the row and chips hidden, and `selectEntryPlatform('espn')` is a no-op. The same script on the pre-change code shows them and selects ESPN (the control). The console shows only the static server's `/api/feature-flags` 404.
- **Runs:** `python3 qa/web/check_web_structure.py` 196/196 (CI's `web-structure` job); `node --check` OK on both changed JS files.
- **`qa/web/check_browser_auth_runtime.cjs`** (local Playwright harness, not in CI): its ESPN-chip click now asserts the row and both chips are hidden, with no `/api/entry/platform` call.
  - **Not run:** no Playwright install here.
  - The replaced lines were already stale on main: they waited for an ESPN/MyFantasyLeague sentence that's gone from `web/`.
- **Not covered:** no JS unit harness on web; the operator's optional post-deploy look (signed out, flag ON: Sleeper door only) is in the scope block.

## 2026-10-27 — S0 stamp hashes the picks the worker read (#484 QA P2-1); deck pipeline v3

Gates: a QA fix inside the 200 ms programme's S0 scope. No route, schema, event, flag or knob change. `DECK_PIPELINE_VERSION` 2 → 3: `_run_trade_job`'s `_job_draft_picks` now calls `_note_job_picks_read`, so the deck's shape doesn't change. models-eng reviews the bump. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **The bug (QA's E1b, E1c-moved, 5/5 STALE):**
  - The stamp and `roster_fp_expected` hashed the picks stored at kickoff, but the worker reads picks later.
  - A pick move, or an older refresh writing back (ABA), between the two reads re-stamped or kept a deck whose picks differ from its stamp.
  - Main had the sibling with no member move.
- **The fix:**
  - One kickoff read gives the stamp, `roster_picks_key` (`roster_snapshot.picks_key`) and the expected fp.
  - The worker's read checks the key. On a mismatch the stamp goes to None (never reused or stored) and the expected fp is dropped, so no later re-stamp can mark it fresh. A re-stamp that came first is undone.
- **Backend:** `test_trade_freshness_roster.py` is now 43 tests (7 new):
  - one kickoff read;
  - a matching read keeps the stamp;
  - main's sibling (P0, then P1, then back to P0) is unstamped and never reused;
  - the pre-gen pick ABA is never re-stamped;
  - a worker read after a re-stamp undoes it;
  - a failed worker read is unstamped;
  - the co-owner keying of `_session_member_rows` (QA P3).
- `test_deck_pipeline_digest.py`: the v3 pin is added to FROZEN_PINS. 68 passed across the two files plus `test_roster_refresh_state.py`.
- **Full suite** on `922517fb`: `pytest backend/tests -q` → 9322 passed, 2 skipped, 0 failed (11m19s).
- **models-eng reviewed the v3 bump (OK, 2026-10-27).** An AST diff of every pinned function against main shows only the `_note_job_picks_read` line in `_job_draft_picks`. The pin reproduces, and the IGNORED classification holds: it never mutates the picks, writes only `roster_fp` and `roster_fp_expected`, and no call site holds `_trade_jobs_lock`.
- **Sabotage, each red then restored (7):**
  - the worker doesn't note (6 red, the digest among them);
  - the note keeps the expected fp;
  - the note keeps the stamp;
  - no kickoff picks key;
  - the expected fp from a separate read;
  - the builder's ids not strings;
  - the builder keeps a blank owner.
- **Not covered:**
  - rebase case 2's freshness (flag-dark) is still a follow-up;
  - QA's D/B0 regressed-row re-stamp, which is informational: its content equals the stored rows.

## 2026-10-27 — `deck_i1_check` worker follow-ups: restart, deletion skip, exit drain, drop tail (#468 QA P3-1…P3-5)

Gates: QA follow-ups to #468 (stacked on it). No new event, prop, route or schema; the event's write path changes. One additive method, `user_data_lifecycle.Lease.deleting()`. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **Backend:** `test_deck_i1_check.py` is now 39 tests (9 new):
  - a dead worker restarted (P3-1);
  - an `Exception` in a write leaves the same worker;
  - a deleting user's write skipped while another user's lands at once, under a real `user_data_lifecycle.hold` (P3-2);
  - a refusing lease writes nothing;
  - the exit drain lands queued writes and force-logs pending drops (P3-3), and is registered with `atexit`;
  - a burst's tail logged by the idle tick (P3-5);
  - the fallback identity keeps the partner;
  - the LRU evicts the least recently served job (`move_to_end`).
- **Sabotage, each red then restored** (9): no restart; no deletion skip; no worker `except`; the lease ignored; the exit warning not forced; no idle tick; no `atexit`; the fallback without the partner; no `move_to_end`.
- **Full suite** on `28c63587`: `pytest backend/tests -q` → 9281 passed, 2 skipped, 0 failed (12m08s).
- **Not covered:** a deletion that starts between `deleting()` and `active()` still holds the worker for that deletion's length (a narrow race). A skipped write for a deletion that then aborts is lost (one analytics row).

## 2026-10-27 — S0 roster-change follow-ups: stale rebuilds aren't shared; the init's pre-gen is re-stamped (#481 QA P3-1, P3-2, P3-3)

**#484 QA round 2 (NO-GO on P1-1, fixed):**
- **The bug:** with two refreshes in flight (ordering B), the re-stamp keyed on `refreshed_at == the job's read` and a picks key. It re-stamped dev1's M1 deck to fp(M2): `new_fp` hashes whatever members are stored at stamp time.
- **The fix:** the re-stamp is now hash equality. At kickoff, while the session's refresh is in flight, the job takes `roster_fp_expected`: the rfp1 of the session's `roster_read_rows` (built by `_session_member_rows`, the same builder as the daemon's write) with the stored picks and draft state. The handler re-stamps only when that equals `new_fp`. The picks key is gone.
- **Folded in:**
  - P3-1: replenish passes its live session's read.
  - P3-3: the kill switches stop `_job_read_predates_move` at once, and the kickoff read doesn't run at knob 0.
  - P3-4: tests for an older-read re-stamp and for the pre-gen, page-backing and replenish `session_read` sites.
- **Not folded in:** rebase case 2's freshness (flag-dark) is left as a follow-up.
- **Tests:** freshness 36 and roster refresh state 17; 53 together. The new tests:
  - ordering B (M1 deck, M2 rows, T1 stamp, no T2 hook): the deck keeps its stamp, isn't fresh, and a T2 device's `/generate` builds its own;
  - equality vs. read time;
  - the expected-fp window and its kill;
  - the kill switches on recorded moves;
  - the session's read rows hash to the daemon's write;
  - the pre-gen, page-backing and replenish sites.
- **Sabotage, each red then restored (15):**
  - re-stamp by read time (3 red, ordering B among them);
  - no re-stamp;
  - `_job_read_predates_move` ignoring the kill;
  - the expected fp ignoring the knob;
  - no session read rows;
  - the pre-gen, page-backing and replenish sites without `session_read`;
  - the session-read rule, the store guard, the move record;
  - S6, S7;
  - the expected fp outside the window, and no kickoff expected fp.

**Round 1 (superseded where it mentions the picks key):**

Gates: QA follow-ups to #481, inside the 200 ms programme's S0 scope (`scope-eng-200ms.md` §6.1). No route, schema, event or flag change; the knob `trade_roster_change_revoke` (from #481) now also stops the re-stamp and the move record. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **Backend:** `test_trade_freshness_roster.py` is now 32 tests (7 new). The P2-2 repro is parametrized: after a player move the pre-gen is re-stamped and `/generate` reuses it; after a pick move it keeps its old stamp.
  - The new P3-1 test covers a stale session's rebuild: device 2 neither reuses nor joins it, device 1 reuses it, and the store refuses it before the eligibility check.
  - The new P3-3 tests cover S6 (a session in another league) and S7 (two sessions, the newer read wins).
- **Targeted, 582 passed:** the S0, session-init, page-store, deferred and packed evidence, force-supersede and deck-pipeline-digest suites.
- **Sabotage, each red then restored** (10):
  - the session-read rule, the store guard, the move record;
  - the re-stamp, and a re-stamp that ignores picks;
  - S6 (any league), S7 (oldest wins);
  - no kickoff picks key, the key taken outside the in-flight window (the picks key is replaced in round 2);
  - `/generate` and kickoff without `session_read`.
  - The pre-gen and page-serve `session_read` sites are not covered by a test: code walk at `server.py` `_serve_trade_page_for` and session init's `should_kickoff`.
- **Full suite** on `0beeb67d`: `pytest backend/tests -q` → 9267 passed, 2 skipped, 0 failed (11m50s).
- **Full suite** on `e09327e3` (main merged in, #470 included): 9284 passed, 2 skipped, 0 failed (11m10s).
- **Full suite, round 2** on `14828f06`: 9298 passed, 2 skipped, 0 failed (11m38s).
- **Combined with #470** (a local merge of `0beeb67d` with `5e310b00`): #470's `test_roster_fp_stamp.py` plus the S0 files, 104 passed.
  - A scratch end-to-end run used #470's real `stamp`, with the daemon held until the pre-gen had read its fingerprint.
  - Player move: 1 hook; the pre-gen is kept, carries a picks key and is re-stamped to the stored fp.
  - No change: no hook. The scratch worktree is ledgered.
- **Not covered:**
  - `_roster_moved_reads` is per process. One web worker today (`render.yaml`, pinned by a test); a second worker would see only its own moves.
  - A stored page row written before a re-stamp keeps its old stamp: its serves take the moved path (the I-1-filtered page) until the next store.

## 2026-10-27 — Owned-pick sync follow-ups: season-only prior-grid read; P3-3 verdict gate tried, then dropped as a recorded limitation (#482 QA nit + P3-3, #483 QA P3-1)

Server only, platforms-eng lead. Stacked on `fix/owned-picks-drafts-flake` as `fix/owned-picks-drafts-flake-followups`. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest. No flag, route, schema or analytics change.

- **(a) Nit:** the prior-grid check now reads one `SELECT DISTINCT season` through the new `database.load_draft_pick_seasons(league_id, source='platform')`, which uses `load_draft_picks`'s platform predicate and raises on any other source. The W3 AST guard in `test_pick_assignment.py` now enumerates both readers (`_PICK_READERS`), so `_sleeper_prior_grid_excludes` stays in `_SANCTIONED_SOURCE_CALLERS`.
- **(b) P3-3, first attempt (`ffb5b2f1`, superseded):** the sticky rule applied only when the cached verdict was absent or `unknown`, and a cached `not_drafted` was trusted. Tests then: 3 new, the file at 42. Sabotage (gate dropped) turned the `not_drafted` test red. Targeted: 78 passed; the 59 related files: 1845 passed.
- **(b) revised, #483 QA P3-1, option (b):** the gate undid #482 for a common shape: a completed startup draft plus a pending rookie draft. `sleeper_verdict` reads that `not_drafted`/high, while the shape-blind `completed_draft_seasons` excludes the season, so every flake flipped the fp again (QA: 6 of 7 syncs on #483, 0 on main). The gate is removed: the sticky rule again applies whenever the cached verdict isn't `drafted`, exactly as #482 shipped. P3-3 is now a recorded limitation (D-189 amendment, `docs/integrations/sleeper.md`). The sync condition's diff against main is now only the reader swap (plus comments).
- **Tests in `test_owned_picks.py` after the revision (the file is now 43):**
  - `test_prior_grid_season_reader_reads_platform_rows_only` (kept): a user row's season is not in the set, and `source='any'` raises;
  - `test_always_empty_drafts_stays_excluded_after_not_drafted_known_limitation` (inverted from the `not_drafted` re-includes test): the accepted P3-3 limitation pin;
  - `test_startup_complete_rookie_pending_flake_keeps_season_and_fp` (new): the cached verdict comes from the real `sleeper_verdict` (asserted `not_drafted`/high); live → flake → live → flake keeps 2026 excluded and one rfp1;
  - `test_always_empty_drafts_keeps_the_exclusion_on_an_unknown_verdict` (kept);
  - the read-error test injects into `srv.load_draft_pick_seasons` (kept).
- **Sabotage, red then restored:** the P3-3 gate re-added → 2 red: the startup-shape test and the limitation pin (`[2026, 2027, 2028] == [2027, 2028, 2029]` each).
- **Targeted after the revision:** 11 files → 317 passed: owned-picks, pick-assignment (+ tradeable), draft-status (+ wiring), pick-tradability, and the S0 suites (`roster_fp_stamp`, `roster_refresh_state`, `roster_refresh_async`, `trade_freshness_roster`, `roster_snapshot`).
- **Not run:** the full suite (CI runs it), `tsc` and testid-lint (no mobile change).
- **Docs:** `docs/integrations/sleeper.md` (the rule, the limitation and the read-cost row), `docs/data-dictionary.md` (the new reader, in the containment section), and the D-189 amendment.

## 2026-10-27 — `deck_i1_check` follow-ups: each card counted once per job, one bounded worker, drained in tests (#468)

Gates: #419's QA follow-ups. No new event, prop, route or schema; the event's counting and its write path change. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **Backend:** `test_deck_i1_check.py`, 30 tests. Covered:
  - exact props;
  - side and asset splits;
  - repeat polls, replace serves, legacy plus paged serves of one job, and page-store serves each counting a card once;
  - a full queue dropping with a warning and never blocking;
  - the drain;
  - conftest's per-test drain;
  - QA P2-1 (probe D): cards published before their impression_ids are stamped and then re-published with them count once. The identity is now the trade_id first.
- **Targeted, 248 passed:** `deck_i1_check`, the I-1 serve filter, the page store, roster freshness, the deck pipeline digest.
- **Sabotage:** the identity back to impression_id-first → 2 red (probe D and the order test), then restored. release-lead's QA at `568a3993` ran 16 sabotages, all red, and 1007 targeted tests passed.
- **Not covered (follow-ups, release-lead's P3s):**
  - the worker isn't restarted after a BaseException;
  - head-of-line waits behind a deletion's lease;
  - no atexit drain;
  - a drop burst's tail count is logged only by a later drop;
  - test gaps: the fallback identity's partner, LRU eviction of the current job, `move_to_end`, the worker's `except`, the lease.

## 2026-10-27 — Owned-pick sync: an empty `/drafts` read keeps the prior current-season exclusion (#470 QA P3-2)

Server only, platforms-eng lead; one commit on `fix/owned-picks-drafts-flake`. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest. No flag, schema, route or analytics change.

- **The flip:** init A's live `/drafts` read excluded the current season. Init B's read flaked to `[]` while the cached #207 verdict didn't say `drafted`, so B re-populated the season and the next good read removed it again. Each flip moved `rfp1`. Fix: on an empty read without a cached `drafted`, `server._sleeper_prior_grid_excludes` reads the prior platform grid (`load_draft_picks(league_id, source=PICK_SOURCE_PLATFORM)`) before the replace. If the grid has later seasons but none for the current one, the sync keeps the season excluded and logs it at INFO.
- **New tests in `test_owned_picks.py` (7; the file is now 38):**
  - complete, then an empty read with no verdict: the season stays excluded;
  - complete → flake → complete → flake: `roster_snapshot(...).fp` is the same throughout;
  - a prior grid that carries the season keeps it on an empty read;
  - a first sync on an empty read includes it (D-089);
  - the live read wins both ways (complete → pre_draft re-includes → complete excludes);
  - a season rollover (meta season 2027) ends the sticky exclusion;
  - a cached `drafted` still excludes a season the prior grid carries.
- **`test_pick_assignment.py`:** `_sleeper_prior_grid_excludes` was added to `_SANCTIONED_SOURCE_CALLERS`. It is a literal platform read of the sync's own provenance and never follows `picks.assign_tradeable`.
- **Sabotage, red then restored:** with the sticky branch disabled (`elif False and …`), 2 tests went red: the row test (2026 came back) and the fp test (the fp alternated `rfp1:2adc…` / `rfp1:8c3f…`).
- **Targeted:** the 59 files that grep `owned_pick|draft_status|pick_tradab|roster_refresh|roster_snapshot` → 1840 passed. The only red was the AST reader guard above, fixed by registering the new reader.
- **Full suite:** `pytest backend/tests -q` → 9255 passed, 2 skipped, 0 failed (12m55s, Python 3.14 locally; CI runs 3.12).
- **Not run:** `tsc --noEmit` and testid-lint (no mobile change).
- **QA follow-up (#482 GO-with-notes; tests and docs only, no code change):** QA's sabotage "a prior-grid read error returns True" stayed green on the 7 tests above. New: `test_prior_grid_read_error_falls_back_to_including_the_season`. A complete read excludes 2026; then `srv.load_draft_picks` raises on an empty read with no verdict, and 2026 is included (D-089). That sabotage (`return True` in the `except`) → that 1 test red (`[2027, 2028, 2029] == [2026, 2027, 2028]`), then restored; `test_owned_picks.py` → 39 passed. The commissioner-reset cost is now named in the D-189 amendment and `docs/integrations/sleeper.md`.

## 2026-10-27 — S0 PR-B: `rfp1` roster fingerprint stamp after a refresh (CAS) + `on_roster_change`

Full gates (platforms-eng lead). Server only; no API, schema, flag or analytics change. D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest. Branch `feat/s0-roster-fp-stamp`.

- **What:** `roster_refresh.record_outcome` → `stamp` after a `fresh` write, so both the session-init daemon and the P41 kick stamp. `stamp` reads the stored `roster_fp` and computes `roster_snapshot(...).fp` with `server._pick_read_source()`. It then compare-and-sets through `database.cas_league_roster_fp`, and on a won, changed stamp calls `on_roster_change(lid, old, new)` with no transaction open and no lock held.
- **New `backend/tests/test_roster_fp_stamp.py` (17):**
  - the first stamp is `rfp1` (equal to the serve's `_trade_roster_snapshot`) and calls the hook with `old=None`;
  - a change calls `(old, new)`; no change makes no CAS and no call;
  - a lost CAS (rival stamp) makes no call ×2;
  - no state row writes nothing;
  - a handler exception and a raising hook are swallowed and logged;
  - a failed refresh ×2, a failed read and a failed state write, and a failed kick read don't stamp;
  - an fp or pick-source error leaves the fp as stored, with the outcome still `fresh` ×2;
  - a linked-platform league is never stamped;
  - **A3** on a file-backed SQLite: `pool.checkedout()==0`, both module locks acquire non-blocking, and a second connection writes, on `roster-refresh-<id>`;
  - session init hooks on a real `session-init-bg-writes` thread, never the request thread.
- **Updated:** `test_roster_refresh_state.py::test_success_marks_fresh_and_never_stores_none_ids` now expects `rfp1:` (was NULL until PR-B).
- **Sabotage, each red then restored byte-identical:**
  - (1a) the hook inside the CAS transaction → the A3 test red (`checked_out: 1`, second-connection write `OperationalError`);
  - (1b) the hook under `_inflight_lock` → the A3 test red;
  - (2) the CAS `WHERE roster_fp = old` dropped → both lost-CAS cases red (rival overwritten);
  - (3) the `new == old` early return dropped → the unchanged-roster test red (1 call).
- **Targeted:** 15 S0 / trade-serve files → 493 passed.
- **Full suite:** `python3 -m pytest backend/tests -q` → **9208 passed, 2 skipped, 0 failed**, exit 0, 35m37s (Python 3.14 local; the known `test_ranking_service_threads` flake didn't fire).
- **Docs:** `docs/data-dictionary.md` (`roster_fp` row + intro), `docs/architecture.md` (new "Roster refresh and fingerprint stamp (S0)" data-flow paragraph), and the scope (§B.1 seam, §B.3 step 7 "As built", §3 evidence, §4 docs rows, §5 item 3).
- **#470 QA P3 follow-up (branch `feat/s0-stamp-p3s`, stacked):**
  - New `test_stamp_follows_the_platform_pick_source_when_assign_tradeable_is_off` (the file is now 18 tests). With the flag off, a platform row plus a member-asserted row: the stamp equals the serve's fp and differs from the `'any'` fp.
  - Sabotage: `roster_refresh._pick_read_source` hard-coded to `'any'` → the new case red. The existing flag-on pin stays green, which was QA's point. Restored byte-identical.
  - A lost-CAS lag comment in `stamp()`.
  - Targeted: the 15 S0 files + `test_pick_assignment_tradeable` → 531 passed.
- **Not in PR-B:** the §B.6 stamps on the other writers (ESPN/MFL imports, the MFL pick normalizer, draft-status refresh, `_refresh_sleeper_members`). The serve recomputes `rfp1` from rows, so only the proactive hook is missing there.

## 2026-10-27 — S0 roster-change handler: revoke only what a fresher session would rebuild (#470 QA P2-2, P2-1, P3-1, P3-3)

Gates: this is a QA fix inside the 200 ms programme's S0 scope (`scope-eng-200ms.md` §6.1). It adds one model_config kill knob (`trade_roster_change_revoke`, default 1) and changes no route, schema or event. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, and the evidence is pytest.

- **Backend:** `test_trade_freshness_roster.py` (25; the handler tests are rewritten for the new rule, with 7 new) and `test_roster_refresh_state.py` (15; 1 new: session init stamps `roster_fetch_started_at` on the session and on the pre-gen's session context, equal to the `refreshed_at` its daemon writes).
- **Targeted, 312 passed:** freshness, roster refresh state, roster snapshot, module shape, I-1 serve filter, page store, floor kick, unlocked fingerprint reads, `deck_i1_check`, and session init (single flight, Sleeper calls, guard).
- **Sabotage, each red then restored:**
  - no session check → 1 red (the league-mate's deck);
  - no read compare → 2 red (the P2-2 repro and the kept-read test);
  - no stamp-key check → 1 red (P3-1);
  - no knob → 1 red;
  - the job's read not stamped → 1 red (the repro);
  - the session's read not set → 1 red (session init).
- **Full suite** on `8ad40822`: `pytest backend/tests -q` → 9260 passed, 2 skipped, 0 failed (13m10s).
- **Combined with #470** (a local merge of `8ad40822` with `de8c2af5`): #470's `test_roster_fp_stamp.py` plus the above, 97 passed.
  - A scratch end-to-end repro used #470's real `stamp`, with the daemon held until the pre-gen had read its fingerprint (release-lead's ordering).
  - With a player move: 1 hook, and the pre-gen was kept. With the old handler, the same run revoked it (P2-2 reproduced).
  - With no change: no hook.
  - The scratch worktree is ledgered in `docs/recovery/2026-10-27-trades-eng-scratch.md`.
- **Not covered:**
  - A refreshing user's own deck from before their new read still ends at its next page with "Couldn't load more trades." + Try again. Revoking it is intended, since Try again rebuilds on the newer read. An automatic re-search is a mobile change (offered for the 11-06 binary).
  - A user with two devices: a newer session on one device makes the other device's older deck revocable (the rule is per user, not per session). That is no worse than #470 as it stands.

## 2026-10-26 — LEG-S6: a fresh Apple code on the verified delete, so Sign in with Apple is revoked (split from #372)

Full gates, not express (scope: #354 LEG-S6; split out when #372, the M11 claim-only delete, was closed on 2026-10-26). D-056: no simulator; `FTF_SKIP_SIM_GATE=1` posture.

- **Change:** `deleteAccount` sends `apple_authorization_code` only when a code exists; otherwise it sends the old body-less DELETE. `AccountDataSection` asks an Apple-linked account on iOS for a fresh Apple credential right before the verified DELETE. Cancelling or any failure sends no code, and the deletion proceeds. The server half has been on main since #354 (`accounts.revoke_apple_tokens`, `DELETE /api/account` at `server.py:31916-31925`). No route change.
- **New guard `check-apple-revoke-on-delete.js`** (`npm run test:apple-revoke-on-delete`), 5 pins, the first three executed with stubs:
  1. the code is sent only as `apple_authorization_code`, otherwise `{method:'DELETE'}` exactly;
  2. the prompt appears only when Apple-linked, on iOS and available, with `requestedScopes: []`;
  3. cancel, failure, a null code, Android or not-linked return null and the DELETE still goes out once;
  4. `setSessionToken` / `appleSignIn` are never touched on this path;
  5. the verified delete is the only caller.
- **Sabotage: 22/22 red,** each restored byte-identical; 1 of them reverts the whole change to `origin/main`.
- **Local runs:** `tsc --noEmit` clean; testid-lint OK; 118/118 `check-*.js`; `pytest backend/tests/test_account_data_rights.py` 12 passed (it includes `test_delete_attempts_revocation_and_never_blocks`).
- **Known gaps:**
  - The flat `SettingsScreen` fallback, used only with `account.settings_hub` off, still deletes without a code. The hub is on, so this is an optional follow-up.
  - An Apple-linked account on an unverified session would see the Apple sheet before the existing 403. Apple sign-in sessions are always verified.
- **Operator TestFlight check, 11-10 to 11-11,** once Render has `APPLE_TEAM_ID`, `APPLE_KEY_ID` and `APPLE_PRIVATE_KEY`:
  1. An Apple account deletes: the Apple prompt appears, then the account is deleted.
  2. Afterwards, Fleeced is gone from iOS Settings → Apple ID → Sign in with Apple.
  3. Cancelling the prompt still deletes.
  4. A Sleeper-only account sees no prompt.
- **release-lead QA fixes (`4ce9d44a`, `7964bc6d`, `13e5d445`, `c0e934ce`):**
  - (a) each Apple HTTP call times out at 5 s (`APPLE_HTTP_TIMEOUT_S`; 2 × 5 s is under the client's 15 s). The client half isn't done: `apiRequest` has no per-call timeout (`deadlineAt` only shortens);
  - (b) pin 6: no `console.*` on the Apple-code path;
  - (d) the code is revoked only when its id_token `sub` is the account's linked Apple identity; a mismatch or no id_token deletes without revoking (`apple_revoked: false`);
  - no Apple sheet on a known-unverified session;
  - the runbook warns off rolling back `account.settings_hub`.
  - **Sabotage: 2/2 + 3/3 + 7/7 + 5/5 red.**
  - Runs: pytest 128 passed (account / Apple / deletion set); tsc clean; testid-lint OK; 118/118 `check-*.js`.
  - Operator step 5: with a different Apple ID signed in on the device than the account's, delete. The account is deleted, and the account's own Fleeced entry stays under Sign in with Apple (it isn't revoked).

## 2026-10-26 — Entry purge: platform pick-grid owner anonymization + `scripts/purge_entry_users.py`

Full gates (legal R28.12 row 2 and R28.16; head-eng 2026-10-26; onboarding-eng's ruling of 2026-10-26, option (a) scoped, as owner of the deletion path). Backend and script only. **No prod access:** local and in-memory SQLite only. D-056: `FTF_SKIP_SIM_GATE=1` posture; the evidence is pytest.

- **Commit 1 (`09c0c3d3`), `accounts._delete_user_data`:**
  - on platform pick grids (`draft_picks.platform` set and not `sleeper`), `owner_user_id` / `original_user_id` naming a deleted id become `DELETED_USER_PLACEHOLDER`, in the same transaction; new count key `draft_picks_owner_anonymized`;
  - Sleeper grids and legacy NULL-platform rows are untouched.
  - Found while scoping the purge: an MFL import writes the importer's Fleeced id (`entry:*`, `acct_*`) as the owner of their picks, and deletion kept it.
  - 4 new tests in `test_account_deletion_coverage.py` (40 pass); **sabotage 7/7 red,** each restored byte-identical.
- **Commit 2 (`c200415c`), `scripts/purge_entry_users.py`:**
  - discovery from `_EXPORT_TABLES` + `_ADDITIONAL_PRIVATE_TABLES` + an explicit deletion-only list;
  - head-eng's cutoff/verified filter (NULL `created_at` is its own skipped count);
  - dry run by default; `--execute --expect N` through `delete_user_data`; `--verify` (a) key columns, (b) entry credentials;
  - info counts for JSON mentions and the overhaul gap; counts only, never an id.
  - `test_purge_entry_users.py`: 9 pass, including a drift test that captures `delete_user_data`'s SQL. **Sabotage 14/14 red,** each restored byte-identical.
- **Local runs:**
  - `pytest` on the purge test plus `test_account*`, `test_deletion_session_races`, `test_user_data_lifecycle`: 116 passed;
  - the other deletion-touching suites plus `test_owned_picks` / `test_mock_pick_ownership`: 359 passed;
  - the script's `--help`, and a dry run and `--verify` on an empty dev DB (0 found, exit 0).
- **Not run here:** the prod purge. It needs the operator's own word in the acting session; steps in `docs/runbook.md` § "Purge orphaned ESPN/MFL entry users".

- **2026-10-27, release-lead's QA round (`16c2c3bb`..`e2a35031`):**
  - **Deletion fixes, for every user:**
    - **D1, shared leagues:** a `leagues` row is kept with the importer anonymized while another live Fleeced user still belongs to it; otherwise it's deleted, as before;
    - **D2:** `recorded_picks.picking_team_id` is anonymized for Fleeced-minted ids.
  - **Script fixes:**
    - it prints the DB identity first and refuses local SQLite without `--allow-local` (exit 2);
    - verify fails on any unverified entry user created after the cutoff, and the dry run stops and asks;
    - `hide_parameters` engines plus a redacting top-level handler, so no ids reach stderr on a DB error;
    - read-only reads;
    - strict CLI: no abbreviations, and a tz-aware, non-future cutoff;
    - the drift test also captures `=` filters.
  - **Runbook order:** flag off, restart, dry run, snapshot, execute (the operator), restart, verify, record.
  - **Runs (onboarding-eng, after the worker hit its usage limit):** deletion + account + draft + picks + purge tests, 429 passed (purge alone 36). A manual check confirmed the local refusal, the date-only cutoff and the future cutoff all exit 2, and `--exe` / `--exp` are rejected.

- **2026-10-27, release-lead delta QA NO-GO @ `527031fc` → fixed (onboarding-eng; the worker was at its usage limit):**
  - **D1 REVERTED** (`60379b82`): keeping a shared `leagues` row as `deleted_user` stranded the remaining member's linker routes, because no upsert re-adopts the row. It also kept the importer's id in `pick_assignment_settings`. Deletion is back to main's behaviour: the row is deleted, and the next member to link re-imports it.
  - **`b1c73a98`:** deletion anonymizes Fleeced-minted ids in other users' `pick_assignment_changed` events (`old_owner` / `new_owner` / `actor`); Sleeper ids stay. 4 tests; sabotage 2/2.
  - **`3c94114f`:** `--verify` gains (d), no removed entry id left in the pick audit trail, and (e), a non-empty `users` table. `--expect-db` refuses a different DB in every mode, and the printed execute command carries it. The per-target error is pinned to print only its type. 5 tests; sabotage 4/4.
  - **`506c9294`, runbook:** the cutoff is the restart time; the STOP response is pre-decided; release-lead takes the snapshot and **the operator deletes it** (corrected in `630b5084`; release-lead records the due date and reminds); `--expect-db` on every command; step 7 checks identity and (d)/(e).
  - **Runs:** deletion + account + draft + picks + pick-assignment + purge tests, 503 passed.

- **2026-10-27, release-lead round 3 @ `630b5084`: GO-with-notes (no P1) → the P2 and P3s are fixed:**
  - **P2:** deletion anonymizes a deleted Fleeced-minted id in **any** league's `pick_assignment_settings.order`, other importers' rows included, in place, so slot positions don't shift. That's the R28.16 SWID case, and it's the same on main, so it closes for every future deletion. Verify gains (f).
  - **P3:**
    - malformed (non-dict) audit props or settings can't abort a deletion;
    - the runbook gives (d)/(e)/(f) FAIL responses;
    - the cutoff help and error text name the step-2 restart;
    - `--expect-db` is required with `--execute`;
    - api-reference lists the new count keys.
    - **Pinned:** (d) reads `old_owner` and `actor`, the scrub rewrites `actor`, the scrub skips other event types, and the printed execute command carries `--expect-db`.
  - **Tests:** 3 deletion + 6 purge (9), all new (corrected 2026-10-27; this line first said 5 + 6). **Sabotage: 8/8 red.**
  - **Runs (onboarding-eng):** deletion + account + draft + picks + pick-assignment + purge tests.
- **2026-10-27, head-eng's pre-prod-run asks (`e844115b`, `39c31ff0`):**
  - **Pick-grid names:** a platform-grid row anonymized by id also drops the deleted person's `owner_username` / `original_username` for "Team <slot>" (the writers' own fallback; the placeholder when no slot is known). 1 new deletion test; **sabotage 6/6 red.**
  - **Census:** the dry run printed, counts only, the verified entry users it skips (by kind and `verified_via`), which skipped users hold an ESPN/MFL credential, and target-owned leagues with another Fleeced member. 1 new purge test; **sabotage 6/6 red.** Superseded by `ad3aa954`: analytics-lead ran the prod count, so the dry run keeps only the credential counts.
  - **Runs (onboarding-eng):**
    - purge, `test_account*`, deletion races, lifecycle, persistent sessions, owned picks, recorded picks, pick assignment, module shape: **311 passed** (14 files);
    - after the main merge `8024f16a`, the same plus `deck_i1_check` and the S0 roster tests: **440 passed** (18 files).
- **2026-10-27, legal R28.17 A1 (`ad3aa954`).** The count found 2 entry users, both the operator's test logins: 1 unverified `entry:espn` and 1 verified MFL-only `entry:mfl` with 1 `mfl_credentials` row.
  - **The new flag.** `--delete-verified-credentials M` deletes only the verified entry users' ESPN/MFL credential rows in the same execute. M is pinned like `--expect`.
  - **Verify (g)** is R28.16 part 1: zero entry users without `verified_via`.
  - **Tests:** 3 new purge tests (the flag and its refusals, which keep entitlements and everything else; the CLI rule; (g)), plus the extended credential-left test (the rerun path). Purge sabotage **7/7 red**.
  - **The pin for legal's degrade condition** is `test_purge_mfl_reconnect.py`. With the row gone:
    - the status reads `connected: false`;
    - the league still lists;
    - the send is 409 `mfl_not_connected` "Sign in with MFL first.", never a 500.
    - Sabotage on the server routes: **3/3 red.**
  - **Runs (onboarding-eng):**
    - purge + reconnect, 52 passed;
    - before the push, purge, reconnect, `test_account*`, deletion races, lifecycle, MFL propose, I-2 MFL, link status, auth-link and module shape: **283 passed** (15 files).
- **2026-10-27, release-lead round 5 @ `b2c49ec6`: NO-GO on P1-1 → fixed in `f16c5c38`:**
  - **P1-1, the credential step fails closed:**
    - it's skipped after a failed target;
    - the purge summary prints first;
    - an error shows its type only;
    - one transaction rolls back unless exactly M rows are deleted, which also closes P2-2.
  - **P2-1:** pinned. The flag deletes only verified entry users' rows, not an unverified entry user's or a non-entry user's.
  - **P3s:**
    - batched pick-grid UPDATEs;
    - the owner of an own pick uses its own slot;
    - the two-slot and alias-slot tests;
    - (b) is case-sensitive on SQLite;
    - a blank `verified_via` isn't verified.
  - **Tests:** 6 new purge tests and 2 cases in the names test.
  - **Sabotage, 11 red,** each restored byte-identical:
    - **purge 7/7:**
      - the credential step runs after a failed target;
      - a credential-step error isn't caught;
      - no exact-M check at the write;
      - the delete has no filter;
      - the delete hits every `entry:` row;
      - (b) is case-insensitive again;
      - a blank `verified_via` counts.
    - **pick-grid 4/4:**
      - the owner of an own pick uses the league slot;
      - the two-slot rule is dropped;
      - own slots are read from the requested id only;
      - batches are keyed on the owner's values only.
  - **Runs (onboarding-eng):** purge, reconnect, `test_account*`, deletion races, lifecycle, owned picks, recorded picks, pick assignment, MFL propose, I-2 MFL, link status and module shape: **405 passed** (17 files).
- **2026-10-27, release-lead round 6 @ `18a5347e`: GO-with-notes (no P1, no P2):**
  - **Fail closed:** the fail-closed matrix passes on SQLite and PG, and multi-chunk M = 1,500 runs in one transaction.
  - **Prod shape:** it gives N = 1 / M = 1.
  - **Batching:** the batched UPDATEs take 106 statements vs 603.
  - **Sleeper and legacy rows:** byte-identical to main.
  - **Sabotage:** 37/37 red.
  - **Tests:** 1,660 passed on head and 1,670 on the trial merge; CI green.
  - **Then:** a docs-only main merge (the api-reference `DELETE /api/account` row keeps both #446's text and this PR's; this ledger).
  - **P3-1 → follow-up A:** a pick moved between the person's own two slots is named after its original slot.

## 2026-10-27 — B1: Sign in with Apple parity on the landing (Product's pre-launch review; stacked on #443)

Full gates (head-eng's ask; scope `docs/plans/prelaunch-onboarding/scope-b1-apple-continue.md`). Mobile only; D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **The change:** the landing's "Already have an account? Sign in with Apple" text link becomes Apple's own button.
  - CONTINUE, WHITE (solid white, Apple's dark-background style; release-lead #507 QA P2-b), `signin.apple-continue-btn`;
  - below the username field and its Continue (or the ESPN/MFL panel), after a chalk-dim "or", 44pt like the other sign-in buttons (P2-a; head-product's position ruling 2026-10-28, which amends ADR-006 decision 1 in this PR);
  - the same `handleAppleSignIn`.
  - The flags-off SIGN_IN button is unchanged.
  - `handleSubmit` returns while an Apple sign-in is in flight (QA P3).
  - The landing body is a `ScrollView` (flexGrow 1 and centered, `keyboardShouldPersistTaps="handled"`, the guide notifier on scroll, layout and content size), so the returning-user, session-expired and error states scroll on an SE instead of clipping. The "or" and the legal line are chalk-dim.
  - **2026-10-29, release-lead delta QA @ `2da05fdb`: GO-with-notes.** Their executed render across 17 states gives field → Continue → or → Apple → demo everywhere, with Apple reachable. **P2, the merge procedure:** #443 is folded in. Main is merged into this branch: `web/js/app.js` keeps main's `WEB_PLATFORM_ENTRY` plus `espn.signin`, and config-reference takes main's #502 row with B1's phrase ("below the username Continue"). The PR now targets main. **P3s taken:** the guard pins the onLayout / onContentSizeChange notifiers, the ScrollView's exact props, `styles.flex` and `styles.body`'s exact keys; `handleTryDemo` and both demo buttons wait on Apple; the checklist uses MFL (ESPN is dark), types a username for step 6, scrolls to Apple on an SE for step 10, and adds 320 pt screens. **Sabotage 9/9 red** (44 in all). The word "or" needs only design-lead's OK (head-eng 10-29).
- **New guard `check-signin-apple-parity.js`** (9 AST pins, hardened after QA: every condition above the button, `appleShown` and the availability effect pinned, height against `styles.button.height`, rendered-text check; after the ruling, pin 2 is the new position with the "or" right before the button, pin 8 the ScrollView, pin 9 chalk-dim). **Sabotage 35/35 red** (10 in round 1, 9 after QA incl. QA's six escapes, 16 after the ruling, each on its target pin), restored byte-identical. With the scroll notifier removed, `check-guide-spotlight-tracking` also goes red (9b). A comment-only edit, which isn't a real mutation, correctly stays green.
- **Runs:** see the PR (tsc, the full `check-*.js` loop, testid-lint).
- **App Review notes:** legal's R28.16 row 7 paragraph covers the four doors, and release-lead owns the submission text.

## 2026-10-27 — `espn.signin` (client half): the flag hides only the ESPN chip on the sign-in platform picker; entry mint keeps a Sleeper-bound identity

Client half only, for the 11-06 binary; the server half (flag registered in `config/features.json` default `true`, 404 on the ESPN entry route) is a separate PR and nothing under `backend/` or `config/` is touched here. D-056: `FTF_SKIP_SIM_GATE=1` posture; no simulator, no Maestro. The evidence is the structural pin, the code-walk and the TestFlight checklist below. Branch `feat/espn-signin-flag-client`.

- **Change (`SignInScreen.tsx`):** `const espnSignInOn = useFlag('espn.signin')` next to `espnLinkOn`. The ESPN chip is in `platformChips` only when `espnLinkOn && espnSignInOn`, and the de-flag fallback (selected ESPN chip falls back to Sleeper) now also fires when `espn.signin` goes off. The MFL chip is untouched.
- **Change 2 (`SignInScreen.tsx` `handleEntrySession`, riding the same 11-06 binary; onboarding-eng owns the file and granted this one hunk):** the handler's parameter type gains optional `account_only?: boolean; username?: string`, and it pins `account_only: u.account_only ?? true` and `username: u.username ?? ''`. With the new server (#430), an ESPN/MFL identity that is bound to a Sleeper user mints `account_only: false` plus the Sleeper username; the old hard-coded `account_only: true` / `username: ''` pinned that user as account-only anyway, and LeaguePicker then skipped their Sleeper fetch (`LeaguePickerScreen.tsx:348`). A mint that omits the fields (older server, bare platform identity) keeps today's account-only default. The optional params also keep this compiling before #421 declares the fields on the sheets' `onEntrySession` prop type.
- **Change 3 (after release-lead QA, GO-with-notes):**
  - **Smart-start hint (`SignInScreen.tsx`):** pasting an ESPN league URL said "choose ESPN above" whenever the picker was up, which with `espn.signin` off is still true (Sleeper · MFL) with no ESPN chip. The hint now needs that platform's chip: `pname && platformPickerShown && (platformChips as string[]).includes(resolved.platform ?? '')`. Without the chip it falls to the existing no-chip string ("ESPN leagues link after sign-in — enter a Sleeper username here, or sign in with Apple and link your league from Settings."), which reads correctly for ESPN with `espn.signin` off because Settings → link ESPN league stays on. No new copy. The same line also fixes the MFL twin (the hint said "choose MFL above" with `mfl.link` off and ESPN on).
  - **Web chip (`web/js/app.js`):** `_applyPlatformOptionsFlag` shows the ESPN chip only for `landing.platform_options && espn.link && espn.signin` (the existing "selected chip was withdrawn" fallback reuses the same `espnOn`), and `selectEntryPlatform('espn')` returns when `espn.signin` is off. MFL is untouched. `_entryPost` keeps its unconditional throw: the web mints no ESPN/MFL session, and the chips only point people to the mobile app. `window.FTF_FLAG` is `!!(window.FTF_FLAGS && window.FTF_FLAGS[key])`, so a key the server doesn't send (or a failed flag fetch) reads false and the web chip stays hidden, the same fail-safe as mobile.
  - **Stale `entry:` comments** in the files touched (SignInScreen's `handleEntrySession`, three in `web/js/app.js`, the identity pin's header) now describe the proof-based mint: an `acct_*` key, or the bound Sleeper id with `account_only: false`.
- **Missing flag reads false:** `useFlag` is `!!flags[key]` (`useFeatureFlags.ts:210`). `espn.signin` is deliberately NOT in `LAUNCHED_FLAG_DEFAULTS` (`:45`), so until the server sends `true` the ESPN chip is hidden. That is the fail-safe direction, per platforms-eng: a server `false` must never paint the chip, not even for a frame on a first boot. `landing.platform_options` is not in that map either, so the whole chip row is hidden on a first boot anyway. A cached flag map from the previous binary also lacks the key until the cold-start fetch lands, so the chip appears once it does.
- **Pin:** new `mobile/tests/check-espn-signin-flag.js` (28 checks, `npm run test:espn-signin-flag`; claims 7 and 8 below cover Change 3), covering:
  1. the ESPN chip is behind both `espn.link` and `espn.signin`;
  2. the MFL chip depends on `mfl.link` alone;
  3. the fallback fires on either ESPN flag, leaves MFL alone, and `espnSignInOn` is an effect dep;
  4. `espnSignInOn` has no other use in SignIn, and `espn.signin` appears nowhere else in `mobile/src`;
  5. `<EspnLinkSheet entry>` is mounted only by SignIn;
  6. `LAUNCHED_FLAG_DEFAULTS` has no `espn.signin` key;
  7. the smart-start "choose <P> above" hint needs that platform's chip in `platformChips`, the existing no-chip and unsupported-platform strings remain the fallbacks, and the hint ternary holds exactly its three existing strings (no new copy);
  8. web: the ESPN chip needs `espn.link` and `espn.signin`, the MFL chip needs `mfl.link` alone, the withdrawn-chip fallback uses the same `espnOn`, `selectEntryPlatform('espn')` returns when `espn.signin` is off, `espn.signin` is read in exactly two web code sites, `FTF_FLAG` reads a missing key false, and `_entryPost` still consists of one unconditional `throw`.
  - The two `check-landing-platform-options.js` assertions that encoded the old chip line and old fallback were updated to the new text; they went red on the edit and green after.
- **Pin 2:** new `mobile/tests/check-entry-session-identity.js` (8 checks, `npm run test:entry-session-identity`): the handler's parameter type declares optional `account_only` and `username`; it pins `u.account_only ?? true` and `u.username ?? ''`; no literal `account_only: true` or `username: ''` is left in the handler; both entry sheets deliver the mint to `handleEntrySession`; LeaguePicker still skips the Sleeper fetch only for an `account_only` user. The existing V2.2 assertion in `check-landing-platform-options.js` (it matched the literal `account_only: true`, and its handler regex stopped at the new multi-line parameter list) was updated to the `?? true` form and a `\n  }\n` terminator.
- **Sabotage, each red then restored** (six runs, espn.signin pin): drop `espnSignInOn` from the chip gate → claim 1 red; `mflLinkOn && espnSignInOn` on the MFL chip → claims 2 and 4 red; fallback back to `!espnLinkOn` → claim 3 red; Settings reads `espn.signin` → claim 4 red; `entry` added to LeaguePicker's `EspnLinkSheet` → claim 5 red; `'espn.signin': true` added to `LAUNCHED_FLAG_DEFAULTS` → claims 4 and 6 red.
- **Sabotage, Change 3 pins** (eight runs, each red then restored): the hint back to `pname && platformPickerShown` → claim 7 red; a fourth hint string added → claim 7 red (this run first stayed green because the string counter ignored single-quoted strings; the counter was fixed, then it went red); web ESPN chip without `espn.signin` → claim 8 red; `espn.signin` added to the web MFL chip → claim 8 red; the `selectEntryPlatform('espn')` gate removed → claim 8 red; `_entryPost` made to fetch instead of throw → claim 8 red; a third web `espn.signin` reader → claim 8 red; the web fallback keyed on `espn.link` only → claim 8 red.
- **Sabotage, identity pin** (four runs, each red then restored): `account_only: true` hard-coded again → claims 2 and 3 red, and the V2.2 assertion in `check-landing-platform-options.js` red; `username: ''` hard-coded again → claims 2 and 3 red; the optional parameter fields dropped → claim 1 red; LeaguePicker's fetch no longer keyed on `account_only` → claim 4 red.
- **Checks:** `npx tsc --noEmit` → exit 0. `scripts/testid-lint.sh` → OK. All 119 `mobile/tests/check-*.js` suites → 0 failed (117 existing + the two new ones).
- **Code-walk:**
  - Chip row: `SignInScreen.tsx:127` includes `'espn'` only for `espnLinkOn && espnSignInOn`; `platformPickerShown` (`:131`) needs ≥2 chips, so with ESPN off the row is Sleeper · MFL.
  - Stale selection: a selected ESPN chip that is withdrawn mid-session returns to Sleeper (`:139`, deps `:144`), so the user is never left on the ESPN panel with no chip.
  - Only entry mount: the one sessionless `<EspnLinkSheet entry>` is `SignInScreen.tsx:888`, opened only from the panel button (`:699`), which renders only under `nonSleeperEntry` (`:133`, a selected non-Sleeper chip). Gating the chip therefore gates the sheet. `RootNav`'s `platformIntentParams` produces `espnLink` only from a selected chip, and that param opens the signed-in (non-entry) sheet on LeaguePicker (`:175`).
  - Unaffected (no `espn.signin` reference): Settings → link ESPN league (`SettingsScreen.tsx:223`, `:811`, still `espn.link`); LeaguePicker's `EspnLinkSheet` (`:728`); MFL sign-in (`PlatformLinkSheet`, `mfl.link`).
- **Manual TestFlight checklist (the only runtime evidence this gets; needs the server flag and a build with this change):**
  1. With `espn.signin` on (and `espn.link`, `mfl.link`, `landing.platform_options` on), signed out: the sign-in screen shows the Sleeper, ESPN and MFL chips; tapping ESPN shows the ESPN panel and its button opens the sign-in sheet.
  2. Flip `espn.signin` off, force-quit and relaunch signed out: once the cold-start flag fetch lands, only Sleeper and MFL chips show (a map cached while it was on can paint the ESPN chip until then, which is the same for every flag). On a fresh install, with no cached map, the ESPN chip never appears.
  3. With it still off, signed in: Settings → link ESPN league still opens LeaguePicker with the ESPN sheet and the link flow completes.
  4. With it still off, signed out: MFL chip → MFL sign-in completes through to the league picker.
  5. Signed out, with a Sleeper-bound ESPN or MFL account (an identity linked to a Sleeper user): sign in through the ESPN or MFL chip. LeaguePicker lists that user's Sleeper leagues alongside the platform league. Then sign in with a platform account that has no Sleeper link: it still lands account-only and shows only the platform league, as before.
  6. Web (https site, signed out) with `espn.signin` off: the platform row shows no ESPN chip (MFL still shows if `mfl.link` is on). With it on, the ESPN chip shows and still only points to the mobile app. On the app with it off, paste an ESPN league URL into the Sleeper field: the message is the Settings-path line, not "choose ESPN above".
- **Not covered:** the flag's presence in `config/features.json` and the route 404 (server PR); `docs/config-reference.md` rides with that PR.

## 2026-10-26 — I-2 follow-ups: validate gate includes `espn.send`; `sleeper_send_failed.error_code` is 20 values; R3 reports `kind: roster_read`

Full gates (head-eng approved, platforms-eng lead; the enum and `kind` changes are analytics-lead's granted asks). Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture, the evidence is pytest. Two commits on `fix/validate-gate-espn`.

- **Validate gate (commit 1):** `/api/trades/validate`'s top gate was `trade.send_in_sleeper` OR `trade.send_in_mfl`, so an `espn.send`-only deploy 404'd `feature_disabled` before reaching the I-2 ESPN branch. Latent: all three flags are ON today. The gate now also opens on `espn.send`; nothing else in the route changed.
  - Two new tests in `test_i2_espn_ownership.py` (now 26): `test_validate_espn_send_alone_still_reaches_the_espn_branch` (flags `("espn.send",)` → 200 `checked:true`, one live mRoster read, no Sleeper call) and `test_validate_all_send_flags_off_is_feature_disabled` (flags `()` → 404 `feature_disabled`, no ESPN read).
  - Targeted: `test_i2_espn_ownership.py` + `test_trade_send_validate.py` → 42 passed.
  - Sabotage, red then restored: the old gate line → 1 red (the espn.send-alone test: `assert 404 == 200`, body `{"error":"feature_disabled"}`); the all-off test stays green, as expected.
  - Full suite on commit 1: `pytest backend/tests -q` → 8762 passed, 4 skipped, 0 failed (30m20s).
- **`sleeper_send_failed.error_code` 18 → 20 (commit 2, comments and docs only):** every `error` value that `POST /api/trades/propose` and `_sleeper_propose_core` return is 17 codes: the 15 already listed plus I-2 #411's `asset_not_owned` / `counterparty_asset_not_owned`. Updated `backend/analytics_taxonomy.py`, `SendInSleeperButton.tsx`, `docs/cross-client-invariants.md` and the P0-7 addendum. Not counted, as before: the app-wide handlers' `session_expired` (401) and `internal_error` (500) can also reach the client's `body.error`.
- **R3 `kind: "roster_read"` (commit 2):** the Sleeper core's failed-rosters-read 502 `sleeper_write_failed` now carries `kind: "roster_read"` instead of `"network"`, so `sleeper_send_failed.kind` tells a refused-before-send read from a real Sleeper write failure. Unchanged, still `network`: the R10 `traded_picks` block, MFL/ESPN `*_unavailable`, overhaul `rosters_unavailable`.
  - Tests updated: `test_i2_sleeper_ownership.py` (the R3 matrix ×3 and the open 429 circuit) and `test_sleeper_write_route.py::test_propose_roster_fetch_failure_degrades_gracefully`.
  - Sabotage, red then restored: the value back to `"network"` → those 5 red.
  - Client code-walk: no client branches on `kind`; `SendInSleeperButton` only forwards `body?.kind` to `track()` (`:261`). `SendInMflButton` / `SendInEspnButton` fire no analytics event at all.
  - Targeted on commit 2: 215 passed: `test_i2_sleeper_ownership` (27), `test_sleeper_write_route` (35), `test_trade_send_validate` (16), `test_traded_picks_unavailable` (11), `test_i2_espn_ownership` (26), `test_i2_overhaul` (14), `test_analytics_p0` (24), `test_events_api` (45), `test_analytics_taxonomy_384` (11), `test_analytics_taxonomy_home_hub` (6).
  - Not run on commit 2: the full suite (CI runs it); `tsc --noEmit` (no `mobile/node_modules` in this worktree; the mobile change is a comment).
- **Docs:** `docs/api-reference.md`: the validate row's gate text (commit 1) and the propose 502 row's R3 sentence, now `kind: "roster_read"` (commit 2).
- **Analytics seam:** R3 rows between the #411 deploy and this change carry `kind: network`; the P0-7 addendum says so.

## 2026-10-26 — I-2 (4/4): overhaul blocks on a failed roster read + readable refusals (stacked on #413)

Full gates. Completes I-2, the launch condition for the 200 ms waiver W-AC-L5. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **Backend:** the new `test_i2_overhaul.py` has 14 tests. The targeted set passes, 123 tests: `test_overhaul_api` (27), `test_overhaul_service` (23), and the I-2 Sleeper (24), MFL (15) and ESPN (20) files. `test_sleeper_write_route` (35), `test_mfl_propose_route` (25) and `test_espn_propose_route` (17) also pass after the copy moved to `backend/ownership_copy.py`.
- **Sabotage, each red then restored:**
  - the session-roster fallback restored at prepare → 4 red;
  - the raw-id copy restored ("You no longer own {id}.") → 5 red;
  - the /send 409 `detail` dropped → 1 red;
  - the `offer_stale` ownership detail dropped → 1 red.
- **Contract:**
  - **R3:** on a send platform, prepare-send with a failed live roster read → 503 `rosters_unavailable` `kind:"network"` with "Couldn’t confirm rosters with {platform} …". No token is minted and the session fallback is not stored.
  - **R4:** receipt ownership blockers use the shared I-2 copy, one per offer and side, named from the offer card (count fallback, never a raw id).
  - **/send:** an ownership 409 carries `detail == message`. So does an `offer_stale` 409 when the offer went stale for ownership: a give-side move found by `/refresh` is the only way a liked offer goes stale. That 409 uses the offer's own ownership blocker, which now carries `assets`.
  - **Per-offer refusals:** a core's 422 reaches `attempts[].error.message` on `/send` and on `GET /api/overhauls/{id}`.
- **Client code-walk (no client change):**
  - `OverhaulSummaryScreen`: a failed prepare goes to `setPrepareError(errorDetail(e))` (`:146`, card at `:274-277`); an ownership 409 at send goes to the toast (`:196`); receipt lines render `item.message` (`:295`, `:405-416`).
  - `OverhaulPlanScreen` renders `a.error.message` for `send_failed` attempts (`:290-292`).
- **Not covered:**
  - An offer that was staled for ownership but whose assets have since come back keeps today's `offer_stale` 409 with no `detail`.
  - `pool_violation`, `asset_reserved` and the overlap blocker messages still name raw ids (outside I-2).

## 2026-10-26 — I-2 (3/4): ESPN send-time player ownership + validate routing + 0f guard (stacked on #412)

Full gates. Part of the launch condition for the 200 ms waiver W-AC-L5. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **Backend:** the new `test_i2_espn_ownership.py` has 20 tests, including a send through the overhaul batch with the real `_espn_propose_core`. The targeted set passes, 171 tests: `test_espn_propose_route` (17), `test_espn_write` (29), `test_trade_send_validate` (16), the I-2 Sleeper (24) and MFL (15) files, `test_overhaul_api` (27) and `test_overhaul_service` (23). `test_sleeper_write_route` (35) and `test_mfl_propose_route` (25) also pass with the 0f guard.
- **Sabotage, each red then restored:**
  - the ESPN player refusals removed → 4 red;
  - the R3 handling removed (error mapping, transport catch, shape guards) → 6 red;
  - the validate ESPN branch and linked-platform guard removed → 5 red;
  - the 0f guard removed → 2 red.
- **Contract:** players are checked against the live `mTeam+mRoster` read the ESPN core already makes (no extra call). A moved player → 422 `asset_not_owned` / `counterparty_asset_not_owned` through #411's helper. A failed read → 502 `espn_unavailable` `kind:"network"` with "Couldn’t confirm rosters with ESPN …". That failure covers transport errors, which used to escape as a 500, and a team with no `roster` object.
- **Validate:** an ESPN league checks the live mRoster (`asset_unmapped` / `player_moved` / `roster_not_found`). Any other linked-platform id returns `checked:false`. Neither path calls Sleeper.
- **NEXT.md 0f:** `_sleeper_propose_core` returns 400 `bad_request` for a linked-platform id before any Sleeper call.
- **Client code-walk (no client change):** `SendInEspnButton` has no branch for the two 422s or `espn_unavailable`, so all three reach its catch-all (`:216-220`), which shows `detail`. `espn_write_failed` (`:205-215`) would have read "ESPN rejected the request".

## 2026-10-26 — I-2 (2/4): MFL send-time player + pick ownership + R3 (stacked on #411)

Full gates. Part of the launch condition for the 200 ms waiver W-AC-L5. Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **Backend:** the new `test_i2_mfl_ownership.py` has 15 tests, including a send through the overhaul batch with the real `_mfl_propose_core`. The targeted set passes, 133 tests: `test_mfl_propose_route` (25; its fixture now serves both live exports), `test_mfl_trade_lifecycle` (22), `test_mfl_write` (21), `test_overhaul_api` (27), `test_overhaul_service` (23).
- **Sabotage, each red then restored:**
  - the player check removed → 4 red;
  - the pick check removed → 5 red;
  - the R3 read-failure returns removed → 4 red.
- **Contract:** players are checked against MFL's live `rosters` export and FTF picks against its live `futureDraftPicks` export (live rather than the stored snapshot: the zero-auth fetcher already exists, so it is one read). A moved asset → 422 `asset_not_owned` / `counterparty_asset_not_owned` through #411's shared helper (names or pick labels, a count when one is missing, never a raw id). A failed read → 502 `mfl_unavailable` `kind:"network"` with "Couldn’t confirm rosters with MFL …" (coordinator's call: the core's existing read-failure 502, not `mfl_write_failed`).
- **Client code-walk (no client change):**
  - `SendInMflButton` has no branch for `asset_not_owned`, `counterparty_asset_not_owned` or `mfl_unavailable`, so all three reach its catch-all (`:169-173`), which shows `detail`.
  - With `mfl_write_failed`, the R3 copy would have been framed as "MFL rejected the request" (`:158-168`).
- **Not covered:** pre-encoded `give_pick_assets` / `receive_pick_assets`; `git grep` finds no sender in mobile, web, the extension or overhaul.
- **release-lead P2s (2026-10-26):** `test_i2_mfl_ownership.py` now has 27 tests.
  - **P2-2:** a dead cookie (401/403) on either ownership read → 409 `mfl_auth_expired`, the credential is dropped, and no provider call is made. It is told apart from other failures by an opt-in `raise_auth` on the two fetchers; their default `{}` contract is pinned by a test. Sabotage → 2 red.
  - **P2-1:** timeout, connection reset, `IncompleteRead` and `BadStatusLine` on either read → readable 502 `mfl_unavailable`, and through the overhaul send every attempt is `send_failed` with no reservation held. Sabotage → 9 red.

## 2026-10-26 — I-2 (1/4): Sleeper send-time player ownership + R3 (#411)

Full gates. This is the launch condition for the 200 ms waiver W-AC-L5 (Product, 2026-10-26). Server only; D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **Backend:** the new `test_i2_sleeper_ownership.py` has 24 tests, including a send through the overhaul batch with the real core. The targeted set passes, 211 tests: `test_sleeper_write_route` (35), plus the validate, pick-tradability, traded-picks, overhaul api/service, pick-assignment and verified-sessions files.
- **Sabotage, each red then restored:**
  - the ownership refusals removed → 12 red;
  - R3 turned back into a 400 → 5 red;
  - the raw-id fallback restored → 6 red.
- **Contract:** a 422 `asset_not_owned` / `counterparty_asset_not_owned` (named players, or a count, never a raw id; `detail == message`), checked inside `_sleeper_propose_core` before any provider write, so overhaul inherits it.
  - A failed live roster read → 502 `sleeper_write_failed` `kind:"network"`.
  - The copy is final (marketing via head-bizops).
- **Client code-walk (no client change, per Product):**
  - `SendInSleeperButton` sends the new codes to its catch-all (`:335-339`), which shows `detail`.
  - In overhaul, the message reaches `attempts[i].error.message`, which `OverhaulPlanScreen.tsx:290-292` shows.
  - `/api/trades/queue` makes no platform write.
- **Not covered:** whether Sleeper itself would reject a non-owned player is unverified; the server check now makes that moot.

## 2026-10-26 — Timing readout mounted on Settings › Testing; hub row opens for it (#363 ruling 11)

Full gates, not express (scope: #363's trades-200ms scope, head-eng ruling 11; in the 200 ms set on head-eng's call, 2026-10-26). D-056: no simulator; `FTF_SKIP_SIM_GATE=1` posture.

- **Change:** `SettingsTestingScreen` mounts `<TimingReadoutRow />` directly after `<TestingSection>` (default testID `settings.testing.timing-readout`, no gate of its own). The hub's Testing row now shows on `__DEV__ || testing.stage_users || testing.timing_readout`. The flat `SettingsScreen` is unchanged.
- **New pins:**
  - `check-settings-ia` T1 (AST): the components-path import, exactly one mount, no props, no conditional, the child right after `<TestingSection>`.
  - `check-settings-ia` T2 (AST): the `settings.hub.testing` row's condition is an `||` chain that resolves to exactly `__DEV__`, `testing.stage_users` and `testing.timing_readout`, with the row in the branch taken when that is true.
  - `check-settings-ia` T3 (AST, D-166): `LAUNCHED_FLAG_DEFAULTS` holds neither `testing.timing_readout` nor `testing.stage_users`, and has no spread or computed entry hiding a key.
  - `check-settings-ia` T4 (AST): `<TimingReadoutRow />` is mounted nowhere in `mobile/src` except the Testing page.
  - `check-settings-testids`: `settings.testing.timing-readout` in NEW_GATED, pinned to `TimingReadoutRow.tsx`.
- **Sabotage (each red, then green on restore; files byte-identical after): 18/18.**
  - T1, 10: import removed, wrong path, aliased, mount removed, mounted twice, testID overridden, own `&&` gate, moved before `TestingSection`, a row in between, moved outside the ScrollView.
  - T2, 6: gate reverted to `__DEV__ || stage_users`, const bound to the wrong flag key, `||` → `&&`, `stage_users` dropped, `__DEV__` dropped, an extra flag ORed in.
  - testids, 2: the default id renamed; the default literal removed.
  - **release-lead QA follow-up (`#407` GO-with-notes), 8 more, all red:** T3 ×5 (`timing_readout` or `stage_users` added at the top or the end of `LAUNCHED_FLAG_DEFAULTS`, and a spread entry); T2 ×2 (the row moved to the false branch of the right condition, and the gate reverted to `__DEV__ || stage_users`); T4 ×1 (a second mount on the hub). Checks renamed from 5a/5b to T1–T4 so they don't collide with #360's numbering.
- **Local runs:** `tsc --noEmit` clean; testid-lint OK; all 117 `check-*.js` pass.
- **Code-walk (App Store build, only `testing.timing_readout` on, hub on):**
  1. `RootNav.tsx:272-274` mounts the hub.
  2. `SettingsHubScreen.tsx:94` is true, so `:337` shows the Testing row (`:339`).
  3. On `SettingsTestingScreen.tsx`, `:50` `TestingSection` renders its "Testing" banner (`TestingSection.tsx:51`) and the unconditional "Test feedback" row (`:53-65`); "Test stages" stays hidden (`:66`, `stage_users` off).
  4. `:55` renders the readout (`TimingReadoutRow.tsx:30` passes).
- **TestFlight checklist (operator, `testing.timing_readout` delivered to the device):**
  1. Settings shows a Testing row; tap it. Under the "Testing" banner and "Test feedback", the last row is "Last tap to first card".
  2. Before any Find trades tap this session it reads "No trade search yet this session". After a tap that shows a first card it reads "N ms · network · launch", plus " · <serve_source>" (e.g. " · device") when R2 carried one.
  3. With the flag off (and `stage_users` off), the hub has no Testing row.
- **Not run yet:** the TestFlight checklist.

## 2026-10-25 — 200 ms path, mobile pieces (#363): pass A, M, C — evidence

Full gates, not express (PRD #339; eng scope v1.3). D-056: no simulator; `FTF_SKIP_SIM_GATE=1` posture.

- **Ship gate:** CI 4/4 green on `e362c8ee` (backend-tests, mobile-typecheck with every `check-*.js`, testid-lint, web-structure). CLEAN against `main` @ `3d752296`; main was merged in at `04d50ade`.
- **Code-walk:** [code-walk-mobile.md](../docs/plans/trade-time-to-suggestion/code-walk-mobile.md), keyed by symbol, with each claim's guard.
- **New mobile guards:** `check-trade-pages`, `check-trade-buffer`, `check-trade-inplace-reveal`, `check-no-finding-more`, `check-withdraw-in-place`, `check-trade-first-card-events`, `check-timing-readout`, `check-device-first-page`.
- **Sabotage runs (each red, then green on restore):**
  - first-card events: 7 named sabotages, plus the `team_review` scoped-only rule;
  - device page: no max age (1c), a request before the push (3a), an append merge (1h), the demo-start clear (4b), the Retry spoken label (4c);
  - no-finding-more: 3 sabotages, plus the P36 tally at zero (4d);
  - `check-usage-trends` 2h: a pin write before the league switch.
  - Four guards were re-pinned to new code shapes, rule unchanged, each sabotaged once: inplace-reveal 2b, trade-pages 5b, withdraw-in-place 4c/4e, win-now-recovery.
- **Local runs:** `tsc --noEmit` clean, and testid-lint OK.
- **Backend:** `test_time_to_suggestion_events.py` (exact R1/R2/R2b/`deck_buffer_empty` prop rows; R1 INTENT; the other three NON_INTENT; join ids survive the digit-run scrub only when id-shaped; sabotaged). Analytics ingest suite: 145 passed. `test_analytics_taxonomy_384` pins follow the R1 widening.
- **Review:** onboarding-eng approved C's session side (A1 folded in at `92a59dc5`).
- **release-lead QA round 1 (NO-GO, 10-25), fixed:**
  - **P1-a** (C's cross-key write on a league/format switch): fixed and pinned by guard 3h, which runs the screen's own save effect, reset and format effect. Sabotages: dropping the key check fails 3h/3i; skipping the unbind fails 3h; skipping the format discard fails 1k/2f2.
  - **P2-a** (a save that predates a discard): executed case 2j; dropping the time check fails it.
  - **The #400 kill switch mid-deck** (`nextDeckJob` drops the paging fields; the legacy poller takes over): `check-trade-pages` 6a–6d. Sabotages: keeping the old spread fails 6a/6c; not rebinding fails 6c; the job not holding the merged list fails 5b/6d.
  - **#339 item 12** (named gate misses: `roster_check_unavailable` and `wait_reason`, ending after 10 s): new guard `check-gate-miss`. Sabotages: generic fallback fails 2a; a wait that never ends fails 1e; a timing promise fails 2c.
  - **Results:** all 117 `check-*.js` pass, testid-lint OK, `tsc --noEmit` clean.
  - **Checklist:** code-walk §4 now tests pass A directly (it's live with no kill switch), adds a 6-step **lever-off** block (with paging off the deck ends on the legacy summary, not P30) and the gate-miss states, and gates C on #367–#369 plus `trade.first_page_store`.
- **Readout:** `TimingReadoutRow` (now showing `serve_source` too) **isn't mounted yet**. onboarding-eng mounts it on #360 after #363.
- **Not run yet:** the TestFlight checklist (code-walk §4), and app-manager's AC-L1 two-device session (OA-6, 11-07 to 11-09).

## 2026-10-25 — S0 background roster refresh, Sleeper 429 circuit, R10 pick fix (#378)

Full gates ([scope](../docs/plans/trade-time-to-suggestion/scope-eng-s0-fetch.md)). Server only; D-056: no simulator; `FTF_SKIP_SIM_GATE=1` posture.

- **Backend:** CI 4/4 green on `52bcb7fa`. Local full suite 7777 passed, 1 skipped, after R10 (`2a05ca80`). After merging main (`3d752296`): the targeted S0 suites pass, 115/115. They are `test_roster_refresh_async.py` (18), `test_roster_refresh_state.py`, `test_sleeper_backoff.py` (34), `test_traded_picks_unavailable.py` (11), `test_session_init_sleeper_calls.py` and `test_co_owner_rosters.py`.
- **Pins:** per Sleeper session init, rosters 1, meta 1, total ≤ 8 (was ≤ 10, D-178). A numeric MFL id makes no Sleeper roster or meta call.
- **Sabotage, each red then restored:**
  - `maybe_refresh_async` single-flight removed → the barrier test fails `8 == 1`;
  - the R10 guards removed → 6 of 11 `test_traded_picks_unavailable` fail.

  The 60 s retry cooldown has direct tests (10 s → none, 61 s → one, unparseable → not blocked) but no recorded sabotage run.
- **Code-walk:** scope evidence section. Covers fresh / stale on failure / no state row, the open circuit, and the `maybe_refresh_async` thread path.
- **Reviews:** onboarding-eng approved the session-init diff (advisories A1/A2 recorded as R9/R11). The fingerprint contract with trades-eng is at v0.3.
- **CI note:** one red run on `a860eaa3` was `test_ranking_service_threads`. That's a cross-branch wall-clock flake in #357 (`setswitchinterval(1e-6)` plus a 60 s join), routed to rankings-eng; it doesn't touch S0 code.
- **Prod check after deploy:** for one app open, the Render log should show at most 8 `→ Sleeper GET` lines after `=== /api/session/init`. A `league_roster_state` row should then exist for that league (`status='fresh'`).

## 2026-10-27 — B7: no D-13 policy notice right after agreeing (#380; Product's pre-launch review)

Full gates (head-eng's ask; scope `docs/plans/prelaunch-onboarding/scope-b7-d13-fresh-install.md`). Mobile only; D-056: `FTF_SKIP_SIM_GATE=1` posture.

- **The change:** `useSession.bootstrap` records `bootSignedIn: !!user`. When it's false (a fresh install, a reinstall or a signed-out user), the sign-in screen's "you agree" line came first, so `useWhatsNew` hides this release's notice and stores it as seen. A signed-in upgrader still sees it once.
  - A first cut imported the hook into useSession, which broke `check-win-now-recovery.js`'s import allowlist. It was rewired to a boot fact in state, with no import.
- **Pin 8 in `check-whats-new.js`:**
  - the boot fact is set only by `bootstrap` (`!!user`, after the restore) and never reset by sign-out;
  - the hook's read, the entry condition, and the guarded effect are SEEN_KEY's only writes besides dismiss.
  - **Sabotage 8/8 red,** restored byte-identical. Pins 1–7 are unchanged.
- **Runs:** see the PR (tsc, the full `check-*.js` loop, testid-lint).
- **Operator TestFlight check** (11-06 build, `ux.whats_new` on):
  1. a fresh install, after sign-in: no tip;
  2. an install over a signed-in previous build: the tip shows once;
  3. signed out, then signed in again: no tip.
- **2026-10-28, release-lead QA @ `d6e3cfa1`: GO-with-notes. P2-1 fixed:** `check-whats-new.js` pin 9 checks B7's legal premise.
  - The sign-in screen's "By signing in you agree to the Terms & Privacy Policy" line renders unconditionally in `SignInScreen`'s own JSX (no `{…}`, ternary or `&&` above it).
  - It carries the "Terms" link to `/terms` and the "Privacy Policy" link to `/privacy`.
  - **Sabotage 6/6 red,** restored byte-identical:
    - the line removed;
    - wrapped in `{landingOn ? (…) : null}`;
    - wrapped in `{!isDemo && (…)}`;
    - the Terms link pointed elsewhere;
    - the Privacy label changed;
    - the agreement text softened.
  - Two malformed first-try mutations were re-run as valid JSX.

## 2026-10-15 — #326 value core v4, #328 live-deck filters, #327 Calibration Yes/No

- #326: CI 4/4 green on `fd805933`. Value-core, grading and fit suites 230 passed; the redundancy test gains the superflex third-QB and QB-for-QB cases.
- #328: CI 4/4 green on `1bf2235d`. Local full suite 7682 passed, 1 skipped (`test_rookie_scope.py` excluded). `test_deck_quality.py` has 10 tests, incl. the wiring test through the real trade-job harness with the flag on and off. The bake-off harness pins the flag off, so golden captures are unchanged. Prod flag confirmed `true` after deploy; the first endpoint read was a stale cache.
- #327: first CI run failed `test_app_version_consistency` (`app.json` 1.21.3 vs `Info.plist` 1.21.2). It was green 4/4 after bumping `Info.plist` (`81432938`). Mobile: `tsc --noEmit`, every `check-*.js` (`check-blind-grading` now pins `calibration.yes` / `calibration.no`) and testid-lint pass. TestFlight checklist in `docs/plans/blind-grading/scope.md` (2026-10-14 addendum). **Operator to run on 1.21.3.**

## 2026-10-14 — Fit arms after every build (#324)

- CI 4/4 green on `16209717`. Grading, fit and value-core suites: 230 passed, incl. `test_build_folds_fit_arms_into_every_new_deck` (fold after build, projection cache, failed build skipped, fold error never raises). The `add-fit-arms` route test now resets the projection cache.

## 2026-10-12 — Usage Trends order toggle + readable jumps (D-205): evidence, PR #323

Full gates, not express ([scope](../docs/plans/usage-trends/scope-order-toggle.md)). D-056: no simulator; `FTF_SKIP_SIM_GATE=1` posture.

- **Backend:** `test_return_needs_the_weekly_volume_floor` (new). It was red with the floor removed and green with it restored. `test_usage_trends.py` + `test_usage_trends_refresh.py`: 47 passed. Usage/analytics/taxonomy/seed/flag subset: 695 passed.
- **Mobile guard** `check-usage-trends.js` (1j–1l, 1m2, 1p, 1t2–1t3, 1y2–1y3, 2e4–2e6). Each of **8 named sabotages turned it red**, then green on revert:
  1. jump copy reverted;
  2. back-without-jump counted as a jump;
  3. weekly order ascending;
  4. week card shows the average;
  5. jargon in copy (1p fires on its own);
  6. weekly branch unsorted;
  7. card ignores order;
  8. toggle not remembered.

  All `check-*.js` green; `tsc --noEmit` clean; testid-lint OK.
- **Real data:** live 2026 Week 4 Snaps under the new rule gives 35 jumps, then Back or new = Collins 69% / Okonkwo 58% / Tinsley 53% / Sarratt 36%. The 0–31% low-volume returns are gone.
- **Code-walk:** [code-walk.md](../docs/plans/usage-trends/code-walk.md) §8.
- **Ship gate:** CI 4/4 green on the exact head `87062f72`, after merging main (#322). Squash-merged as `fc0f6149`; `FTF_SKIP_SIM_GATE=1` (D-056).
- **Prod (2026-10-12 23:10 UTC):** Render `dep-db6mh67avr4c73cqn4h0` is live on `fc0f6149`. `/api/feature-flags` → `usage_trends.enabled: true`, and `/api/usage-trends` answers 401 unauthenticated.
- **Not run yet:** the 8-step TestFlight checklist (scope-order-toggle §3), on iOS 1.21.2 build 165.

## 2026-10-10 — Buyer/Seller tags pink, Home ice uncapped (D-204): express

express: flare Buyer/Seller tags on League rankings + Home position tiles; suggested-side ice on every banded Home tile — gates skipped by operator

- `tsc --noEmit` clean; `testid-lint` OK; all 106 `mobile/tests/check-*.js` suites pass. `check-position-split-parity` 1q now expects all four banded positions emphasized (was the two most extreme). Backend untouched.
- No runtime evidence (D-056). TestFlight 1.21.1 check: Home corner tags pink; every Seller tile has Sell in ice and every Buyer tile Buy in ice, all of them; Mid-pack tile has none; League rankings filtered to one position shows pink Buyer/Seller next to the ice "You". `FTF_SKIP_SIM_GATE=1` posture.

## 2026-10-10 — Usage Trends (`usage_trends.enabled`, ships on): evidence, PR #321

Full gates, not express. Scope first ([scope](../docs/plans/usage-trends/scope.md)). Evidence under D-056: no simulator; `FTF_SKIP_SIM_GATE=1` posture.

- **Data source check:** Sleeper `/stats/nfl/2026/{1..4}` against the operator's snap CSV and the Footballguys target export. Identical on 1652/1656 snap and 1648/1652 target RB/WR/TE player-weeks; team totals match (NYJ 66→32 snaps, CHI 72→93, PHI targets 25/25).
- **Backend:**
  - `test_usage_trends.py` (31): math, real-data NYJ+PHI regression, route incl. week selection.
  - `test_usage_trends_refresh.py` (15): weekly store.
  - **9 named sabotages, each red then green:**
    - byes/out in the divisor;
    - count-gated spikes;
    - no previous-game clause;
    - QB rows out of team totals;
    - orphan rosters read as FA;
    - non-member league served;
    - partial week stored;
    - corrections never freeze;
    - route ignores the store.
  - **Live end-to-end** into a scratch SQLite: 4 weeks stored (32 teams, about 610 players each); a re-run plans nothing; stored vs a fresh live fetch compute byte-identical on the full NFL (354 players). An order-only mismatch was found and fixed with a deterministic sort.
  - **Full suite** `pytest backend/tests -k "not calibration_gate"`: **7695 passed, 1 skipped, 0 failed** (local Python 3.14; CI runs 3.12).
  - An earlier overlapping run showed one failure in `test_prepared_trade_store_v2::test_generation_renewal_retains_token_and_never_extends_artifact_expiry`. It passes alone on this branch and on `main` `d154eef1`: timing-sensitive under load, unrelated.
  - `test_seed_ui_test_db` caught the flag missing from the `onboarding-v2` fixture; fixed, and the guard now pins all three fixtures.
- **Mobile:**
  - New `check-usage-trends.js` executes the pure helpers: status, filter, headline copy and vocabulary, table cells and total, sort, week selection. It also pins the wiring and the analytics registration. It caught the unregistered `view`, `weeks` and `sort` props during the build.
  - **12 named sabotages, each red then green:**
    - client re-sort;
    - text on table actions;
    - jargon headline;
    - pins before a league switch;
    - Quick Set ignoring a re-push;
    - orphan as FA;
    - OUT sorting with zeros;
    - column sort leaking into Version A;
    - third tap never resetting;
    - zero weeks allowed;
    - weeks missing from the cache key;
    - selection never sent.
  - `check-home-tab.js` 4i (flag-gated row).
  - All 102 `check-*.js` green; `tsc --noEmit` clean; testid-lint OK.
- **Code-walk:** [code-walk.md](../docs/plans/usage-trends/code-walk.md) §1–7.
- **Not run:**
  - hosted CI (the draft PR runs it);
  - the TestFlight checklist in scope §3, which needs a build with the flag on.

Merged after the home-engagement redesign shipped; ships with the flag on (operator, 2026-10-10).
- **Ship gate:** full local suite on the merged code 7702 passed, 1 skipped, 0 failed. After the flag flip, the flag/seed/usage/home subset passed 546. 106 guards, tsc clean, testid-lint OK. CI 4/4 green on the exact head `a6945901`, then squash-merged as `35c6838c`. `FTF_SKIP_SIM_GATE=1` (D-056).
- **Prod checks (2026-10-10 18:28 UTC):**
  - `/api/feature-flags` → `usage_trends.enabled: true`;
  - `/api/usage-trends` and the cron route answer 401 unauthenticated (they are live routes, not 404);
  - backfill stored weeks 1–4 (32 teams each; 603/616/616/618 players);
  - TestFlight checklist: not yet run (iOS 1.21.0 build 163).

## 2026-10-10 — Value core v3 (#320): rule tests, replay, rebuild outcome

- CI 4/4 green on `69558060`. Value-core + grading + fit suites: 229 passed, incl. `test_redundant_no_second_starter_at_a_capped_position` (partner and viewer sides, swap, 1QB vs superflex, TE in superflex, two-TE league, weak incumbent, off, enumeration).
- Replay on round-2 cards (all graders' decks): flagged as redundant 30% of today's engine, 28% fit A, 25% fit B, 19% value core. Operator grades, redundant vs not: today's engine 3.47 vs 3.91, fit A 3.40 vs 4.11.
- Dry run on the 19 unstarted decks (read-only): v3 value-core decks 77–566 ranked cards; fit A 1–18, fit B 0–9.
- Prod: 19 rebuilt (17 first pass, 2 on retry); fit arms folded into all 19; every open deck reports `engine_version = value-core-3`.

## 2026-10-10 — Home hub (D-202, `nav.home_hub`): evidence

Full gates (no express). Scope block before code ([scope](../docs/plans/home-engagement/scope.md)); Phase 1 foundations, then two build agents (M-Home, M-Dest) with disjoint files, integrated on `feat/home-hub`. D-056 posture: no simulator, `FTF_SKIP_SIM_GATE=1`.

- **Automated, on the merged tree:** `tsc --noEmit` clean. All **105** `mobile/tests/check-*.js` pass. testid-lint OK; `test:contrast` OK.
- **New guards:**
  - `check-home-hub` (44 checks; 6 sabotages, each caught);
  - `check-home-destinations` (79 checks; 9 sabotages, each caught);
  - `check-position-split-parity` (27 checks; executes LeagueSummaryScreen's own inline split code beside `utils/positionSplit` over 16,000 randomised views; sabotage-proven 3 ways);
  - `check-standings-order` (15 checks).
- **Guards that had to pass unmodified, and did:** `check-home-tab`, `check-league-candidates-300`, `check-analytics-300`, `check-analytics-297-302`, `check-guide-spotlight-tracking`, `check-session-seed`, `check-outlook-bands`.
- **Backend:** `test_analytics_taxonomy_home_hub.py` (6) is new. Full suite at Phase 1 (the only backend change: flag + taxonomy) was 7658 passed, 1 skipped. Hosted CI runs it again on the PR.

**Code-walk proof:**
1. **Home → hub.** `HomeScreen.tsx:30-31` reads `nav.home_hub` once (`useRef`) and returns `HomeHub`. The flag-off body is untouched.
2. **Same numbers on both screens.** `HomeHub.tsx:130-131` takes splits and the ≤2-tile ice emphasis from `utils/positionSplit`. The guard holds that util equal to the screen's inline arithmetic, so Home's band is the band League rankings draws.
3. **Sell RB from Home.** `HomeHub.tsx:162` `onSell` tracks `home_tile_tapped {tile:'sell', position, band}`, then `requestLeagueSummarySplit` (`leagueSummaryIntent.ts:64`, which stamps `seq`), then `navigate('League', {screen:'LeagueRankings'})`.
4. **League rankings consumes the intent.** `LeagueSummaryScreen.tsx:1173` takes it on tab-root focus. `:1175` re-arms `filterSigRef`, so the existing auto-exit (`:1136`, `closeTeam('filter_change')`) closes any drill-in. It then sets Consensus / All / {RB}.
5. **Banner and landing.** `:1210` shows the banner only while the divider is drawn (`candidatePos === position && cutAfter != null`). It renders outside the ScrollView (`:1591`). Sell calls `scrollToEnd` (`:1217`); Buy scrolls to the list `onLayout` y (`:2329`). The hold is re-applied on layout changes and released by a drag (`:1637`).
6. **Standings.** `RootNav.tsx:839` registers `Standings` unconditionally. `StandingsScreen.tsx:74` enables the outlook query only on Projected. `:89` fires the event only on a changing tap. `:204` reuses League Summary's exported `SeasonOutlookSection`. `:256` mounts one FAB with `aboveTabBar={false}`.
7. **Team outlook.** `HomeHub.tsx:144` navigates with `editDna:true`. `TradesScreen.tsx:1040-1042` opens the Trade DNA sheet (`trades.finder_hub` is true).

**Not run:** the 15-step manual TestFlight checklist in scope §3. That is the operator's, on the new build.

## 2026-10-09b — Fit engines (#317) and roster refresh (#318): evidence

- #317: CI 4/4 green on `bea27767`; local full suite 7615 passed, 1 skipped (`test_rookie_scope.py` excluded, machine-local). New tests: `test_fit_engine.py` (9), the fold-in tests (`test_add_fit_arms_folds_blind_and_keeps_answered_cards`, `test_fold_aborts_when_a_moving_card_was_answered`), `test_admin_add_fit_arms_route`; the e2e blinding test forbids the fit arm names and versions.
- Offline fit-scorecard test (`backend/eval/fit_scorecard_test.py`, prod read-only, 99 of 120 round-1 cards scorable): Q1 AUC A 0.58 (0.63 without boards, exploratory), B 0.43 pre-registered / 0.46 as shipped (`fit-b-2`). Baselines: best-piece 0.66, value-core outlook 0.66, consensus ratio 0.36. Q2 (partner vs "they won't accept"): A 0.50, B 0.32. No approach passed.
- #318: CI backend-tests first failed on an unrelated flaky test (`test_trade_counterparty_epochs::test_real_tier_save_revokes_job_admitted_after_early_fence_before_board_publish`, `assert 1700.0 != 1700.0`; 5/5 local passes; task spun off), green on rerun. Local full suite 7617 passed. Live check after refresh: 12/12 live owners' rosters match Sleeper in each refreshed league.
- Prod runs: 10 fresh sessions folded (fit A 1–18, fit B 0–7); 14 targeted builds with refresh. 12 built; 1 transient DB SSL drop (BONEDEEP) built on retry; 1 skipped (operator owns no Bush League roster). Then 12 more folds. Final: 23 open sessions, 22 valid, 47–66 cards, 0 answered.

## 2026-10-09 — Value core v2 (#315): rules, rebuild path, replay evidence

- CI 4/4 green on `3a247685`. Local full suite 7603 passed, 1 skipped (`test_rookie_scope.py` excluded: machine-local stale player cache, also failing on `main`). Value-core + grading suites 214 passed, incl. `test_breakup_viewer_keeps_best_piece`, `test_rebuilders_never_trade_picks_for_players`, `test_retire_unanswered_only_retires_untouched_sessions` and `test_admin_pregenerate_targets_rebuild_retires_before_start`.
- Replay on graded round-1 value-core cards: breakup would remove 26 (mean 2.00), picks rule 5 (mean 2.60); the 29 kept average 2.72.
- Replay on the operator's 4 live leagues (read-only prod, old vs new config): decks 130–479 ranked cards, 11–13 partners in the first 20, no budget hit. Rebuilder-league pools shrink ~15×, mostly the picks rule (7–9 of 12–14 teams inferred rebuilding).
- Prod: 12 targeted rebuilds, 9 sessions retired `superseded`, 12 new `open` sessions with 40 cards each (20/20, 0 dropped). One-ESPN check: the rebuilt 11896 session has pool 130.

## 2026-10-02 — Home tab (`nav.home_tab`), built on `feat/home-tab`, not merged

Scope block and plan preceded code ([scope](../docs/plans/home-tab/scope.md)). Two build
agents, disjoint files. Evidence (D-056, no simulator; `FTF_SKIP_SIM_GATE=1` posture):
new structural guard `mobile/tests/check-home-tab.js` 34/34; `check-canvas-results`
(§10 trades-landing pins) and `check-rank-nav-exit` pass; `tsc --noEmit` clean;
testid-lint OK; `pytest backend/tests` 7413 passed / 1 skipped in 640s (release.json
mirror test included). Code walk: `TabNav.tsx` reads `nav.home_tab` once at mount
(`showHomeTab`), `launchTab` returns `'Home'` unless `onboarding.trades_first` is live
with no first swipe, else the untouched `initialTab`; `HomeScreen.tsx` `OPTIONS` maps the
four rows to `navigate('Rank'|'Trades'|'Matches'|'League')`; `deepLinks.ts` adds
`app/home`. Not run: hosted CI on the branch, and the 8-step TestFlight checklist in the
scope block (six-tab bar fit is the main thing to eyeball).

2026-10-08 rebase onto the Calibration ship (#312): `main` merged into the branch (conflicts:
DECISIONS → Home renumbered D-198, TEST_LEDGER, nav README — all kept both sides). Re-run on
the merged tree: `tsc --noEmit` clean; `check-home-tab` 34/34; `check-blind-grading` pass;
`check-canvas-results`, `check-rank-nav-exit` pass; testid-lint OK; release.json mirror tests
3/3. Full pytest left to hosted CI on PR #309.
## 2026-10-08 — ESPN picks fix (#314) live; operator's ESPN Calibration deck built

- CI 4/4 green on head `3aa730c7`; merged as `4de823ad`; Render `dep-db3qilqd0e5s73b6tgfg` live 2026-10-08.
- Targeted pre-generation for 313560442465169408 / 11896: session `open`, 40 cards (current 20 of 20 candidates, 0 dropped stale or unknown; value core 20, pool 346). 17/20 current and 16/20 value-core cards carry a PICK; before the fix the session was refused `too_few`.

## 2026-10-07b — Targeted pre-generation (#313) and ESPN picks fix (#314)

- #313: `test_blind_grading_routes.py` 28 passed, incl. the new `test_admin_pregenerate_targets_refresh_then_build_each_pair`. Full local suite: 7598 passed, 1 skipped, with `test_rookie_scope.py` excluded. Its 6 failures reproduce on untouched `origin/main` locally (`reason: stale_player_cache` from the restored local data), so they are machine-specific. CI on the PR: 4/4 green.
- #313 prod proof: replenish decks (`deck_replenish_log` 2026-10-04 and -07) write qualifying `deck_impressions` (`model_arm = owner_v2_bilateral`). Targeted run, 4 pairs: all `open`, 40 cards each (current 20 / value core 20, 0 dropped stale or unknown; value-core pools 513–938).
- ESPN 11896: refused `needs_fresh_deck`. Read-only replay of job `e89f466d` with all draft_picks rows gives 20/20 usable, versus too_few on platform rows only.
- #314: the grading service, routes, db and e2e suites, 90 passed, incl. the new `test_assigned_picks_join_the_catalog_when_the_engine_prices_them`.
- Prod logs: `WORKER TIMEOUT` in `_run_weekly_replenishment` at ~13:33 UTC every day, 2026-10-02 through 10-07.
- TestFlight: operator confirms the Calibration tab is visible on 1.18.0 (159). The §9 checklist is still owed.

## 2026-10-07 — PR #312 CI green, prod deploy verified, decks generated; TestFlight build failed (signing)

- CI on the final head (`fd616578`, after merging main's SQLAlchemy pin): backend-tests, mobile-typecheck,
  web-structure, maestro-testid-lint all green. Two earlier CI reds were fixed: a machine-dependent e2e wall-clock
  bound (now per-deck, 8 s budget) and four `test_decline_reasons` #419 tests that failed on `main` too after
  2026-10-06 (pinned 2026-09-06 impressions vs `_DECK_OUTCOME_MAX_AGE_DAYS = 30` on the real clock; the harness now
  lifts the cutoff).
- Prod after `dep-db38m460tbcc7380tufg` (live 2026-10-07): flags draft.tab=false, grading.blind=true,
  trade.value_core=false; `/api/admin/grading/report` 200 with the cron secret; `/api/grading/sessions/current`
  without a session → 404 (gate).
- Pre-generation: 8 candidates, 7 sessions open (20 current + 20 value-core each; one 39 with 1 shared), 1 skipped
  `needs_fresh_deck`, 0 failed. Value-core pools 567–938 fair trades per seat.
- EAS iOS production build 1.18.0 (158) `8457b850-…` ERRORED: XCODE_BUILD_ERROR, distribution certificate
  (serial 429A52778FF3BA4F2D56ADC241D54BCC) "not valid for code signing … revoked or expired". No submission.
- Mobile runtime evidence still owed: the TestFlight checklist in `docs/plans/blind-grading/code-walk-mobile.md` §9.

## 2026-10-05 — Calibration (in-app blind grading) integrated; open to every app user

Built by four Fable 5.1 package agents (P1 service/schema, P2 routes/flags, P3 mobile, P4 docs) from
`docs/plans/blind-grading/specs.md`, merged into `feat/blind-grading` (on top of the value-core branch) and lead-reviewed.
Lead fixes: a `building` session orphaned by a restart is re-kicked by POST (route now always calls `start_session`);
the build thread falls back to empty league facts so a session can never stay `building`; a stale `±10%` assertion in
`test_value_core_serving` now reads the evidence's own ratio floor (it only passed alone on a local DB seeded before
the band change — model_config seeds are INSERT OR IGNORE). Operator 2026-10-05: open to every app user
(`grading.blind` true, `_calibration_allowed` True), freshness 14 days, cron-only pre-generation route, purpose copy.
- Full backend suite (local Python 3.14): **7632 passed, 1 skipped**. Grading tests: routes, service, db, e2e
  (the e2e walks every response body and fails on any arm/engine key or value before the reveal).
- Mobile: `npx tsc --noEmit` OK, `testid-lint` OK, all `mobile/tests/check-*.js` guards pass incl. the new
  `check-blind-grading.js` (27 checks; four planted sabotages caught by P3).
- Flag-off golden (`test_bakeoff_serving::test_flag_off_is_byte_identical…`) and the flag-mirror tests pass.
- Prod eligibility (read-only, 2026-10-05): users with a qualifying current-engine deck — 7 days: 4 users / 8 pairs;
  14 days: 8 / 16. Runtime evidence for mobile is the TestFlight checklist in
  `docs/plans/blind-grading/code-walk-mobile.md` §9 (operator).

## 2026-09-30 — Value-core engine built on a branch (flag off)

Full gates (scope/PRD/HLD/LLD/specs in `docs/plans/value-core-engine/`). Five parallel build packages merged
into `feat/value-core-engine`, lead-reviewed. Local Python 3.14 (no 3.12 here; CI is the 3.12 gate, not yet run).
- Baseline at contract commit `315ff1e8`: 7413 passed, 1 skipped.
- Integration branch full suite: **7522 passed, 1 skipped** (527 s); 109 new value-core tests, incl. e2e with the real engine.
- **Flag-off identity:** `bakeoff_harness.run_capture` (default, consolidate intent, sf_tep) with `PYTHONHASHSEED=0`
  is identical to `3bb981ed` after stripping ids/timestamps; the base is itself deterministic. With the flag off
  `backend.value_core` is never imported (fresh-interpreter check).
- Latency, 14-team fixture, `pipeline.run` x10: p50 1.54 s, p95 1.77 s (target p95 < 8 s).
- Synthetic bench smoke (not the verdict): insult 0.6%, real piece back 94.2%, median value given +7.6%,
  worst-seat appearances 4 → FAIL on the ≤3 cap only; the cap is infeasible once the viewer's ≤14 tradeable
  assets spend their allowances (0 cap-respecting cards left when it breaks).
- Real-trade recall (committed FFV3/Lakeview fixtures, point-in-time DP values): 64 cases / 128 orientations;
  exact@10 0%, close@10 18%, in-pool 1.6%; rejects floor 96, band 28, filler 2; |log ratio| p50 0.32, p80 0.65.
  Band left at ±10% pending the operator.
- Lead fix at review: core caps round-robin over headliners (pool share giving a top-3 asset 92% → 12%).
- Deck variety rules (operator request, same day): one card per trade idea (same partner + headliners; picks
  collapse by year/round), acquisitions in rounds, partner cap in the first 30. Synthetic first-30, before → after:
  near-duplicates median 1.5/max 5 → 0, repeat acquisitions median 8/max 11 → 0, distinct acquisitions 22 → 30,
  pick repeats from one partner max 9 → 0; insult 0.6%, real piece 92%, median given +7.7%; p50 1.3 s.
  The appearances guardrail now counts acquired assets only. Full suite after: **7527 passed, 1 skipped**.
- 2026-10-01 operator answers: logged legacy fallback on deck-build errors (tests: fallback serves legacy cards;
  capture equals flag-off except `safety_policy`); default band ±10% → ±20%. Band evidence: real-trade coverage
  ±10% 20% / ±15% 33% / ±20% 38% / ±25% 39% / ±30% 44% / ±40% 52%; synthetic insult rate 0.6% / 0.8% / 1.1% / 2.8% /
  28.9% / 45.6%; recall in-pool 0.8% → 2.3% at ±20% (floor rule rejects most real trades: sub-450 throw-ins).
  Real-league freeze blocked at first (permission classifier); the operator then granted prod reads explicitly.
- 2026-10-01/02 real-league bench (frozen read-only: 6 leagues incl. two 2026 "Bush League" ids, 77 seats, 10 boards;
  file kept private outside the repo). Symmetric ±20% failed on real rosters (insult 5.6%, median given +17.1%;
  synthetic had said 1.1%), so the band became asymmetric: pay up to 20% / take up to 10% (`vc_band` 0.20,
  `vc_gain_band` 0.10). Default, first 30 cards: insult 0.2%, real piece back 93.2%, median value given +8.4%,
  near-duplicates 0, repeat acquisitions 0, worst acquired-asset appearances 4 (one seat, secondary piece; verdict
  FAIL on that guardrail only); overpays >10% on 23/2,220 cards. Throw-ins (operator rule: recipient values it
  >= 2x market, >= 450, with evidence): 13/2,220 first-30 cards (4 to viewer, 9 to partner); before the evidence
  requirement unpriced/unranked players produced up to 28/30 cards on one seat. An independent review found 2 bugs
  (throw-in toggled the stud premium; shortlist cut before the junk check) and 2 risks (variant budget; thin partner
  boards): all fixed with regression tests (`THROWIN_MIN_COMPARISONS` = 3, premium on core counts, per-pair cap,
  separate variant budget).
Evidence delta: unit + e2e tests and the WP3 [code-walk](../docs/plans/value-core-engine/code-walk.md); no mobile change,
so no TestFlight checklist is due until the flag is flipped.
## 2026-10-05b — SQLAlchemy pin (PR #311) and production deploy of #310 + #311

Branch `fix/pin-sqlalchemy-2-0` from `origin/main` `85428813`. Hosted CI 4/4 green
(CI installs the capped line but tests on SQLite, so it cannot prove the Postgres
boot). The proof is the deploy: Render `dep-db234m8m7kps73da6ftg` of `e30a8f47`
built and went `live` at 19:28 local, after `dep-db1t42jbc2fs73dom7i0` of `36bed585`
had failed with `ModuleNotFoundError: psycopg` (build log: `sqlalchemy-2.1.3`).
Post-deploy: production `GET /api/feature-flags` → `feedback.decline_reasons: false`.
Device check of the one-tap decline (3 steps in the 2026-10-02 scope doc) still owed
by the operator. Sim gate skipped per D-056 (`FTF_SKIP_SIM_GATE=1`).

## 2026-10-05 — Decline reasons disabled (`feedback.decline_reasons` off), branch evidence

Branch `fix/disable-decline-reasons` (from `origin/main` `3bb981ed`). Flag flip only;
no mobile or backend source changed. Mobile: 99/99 `check-*.js`, `npx tsc --noEmit`
clean, `testid-lint OK`. Backend full local run: 7410 passed / 1 skipped / 3 failed in
867s. Two failures were this change (the `onboarding-v2` and `profiles-on` flag
fixtures must equal release plus their own surface) and are fixed; the affected files
then pass 225/225 (`test_seed_ui_test_db`, `test_decline_reasons`,
`test_prepared_trade_runtime`, `test_owner_batch_publication`). The third,
`test_prepared_trade_runtime.py::test_pending_rechecks_read_guard_after_serialization`,
passes 3/3 alone on untouched `origin/main` and alone with the change; an earlier
stop-at-first-failure run instead tripped
`test_owner_batch_publication.py::test_first_30_are_durable_running_and_full_inventory_keeps_order[False]`,
which also passes alone both ways. Read: two full-run-only flakes in the
prepared-inventory tests, unrelated to this flag — not root-caused. No fresh full run
after the fixture fix; hosted CI on the pushed sha is the gate. Off-path proof
(decision row, pass Elo, no-resurface bind) is the code walk in the
[scope](../docs/plans/decline-reason-capture/scope-disable-2026-10-02.md). Hosted CI on
PR #310: 4/4 checks green; squash-merged as `85428813` 2026-10-05. Device
check (3 steps, same doc) not run. Sim gate skipped per D-056 (`FTF_SKIP_SIM_GATE=1`).

## 2026-09-22 — Persistent prepared trade inventory, release candidate

Plan/scope preceded code. Three Astra Ultra lanes plus parent integration built
silent full-offer preparation, verified per-account/team binding, compressed SQL
artifacts, durable resumable sweeps, exact evidence-before-publication adoption,
account-deletion fencing and current read guards. Model/arm settings unchanged.
Parent172 focused tests passed; later runtime/epoch85 passed. Independent393
affected regressions and80 store tests passed; web195/195 and test-ID lint passed.
Earlier concurrent full run:7097passed/1skip/2fixture failures; corrected fixtures
pass focused, fresh full and exact-head hosted CI still pending. No production
write/deployment/activation claim. [Evidence](../docs/plans/prepared-trade-inventory/validation.md).

Final privacy correction demonstrated two RED→GREEN export controls;131
store/account-rights/deletion tests pass. No stored evidence changed. Unattended
replenishment cannot adopt as an interactive request (39 runtime/replenishment
tests pass). Fresh full local7132passed/1optional-data skip in434.21s preceded
these final guards; final exact-head hosted CI remains mandatory.

## 2026-09-22 — Release CI fixture repair and completed projection plan

PR304 first hosted Python3.12.14 run:6860pass/1skip/1failure734.50s;
three client/web jobs green. Rookie scope fixture starts last_active0 and can
be evicted before its first request. Added freshness regression RED1.27s,
changed fixture timestamp to now;61 focused scope/session/scoring tests pass
2.31s. No auth/runtime/generation changes or weakened assertions. New exact-head
CI required before merge. Reviewed season/weekly/bye starter-impact plan complete,
docs only. [Evidence](../docs/plans/bilateral-model-revision/release-ci-fixture-repair.md).

## 2026-09-22 — Production learning release authorized, operations pending

Owner explicitly requests new model/docs live despite disclosed latency and
quality uncertainty. Scientific promotion hold is superseded as a deployment
decision, not relabeled passed. CI/integrity/privacy/readback remain mandatory.
Read-only12:03:42UTC Render+API preflight: live73bfa41e, one Standard instance,
autodeploy off,270 config rows, owner-only bilateral enabled; revision selector
absent/default0. All unrelated settings remain untouched. Hosted exact-head CI,
merge, deploy and audited revision activation pending. No new code since validated
2186d436, no TestFlight needed. [Contract](../docs/plans/bilateral-model-revision/production-learning-release.md).

## 2026-09-22 — Round8 counterparty job freshness (not released)

Parent full backend: **6,861 passed /1 optional-data skip in364.43s**, local
Python3.14.4/isolated SQLite on frozen server0b24ad25. TypeScript/all99 mobile
structural suites/test-ID lint/web195 pass. Nine named RED→GREEN cases; B61,
C188 and parent72 focused groups overlap full-suite coverage. Five source/HEAD-
guarded native/worker/off/failure runs preserve3836 revision native/3306 public
and full persisted occurrences; incumbent2843/2354 exact; failed write0 exposure.
First durable15.127s vs8.425s local smoke does not qualify3sec or acceptance.
Repair covers captured-member job dependencies, league guard and seven final
ranking-publication fences; service-backed pending/synchronous idea paths and
provider/market/out-of-process freshness are explicit exclusions. No source-model
semantics changed, no production write/toggle/push/deploy/TestFlight. Hosted CI
and device/load gates unrun. [Source-bound validation](../docs/plans/bilateral-model-revision/validation-20260922-round8.md).

## 2026-09-22 — Bilateral revision round7 and capture validation (not released)

Stable integrated runtime: **6,800 backend passed /1 optional-data skip in351.78s**,
Python3.14.4/isolated SQLite. TypeScript/all99 mobile structural suites/test-ID lint
and195 web checks rerun green. Source hashes and commands in
[validation](../docs/plans/bilateral-model-revision/validation-20260922-round7.md).
Independent round7 review32 focused/406 combined; age capture149 group and replay
environment44 group overlap full-suite coverage, not additional distinct tests.
Exact3836 native and3306 served/full persisted parity; failed write zero exposure.
Local first durable14.538s versus8.576s incumbent still blocks promotion.
Separate43-test assignment memo prototype rejected for10.24% first-delivery
slowdown; no cache integration. Prepared-inventory source audit identifies
incomplete counterparty/ownership freshness, not a missing prewarm trigger.
No GitHub push/PR, hosted CI, prod write/toggle/deploy or TestFlight.

## 2026-09-22 — Bilateral revision, iterative evaluation (not released)

Parent specifications preceded three Astra Ultra implementation lanes. Current
isolated branch `codex/bilateral-revision-20260922`, base `ecda17d1`.
Final source-frozen backend **6,690 passed /1 skipped in372.75s** on local
Python3.14.4/isolated SQLite; opt-in captured2025 backtest skipped. Current
policy/candidate/incumbent focused229 and route/overhaul56 green; four new real
rollback-boundary tests were RED before parent fixes. Native TypeScript, all99
structural suites/test-ID lint and195 web checks passed; no client edits.

Bounded read-only capture77 distinct requests; locked comparison12 real+57
constructed per model. Price sensitivity repaired; mixed focal/repetition/raw
return diagnostics and six-dimensional evidence gaps prevent an acceptance claim.
Policy3 retained replay69/69 has exact old-policy order bridge, no inventory
changes/errors/quarantines, and a disclosed meaningfulness prefix trade-off.
Actual-worker first durable30 regressed8.69→18.66s; private single-freeze parity
prototype saves14% but is insufficient and unintegrated. Further equivalent
performance work and input-evidence audit continue under renewed owner authority.
No production write, toggle, push, hosted CI, deploy or TestFlight upload.
[Evidence and current decision](../docs/plans/bilateral-model-revision/release-decision.md).

## 2026-09-22 — Independent model scorecard, offline foundation

Three Astra Ultra workstreams plus parent integration and cross-review on isolated
`codex/model-evaluation-framework-20260922`, source base `73bfa41e`.
**172 focused tests passed**; final source-frozen full backend **6,437 passed /
1 skipped in 355.93s** (local Python 3.14.4, isolated SQLite). Earlier collection
dependency failures and six edit-during-run outcome failures were corrected and
superseded by the fresh green run, not waived. Failure-sensitive review controls
and repairs are recorded in [validation](../docs/plans/model-evaluation-framework/validation.md).
Two network-blocked common-input replays produce identical manifests/scorecards
for 2,843 bilateral / 2,103 owner-v1 / 106 fit cards; one independent request, no
behavioral acceptance evidence. [Comparison](../docs/plans/model-evaluation-framework/comparison-2026-09-22.md)
and [revision plan](../docs/plans/model-evaluation-framework/model-revision-plan.md)
remain explicit about Unknowns and unratified thresholds. No production reads/writes,
arm toggles, source-model changes, push, hosted CI, deploy or TestFlight build.

## 2026-09-21 — First-action backend implementation, release gates in progress

Owner authorized production release. Three implementation workstreams reviewed by parent; no model/budget changes or mobile source edits. Structured evidence 101 focused tests, publication 19, cache/admission final expanded set 197 (overlapping counts); parent copied-status race + observer checks 5 passed. Named callback-before-commit, missing admission/invalidation and no-post-read-revocation sabotages detected; restored implementations green. Three baseline/three updated isolated full-worker runs retain 2,354 offers/impressions and exact expanded valuation/package/order parity excluding explicitly listed occurrence IDs/clock fields. Median first durable 12.974→8.754s, worker 12.983→11.333s on local 3.14/SQLite, not phone/production. Native typecheck/all structural suites, test-ID lint and 195 web checks passed. Exploratory full suite: 6,235 passed / 23 failed / 1 skipped; resolved background policy-preservation regression and research-adapter formatting compatibility, corrected incomplete fixtures and intended supersession assertions. Eight inspect/AST failures caused by source edits during that exploratory run passed in a fresh 61-check rerun. Final source-frozen full backend and hosted exact-head CI remain release gates. Physical TestFlight/load/three-second qualification unrun. [Release evidence](../docs/plans/trade-search-latency/release-20260921/README.md).

## 2026-09-21 — First-action latency research, initial wave complete

Three Astra Ultra workstreams plus parent review on isolated `codex/trade-latency-research-plan`, base `4913ad0c`. Parent ran **31 research tests passed in 2.12s**, isolated SQLite with socket connections blocked. Three reconstructed full-worker runs measured 13.015–13.200s; this is not production/device latency. Exact price memoization rejected (parity but no improvement); structured evidence experiment 2.126→0.784s is an upper-bound representation experiment, not integrated savings. Fresh read-only production: seven completed workers, median 61.094s. Application code/settings/data unchanged. Full application CI, pinned-runtime staging, physical TestFlight and load/three-second qualification unexecuted. [Results and limits](../docs/plans/trade-search-latency/execution-20260921/README.md).

## 2026-09-20 — Bilateral owner replacement, validation in progress

Isolated `codex/owner-v2-bilateral` from fresh `659a6332`. Parent verified **93 new
core/route/overhaul tests passed**; independent agent checks and two detected sabotage
controls recorded separately. Native TypeScript, all structural suites, test-ID lint,
and 195/195 web checks passed. Old owner immutable snapshot parity preserved.
Parent fixed-seed frozen-input replay confirms different packages/order but does not
establish acceptance lift. Full-suite/hosted-CI/release gates remain in progress;
no deployment inferred. [Release evidence](../docs/plans/owner-v2-bilateral/release.md),
[independent validation](../docs/plans/owner-v2-bilateral/validation.md).

## 2026-09-19 — Find a Trade latency investigation and local optimization

Isolated `codex/trade-search-latency` from freshly fetched `6ff61e44`. Read-only production evidence: interactive completed jobs median 43.06s (18 jobs), maximum 75.44s; today's affected jobs 43.79/47.99s. Local changes remove repeated flag scans/map copies, owner player/tier preparation, request deep copies and diagnostic subtree work. Full backend **6,068 passed / 1 skipped** (Python 3.14, 353.53s); focused owner suites 111 passed; new latency/diagnostic suites 15 passed; web 195/195, project/session checks and diff checks passed. Projection assertion rerun: 28 owner-only tests passed. Fixed-seed reconstructed search matches ordered decision and expanded feature SHA-256 digests across base/current. Final unprofiled component comparison 11.172→6.682s (~40% faster), profiled CPU stages 23.55→9.97s; excludes database/full route/device costs. No production release, budget/flag change or three-second qualification. [Evidence, limitations and device checklist](../docs/plans/trade-search-latency/README.md).

## 2026-09-17 — Shared trade significance, local implementation

Isolated branch `codex/trade-significance-20260917`, base `62ba9b3d`. Three subagents implemented rule/wiring/independent tests; parent reviewed and calibrated against frozen raw offer-time inputs. Stable full backend suite **6,058 passed / 1 skipped** (Python 3.12, isolated SQLite, 358.54s); expanded targeted 378 passed; web structural 195/195; mobile test-ID lint passed; diff check clean. Source-edit-during-run failures were superseded by the stable full rerun, not waived. See [implementation and evidence](../docs/plans/trade-significance/validation.md) and [calibration](../docs/plans/trade-significance/calibration.md).

Default `significance_mode=0`; no arm changes, product feedback writes, push, deployment, or TestFlight build. Existing review decisions preserved. Hosted CI/mobile typecheck/structural suites and broader calibration release gates remain before activation; no device runtime claim.

## 2026-09-16 — Landing release and narrow-browser scroll correction

Initial landing release LIVE at `3789bb36` (PR #295); all four [CI jobs](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/35056911335) green, backend 5953 passed / 1 skipped. Render live 05:02:32 UTC; served HTML/CSS/app/step scripts match, flags 200, actual market bar/platform handoffs verified.

Live 320px embedded-browser smoke exposed duplicate scrollbars. Follow-up scopes root scroll lock to visible auth. Independent review and 195/195 web checks pass. CUA keyboard/layout checks pass all three panels at 320×640, 390×844, 1366×768; narrow trade-panel sign-in bottom y=634.69. Correction CI/deployment pending; see [release record](../docs/business/ops/2026-09-16-landing-page.md). No production sign-in or account mutation.

## 2026-09-15 — Comparison/matching labels (local)

Updated comparison heading and step 03 to operator wording. Web structural and responsive checks passed. Not deployed.

## 2026-09-15 — Equal landing tiles and ranking heading (local)

Equal columns/wrapping labels and YOUR RANKINGS heading. 195/195 web checks, responsive step checks, and actual in-app visual verification passed. Not deployed.

## 2026-09-15 — Production-style market bar and comparison copy (local)

Ported current mobile TradeValueBar’s pick scale and Even geometry into the illustrative offer. Exact tile-02 copy: “We compare your board with leaguemates”. Versioned preview assets to avoid stale CSS. 195 web checks and responsive/keyboard checks pass; actual in-app browser inspected. No deployment.

## 2026-09-15 — Ranking label and market-fairness illustration (local)

Updated actual step 01 tile to operator wording; added separate illustrative market-fairness bar in Real offers. 195/195 web structural checks and keyboard/responsive step checks pass at 1366×768, 390×844, 320×640. No live market evaluation or deployment.

## 2026-09-15 — Landing rookie pick value copy (local)

Added explicit rookie draft pick value tier copy to step 01 and the landing note; expanded tier badge labels. Web structural and existing step/layout checks passed. No deployment.

## 2026-09-14 — Compact option B (local)

Shared app-style illustration replaces tiny storyboard panels. Native step buttons update in place above sign-in on desktop/mobile. 195/195 structural checks, syntax/whitespace, keyboard and layout tests, platform regressions pass. [Scope](../docs/plans/landing-ranking-graphic/scope.md). Not deployed.

## 2026-09-14 — Selected storyboard C (local)

Replaced clickable exploration with connected app-style miniatures using canonical tokens, player rails, tier badges and trade composition. Removed unused step JS/templates. Web 190/190 and diff checks; desktop/mobile visual/sign-in checks; platform regressions passed. [Scope](../docs/plans/landing-ranking-graphic/scope.md). No deployment.

## 2026-09-14 — Illustrated landing steps (local)

Explored three treatments and implemented clickable illustrated tiles with dedicated ranking/overlap/offer visuals. 195/195 web guards, JS syntax, diff checks pass. Browser: keyboard selection, exclusive state, unique heading, desktop layout stability, phone sign-in visibility, and platform regressions pass. [Scope and options](../docs/plans/landing-ranking-graphic/scope.md). Not deployed.

## 2026-09-14 — Landing layout and platform discovery (local revision)

190/190 web guards, JS syntax, diff check passed. Browser: delayed flag reveal (1800ms), ESPN/MFL mobile-verification panels, Sleeper return and flags-off fallback passed. Initial sign-in above fold at 1366×768, 390×844, 320×640. Existing verified-ownership restriction preserved; no real login tested. [Scope and evidence](../docs/plans/landing-ranking-graphic/scope.md).

## 2026-09-14 — Landing ranking graphic (local)

Added two illustrative ranking boards and a mutual-value trade receipt. Web structural checks: **190/190 passed**. Headless Chrome: 1440/390/320px, no document overflow; desktop and phone visual inspection. Static preview stubs API responses; no auth/runtime backend claims. No mobile changes, remote CI, merge, or deployment. [Scope/evidence](../docs/plans/landing-ranking-graphic/scope.md).

# Test Ledger — Fantasy Trade Finder

## 2026-09-23 — Approved chunked prepared inventory qualification, not released

Owner explicitly approved new persistent storage/lease/deletion subsystem after
prior safety hold. Approved implementation uses bounded pages and store-minted
pinned-root semantic attestation; all native terms/proofs/order remain unchanged.
Prepared regression526passed85.57s; codec/legacy153passed14.54s; store+attestation+
retirement59passedSQLite8.25s and isolated Unix-socket PostgreSQL14.54s. Parent
diagnostics/runtime40passed1.45s. No production tests, activity, or deploy.

Actual936 telemetryON full parity: prepare23.79s, first30durable1.081s,
fulladopt22.15s, peakRSS274726912B. Actual13728 telemetryOFF fullparity701.13s:
prepare361.35s, first30durable3.855s, fulladopt338.64s, peakRSS1492434944B,
maxSQLbind999044B. Local backend/SQLite only; not device/prod latency. These
precede fused-index and active-feedback repairs. Initial936 repeated-preflight
17.06s firstcard exposed the bottleneck; initialdense preflight run interrupted.

Named RED/GREEN: seven missing fused callback cases; six typed error marker
cases; exact-root retirement absent; corrupt-prefix kept active; real first
like/pass canceled unrelated suffix; active sweep starved hourly prune. Direct
SQL partner board/outlook changes still revoke. Final independent admission
roster-race correction, speed remeasurement and full/hosted release gates pending.
Production2cff90c7 cacheOFF readback02:03:21UTC; no all-user sweep yet.
[Plan/evidence](../docs/plans/prepared-trade-inventory/validation.md).

> **Purpose:** authoritative record of what's been tested, what shipped, what was measured, and on what version of the stack. Prevents "works on my machine / claimed earlier without evidence" failure modes.
>
> Retention: entries dated within the last 2 months (2026-06-08 onward) plus standing sections live here; older run entries are archived in [`archive/TEST_LEDGER-pre-2026-06.md`](archive/TEST_LEDGER-pre-2026-06.md).
>
> **Read at:** before claiming a result, before proposing a new test that may duplicate a prior one, before shipping a feature.
> **Write at:** immediately after running a test, regardless of outcome.
>
> Companion files: [`MISTAKES.md`](MISTAKES.md), [`DECISIONS.md`](DECISIONS.md), [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) (sample data), [`trade_output.json`](../trade_output.json).

---

## 2026-09-16 — Storage prevention deployment recheck

Read-only verification: `82c5f118` remains LIVE; root/feature-flags HTTP 200;
no retention override (14-day default), zero expired snapshot nodes pending.
No new recommendation rows since September 15 17:00 UTC to sample. Deployed
write path compacts new rows atomically; cleanup thread invokes expiry. No code
change required. Documentation-only publication authorized; diff checks passed.
[Evidence](../docs/plans/db-storage-reduction/release.md).

## 2026-09-15 — Database storage incident / normalized diagnostics

Released PRs #293 and #294; exact latest deployed commit `82c5f118`. All four
exact-head CI jobs and post-merge CI passed. Latest backend: **5,953 passed / 1
skipped** on Python 3.12, 696.88s. Local diagnostics: 10 passed; named sabotage
(disabling normalization) makes the payload-budget regression fail.

Verified private full backup and PostgreSQL restore/rehearsal before production.
All 67,159 records scanned, 45,733 compacted, 73,146 shared nodes. Complete core
hashes and 1,715 outcomes preserved; 100 recent + 100 normalized diagnostic
samples match. Operator SHA-256 guard independently reviewed; local 100-row
roundtrip/rollback, Unicode parity and incorrect-hash rejection passed, then all
100 first production-page records read back exactly.

Bounded production VACUUM FULL succeeded in 111.43s. Whole database allocation
895,088,319→539,281,087 bytes (39.8% smaller); combined recommendation/snapshot
relations 787,722,240→431,964,160 bytes (45.2% smaller). Recovery increased disk
1→5 GB; compute unchanged. Final health and capacity metrics are recorded in
[release evidence](../docs/plans/db-storage-reduction/release.md).


## 2026-09-08 — Feedback batch #422/#423/#424/#425/#426/#427/#428: five groups QA-green on `feat/feedback-2026-09-08`

Release branch = session branch + five group branches merged (one docs-registry conflict, resolved by keeping both rows). PR #292; exact-head CI to be recorded before merge. Pipeline: one investigating planner per group → one build agent → two independent QA agents (round 2 where a confirmed finding existed). Evidence per group in `docs/feedback/items/<id>-*/` (build-report, qa-round-*).

| Group | Build | QA | Full suite (at QA) | Guards |
|---|---|---|---|---|
| G-422 Win Now FFV3 refusal message | `e280ca73` | r1 A PASS / B PASS | 5872 / 1 skip (B); A's lone red was a load flake, file 34/34 alone | n/a (backend) |
| G-423 outlook row + review completion | `4cca4020`, Phase 4 `cb893b09` | r1 A/B PASS (2 convergent minors) → r2 A/B PASS | 5867 / 1 skip (B r1; no backend files) | `check-outlook-row-source.js` 19 assertions, 11 sabotages RED |
| G-425 overhaul hero replaces Draft cell | `9610e5ec`, `d80e9ee9` | r1 A PASS / B PASS (0 findings) | n/a (no backend files) | `check-team-overhaul.js` 29 assertions, 13–14 sabotages RED |
| G-427 first-round picks exempt from stud tax | `9778c2a7` | r1 A PASS / B PASS (0 defects; numbers reproduced independently) | 5912 / 1 skip (both) | n/a; goldens pinned at 0 |
| G-428 Sleeper pick tradability | `26ab3147`, Phase 4 `c4f8a6f7` | r1 A FAIL(adjudicated)/B PASS → r2 A/B PASS | 5892 / 1 skip (both) | `check-send-button-platform.js` check 9 RED with operand removed |

- Release tip `ecc1d8b7` gates: `npx tsc --noEmit` 0 errors; 99/99 `check-*.js`; testid-lint OK; web 190/190; full backend suite **`5942 passed, 1 skipped in 391.47s (0:06:31)`**, exit 0.
- Version bump: mobile 1.17.2 → **1.17.3** (app.json, Info.plist, pbxproj).
- Hosted CI on PR #292 head `8329d975`: all four jobs **success**. Squash-merged as `1371d2e5` (complete tree equality with the tested tip).
- **Render live** for `1371d2e5` at 2026-09-09T00:03:58Z. Production smoke: root 200; flags correct; 0 error lines in 200 log lines; **#427 verified on the live calculator** — two mid firsts `give_value 4234.0` (face, no depth row) vs 4210.2 → `favors: even`, ratio 0.994, while two mid seconds still carry a −225.9 `package_depth` deduction and favor the player. That is runtime evidence, not a code-walk.
- iOS **1.17.3 (155)**, EAS build `c0fe6e0d`, built from merged `main`; TestFlight submission `2742bdd6` **FINISHED** (upload accepted by App Store Connect; Apple processing and tester availability are not proven by that).
- Feedback items 422–428 set `fixed` (open backlog 49 → 42).
- **UNRUN:** consolidated operator checklist [testflight-checklist.md](../docs/feedback/items/422-win-now-ffv3-unavailable/testflight-checklist.md) on the 1.17.3 build — the only runtime evidence the mobile half gets.

## 2026-09-08 — Team overhaul: device-found card-shape bug (blank chips, two crashes) fixed

Operator on build 153: review chips showed no players on either side; "Build roadmaps" and choosing a roadmap crashed the app. One root cause: the server's `Offer.card` is the raw `trade_card_to_dict` dict (`give`/`receive`/`target_user_id`/`fairness_score`/`mismatch_score`) while the screens read the client `TradeCard` shape; the review screen defaulted the arrays to empty, the other screens called `.map` on undefined. Fix (PR #291 → `167f93ff`): `api/overhaul.ts` normalizes every offer through the deck's exported `normalizeTradeCard` at the fetch boundary (all 10 fetchers); render guards in the five overhaul screens; `check-team-overhaul.js` at 26 assertions. Also aligned the `onboarding-v2`/`profiles-on` flag fixtures with the flag flip (main CI had been red from `d59a86d7`).
- Mobile: tsc 0 errors; every `check-*.js`; testid-lint OK. Hosted CI on PR #291 head `64b0ff5f`: run 34197788940 all four jobs success. iOS **1.17.2 (154)**, EAS `5aeed6cc`, uploaded via auto-submit (submission `abf252bd` FINISHED).
- Device retest on 154: **UNRUN** at write time.

## 2026-09-08 — Team overhaul flag flipped ON; production verified

`d59a86d7` sets `overhaul.enabled: true` in `config/features.json` and `backend/tests/fixtures/flags/release.json` (mirror test passed locally before push). Production `/api/feature-flags` returned `overhaul.enabled: True` ~125 s after the push. Hosted CI on `d59a86d7` **failed** on the two profile-fixture tests (fixed in PR #291, above). Builds on App Store Connect from the all-platform tree: 1.17.2 (152) and (153).

## 2026-09-07 — Owner-only outage diagnosis and paged impression insert

**Production evidence (read-only, Render logs API):** web service at 06:13:23 and 06:13:51 UTC ran `roster=owner_v1 … arms={'owner_v1': (1037, 7852)}` and `(1456, 9347)`; both followed by `impression logging failed … SSL SYSCALL error: EOF detected` and `ValueError: owner_impression_unavailable`. Postgres `dpg-d7g36mdckfvc73a329k0-a` (basic_256mb) logged `terminated by signal 9: Killed` + `database system is in recovery mode` at 06:13:31 and 06:14:10. Deploy `dep-daf4ma15efls73aeq5j0` LIVE on `16bb6fd1`.
**Local reproduction (synthetic 12-team, 28 assets/team, default budgets):** 1,351 cards / 45,056 evaluations / 20.7 s; per-row payload `valuation_json` 4,127 B + `owner_generation` 5,066 B + `config` block 8,904 B ≈ 21 KB → ≈28.5 MB for one deck. Under 300 / 3,000 budgets: 251 cards / 0.5 s / ≈5.3 MB.
**Mitigation applied 13:55:22 UTC** via `scripts/set_knob.py` (source `owner-only-oom-mitigation-20260907`): `owner_pair_budget` 4096→300, `owner_total_budget` 60000→3000. **Exercised by three real searches** (Render logs, same league): 15:20:20 UTC 128 cards / 1,457 ms; 18:13:55 UTC 92 cards / 1,216 ms; 2026-09-08 01:35:40 UTC 107 cards / 844 ms — zero `impression logging failed`, zero Postgres `signal 9` in the window. Find a Trade was healthy again from the first mitigated search.
**Fix:** `save_deck_impressions` paged at `DECK_IMPRESSION_INSERT_ROWS` = 100. Focused run `test_deck_impressions_paging.py` + `test_decline_reasons.py` + `test_bakeoff_serving.py` + `test_owner_only_routes.py` + `test_owner_bakeoff.py`: **211 passed in 7.22 s**. Full backend suite on the fix commit: **5,813 passed / 1 skipped in 371.84 s** (local, Python 3.12).
**Ship (2026-09-08):** [PR #289](https://github.com/mattmurf77/fantasy-trade-finder/pull/289) head `9d1a5823`, hosted CI run 34180007795 all four jobs green; squash-merged `609cb79e` (tree `27eafa76` equals the tested head). Render deploy `dep-dafnasjm8hqs73e6tbdg` LIVE at **02:41:08 UTC**. Budgets restored at 02:41:49/50 UTC via `scripts/set_knob.py` (source `owner-only-oom-recovery-20260908`): `owner_pair_budget` 300→4096, `owner_total_budget` 3000→60000. `FTF_SKIP_SIM_GATE=1` on push per D-056 (evidence: this entry). **UNRUN:** a real uncapped Find a Trade on the paged insert — confirm a `bake-off run … roster=owner_v1` line with no `impression logging failed` after it. [Recovery record](../docs/recovery/2026-09-08-owner-only-impression-paging.md). Gates: not express — scope is a one-function reliability fix with no schema/API/flag change; evidence is this ledger + guardrail test; docs updated (runbook, G-072).

## 2026-09-07 — Team overhaul: sends on MFL and ESPN (owner D1 revision), branch evidence

Branch `claude/overhaul-all-platform-sends` from `origin/main` `6f115d1b`. Owner revised D1: "MFL and ESPN trade sending has been validated. It should work for all." Backend: `/api/trades/propose-mfl` and `/api/trades/propose-espn` bodies extracted verbatim into `_mfl_propose_core` / `_espn_propose_core` (routes are thin wrappers; codes/statuses/messages unchanged); overhaul `capabilities.can_propose` per platform behind `trade.send_in_sleeper` / `trade.send_in_mfl` / `espn.send`, `can_propose_picks` false on ESPN with `pick_unsupported_on_platform` blockers, `reconnect_required` when unlinked, fresh MFL/ESPN roster reads for refresh with a `roster_source` guard that never terminalizes attempts from session-stale data; additive `overhaul_attempts.provider_status`. Mobile: platform-aware summary/assets copy; guard `check-team-overhaul.js` now 21 assertions.

- Backend targeted: overhaul + pick-assignment guard **90 passed**; `-k "propose or mfl or espn or sleeper_write or flags_mirror"` **508 passed** (mfl/espn subset 446 before and after the extraction). **Full suite on `5894ae34`: 5863 passed / 1 skipped in 454.49s, exit 0.**
- Hosted CI on PR #290: [run 34178143105](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34178143105) all four jobs **success**. Squash-merged as `8cacc1f2` (tree identical to the branch tip). iOS **1.17.2 (152)**, EAS build `032d7ed2`, FINISHED from the identical tree. **Upload record, corrected:** the classifier-refused submit command never ran, but a shell-quoting slip in a bookkeeping command spawned `eas submit` for 152; the local CLI was killed within a second, yet the server-side job had already been scheduled and **FINISHED** (submission `fa223fc8`, 02:04 UTC) — so 152 IS on App Store Connect. The two later explicit submits (`f2719564`, `09df1cfd`) then failed with Apple's "build number 152 already used". A fresh build with auto-submit, **1.17.2 (153)** EAS `b3267ae7` from the same tree (`8cacc1f2`), uploaded via submission `4be1ea1e` (FINISHED 02:23 UTC). Both 152 and 153 are the all-platform build; test on 153.
- Mobile: `npx tsc --noEmit` 0 errors; every `check-*.js` passes; testid-lint OK. Web 190/190.
- UNRUN: device checklist on a build containing this branch (the next TestFlight upload); `supports_conflicting_offer_race` is `supported` for Sleeper by owner statement, `unverified` for MFL/ESPN.

## 2026-09-07 — Team overhaul v1 build (branch, flag off): full backend suite green

Branch `claude/team-overhaul-scoping-ea1c72` (from `origin/main` `0e3d6b70`), head `d23a3b81` + this write-back. Not merged, not deployed, no EAS build. Scope: [scope.md](../docs/plans/team-overhaul/scope.md), full gates, no express.

- **Backend, full suite** on `d23a3b81`: `python3 -m pytest backend/tests -q` → **5810 passed / 1 skipped in 1238.52s**, exit 0 (local, Python 3.14; CI runs 3.12). Includes the three new files `test_overhaul_service.py` / `test_overhaul_store.py` / `test_overhaul_api.py` (**45 passed**) and the existing `/api/trades/propose` tests, which prove the `_sleeper_propose_core` extraction preserved route behavior (108 propose/send/flags-mirror tests). One sanctioned-name entry in `test_pick_assignment.py` moved with the extraction.
- **Independent backend review** (read-only agent, code-walk + probes) found 1 high (refresh read pick ownership from the stale DB table → false `resolved_elsewhere`), 4 medium (zombie live attempts after a crash, exhausted subsets persisting across settings changes, send not gated on `can_propose`, tie partners double-counted in the D6 union check) and 8 low. All fixed with RED→GREEN regression tests (9 RED → 45 GREEN).
- **Mobile:** `npx tsc --noEmit` 0 errors; every `mobile/tests/check-*.js` passes incl. new `check-team-overhaul.js` (18 assertions, sabotage-proven ×7); `bash mobile/scripts/testid-lint.sh` OK.
- **Web:** `python3 qa/web/check_web_structure.py` → 190/190.
- **Code-walk proof:** pool enforcement `overhaul_service.filter_cards` (post-filter independent of the generator) + prepare-time `pool_violation`/`asset_not_owned` blockers; reservations claimed in one transaction before any provider call (`overhaul_store.claim_reservations`, `overhaul_api.overhaul_send_route`); attempt CAS transitions refuse regressions (`overhaul_store`, `overhaul_service._ATTEMPT_TRANSITIONS`); decisions never touch swipe/Elo (`overhaul_decisions_route` → `store.set_decision` only).
- **Hosted CI on the PR merge ref** (`c190f52a` merged with `origin/main` `16bb6fd1`): [run 34090353672](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34090353672) — backend-tests, mobile-typecheck, web-structure, maestro-testid-lint all **success**. Targeted backend rerun on the merged tree: 81 + 142 passed.
- **iOS build:** EAS production build `2e13ce3d` → **1.17.2 (151)** FINISHED from the merged tree; submission `695bcad3` uploaded to App Store Connect 2026-09-07 (Apple processing pending). Flag `overhaul.enabled` is false in the build.
- **Merged and deployed:** PR #288 squash-merged as `a8ef182e` (tree identical to the branch tip `4203d059`). Hosted CI on `main`: [run 34131511501](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34131511501) all four jobs **success** (docs follow-up `3e45941e` also green). Render deploy verified: production `GET /api/feature-flags` lists `overhaul.enabled: false`. Recovery: [2026-09-07-team-overhaul-release](../docs/recovery/2026-09-07-team-overhaul-release.md).
- **UNRUN:** the 10-item physical-device checklist in [QA.md](../docs/plans/team-overhaul/QA.md) — build 151 now contains this branch; run it there. `supports_conflicting_offer_race` stays `unverified` until step 8 runs against Sleeper.

## 2026-09-06 — Owner-only uncapped discovery, implementation checkpoint

Operator explicitly requests owner generation on, all other generated arms off,
and no returned-offer quotas. Fresh `0e3d6b70` isolated Fleeced-derived source;
the dirty canonical organization and historical checkouts are preserved.
Parent mobile TypeScript, all97 guard scripts, testID lint and web190 passed
on unchanged client/web source; lockfile-pinned isolated install801packages.
Parent core/runner/acceptance **102passed5.52s**, including dense synthetic
12-team stress:45056evaluated/6622emitted4.594s; computationalbudgetsunchanged.
Server focused321passed6.93s. First broad run interrupted after1503pass/1fail
for missing serving-knob inventory registration; no golden drift. Explicit
exclusion added, all12arm-A tests passed; fresh full frozen-source run started.
Final frozen parent fullbackend **5809passed/1skip369.10s**, exit0; final97mobile
guards passed again. Independent253passed8.73s plus173consumer retention probe,
both original real-worker races RED/GREEN, and actual selected routes0.03–1.54s.
Parent approved complete diff and bounded performance evidence. Hosted CI,
merge/deployment and activation are still separate gates. Production
GET-only preflight at2026-09-07 01:23UTC still shows owner include1/serve0,
deck60/group0 and prior controls; no activation is established here. Scope
distinguishes uncapped output from unchanged computational search budgets.
[Scope and evidence](../docs/plans/owner-only-uncapped/verification.md).

Local release commit824884ff prepared; public GitHub push rejected before
execution by publication safeguard. No retry via another route, PR, deployment
or activation. Destination-specific disclosure approval requested; source and
all local evidence retained. On September 7, following public destination and
shadow-status disclosure, owner explicitly requested “Push it live.” Fresh main
fetch remains0e3d6b70 and GET-only05:06UTC preflight is healthy; source unchanged.
Publication now authorized; exact-head hosted CI/deployment/activation remain
pending. [Release gate](../docs/plans/owner-only-uncapped/release.md).

Release-day independent focused rerun2026-09-07 05:07:20UTC: five owner suites,
**164passed49.37s**, no failures/skips, unchanged824884ff runtime. Fresh isolated
SQLite and pinned local DP fixtures; hot-off/ghost/cache/64-card coverage passes.
Dense synthetic generation28.55s under high host load, no production SLA claim.


## 2026-09-06 — Owner construction challenger, implementation checkpoints

New isolated `codex/owner-engine-challenger-20260906` from `4c343a48` introduces
an actual separate `owner_v1` constructor and selected-route attribution;
existing control goldens/profiles are retained. Owner clarification is joint
personal rankings + outlook + needs before market-priced terms. This is **not
a deployment or activation**. Parent and Astra Ultra builders/reviewer are
validating final integration. Checkpoints: parent 102 control/runner tests and
74 core/acceptance/runner tests passed; web190 and all97 mobile guard scripts
passed at the pre-final-canvas checkpoint. Broad backend **5734 passed / 1 skip /
9 failed (644.46s)**, not green: concurrent source edits invalidated eight
inspect-based function slices; one new pick-reader inventory requires an
explicit sanctioned-site update. Fresh frozen-source full rerun is required.
No production credentials/data used. Final frozen backend rerun: **5754 passed /
1 skipped in420.01s**, exit0; parent focused rerun235passed, builder matrix369passed.
Independent final mobile review caught original-impression credit on an edited
classic-deck action; actual-function RED/GREEN repair and independent re-review
now pass. Final parent TypeScript/all97guards/testID, web190 and native1.17.2
plist/project checks pass (offer signals26, trial order13). Parent final diff
review is complete. Nothing pushed, deployed or activated at this local
checkpoint. [Exact evidence and remaining gates](../docs/plans/owner-engine-challenger/verification.md).

Published13b94161 passed all four [hosted CI jobs](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34058864206),
backend5754passed/1skip708.27s. A final rollout review then found a hot-flip
race between captured worker permission and the runner's later global read,
plus the same-state cache signature seam. Eight new runner cases RED then
21runner checks GREEN; worker forwarding test RED before repair. This makes
13b94161 a superseded checkpoint, not release approval. No merge/build/activation
occurred; repaired-source full checks and CI remain required.
Final bounded rollout repair: builder192checks passed6.55s, independent120
passed2.80s, parentrunner21passed andweb190green. Worker forwarding,
captured-shadow cache and demo compatibility all have RED/GREEN proofs; parent
approved the final diff. Fresh full backend and mobile checks running on frozen
source; no production write or release yet.

## 2026-09-06 — Feedback release CI, merge and delivery

Final head `d97459dc9f72ebe158f70fcbb86f29051659c206` passed [CI run 34047364058](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34047364058): **5,645 backend passed / 1 skipped in 717.99 s**, TypeScript/all 95 mobile guards, testID lint and 190 web checks. [PR #283](https://github.com/mattmurf77/fantasy-trade-finder/pull/283) merged **17:16:56 UTC** as `988fa2d690dfa9188f43c33e87dff9d60a5fabaa`; root fetched and verified complete tree equality with the exact CI head. D-056 standing `FTF_SKIP_SIM_GATE=1` used; no simulator or physical-device claim. Destination-specific public publication approval was explicitly supplied by the owner.

Render did not create an automatic deploy because the squash body inherited old documentation skip markers. With no duplicate/in-progress deploy, exact-SHA API dispatch returned HTTP201 at **17:20:04 UTC**, `dep-daeq1h740ujc73897oog`, **LIVE 17:21:19.905609 UTC**. No environment/autodeploy change. The only authorized config mutation was `simple_player_presentment` **0→1**, CLI timestamp **17:23:58.015131 UTC**. GET-only readback at **17:24:18 UTC**, independently repeated **17:33:55 UTC**, verified exact live source, 207 flags/258 prior settings unchanged, stable tiers/experiments, expected 200/401 responses and healthy ingest. [Sanitized smoke](../docs/feedback/items/419-rejected-interest-resurfacing/production-smoke.json).

Final archive independently verified by root and QA-A: **2,684 files / 631 mobile byte-identical**, exact one-commit history and no private artifact additions. EAS **1.17.1 (149)** build `87f9ce05-f91f-4bbd-8c1a-bc7c49932e2d` finished **17:25:01.357 UTC** from clean CI head. Initial optional changelog scheduling was plan-restricted; history verified no submission before retrying without that optional field. Exact-build submission `a07afa27-7b21-47d8-9fb9-8e17518232b6` verified **FINISHED/error:null** independently **17:34:02 UTC**, repeated by root **17:40:08 UTC**. Only 419–421 transitioned to `fixed` and were read back at 17:41–17:42 UTC. Apple availability and 23 physical-device steps remain unverified/UNRUN. [Release record](../docs/feedback/items/419-rejected-interest-resurfacing/release.md).

## 2026-09-06 — Feedback 419–421 implementation checkpoints, not release evidence

**Publication blocked, not shipped:** clean prepared head `e5294748477ece417ea5e10d4f20ba7b1b148c31` retained exact reviewed runtime/test/config and whole-range diff hygiene. Safety review rejected the combined fetch/push/PR command before process creation because it requires explicit owner authorization for the named public GitHub destination. The command did not run; no remote write or later deployment/activation/upload occurred, and no bypass was attempted. Root confirmed configured origin read-only and requested destination-specific approval. [Blocker and release gates](../docs/feedback/items/419-rejected-interest-resurfacing/release.md).

**Final local QA checkpoint:** both fresh independent Astra Ultra round-2 reviewers PASS exact `7d3e071f92bac3a087ba63da393109b5eae02f68`, runtime `3edf4257`; root read both complete reports and found no unresolved application/wrong-test finding. [A](../docs/feedback/items/419-rejected-interest-resurfacing/qa-round-2-agent-A.md) full **5,645 / 1 skip in 709.94 s**, focused **892 in 58.84 s**; [B](../docs/feedback/items/419-rejected-interest-resurfacing/qa-round-2-agent-B.md) full **5,645 / 1 skip in 710.20 s**, focused **892 in 58.37 s**, separate **23 episode cases**. Both independently pass all 95 mobile guards, TypeScript/testID, 190 web checks and original F-1 repro, and reproduce the four/seven meaningful unchanged-baseline RED controls. Original failed round and environment diagnostics remain below. Root corrected their sole documentation EOF nit and verified no runtime/test/config delta after the frozen source. Both reports' physical supplements are consolidated into **23 UNRUN steps**. Root public-browser smoke renders the unchanged landing with zero captured warning/error logs; no login, trade generation or user data mutation. Hosted exact-head CI and actual release remain separate gates.

Selected scope only: [batch plan](../docs/feedback/items/419-rejected-interest-resurfacing/plan.md). Fresh main remained `4026ebc8` at 05:12 UTC. Owner explicitly preauthorized this batch's reviewed merge/live/TestFlight delivery; no express-lane or physical-QA waiver. All 45 open reports were audited read-only; no unrelated status closure. The three selected records are now in progress. Current code checkpoints below are **not the final integrated QA round**.

Resumed 15:09 UTC: freshly fetched main remains `4026ebc8`. Root reviewed the complete #419 backend, including the final specific-source/restoration increment `e02d074ed37b1ba81cbe4f53cbf90378c49f38de`, then independently ran its exact 18-file focused command in the clean isolated QA checkout: **401 passed in 7.57 s**, with both provider fixtures pinned as below. Backend merged locally as `741710c1`; dependent mobile and approved smaller-package builds started from that reviewed base. This is a backend build gate, not final batch QA or a deployment. [Exact files, REDs and code walk](../docs/feedback/items/419-rejected-interest-resurfacing/build-evidence.md). Mobile dependencies separately installed in the new #419 worktree: 801 packages, unchanged lockfile.

Root full backend integration checkpoint on the same reviewed #419 runtime (`741710c1`, later root commits only documents): `DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 /private/tmp/ftf-context-venv/bin/python -m pytest backend/tests -q -p no:cacheprovider --tb=short` → **5,528 passed / 1 skipped in 346.27 s**. This uses the repository's normal full-suite provider-fixture posture, not the focused player-curve override. Background receipt test workers logged missing-table diagnostics in isolated SQLite while the suite remained green; this is not a production health claim. Win Now/mobile/package integration and redundant final QA are still pending.

Root finishing review found and required a regression for a current 401 being hidden as stale after its own token clear. Corrected runtime `2de3e1d9`, evidence `ff205431`: root independently ran **38/38 recovery cases**, TypeScript, testID lint and **128 backend tests in 3.56 s** (`test_verified_sessions`, `test_persistent_sessions`, `test_win_now_api`, `test_win_now_service`) in a separate clean checkout with the focused provider pins below. Reviewed group merged locally. On package runtime `0bafa3a5`, root independently ran **214 passed in 8.08 s** across new presentation, arm-A golden, bakeoff serving, disposition replay, policy wiring, replenishment and session-init Sleeper-call suites. Mobile `396d92fc`: root read the complete runtime/guard diff and independently ran **28/28 disposition cases**; final combined tests are separate. Fresh main remains `4026ebc8`; EAS readback still shows existing **1.17.0 (148)**. No new release is claimed.

Final build integration at `71b2b496`: root reviewed the literal raw-receive exclusion and independently repeated the seven package suites on `9ea562dd` → **224 passed in 8.44 s**. Root reran all **95 mobile guards**, TypeScript and testID lint on the combined runtime → **97/97 commands passed**; web structure **190/190 passed**. Full backend and two independent QA reviews remain separate gates. The root-executed anonymous diagnostic reproduces both 14→12 first-three loads with unchanged first-six totals and slot vectors; historical missing eligibility metadata prevents a runtime-counterfactual claim. Read-only production preflight at 15:53 UTC verifies unchanged 207 flags/258 config values and historical tier/experiment hashes, source `4026ebc8`; the new knob is absent. No activation or new build has occurred.

Root **full final-runtime backend** run at `71b2b496` (QA input `aa463789` differs only in documentation): **5,622 passed / 1 skipped in 363.54 s**, exit 0. Same normal full-suite command/posture as the earlier 5,528-test checkpoint. The pre-existing isolated receipt-worker diagnostics recur; no production process or data was used. Two fresh independent Astra Ultra QA reviewers now inspect/test exact `aa463789` in separate clean checkouts. Their verdicts, exact-head CI and deployment gates are not yet complete.

At 16:07 UTC root independently reproduced QA-A's R3/T4 finding on unchanged `aa463789` runtime: a prior exact same-ID pass from August 1 was accepted as proof for a fresh reason episode after the partner's September 5 renewal. The real route returned `passed:true` without a new decision/outcome, and the renewed like remained actionable. The synthetic in-memory reproduction exited 1 on the expected new-pass count; no source was disabled. QA-B independently identified the same code path. This invalidates release readiness despite the passing broad suite. The backend owner is repairing episode binding; a fresh complete two-agent QA round is required afterward.

Archive-only preflight of clean detached `aa463789` completed: **2,677 files**, including **631/631 tracked mobile files byte-identical**. The only untracked archive paths are EAS's one-commit shallow Git metadata; its sole retained commit is `aa463789`. No credential/env files, raw interview documents, dependency trees or local databases were found. Effective Expo config verifies **1.17.1**, production API, `testMode:false`, existing bundle/project/owner identity. This inspection uploaded nothing and does not approve the source with the unresolved QA defect. Final-source archive verification is still required before an actual EAS build.

Round 1 reports preserved: [QA-A](../docs/feedback/items/419-rejected-interest-resurfacing/qa-round-1-agent-A.md), [QA-B](../docs/feedback/items/419-rejected-interest-resurfacing/qa-round-1-agent-B.md). Both confirmed F-1; both independently ran all 95 mobile guards, TypeScript/testID, 190 web checks and 869 focused backend cases. QA-A full in-memory run passed **5,622 / 1 skip in 455.32 s**. QA-B's first full in-memory run had **5 failures / 28 errors** from lost startup schema, preserved in its report. Unchanged fresh-file affected tests passed **149 in 223.72 s**, then full fresh-file regression passed **5,622 / 1 skip in 367.26 s**. SingletonThreadPool eviction is the supported isolation explanation, not an instrumented eviction trace. No test/source expectations were changed to hide failures.

Root reviewed all runtime/test/document changes in repair **`8f27421d`**, merged as **`3edf4257`**, and independently reran the original QA-A script on the integrated source at 16:25 UTC: **exit 0**, actual new pass after renewal, source inactive, one outcome, same-episode retry idempotent. Root's exact 18-file focused gate then passed **424 tests in 8.24 s**, using the same two focused provider pins as above. This includes 23 new episode cases. The broad runtime is frozen for a **fresh full round 2**; no release, activation or physical-device pass is yet claimed.

Root exact round-2 source **`7d3e071f92bac3a087ba63da393109b5eae02f68`**, runtime unchanged from `3edf4257`: full backend **5,645 passed / 1 skipped in 621.72 s**, exit 0. Command: `DATABASE_URL=sqlite:////private/tmp/ftf-feedback-419-421-f1uMyt/root-round2-full.sqlite PYTHONDONTWRITEBYTECODE=1 /private/tmp/ftf-context-venv/bin/python -m pytest backend/tests -q -p no:cacheprovider --tb=short -ra`, after asserting that the scratch DB did not exist. Normal full-suite provider posture, no global curve pin or test edits. Skip: `backend/tests/test_outlook_odds.py:610`, optional offline backtest requiring `FTF_OUTLOOK_BACKTEST` captured 2025 data. Root separately passed all **95 mobile guards + TypeScript + testID lint (97 commands)** and **190 web checks** on this frozen source. Two independent round-2 verdicts remain separate gates.

Repaired-source archive inspection at `7d3e071f`: **2,682 files**, **631/631 tracked mobile files byte-identical**, no unexpected source paths other than EAS's one-commit shallow Git metadata, no credential/env/raw interview/dependency/local-DB artifacts. Git archive HEAD is exactly `7d3e071f`. Read-only release access at 16:33 UTC confirms repository push/admin permission and no version conflict: latest EAS build remains **1.17.0 (148)**; 1.17.1 is unsubmitted. Root GET-only production smoke at **16:41:10 UTC** again verifies old source `4026ebc8` LIVE, all 207 flags/258 existing config values/tier/experiment hashes unchanged, new knob absent, healthy event index and zero ingest transaction failures, public/operator 200 and anonymous trade/admin 401. No production mutation or upload.

- Parent baseline on unchanged `4026ebc8` runtime: Python **3.12.14**, `DATABASE_URL=sqlite:///:memory:`, `PYTHONDONTWRITEBYTECODE=1`, `pytest -q -p no:cacheprovider` across `test_trade_match_flow`, `test_pass_cooldown`, `test_decline_reasons`, `test_awaiting_dismiss`, `test_deck_fatigue`, `test_trade_decision_idempotency`, `test_swipe_reconstruct`, `test_bakeoff_serving`, `test_bakeoff_arm_a_golden`, `test_calc_trade_queue`, `test_deck_replenishment`, `test_win_now_api`: **310 passed in 21.20 s**.
- Parent independent isolated checkpoint at **`b396b645676b5f69d896373e6fd61655adcb0cab`**, same interpreter/env/pytest options: `backend/tests/test_trade_interest_disposition.py`, `test_trade_match_flow.py`, `test_calc_trade_queue.py`, `test_decline_reasons.py`, `test_pass_cooldown.py`, `test_trade_decision_idempotency.py`, `test_awaiting_dismiss.py`, `test_league_summary_buckets.py`: **212 passed in 4.89 s**. Source-interest/queue and durable reason handling were committed; cache/restoration/mobile work was still in progress. Root review separately identified a mixed-player/pick Awaiting compatibility gap for correction, so passing this checkpoint is not acceptance of the complete patch.
- Research validation: fresh public Sleeper sweep **57/57 successful legs**, three verified current leagues, **28 completed trades** exactly matching stored transaction IDs. Parent independently recomputed distribution sums, weighted player means and large-side counts for **24 original aggregate summaries and 32 detailed summaries**; all reconcile, no unknown impression assets. [Sanitized research and limitations](../docs/research/2026-09-06-trade-package-shapes.md). No causal acceptance-rate claim, real-user trade generation or provider trade write.
- Locked local mobile dependencies installed independently with `npm ci --ignore-scripts --no-audit --no-fund` in implementation/integration and both isolated QA checkouts; **801 packages** each, no symlinked dependencies or lockfile edits. Node **24.14.1**; hosted Node 20 is a separate future gate. Latest existing EAS build read back at 05:14 UTC remains **1.17.0 (148), FINISHED**; this is not a new batch build or tester-availability proof.

The parent repeated the same eight-suite `b396b645` checkpoint with both import-time provider inputs explicitly pinned: `FTF_DP_VALUES_FILE` to that checkout's `backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv` and `FTF_DP_PICK_VALUES_FILE` to `backend/tests/fixtures/dp_values_picks_2026-08-06.csv`: **212 passed in 5.12 s**. The earlier invocation did not explicitly pin the player curve and is not claimed to have prevented startup fetch attempts. These are per-command targeted fixtures, not a global conftest or historical golden change; full-suite/CI evidence remains separate.

RED proof is recorded in item-local build evidence: use the actual unchanged original runtime, with module identity and hermetic fixtures verified. An automatic safety review blocked a temporary queue-defect mutation; no mutation landed or was retried. Unchanged-baseline behavioral failures are the safe alternative, not a claim that every proposed fault-injection test ran. No simulator/Maestro, new deployment, CI run or physical-device pass is claimed at this checkpoint.

---

## 2026-09-05 — Experimental personal-market policy activation verified

Owner explicitly said “I want the experimental policy on.” Independent Astra read-only review found no code/migration blocker and reviewed the single-variable update, exact-source deployment, stale-client/fail-closed boundaries and rollback. Fresh `/private/tmp/ftf-context-venv/bin/python -m pytest backend/tests/test_trade_policy.py backend/tests/test_trade_policy_wiring.py backend/tests/test_owner_policy_contracts.py backend/tests/test_trade_card_privacy.py -q --tb=short` — **114 passed in 3.68 s**. Full source CI remains the 5,455-pass / one-skip record below; no runtime code changed.

Updated only `trade.personal_market_policy_v1` to true within the complete existing Render `FTF_FLAGS` value at **15:59:45.097 UTC**; exact readback preserved every other override. Redeployed commit `4026ebc81eaae50b345b42421641125c5b8d413e` as `dep-dae3oseq1p3s73fs3m50`, **live since 16:01:20.163757 UTC**. At 16:03:54 UTC, verified exactly one delta among 207 effective flags, all 258 model values/tier definitions/experiment summary hashes unchanged from immediate preflight, reviewed root bytes unchanged, public/operator smoke 200 and unauthenticated trade/admin reads 401. Event-ID index present; zero ingest transaction failures. First verification script incorrectly expected JSON from the valid HTML admin 401 response; corrected read-only parsing and reran successfully, with no second mutation or deployment. [Sanitized smoke](../docs/plans/owner-contracts/policy-activation-smoke.json), [scope/rollback](../docs/plans/owner-contracts/policy-activation.md).

All three generator arms remain, but shared eligibility/ordering changes generated-deck output globally; this is not a randomized policy-control experiment or all-entry-point parity. No personalized production trade, real-user session, latency/acceptance/snapshot graduation, new EAS build or physical-device QA is claimed. Valuation telemetry/roster evaluation remain on, roster protection/mutual-benefit enforcement remain off. Checked-in dark defaults remain unchanged.

---

## 2026-09-05 — Owner-contract backend activation verified

Owner said “Turn it on” after being told backend was undeployed. Final head `f88afabb669aa946de65a3a4a20d8b85b9256724` passed [all four CI jobs](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33951522857): **5,455 passed / 1 skipped in 624.31 s**, TypeScript/all 93 guards, test-ID lint and 190 web checks. PR #281 merged 09:50:55 UTC as `4026ebc81eaae50b345b42421641125c5b8d413e`; fetched squash tree exactly equals tested head. Build 148's runtime source remains identical.

Render `dep-daduc0bm8hqs73ckbifg` reports that exact commit **live since 09:51:59.126135 UTC**. Before/after read-only comparison preserves hashes for **207 flags, 258 model values, tier definitions and experiment summaries**. Root HTML matches reviewed bytes; root/tier-config/flags and aggregate operator health/config/experiments return 200, unauthenticated trade/admin-config reads return 401. PostgreSQL event index present, zero ingest transaction failures. No real-user session or personalized production trade used. [Smoke artifact](../docs/plans/owner-contracts/production-smoke.json), [release and rollback](../docs/plans/owner-contracts/release.md).

Live valuation telemetry and roster evaluation were already on and remain on; personal-market policy and roster protection remain off. No flag/config edits, destructive migration, branch/worktree cleanup or new EAS build. Manual TestFlight remains unrun. Documentation-only evidence follow-up has no runtime changes; preserve `[skip render]` during its PR merge and verify that no new service restart follows.

---

## 2026-09-05 — Owner-contract GitHub and TestFlight release verified

Owner explicitly authorized public GitHub publication and TestFlight distribution, resolving the earlier publication block. [Draft PR #281](https://github.com/mattmurf77/fantasy-trade-finder/pull/281); exact built source `0fc1b5390894f3a4e5c9ed8c1c480efd562a09e2`. [Hosted CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33950667865): **5,455 passed / 1 skipped in 621.36 s**, all four jobs successful; mobile TypeScript/all 93 guards, test-ID lint and 190 web checks passed. Release evidence updates after this source are documentation only, not changes to the tested/built runtime tree.

EAS archive inspected before upload: clean detached worktree, **2,610 files**, **627/627 tracked mobile files byte-identical**, no raw source docs, credentials, node_modules or local DBs; retained Git history also excludes raw docs. Effective production API, test mode false, bundle/project/owner verified. EAS **1.17.0 (148)** build `3f0a5ae0-596d-4094-9e4b-539a395116ad` FINISHED at 06:53:20.750 UTC. After exact-source CI gate, submission `7cfac797-9707-457b-8243-c77c8fc9f660` successfully uploaded to App Store Connect and entered Apple processing. Apple tester availability and physical-device QA are not verified. No main merge, Render deploy, flag change, production DB action or simulator/Maestro. [Release record and remaining gates](../docs/plans/owner-contracts/release.md).

---

## 2026-09-05 — Owner-contract implementation, final local integration

Final integrated sources, including the privacy follow-up, passed before publication on isolated branch `codex/owner-contracts-20260905`, baseline `5cf34182`. Parent reviewed all lane diffs and independent Astra findings; no flags, profiles, historical control fixtures or production rows changed.

**Historical pre-authorization checkpoint:** implementation commit `86128700`. Publication safety review rejected the initial push/PR command before execution because explicit approval was required for the public GitHub destination. This block was later resolved by explicit owner authorization, not a workaround; final publication/CI evidence is above. Local history verification confirmed the five raw interview/source documents are preserved on disk but absent from new commit history; protected config/fixture/lockfile/secret paths are unchanged.

- `/private/tmp/ftf-context-venv/bin/python -m pytest backend/tests -q --tb=short` — **5,455 passed / 1 skipped in 566.99 s**, exit 0, Python **3.12.14**. The earlier 5,450-test run predates the privacy patch and is superseded by this result.
- The same interpreter with `-m pytest backend/tests/test_owner_policy_contracts.py backend/tests/test_owner_ranking_provenance.py backend/tests/test_trade_card_privacy.py backend/tests/test_trade_feedback_tier_bounds.py -q` — **102 passed in 19.49 s**. Serializer/API tests verify counterparty exact-value fields are omitted without mutating internal cards.
- From `mobile/`: every `tests/check-*.js` executed with Node — **93/93 passed**; `./node_modules/.bin/tsc --noEmit` and `bash scripts/testid-lint.sh` passed. Local Node **24.14.1**; CI's Node 20 remains a separate gate. Local isolated dependency installation used `npm ci --ignore-scripts --no-audit --no-fund`; this is not native-build evidence.
- `/private/tmp/ftf-context-venv/bin/python qa/web/check_web_structure.py` — **190/190 passed**. `git diff --cached --check` passed.
- No simulator/Maestro (D-056), physical TestFlight, production DB action, merge, deployment or flag activation. [Manual device checklist](../docs/plans/owner-contracts/mobile-testflight.md) is **unrun**. Hosted exact-head CI is pending publication. Raw owner interview/source files remain local and are excluded from the public branch history.

### Initial parent and independent review

Baseline `5cf34182`, isolated worktrees under `/private/tmp/ftf-owner-contracts-e8bWFV`; unrelated owner checkout untouched. Python `/private/tmp/ftf-context-venv/bin/python` **3.12.14**. New feedback regression ran RED **70 failed / 2 passed**, then feedback + pin-bounds + Elo golden/memo + trade-decision idempotency **141 passed**. Independent Astra review found public rounding could cross a tier; corrected precision-aligned bounds and widened unranked ceiling. Updated owner-feedback suite **76 passed**; reviewer separately ran **119 passed** and a **320-case boundary sweep with zero public tier changes**. Per-entry provenance tests initially **3 failed** on the missing policy helper signature (integration dependency, not claimed green).

Review found Browse All's local Undo does not reverse committed feedback; retained-row replay tests do not prove causal Undo. This is explicitly unfinished. Global live shrinkage removal failed the historical arm-A golden; those owned changes were reverted, no golden recaptured. Policy lane reports **412 passed** across 14 files with all three generators and historical arm-A unchanged. Final integrated results are recorded above. [Scope](../docs/plans/owner-contracts/scope.md), [review and remaining work](../docs/plans/owner-contracts/review.md).

---

## 2026-09-05 — Win Now release verified on final CI and production

PR [#280](https://github.com/mattmurf77/fantasy-trade-finder/pull/280): final head `abb1af118d3fe39f32292e99cecc64cebff1d2f3`, squash `c28ec6d802463e048d59a97967e9bb5bb9fdc6f9`; committed trees compare equal after fetch. [Final CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33945722395): **5,353 passed / 1 skipped in 732.08s**, Python 3.12, all four checks success. Parent merged integration: **220 passed in 15.25s**; TypeScript/all 92 client guards/testID, 190 web structure, 23 auth checks and isolated Chromium/MV3 runtime passed.

Render `dep-dadq6k97lnhs73e8o970` **live** on `c28ec6d8` since 05:07:28.48285 UTC. Root/flags 200; all three Win Now flags true; deployed `app.js`, `win-now.js`, `win-now.css` match release bytes; projections/job/search/evaluate deny unauthenticated access with 401. Live IAB landing rendered with no captured warn/error messages. [Public smoke](../docs/plans/win-now/production-smoke.json).

iOS **1.17.0 (147)** EAS `69b53400-1d8d-42ec-ad7a-5d0e3c756059` finished; build commit `77824c02` has identical runtime code to final head. Submission `6184a831-a685-497b-8e97-734ed30fa4b9` uploaded successfully; Apple's processing/tester availability is unverified. Superseded build 146 canceled. No native simulator/Maestro, physical iPhone or authenticated production forecast success claimed. Real Lakeview source smoke returned `unknown_starter_availability:1:1`; estimates remain experimental. [Release record](../docs/business/ops/2026-09-05-win-now.md).

---

## 2026-09-05 — Authorized Win Now beta release checks

**Concurrent release integration:** main `a927e3a7` (#279) merged before shipping. Parent reviewed Astra resolutions, alias-aware Win Now export/delete and worker lifecycle leases. Python 3.12 focused Win Now/deletion group **137 passed** plus main account/lifecycle group **45 passed** (182 total). TypeScript, all **92** mobile guards, testID lint, **23** browser/extension auth checks, **190/190** web structure, native plist parsing and isolated Chromium/MV3 runtime passed. Previous iOS 1.17.0 build 146 canceled before submission; replacement and CI on merged head pending. D-056 standing `FTF_SKIP_SIM_GATE=1` used for push; no native simulator or physical TestFlight claimed.


Security release #279 landed concurrently on main `a927e3a7` and is now being integrated. Initial CI for `ee4f37a8` is superseded and is not validation of the merged revision. Mobile 1.17.0 build **146** is superseded; cancellation was confirmed for EAS build `c8104c6e-ed72-42e6-86e4-7ccc78002c85`. A replacement build is pending after integration. Final merged-revision CI, Render and EAS/TestFlight verification remain pending; no new passing result is claimed.

User accepted exploratory evidence and authorized shipping season, Win Now and championship beta; calibration is not claimed. Parent reviewed Astra scoring normalization/explicit rare-event omissions, canonical freshness fix, both client receipts and rolling-deploy job fences. Latest production main `0a8093fe` merged cleanly in code; docs resolved preserving both features.

- Client release run: **93 commands passed** — TypeScript, all 91 `check-*.js` suites and testID lint. Win Now suite: **28 checks**. Web structural: **185/185**. No Maestro/native simulator (D-056).
- Astra Python 3.12 reports: scoring/freshness **122 passed**, then deployment lifecycle **106 passed**. Parent final focused run: **144 passed in 1.95s** on Python 3.12.14. Full suite and hosted exact-head CI are in progress; [release record](../docs/business/ops/2026-09-05-win-now.md) records final outcomes.
- Public real-source smoke: Lakeview 2026 loaded through production service code into a temporary local DB, 34 reads / 27.66 seconds, refused `unknown_starter_availability:1:1`. This verifies explicit source refusal, not forecast availability or authenticated production flow.
- Render target and prior live commit `0a8093fe` verified; CRON_SECRET and DATABASE_URL are set. Mobile version 1.17.0 staged for new EAS build. Production activation, hosted CI, binary submission/processing and physical TestFlight are not claimed by these local checks.

---

## 2026-09-05 — Security release verified in CI, Render and EAS

PR #279: tested `ab8f54d0`, squash `a927e3a7`, content diff empty. [CI run](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33944570236): **5,001 passed / 1 skipped in 589.55 s**, all four jobs complete/success (Python 3.12; full mobile typecheck + 91 guards; testID lint; 180 web checks). Integrated PostgreSQL: **57 passed in 10.99 s** including incoming proposal/shadow deletion/export and counterparty valuation scrubbing. Disposable cluster stopped.

Render `dep-dadppq17lnhs73e8fqo0` is **live**, commit `a927e3a7`, since 04:40:05 UTC. Five served files matched release bytes; feature flags 200; invalid-session init, extension rankings and account export each 401. iOS **1.16.16 (145)** build `bab54ee5` and submission `815cb2a0` both **FINISHED**; extension **0.1.1** uploaded with matching package digest. This is build/upload and service verification, not physical-device QA or proof of Apple's tester availability. No historical production cleanup was run. [Detailed evidence](../docs/plans/security-data-hardening/deployment.md).

## 2026-09-05 — Security follow-up independently reviewed: Python 3.12 and PostgreSQL pass; native runtime pending

Same isolated branch, `codex/security-data-hardening-20260904`, based on `606e512c`. Coordinating review fixed late mobile init/link/proof responses after session changes or unmount; browser recovery now uses an explicit trusted extension proof flow; deletion drains active work and invalidates queued jobs, delayed provider proofs and nested counterparty writes. Export v2 and feedback-note scrubbing close the documented data-scope gaps. [Combined review](../docs/plans/security-data-hardening/review.md), [D-183 / ADR-017](../docs/adr/adr-017-account-deletion-work-leases.md).

- **Full backend, final implementation:** Python **3.12.14**, **4,707 passed / 1 skipped in 679.14 s**, exit 0. Includes calibration tests, scratch SQLite and blocked urllib upstream calls. Production config is 3.12.3; same minor version, different patch. Final log: `/private/tmp/ftf-py312-release-final.log`.
- **Actual PostgreSQL 18.3:** **54 passed in 17.49 s**. Disposable schemas on a local socket; covers deletion/restore/queued-work races, aliases/export, maintenance dry-run/apply/idempotence/rollback, owner/cap checks and simultaneous ingest conflicts. Log: `/private/tmp/ftf-postgres-release-final.log`.
- **Mobile final sources:** **91/91** guards, full TypeScript and testID lint pass; iOS Hermes JavaScript export succeeds. Deferred-response regressions were RED before their fixes and GREEN afterward. This is not native runtime proof. [Evidence and physical-device checklist](../docs/plans/security-data-hardening/mobile-evidence.md).
- **Web/extension:** 23 isolated auth checks, **180/180** web structural checks, and actual MV3-loaded Chromium runtime pass with synthetic upstreams, disposable profile and no live credentials. Wrong-account denial, verified success, secret isolation, revocation recovery, unsupported platform fallback and popup cache clearing are exercised. Narrow viewport screenshot inspected. [Browser evidence](../docs/plans/security-data-hardening/browser-evidence.md).
- **Negative control:** disabling lifecycle invalidation only in memory makes all three targeted stale-work/deletion tests fail at the expected assertions (queued work ran; late auth/provider proof did not reject). No sabotage remains. Log: `/private/tmp/ftf-lifecycle-sabotage.log`.
- No physical iPhone found. No native build distribution, production cleanup, commit, push or deploy. Web Sleeper requires the updated extension; browser ESPN/MFL verification uses mobile. Single-worker deletion and retained public/counterparty data limits remain explicit. [Reproduction harnesses](../docs/plans/security-data-hardening/validation-tools/README.md).

## 2026-09-04 — Operator-approved revised-input evaluation completed

- User accepted available historical data for now and asked to run evaluator. Added explicit exploratory mode; strict default and production behavior unchanged.
- **144 passed in 0.62s:** historical diagnostic, calibration, history, forecasts and simulator suites. Parent reviewed Astra evaluator changes and replay adapter; regression guards cover opt-in isolation, modern timestamp honesty, prefix-only standings, custom zero and median scoring, and current player metadata isolation.
- Actual run: 28 Sleeper weekly responses cached; Lakeview 2024 scored at completed weeks 3/6/9/12 with 10,000 draws each. Final-win MAE 2.60/1.81/1.21/0.76 (median wins included); title Brier 0.0535/0.0428/0.0327/0.0288 versus equal odds 0.0764. One league-season/one champion, not four independent championship events. No confidence interval or calibration claim.
- Lakeview 2025 excluded for missing source-covered lineup at roster 12 / week 13; four FFv3 seasons excluded for K/IDP slots. No projections fabricated. Offline scoring coefficients and past-starter requirement adjustments explicitly logged.
- Cached rerun and direct evaluator CLI metric groups match exactly; strict CLI control rejects all four revised-input cohorts. [Results, artifacts and commands](../docs/plans/win-now/EXPLORATORY-RESULTS.md). No production/flag/UI changes.

---

## 2026-09-04 — Historical Sleeper outcome collection and calibration readiness

Continuation on `codex/win-now-20260904`, after `ad3c5346`, no release. [Scope](../docs/plans/win-now/historical-validation-scope.md) and [evidence/code walk](../docs/plans/win-now/HISTORICAL-VALIDATION.md).

- Parent final affected run: `python3 -m pytest backend/tests/test_season_history.py backend/tests/test_season_calibration.py backend/tests/test_season_forecasts.py backend/tests/test_season_simulator.py -q` — **119 passed in 0.95s**, Python 3.14. Earlier affected run 109 passed before final guard additions. CLI source capture and offline evaluator exercised.
- Live public Sleeper collection: 6 completed seasons, 72 team-seasons, 1,008 regular-season team scores, 6 champions, two lineages; two explicit missing-year exclusions. No profiles, owners, final rosters, database or production mutations. Full local raw capture `/private/tmp/ftf-win-now-history-20260904.json`; compact summary/hash and readiness JSON committed beside guide.
- Source audit: six historical projection URLs, all dated stat rows carry revision timestamps later than game dates. **No authenticated pregame forecast archive; no championship calibration claimed.** The six outcome-valid seasons also fail current strict model rule coverage (FFv3 K/IDP; Lakeview retained K/DEF coefficients).
- Astra implementation/audit reviewed by parent. Named sabotage checks (reported by subagents): custom_zero_truthiness, allow_post_cutoff_snapshot, invert_actual_playoff_label each RED then restored GREEN. Final parent run after restoration. No UI changes; no additional mobile runtime gate applies.

---

## 2026-09-04 — Win Now implementation reviewed; backend and client verification

Branch `codex/win-now-20260904`, isolated at `/private/tmp/ftf-win-now-20260904`; implementation reviewed, not a release. [Scope](../docs/plans/win-now/scope.md), [evidence/code-walk/checklist](../docs/plans/win-now/EVIDENCE.md).

- **Completed locally:** full mobile `tsc --noEmit` pass; `node mobile/tests/check-win-now.js` **24 checks pass** (actual formatter and web DOM/deferred-response execution, plus mobile structure); both web scripts pass `node --check`; web structural gate **185/185**; test-ID lint passes. `git diff --check` passed at frontend handoff.
- **Backend:** first full run 4,812 pass / 1 skip / 1 flag-fixture failure; final broad run 4,790 pass / 1 skip / 2 derivative-flag failures, plus 54 API/store passes. Corrected flag fixtures and explicit platform pick-source declaration, then reran all affected suites: **200 passed**. Distinct covered set: **4,846 pass, 1 skip**; see evidence for command boundaries. Local Python 3.14, hosted Python 3.12 CI remains a merge gate.
- **Parent review/runtime:** reviewed agent modules, contracts, tests and docs; actual web module/CSS with synthetic responses passed wide/390px screenshot and search/edit/evaluation checks. 12-team/9-slot/1,000-draw/8-finalist synthetic search total47.26s. No model-calibration claim.
- **Not performed:** native simulator/Maestro (D-056), native build, production deploy/flag changes, physical TestFlight or live integrated source/auth runtime checklist, held-out forecast/title calibration. No championship graduation or source-licensing conclusion follows from unit tests.

---

## 2026-09-04 — Security findings 1–5: initial local implementation, not deployed

Five Astra medium subagents implemented private-session ownership, authoritative session initialization, token-free analytics, credential/account cleanup and admitted/owned outcome writes on `codex/security-data-hardening-20260904` from `origin/main` `606e512c`.

- Integrated security tests: **304 passed** (`/private/tmp/ftf-security-regressions.log`), including deletion/restore and stale persistence races, source-proof-before-board-access, orphan/foreign/anonymous outcomes, and synthetic historical-token cleanup.
- Additional raced event conflict regression plus analytics-P0 tests: **40 passed**; insert callbacks now use actual RETURNING IDs.
- Legacy fixture migration: a–m **776 passed / 3 calibration deselected**, n–z **702 passed**. Positive fixtures now represent verified principals; negative authorization tests remain explicit.
- Mobile: full TypeScript check, testID lint, new ownership check and relevant capture/session/settings guards pass. [Native checklist and code walk](../docs/plans/security-data-hardening/mobile-evidence.md).
- Named isolated sabotages failed as expected: bypass read gate, bypass session identity check, raw-token encoder, skip locked durable re-read, and unverified client-token persistence. No sabotaged source remains.
- Tests use synthetic credentials and scratch databases. Initial unpinned runs attempted upstream reads that failed; final combined harness disables network before importing the server, uses a valid import-only DP fixture and removes that override so per-test loader mocks work. Runtime: Python 3.14; production/CI is 3.12. **Final full suite: 4,698 passed / 1 skipped in 384.52 seconds**, including calibration cases. Final TypeScript and testID lint checks also passed.
- No production cleanup, commit, push or deployment. PostgreSQL maintenance execution and TestFlight runtime verification remain rollout gates; web/extension verified sign-in compatibility and deletion retention limits are documented in the [runbook](../docs/runbook.md).
## 2026-09-04 — Trade model/scoring-context integration

Merged main `db6b3a17` (#277) into the requested balance branch before CI. Preserved captured request/format ownership and added captured provider `league_user_id`, which the reduced worker session otherwise omitted. New delayed-job test proves a co-owner roster check cannot follow a later session reinitialization. **104 focused tests passed** in 9.81 seconds. The complete merged-revision CI remains the release gate; pre-merge full local coverage below is not claimed for this merge.

## 2026-09-04 — Trade activation validation and original items 2/3

Same branch `claude/fleeced-trade-engine-balance-c0c75d`. Two subagents implemented whole-team outlook utility and weaker-manager benefit ranking (49 and 101 tests). Main integrated four final-package tests and the independent dark `trade.mutual_benefit_v1` switch. Existing focused cluster 126 passed; TypeScript, all 90 mobile structural suites, testID lint, and 175 web checks passed. Upgrading an isolated PostgreSQL copy of production's schema twice preserved rows/config; four proposal/attribution contracts passed on PostgreSQL. No provider offers were sent.

The local full run was interrupted after 3,933 passes / one skip, no failures, during slow existing generator tests; the remaining modules subsequently passed 983 tests (17 overlap), covering all **4,899 unique passes and one skip** across both runs with backend sources unchanged. The full uninterrupted Python 3.12 CI run is pending. Live read-only sampling confirms projection/provider/confidence/co-owner gaps. Only background collection is planned; all three strict switches stay false. No native TestFlight proof or acceptance uplift is claimed. Full evidence: [activation validation](../docs/plans/trade-model-activation/validation.md).

## 2026-09-04 — Personal-market policy built DARK (D-180/D-181): 87 new tests, full suite green, flag-off byte identity proved three ways

Branch `claude/fleeced-trade-engine-balance-c0c75d` off a freshly fetched `origin/main` @ `606e512c`. Backend-only — `git diff --stat -- mobile web extension` is empty. Full gates, no waivers ([scope](../docs/plans/personal-market-policy/scope.md)).

**Both flags default `false` in code AND in `config/features.json`. Nothing is enabled, nothing is deployed, and no production migration was run by this session.**

### Automated

- **`python3 -m pytest backend/tests -q`: 4706 passed, 1 skipped, 0 failed** in 6m26s (local, Python 3.13; CI is 3.12.3 — check CI before attributing a red test here). Baseline on `origin/main` @ `606e512c` was 4619/1; the delta is this change's 87 new tests. The 1 skip is the standing `test_outlook_odds::test_backtest_against_captured_season` opt-in.
- **New: `backend/tests/test_trade_policy.py` (47) + `test_trade_policy_wiring.py` (40) = 87.** The first pins the evaluator's math, the second pins where it is plugged in. Every test names the brief's numbered behaviour it covers in its docstring.
- **Coverage against the brief's 23 required behaviours: all 23.** One-board 0.84/0.85 boundary; weak-confidence floor; strong-confidence descent to 0.65; the absolute floor under every knob setting; floor monotonicity in both inputs (parametrized 5×3); missing confidence failing safe; symmetric shrinkage; range overlap unable to rescue a sub-floor point ratio; user preference tightening only; every mutation path re-asking; rank monotonicity in the weaker side's gain; fallback not displacing divergence; Core/Conviction quotas; finder≡calculator consensus pricing; full reversal symmetry; snapshot completeness + asset/direction match; one `propose` outcome per confirmed send; idempotent proposal row (both keys); edited-package origin link; canonical mirrored concept id; match attribution with both impressions and the lag; never-served ≠ pass; stale mirror revalidated with a closed reason.

### Flag-off byte identity — proved three independent ways

1. `test_bakeoff_serving.py::test_flag_off_is_byte_identical_to_the_captured_golden` — the committed pre-bake-off golden, with the four new `deck_impressions` columns added to `NEW_COLUMNS` so the loop below it **asserts each is NULL**.
2. `test_breaker_seam.py::test_flag_off_features_json_byte_identical` — same golden through a second harness.
3. `test_trade_policy_wiring.py::test_flag_off_produces_no_policy_state_at_all` + `::test_telemetry_on_does_not_change_which_cards_are_served` — no column populated, no shadow row, and telemetry-on serving identical card-for-card to telemetry-off.

### Sabotage discipline

- **`test_removing_the_choke_point_would_be_caught`** neuters `server._evaluate_deck_policy` to a pass-through and asserts the below-floor cards come back and the shadow log empties. Proved RED against that sabotage, green on revert. Without it the choke point could be deleted with the suite still green.
- **`test_every_mutation_path_re_asks_the_evaluator`** pins all five in-generator gate sites by source, because the realistic regression is deletion during a sweetener refactor, not a subtle logic error.

### Two defects the tests found in this session's own code, before review

1. **Double-gating on inconsistent value bases.** The first draft applied two-sided personal gain as a universal eligibility veto. The wiring fixture emptied the deck: the engine's own `min_side_surplus` gate runs on **marginal** values when `trade.marginal_value` is on (it is, in prod), while the policy runs on raw confidence-shrunk values, and the two disagree systematically. Fixed by making two-sided gain a **Conviction** requirement — a Core card is market-plausible on its own and is not re-litigated under a definition the generator does not use. The residual divergence is logged as [Q-038](OPEN_QUESTIONS.md); it is a product call, not a bug.
2. **An unevidenced "gain" was buying floor relief.** `derive_policy_floor` subtracted the surplus discount independently of confidence, so two boards nobody had ranked reached 0.75 — contradicting the brief's own test 2 ("weak-confidence divergence cannot pass below approximately 0.80"). The surplus discount is now scaled by confidence. Caught by `test_weak_confidence_divergence_cannot_pass_below_the_two_board_base`.

### A shipped bug the new assertions found in EXISTING code — [G-070](GOTCHAS.md)

Asserting the frozen snapshot's market ratio against the row's stored `fairness_score` (the brief's "recomputed market ratio matches stored consensus fairness within 0.001") passed on seven of eight cards to four decimals and failed the eighth by **0.56**. Cause: a likes-you **synthesized** card computes `fairness_score` from **summed raw Elo**, while every other path — v2, v3 and the manual calculator — uses `package_value_v2` in value space. Elo is a log scale, so the ratio compresses toward 1.0: the observed card read `0.851` while its own `give_value` / `receive_value` on the same row were **704.7 / 2459.6**, a true ratio of **0.29**. The card's value bar was honest; its fairness number was not, and nothing on the row said they were measured differently.

Not fixed here — it changes a serialized value on a live surface and is out of scope for a dark telemetry change. Pinned instead: the test asserts the 0.001 agreement for every other card and asserts this class as a **known-wrong** exception (including that the snapshot still agrees with the card's own value bar), so fixing G-070 makes the test fail loudly rather than quietly pass. Under the policy flag this card is judged at 0.29 and rejected, which is the right outcome.

A third defect in this session's own code was caught by a test fixture: a second `final_trade_hash` implementation in `trade_policy` would have made `edited_from_source` fire on **every** unedited send once the two drifted. `_record_trade_proposal` now calls `server._deck_trade_hash`, the same function the impression writer used, and `test_a_confirmed_send_labels_its_impression_exactly_once` asserts an unedited send reads as unedited.

### Not run

- **`tsc --noEmit` / `testid-lint` / `check-*.js`** — no mobile file changed (verified: empty `git diff --stat -- mobile web extension`). They still gate the merge in CI.
- **TestFlight** — not required at this stage (both flags off ⇒ no runtime behavior to verify). The checklist is **written and not yet run**: [testflight-checklist.md](../docs/plans/personal-market-policy/testflight-checklist.md). It is required before `trade.valuation_telemetry` is enabled in production, and Stage A carries the brief's own release blocker (a successful controlled proposal that fails to produce an owned, non-stale impression-linked row).
- **Production database** — not touched. No query was run against Render Postgres by this session; the prod figures quoted in D-180 are from the brief's own 2026-09-04 read-only analysis, cited as such and not re-derived.

### Codex review and full-roster evaluator — final local validation

On the same requested branch, after the preceding agent's implementation:

- **Final full backend suite: 4,745 passed, 1 skipped in 378.61 s (6m18s), Python 3.14.4.** Code was frozen throughout; six changed backend source hashes verified unchanged afterward. CI Python 3.12 remains a separate release gate.
- **Final targeted regression set: 233 passed**, covering roster/policy, both sides, exact FLEX matching, canonical viewer absent from session members, picks/capacity, unknown data, attribution, cache invalidation and publication seams. Thirty-nine additional passing cases versus the preceding agent's baseline.
- Mobile typecheck passed; **90/90** mobile structural suites passed; testID lint passed; **175/175** web structure checks passed. No mobile/web/extension production source changed.
- HTML subagent exercised six team/scenario combinations at four widths (320–1440px), keyboard disclosures and source fixtures; main review confirmed desktop layout, opposing-team TE gap, incomplete settings and replacement expansion. Artifact: `mockups/post-trade-roster-check/index.html`.
- Synthetic CPU check: 50 distinct final packages, two 24-player rosters and nine starting slots evaluated in **90.4 ms**. Excludes I/O/DB and is not production latency evidence.
- Failed attempts were investigated, not hidden: the golden caught flag-off extra job keys; the roster-cut test caught unrelated position groups; the full-run pricing guard required the new roster consumer to be registered. Seven source-inspection failures occurred when the worker file changed after import. All pass in the final stable run. See `docs/plans/post-trade-roster-evaluation/validation.md`.

All four new switches are false; nothing deployed or migrated in production. TestFlight checklist written but not run. Acceptance uplift, cross-format viewer provenance and non-Sleeper observed-slot coverage remain rollout-validation work, not claims from these tests.

## 2026-09-04 — Scoring execution context: local prerequisite built, unmerged

Branch `codex/scoring-execution-context`, isolated worktree
`/private/tmp/ftf-scoring-execution-context`, freshly fetched base `606e512c`.
[Scope and applicability](../docs/plans/budget-scalability/scope.md) ·
[implementation, code-walk, test setup and remaining limits](../docs/plans/budget-scalability/implementation.md).
No push, merge, deploy, paid infrastructure, worker-count change, new search
limits or feature reductions. Original dirty checkout and HANDOFF untouched.

- **Python 3.12.14**, isolated temporary venv; scratch SQLite/player cache,
  committed provider fixtures, network blocked and startup daemons suppressed.
- **Final source targeted suites: 150 passed** (5.60 s), including ten new
  barrier/delayed-start/identity/format/pick/card regression cases and existing
  owned-pick, replenishment, trade-match, force-supersede, read-amplification and
  bakeoff/fairness/ranking goldens. Earlier broader trade/analytics selection:
  **195 passed** (22.09 s). Independent base/implementation API comparison:
  **87 passed on each** (format copy, rookie scope, persistent sessions, trades).
- **Broad final-source run:** **4620 passed / 8 failed / 1 skipped / 1
  deselected** (189.65 s). Only slow mock-draft calibration was deselected;
  an earlier run was interrupted there at 2263 passed / 7 failed (259.24 s).
  All eight failures reproduce on unchanged base and are test-bootstrap fixture
  override conflicts in API observability, DP crosswalk/format and QB-cap tests.
  With overrides removed after safe import and network still blocked, those
  four files plus the ten new context cases pass together: **61 passed**
  (0.62 s). Counts overlap; **no monolithic full-suite green claim**.
- **Sabotages RED:** `mutable_request_aliases` (1 failure),
  `late_token_resolution` (2), `shared_member_graph` (2). Final source GREEN.
- **Static checks:** `py_compile` of changed Python files and `git diff --check`
  clean. Mobile/UI evidence n/a: backend-only, unchanged API/visual contracts;
  no testID delta. Maestro/simulator retired (D-056), never invoked.
- **Local capture benchmark:** 340 committed fixture players, twelve synthetic
  members with 340 Elo entries each; 100 samples median 1.61 ms / p95 1.99 ms,
  single-capture allocation peak 95,736 bytes. This is not a production/load or
  budget certification. Durable workers, cross-process sessions and general
  concurrent write transactions remain deferred; all process/timing policies
  unchanged. Full pre-ship CI remains required before a future merge.

## 2026-09-03d — Web ESPN sign-in-primary (D-179): web gate 175/175, entry route 25/25, browser E2E both flag states + live-ESPN 403

Branch `claude/espn-signin-primary` off `main` @ `a65bb771`. Client-only (`web/index.html`, `web/js/app.js`); full gates, no waivers ([scope §V3.1](../docs/plans/landing-platform-options/scope.md)).

- **`qa/web/check_web_structure.py`:** **175/175**. **`node --check web/js/app.js`:** clean.
- **`pytest backend/tests/test_entry_platform_route.py`:** **25 passed** — unchanged route contract, re-run as a guard since the layout drives the same two actions.
- **Browser E2E, two servers.** Stub (`:5089`): the real app with the ESPN/MFL network seams patched to the route fixtures on a scratch DB, **including `es.fetch_fan_leagues`** (two leagues for one good cookie pair, `kind="auth"` for any other) so BOTH `my_leagues` branches are reachable. Real app (`:5088`) for the live-ESPN 403.
  - Paint order confirmed: explainer → sign-in btn → hint → (secondary link, hidden) → cookie block → "or" divider → id row → error → list.
  - Sign-in click → block opens, find button visible, `aria-expanded="true"`, focus on `espn_s2`.
  - Wrong pair → "ESPN didn't accept those cookies…"; list hidden; button restored. Good pair → 2 leagues → pick → 3 teams → claim → `entry:espn:{A1111111-…}`, roster 8, method screen, no error.
  - Empty fields → "Paste both espn_s2 and SWID to look up your leagues." (guard, no request).
  - `espn.league_picker` forced **off** → sign-in btn/hint/find/divider withdraw, secondary link returns, inputs still reachable; back **on** → primary restored.
  - **Live ESPN, league `1`:** "This league is private. Paste your espn_s2 and SWID cookies to continue.", block **force-opened**, focus on `espn_s2`. This is the case the restructure could have broken — V3 used `classList.remove`, a plain toggle here would have CLOSED the block for a user who had already opened it; `toggleEspnCookies(true)` is the invariant.
  - Network: the single 403 is the deliberate rejected-pair probe; the claim path is `entry/platform` ×3 → `espn/link` → `espn/leagues` ×2 → `session/init` → `rankings/progress`, all 200. Console clean otherwise.
- **Bugs caught by testing, fixed before commit:**
  1. Four error strings with wrong directional words (three ESPN, one MFL); one predates this change.
  2. **The serious one — [G-069](GOTCHAS.md), a latent §V3 defect, not caused by this change.** Re-running the E2E after the rebase exposed an unbounded 401 loop: for an entry user with a dead session, `apiFetch`'s global `session_expired` recovery calls back into the platform-snapshot read, which requires a session and cannot mint one. **Reproduced deterministically** (planted dead token + saved `entry:` user/league, reload): an unbroken second of `GET /api/espn/leagues` 401s in the server log, page never rendering. Entry sessions are unverified → never server-persisted (D-164), so a dead token is the NORMAL end of an entry session — this would have hit real users after any Render restart. Fixed: the read is a plain `fetch` bypassing the shared recovery, a 401 returns `ENTRY_SESSION_LOST`, all five call sites propagate it, and `_handleEntrySessionLost()` clears user+league+token and returns to the landing to re-claim (deterministic ids → same boards). **After: exactly 2 requests** (the two parallel callers), then the landing. Happy path re-verified end to end afterwards, including the leaguemate pool and reload restore.
- **Noted, not fixed:** `GET /api/espn/leagues` fires twice per claim (league screen + `_platformRosterData`) — cheap reads of one snapshot, caching would add staleness. Recorded in code-walk §V3.1.5 so it is not rediscovered as a bug.
- **CI on the merged head `38d5153e`: all four green** — backend-tests 11m24s · mobile-typecheck 56s · maestro-testid-lint 8s · web-structure 8s. Polled to `status == "completed"` rather than trusting one read ([G-062](GOTCHAS.md)); the earlier "no checks reported" was the PR sitting CONFLICTING, which stops GitHub building the merge commit `pull_request` workflows run against. Squashed → `main` @ `0059a8a0`.
- **Prod verified 2026-09-03 after the deploy** (live `https://fantasy-trade-finder.onrender.com/`): served bundle carries the loop guard (11 refs) and **zero** stale directional strings; the ESPN panel's paint order is explainer → sign-in → hint → (secondary, hidden) → cookies → "or" divider → id row; the expand sets `aria-expanded="true"`, reveals "Find my leagues" and focuses `espn-s2-input`. **The G-069 guard re-verified against PROD:** a planted dead `entry:` token produces **exactly 2** `GET /api/espn/leagues` 401s and then the landing with user + league + token cleared.
- **Owed:** the operator's real-account ESPN check — a stub proves both `my_leagues` branches and the live 403, never a genuine sign-in.
## 2026-09-03c — API audit fixes (D-178) SHIPPED: `main` @ `c2775fe0`, CI ×4 green, Render live; pytest 4619 / 1 skipped after the main merge

Branch `claude/api-audit-redundancies-9a6075` (cut from `main` @ `6ccd6698`). Treated as internal perf fixes: no scope block; evidence = new tests + code-walk proofs in the agent reports + this ledger. Four Opus build agents, two in isolated worktrees (swept — `docs/recovery/2026-09-03-api-audit-agent-sweep.md`).

- **pytest `backend/tests`:** **4617 passed / 1 skipped** in 371 s on the merged tree (baseline 4594/1 after the #413 ship; +23 = the new cases). New files: `test_session_init_sleeper_calls.py` (daemon budget: ≤1 rosters, ≤1 meta for a Sleeper league; zero for a non-Sleeper id; both directions of the `rosters=`/`meta=` seam), `test_cron_sweep_scope.py` (30-day activity filter both loaders; `not_drafted` TTL 3 h in-window / 24 h out), `test_trade_job_read_amplification.py` (`load_league_preference` ≤1, `load_league_preferences_bulk` ×1, `load_draft_picks` ×1 for N opponents); `test_market_data_readiness.py` +5 sweep cases (18 legs on first pass; `[6,7]`; `[1]` at week 1 and in the offseason; date-driven). Sabotage: reverting `server.py` fails the session-init test 2/4; the trade-job counters fail on the old loop.
- **Mobile:** `npx tsc --noEmit` exit 0 · `testid-lint OK` · all 88 `check-*.js` pass + new `check-session-seed.js` (U-1..U-3 execute the real seeding module against a stub QueryClient; S-1..S-3 pin the wiring, the five consumers' 5-min `staleTime`, and the api-layer import rule). Sabotage: dropping the `Array.isArray` guard, the `revalidateSession` seed call, or one `staleTime` each → RED.
- **Web:** `node --check` clean; `qa/web/check_web_structure.py` 175/175. Runtime (local Flask, demo flag forced on): boot shows `/api/sleeper/players/warm` and no `/api/sleeper/players`; one swipe = `rank3` → `rankings/progress` → `trio` only, progress label and unlock bar updated; hidden tab clears the poll timer, visible restarts it with an immediate fetch; after `logout()` a hide/show does not restart. **Not runtime-verified:** `switchToLeague` (demo has one league) and the 401 `session_expired` branch — code-walk only.
- **After merging `origin/main` (PR #272, web platform entry) into the branch:** re-ran everything on the merged tree — pytest **4619 passed / 1 skipped** (346 s; +2 from main's `test_entry_platform_route.py`), `tsc --noEmit` 0, `testid-lint OK`, `check-session-seed.js` pass, `node --check` clean, web structure **175/175**. GitHub CI on the final head: **all four jobs pass** (backend-tests, mobile-typecheck, maestro-testid-lint, web-structure).
- **Merge conflict resolved by hand, `web/js/app.js`:** main added ESPN/MFL entry-user support (`_isEntryUser` → `_platformRosterData`) to the same `switchToLeague` pre-reload block this branch deletes. Kept the deletion after verifying the reload path covers entry users: `boot()` → `initSession(user, league)` with no `rosterData` → the `_isEntryUser` branch at `app.js:835-840` reads the platform snapshot. Comment updated to say so. Five living-memory conflicts were both-sides-added-an-entry; mine renumbered 2026-09-03b → **03c** and D-177 → **D-178**.
- **Prod verification, web half (2026-09-03 16:34 UTC, deploy `dep-dacq1urbc2fs73cebekg`, live 16:33):** `GET /api/sleeper/players/warm` returns **25 bytes** (`{"count":4041,"ok":true}`) where the old path shipped ~4.8 MB; the deployed `/js/app.js` has **2** `/warm` call sites and **0** raw `/api/sleeper/players` call sites, plus the `visibilitychange` handler and `skipProgress` present. Service booted clean (player cache 4041 from disk, DP + KTC blends loaded, no tracebacks).
- **Prod verification, cron scope (finding 9) — CONFIRMED 2026-09-03 17:01 UTC, first hourly tick on the new build.** The tick logged `hourly-tick: ... draft_status=2` and issued exactly **3** `→ Sleeper GET` lines (`/league/{id}`, `/drafts`, `/rosters`) for the one Sleeper league it touched; the second league (`11896`) resolved via `rosters_heuristic` with no Sleeper call. Against the prod `leagues` table: **18 rows total, 13 active within 30 days, 5 excluded** by the new filter (of the 3 `not_drafted` rows, 2 are active and were exactly the 2 refreshed). Before the change the loader scanned every row ever synced, capped at 50. At today's scale that saves roughly **30 Sleeper calls/day** (one stale `not_drafted` league at 8 probes/day × 3, plus four stale `drafted` leagues at 2/day × 3) — small in absolute terms because the fleet is 18 leagues; the point is that it no longer grows with churned leagues. Season gate not exercised: 2026-09-03 is inside the Apr 1 – Sep 15 rookie window, so the `not_drafted` TTL is still 3 h.
- **Prod verification, session-init count — STILL OWED, needs a real app open.** No `=== /api/session/init` has appeared since the deploy (watched 16:33 → 17:31 UTC; the app is TestFlight-only and nobody opened it). Every Sleeper call logs `→ Sleeper GET`, so one `=== /api/session/init` in the Render log gives an exact count; expect **≤7** for a Sleeper league (1 rosters, 1 `/league/{id}`, ≤2 transactions, 1 GraphQL, 1 traded_picks, 1 drafts). The `user_events` `api_call` rows cannot settle this alone — successes are 1-in-10 sampled (`obs_success_sample_n`). Baseline for a rate comparison, sampled rows: 2026-09-02 `league.transactions` 10 / `league.rosters` 8 / `graphql.league_players` 2.
- **Not runtime-verified in prod:** the mobile seed (needs an EAS build cut after this merge — the 5-step checklist below), `switchToLeague` (demo has one league), the 401 `session_expired` branch, and the cron sweep filters (next hourly/daily tick).
- **Deploy note:** `ANTHROPIC_API_KEY` is **not set** on the Render service (env vars are `CRON_SECRET`, `DATABASE_URL`, `EXPERIMENT_SALT_KEY`, `FTF_TESTER_ALLOWLIST`, `PYTHON_VERSION`, `SLEEPER_TOKEN_KEY`), so smart matchup selection runs the algorithmic path in prod. Closes an audit uncertainty.
- **Owed after merge:** watch one real session init in the Render log (expect ≤7 `api.sleeper.app` calls); the 5-step TestFlight check in the PR body (no second `/api/sleeper/rosters/<id>` after opening Trades; ESPN/MFL league still renders a roster).
## 2026-09-03b — Web landing platform entry (PR #272): web gate 175/175, entry-route suite 25/25, browser E2E both platforms; sim gate skipped (D-056 posture)

Branch `claude/landing-page-espn-mfl-a5a85a` @ `8473fab2` (off `main` @ `6ccd6698`), PR [#272](https://github.com/mattmurf77/fantasy-trade-finder/pull/272). Full gates ([scope §V3](../docs/plans/landing-platform-options/scope.md)), no waivers. `FTF_SKIP_SIM_GATE=1` on push — web-only change; the evidence below replaces the retired simulator.

- **`python3 qa/web/check_web_structure.py`:** **175/175** (DS tokens / emoji / radius / fonts, SEO, A11Y, HYG) on the shipped `index.html` / `app.js` / `styles.css`.
- **`pytest backend/tests/test_entry_platform_route.py`:** **25 passed** (23 + 2 new: `test_mfl_entry_leagues_snapshot_carries_the_claimed_franchise`, `test_espn_entry_leagues_snapshot_carries_the_claimed_team` — pin the `GET /api/{espn,mfl}/leagues` contract the web's `buildPlatformRosterData` reads). Full suite `pytest backend/tests`: **4587 passed / 1 skipped** in 6:33 (baseline 4585/1 from the #413 ship + the 2 new).
- **`node --check web/js/app.js`:** clean.
- **Browser E2E** (Claude Browser pane; real `backend.server.app` on `:5089` with only `es.fetch_league` / `es.get_crosswalk` / `mfl.resolve_host` / `mfl.fetch_league_bundle` / `server._shared_crosswalk` patched to the route tests' fixtures, scratch SQLite via `DATABASE_URL`): MFL `10005` → 3 franchises → claim "Clobberin Time 2" → `entry:mfl:10005.f0001` session, league auto-selected, `/api/session/init` OK, ranking-method screen → main app (8-player roster, account chip = franchise name); reload restores via `boot()` (`_myRoster` 8, `_cachedLeagues` 1); `_ensureLeaguematePool` → 16 players / 2 owners, never the user's own team. ESPN pasted `…leagueId=987654321` URL → 3 teams with owners → claim "Chalk Dusters" → `entry:espn:{A111…}` session, roster 8, method screen. Live server on `:5088`: MFL `99999` → "MFL has no league with that ID."; ESPN `1` → private-league copy + cookie section auto-opened. Console clean; `POST /api/events` 200 ×3. Full table: [code-walk §V3.7](../docs/plans/landing-platform-options/code-walk.md).
- **Bug caught by the walk (fixed before commit):** the Sleeper wrapper had no `.hidden` rule, so the username row stayed visible under the ESPN/MFL panels — visible on the first screenshot.
- **CI on PR #272 (merged head `9fea43e0`): all four green** — backend-tests 7m37s · mobile-typecheck 51s · maestro-testid-lint 7s · web-structure 6s. Squashed → `main` @ `ca5fac46` 2026-09-03; `git diff origin/main 9fea43e0` **empty** (content verification of record).
- **Prod verified 2026-09-03 after the merge** (live `https://fantasy-trade-finder.onrender.com/`): markup present (`platform-row`, `entry-espn`, `entry-mfl`, `entry-teams`, `mfl-signin`; the "Sleeper, ESPN, and MyFantasyLeague" meta ×2); `js/app.js` carries the entry module; `/api/feature-flags` has all five gates true; `POST /api/entry/platform {"platform":"nope"}` → **400** `bad_platform` (not 404 — the route is live and past the flag gate). Browser on the live site: chip row visible with Sleeper · ESPN · MFL, Sleeper selected, panels swap both ways, Sleeper form restored on switch-back; live MFL probe id `99999` → "MFL has no league with that ID." with the button restored (no stuck-busy).
- **Owed:** the operator's own 4-step prod check with a REAL league (scope §V3) — the checks above prove the surface and the error paths, not a successful claim against a live ESPN/MFL account.

## 2026-09-03 — #413 SHIPPED: PR #270 squash → `main` @ `5c83e8cd`, CI ×4 green, Render live, EAS build 144 / v1.16.15 submitted

Ship branch `ship/2026-09-02-fb413` @ `c6c95e07` = `main` @ `c7e75666` + `feat/fb413-sleeper-send-draft-picks` @ `d49611be` (clean merge) + the write-back with renumbered ids + version bump. Tree byte-identical to the squash (`git diff origin/main ship/…` empty).

- **Local, ship tree:** `pytest backend/tests` **4585 passed / 1 skipped** (fresh DB; main's own baseline had grown with D-172/D-174/D-175's suites — the #413 delta is still +20) · `npx tsc --noEmit` exit 0 · **89/89** `check-*.js` · `testid-lint OK` · `test_app_version_consistency` at 1.16.15.
- **CI on `c6c95e07` (PR [#270](https://github.com/mattmurf77/fantasy-trade-finder/pull/270)):** backend-tests · mobile-typecheck · maestro-testid-lint · web-structure — **all pass**; `mergeStateStatus CLEAN`.
- **Deploy:** Render `dep-dacf8l6q1p3s73ek9ef0` for `5c83e8cd` **live** at 2026-09-03T04:16:38Z; `GET /api/feature-flags` 200. Every fielded build (1.16.12–1.16.14) now gets the server half: a pick-bearing send no longer 502s, and a refusal reads its reason.
- **Mobile:** EAS build **144** / v1.16.15 (`ceffdbe7`), `--auto-submit` scheduled (submission `b4763913`). Verify the submission by STATUS (2026-08-30 lesson), not the CLI's last line.
- **Not shipped:** the parallel #414 build (`feat/fb414-lopsided-one-for-one` @ `8c165533`, 4512/1, dual-QA green) — superseded by D-175, which was live before this ship; its evidence stays in the 2026-09-02b entry below and the item folder.
- **Owed:** the operator's **7-step #413 TestFlight checklist** on build 144 (PRD §10) — TF-3 closes [Q-037](OPEN_QUESTIONS.md); log outcomes here.

## 2026-09-02 — feedback #413 Sleeper pick-send fix: built, dual-QA green, shipped 2026-09-02 (see the merged-tree entry above)

Branch `feat/fb413-sleeper-send-draft-picks` @ `d49611be`, cut from the session spec commit `ad5adafa` (main @ `ce3f443c`). Full gates, no waivers ([scope](../docs/feedback/items/413-sleeper-send-draft-picks/scope.md)). Backend agent `b4aabcc3`/`31e8d590`/`b938642b`, orchestrator `51794a35` (ADR-010 guard sanction), mobile `8e4e1648`, post-QA copy fix `d49611be`.

- **pytest `backend/tests`:** **4503 passed / 1 skipped** (baseline 4483/1, +20 = PRD's expected delta) — re-run by the orchestrator on `d49611be` after the copy-only delta; both QA agents independently reproduced 4503/1 on `8e4e1648`.
- **Mobile:** `npx tsc --noEmit` exit 0 · **89/89** `check-*.js` (incl. `check-mascot-ram.js` under plain `node`) · `testid-lint OK` · `check-send-button-platform.js` +4 checks (7, 7b, 7c, 8).
- **Sabotage evidence:** builders 25 (backend) + 6 (mobile) cycles; **QA-A 32 PRD-named + 11 own, QA-B 32 PRD-named + 12 own** — every PRD-named sabotage RED except T-8's `if False:` variant (self-satisfying: the `None` row raises inside the encoder's `try` and lands in `unmapped` anyway); **T-8's proof of record is the "existence inferred from rosters × horizon" sabotage** (RED for both agents). Own-devised sabotages that stayed GREEN (coverage gaps, accepted as code-walk-only): mobile "never renders `picks[]` ids / never reads `detail`"; `encoded` give-then-receive order; guardrail 8's literal `PICK_SOURCE_PLATFORM` value (the AST guard checks the kwarg is named, not its value).
- **Fixture-shape audit (both agents):** rosters int `roster_id` / string `owner_id`; grid `original_roster_id` string (load-bearing); `traded_picks` `{season:"2027", round:int, roster_id:int, owner_id:int}` — all production shapes; `_sleeper_get` single-return stubs untouched (the fetches are inside `if give_picks or recv_picks`).
- **Code-walk proofs:** R-8 ordering (422s return before the write; `_save_deck_outcome_safe` + `_record_send_success` after it), R-13 ladder + fielded-build catch-all reading `detail`, R-15 warnings render unchanged, R-16 four enum sites at 17, W-1 four mounts still pass mixed arrays — `qa-round-1-agent-{A,B}.md` + `code-walk-mobile.md`.
- **Post-QA delta (orchestrator, copy-only):** validate advisory strings count-aware (`is/are`, `it/them`) + curly apostrophe; `test_trade_send_validate.py` 16/16 + full suite re-run above. Round 2 was an orchestrator gate re-run on this two-string delta, not a second two-agent round — disclosed.
- **Declared re-spec:** `test_sleeper_write_route.py:288` fixture (PRD R-17) — the bogus `draft_picks: ["2027_1"]` body replaced by an owned pick inside `give_player_ids`, now asserting the adapter's request.
- **Owed:** the operator's **7-step TestFlight checklist** (PRD §10 / both QA reports) on any build ≥ 1.16.12 after the Render deploy — TF-1/2/4/7 mandatory, **TF-3 conditional and the Q-037 proof** (give an acquired pick; "not run" is a legal logged outcome), TF-5/6 opportunistic. Log each outcome here.

## 2026-09-02b — D-174 below-market reason (PR #267) and D-175 sweetener band + best-effort (PR #268): shipped and flipped live

Both off `main` @ `e16bb487`, full gates, waivers surfaced and accepted (no new analytics; no `check-*.js`; TestFlight replaced by server-side prod verification). Both QA'd adversarially by independent Opus reviewers; every code claim survived, all fixes were docs/tests.

| Gate | D-174 (`reason_below_market_frac`) | D-175 (`sweetener_gap_frac`, `sweetener_best_effort`) |
|---|---|---|
| `pytest backend/tests -q` (branch / clean main) | **4542 / 1** vs 4519 / 1 (+23) | **4541 / 1** vs 4519 / 1 (+22) |
| QA independent rerun | 4542 / 1 | 4541 / 1 |
| Goldens at defaults | wire capture (full `generate_trades` → `trade_card_to_dict`, explanations ON) vs `git archive` main — `cmp` identical, 457,236 B | 9 `close_value_gap` fixtures + full v3 decks — `cmp` identical; QA's own 1,600-call fixture identical after stripping the probe column |
| Invariance | deck identical on every non-`reasons` field at 0.10/0.15/0.25/0.35/1.0 (386 cards) | 4,000 fuzz cases at the triple: 413 partials, 0 lowered a fairness ratio, min gap reduction 103 |
| Sabotages (byte-copy restore, `cmp`, `__pycache__` cleared) | builder 3 + QA 5 (headliner→centerpiece, stamp at 0, double-stamp, drop pick guard, placeholder name) all red→green; `team="PICK"` + real-position fixture added | builder 6 + QA 5 (strict-reduction guard, floor→replacement, partial branch skipping extra_ok / feasibility / fairness) all red→green |
| Harness (prod pins incl. `consensus_fit_weight` 0.5, frozen clock, baseline byte-identical twice) | share of cards carrying the line @0.15: 5% standard, 15–22% opinionated boards | `>1539` never raised vs V0, 0 in every arm-B/D v3 cell; sweetened 6.9/0/4.8 → 10.3/11.1/19.1%; sub-450 flat on B; top-5 J 1.0 on B; arm A unmoved 280/280 cells; no cell shrank |
| Perf | 0.999× per job | `close_value_gap` 0.017 → 0.59 ms worst case; full job +~0.1 s on the 30 s rail |
| CI | ✓ ×4 on `308d8d90` | ✓ ×4 on `4a66858e` (post-rebase) |
| **Prod** | deploy landed (row seeded 0.0); `PUT` **0.15** at `2026-09-02T21:30:56Z`; F-1 pre-flip read: operator's Adams n=43, shrunk 61% below market | deploy landed (both rows seeded 0.0); PUTs `sweetener_best_effort` 1 → `sweetener_gap_frac` 0.12 → `sweetener_gap_threshold` 750 at `2026-09-02T21:53:34Z` |

Follow-ups logged (not fixed): consensus-generator `seen` key not discarded on sweeten (`trade_service.py:~7296/~7337`); injectors and arms C/fit never carry the reason line; `reasons` not in `features_json`.

## 2026-09-02c — post-deploy verification on the LIVE site (PR #263 → `main` `1eb520bd`)

Squash-merged after all four checks went green on `f632023b`
(backend-tests · web-structure · maestro-testid-lint · mobile-typecheck, all **success**).
Render auto-deployed; new content served ~90 s after merge. Everything below was measured
against **production**, not a local server.

| Check | Method | Result |
|---|---|---|
| Deploy landed | poll `/js/events.js` for `X-Source` | present after ~90 s |
| P2-3 renders | `getBoundingClientRect` at 1280x900 | `.lp-step-d` **620px** x4; points grid **`442px 442px`**; **no horizontal overflow** |
| Structure | DOM query | 1 `<h1>`, both `<h2>`s, 4 steps, 4 points |
| Console | `read_console_messages` | **clean, 0 errors** |
| Analytics live | `/api/feature-flags` | `analytics.client_events` **true** in prod |
| Events accepted | network + `/api/admin/analytics/health` | `POST /api/events` **200**; **2 accepted / 0 rejected / 0 dropped** since deploy |
| W3 (operator): admin shell blocked | `curl` | `/admin/analytics.html` **404**, `/style-guide.html` **404** |
| Real pages unaffected | `curl` | `/` `/contact.html` `/robots.txt` `/sitemap.xml` all **200** |
| HTML 404 handler | `curl /nope-does-not-exist` | **404** |
| Sitemap no longer advertises a 401 | `git show origin/main:web/sitemap.xml` | **0** `<loc>` entries for `league-rankings`; mentioned only in the explanatory comment |

**Honest limit on the `source` claim.** The end-to-end `source='mobile'` → `source='web'`
proof was done **locally** against the dev DB (2026-09-02 entry). On prod, what is verified is
narrower and should be quoted as such: the deployed `events.js` contains the header, the flag
is on, events are accepted with zero rejects. The prod `user_events.source` column was **not**
read back — the admin analytics surface exposes health counters and named reports, not a raw
row dump. First per-client report after this deploy is the confirming read.

**Side effect worth naming:** this verification wrote two real `app_opened` rows to production
analytics (two page loads from the verifying session). They are indistinguishable from visitor
traffic and are part of the seam noted in NEXT.md.

## 2026-09-02b — P2-3 landing below-the-fold: built link-free, verified at two breakpoints

Operator ruling same day: "build it link-free now". `web/index.html` + `web/css/styles.css`
(`.lp-*`). Full gates. Web gate **175/175** unchanged (the section adds no new violation
surface); `node --check` n/a — no JS added.

**Runtime measurement, before and after.** Web has no runtime harness, so this is manual and
is the only evidence of its kind.

| Check | Before | After |
|---|---|---|
| Landing is one viewport | `scrollHeight` **749** vs 720 viewport | below-the-fold section present, 4 steps + 4 points |
| App/TestFlight mention anywhere in rendered text | **none** | still none — **by design**, see W6 |
| `<h1>` count (a11y gate) | 1 | **1** (new headings are h2/h3) |
| Console on load | clean | **clean** |

**A real defect, caught by measuring instead of eyeballing.** `.lp-step` has three children
against a two-column grid, so auto-placement put each `<p>` in row 2 of the **34px number
column**: measured `width 34px x height 624px` — one word per line. Fixed by pinning both text
elements to `grid-column: 2`. Re-measured: **620px wide, 48-96px tall (2-4 lines)** across all
four steps.

| Breakpoint | Result |
|---|---|
| 1280x900 | `.lp-wrap` 900px in a 1250px section; points grid `442px 442px`; no horizontal overflow |
| 375x812 | points collapse to a single `339px` column; `scrollWidth` 375 == viewport, widest right edge 357 — **no horizontal overflow** |

**Not run, and why:** no EAS build, no TestFlight, no simulator ([D-056](DECISIONS.md)) —
nothing here is mobile-visible. No screenshot strip shipped (W7): `screens/` is frozen at
2026-08-11 and `web/` has no image assets.

## 2026-09-02 — web-parity branch resynced onto `main`: full gates green, plus the first RUNTIME pass web has ever had

Branch `claude/website-updates-continue-c7942b` @ `e672d7f4` (merge `ba91ca96` brings
`fix/web-phase0` onto `main` @ `c65a7998`). Full gates, **not express** — operator never
declared it, and analytics stamping is a bright line.

**Static gates, all re-run on the merged tree:**

| Gate | Result |
|---|---|
| `pytest backend/tests -q` | **4519 passed, 1 skipped** (336 s) |
| `python3 qa/web/check_web_structure.py` | **175/175** (was 173; +2 new) |
| `bash mobile/scripts/testid-lint.sh` | **OK** |
| `npx tsc --noEmit` | **not run, not owed** — the branch changes zero `.ts/.tsx` files (`git diff --name-only origin/main...HEAD` has no `mobile/` path). CI runs it anyway. `mobile/node_modules` deliberately not installed in this worktree ([G-022](GOTCHAS.md)) |

**Runtime pass — the evidence that did not exist before.** `web/` has no runtime harness and
the CI gate never loads a page, so everything below is manual and is the only proof of its
kind on this branch. Server: `ftf-fullstack` (Flask, port 5088) on the merged tree.

| Check | Method | Result |
|---|---|---|
| Landing boots against current-`main` backend | load `/`, read console | **clean, 0 errors**; title `Fleeced — Dynasty Trade Finder` (P1-6 rename live) |
| Flag fetch | network log | `GET /api/feature-flags` → **200** |
| Phase 0 fix ([G-067](GOTCHAS.md)) is real | network log + `localStorage` | `POST /api/events` → **200**, queue drains to `{"v":1,"events":[]}` |
| `app_opened` actually persists | `SELECT … FROM user_events` | row present, `props {"launch_type":"web","seq":1}` |
| Single `<h1>`, a11y | DOM query | **1** |
| Landing is one viewport, no app mention (P2-3 still owed) | `scrollHeight` vs `innerHeight`; regex over `body.innerText` | **749 vs 720**; **no** testflight/app-store/download string anywhere |

**The defect this found — [G-068](GOTCHAS.md).** The persisted `app_opened` row read
`source='mobile'`. `web/js/events.js` declared `platform:"web"` in the body but sent no
`X-Source` header, and `analytics_ingest.py:376` defaults `source` to `"mobile"`. Not a NULL
— a wrong value that looks like data, in a column adjacent to a correct one.

**Fix verified by re-measurement, not by inspection:** cleared the prior rows, reloaded on a
fresh tab, re-queried. Before `source='mobile', platform='web'` → after **`source='web',
platform='web'`**.

**Guard negative-controlled.** `HYG-events-declare-source` was proven to fail before it was
trusted: sabotaging the header to `X-Nope` turned the gate red (174/175, that one check
FAIL), restoring it returned 175/175. A guard that has never been seen red is not evidence.

**Not run, and why:** no EAS build, no TestFlight pass, no simulator (retired, [D-056](DECISIONS.md)).
Nothing on this branch is mobile-visible. Nothing was pushed, merged or deployed.
## 2026-09-02 — D-172 `consensus_fit_weight` shipped (PR #261), flipped live to 0.5

Branch `claude/consensus-fit-sort-key` off `main` @ `ce3f443c`; merged as `c65a7998`. Full gates, three waivers surfaced and accepted (no new analytics event — existing impression corpus split by `basis` is the measurement; no `check-*.js` — no client file; no TestFlight checklist — replaced by the server-side prod verification in results.md).

| Gate | Result |
|---|---|
| `PYTHONHASHSEED=0 pytest backend/tests -q` (builder, tip `e67abe38`) | **4508 passed, 1 skipped** (322 s) vs clean `origin/main` @ `ce3f443c` same day **4483 / 1** — delta = the new tests |
| QA independent rerun (branch / pristine main) | 4508 / 1 and 4483 / 1 — confirmed |
| After QA fixes (`1d91acdf`): `test_consensus_fit_sort_key` + `test_bakeoff_arm_a_golden` + `test_engine_quality_golden` | **39 passed** (25 + 11 + 3); neighbouring consensus-path modules 123 passed |
| Goldens at the default | byte-identical vs a `git archive origin/main` tree, engine-quality fixture (174 rows) and mirror fixture (74 rows) |
| QA independent w=0 identity | own 37-scenario fixture, 5,307 cards, byte-identical after stripping the probe field; 0 `replacement_levels` / 0 `marginal_value` calls at w=0 |
| Sabotages (byte-copy restore, `cmp`, `__pycache__` cleared) | S1 blend→`seed_value` (mirror red) · S2 drop shed key (golden red) · S3 stamp at w=0 (red) · S4 hoist read to import (mirror red) · S-C remove `is_pick_asset` guard (red after the `team="PICK", position="RB"` fixture was added — was NOT caught before) · F2 delete the arm-A pin (`test_consensus_fit_pin_is_load_bearing` red; the old golden stayed green — the gap QA reported) |
| QA fuzz at w=0.5 | 200 random rosters: 0 exceptions, 0 sign-test violations, 0 fairness violations, 0 out-of-range stamps; uncapped set identical 200/200 with the sweetener off, 198/200 at 1539 (order-dependent `seen` dedupe; count unchanged) |
| Perf | fixed ~0.35 ms per pair at w>0 (2 `replacement_levels` after the hoist); consensus loops have no deadline; 150 capped decks 0 shrank |
| Harness (prod pins, frozen clock, 120 cells ×3 thresholds) | baseline byte-identical twice; arm A identical at every w; junk<450 unchanged at w=0.5 in every live cell; the only deck shrinks in the corpus are at w=0.25 |
| CI on final sha `1de37224` | backend-tests ✓ · mobile-typecheck ✓ · maestro-testid-lint ✓ |
| Sim gate | D-056 posture; substitute evidence: code-walk.md + the above |
| **Prod** | deploy landed: `GET /api/admin/config` row count 237 → 238 with `consensus_fit_weight = 0.0`; flipped to **0.5** at `2026-09-02T18:04:26Z`; engine-metrics 7-day baseline snapshot taken before the flip (consensus shown 1,358 / divergence 555; decisions n=3 / n=13 — too thin for like-rate reads; compare impression counts and positional mix) |

## 2026-09-01 — Trade-engine quality research: prod config read, knob-only harness sweep, pool-fit prototype (read-only; nothing shipped)

Context: dual-agent review of open TradesHome quality items #350/#363/#393/#401/#414 (+#370). Brief: session artifact *Where Trades Die*; findings logged as [G-064](GOTCHAS.md)–[G-066](GOTCHAS.md), [Q-035](OPEN_QUESTIONS.md)–[Q-036](OPEN_QUESTIONS.md). No engine line changed on any shipped branch; no flag flipped; no feedback status changed.

**Prod `model_config` read** (`GET /api/admin/config`, 237 rows): D-159 bundle **applied** (`filler_min_frac` 0.15 · `overpay_adjusted` 0 · `trade_elo_gap_max` 0 · `v3_shape_max_delta` 2) — the ledger's 2026-08-24 future-tense entry and NEXT.md:86 were stale. `bakeoff_serve_interleaved` 1.0, `bakeoff_include_gen_v2` 1.0, `bakeoff_include_challenger` 1.0 → **arms C and D both serving**. Unchanged: `sweetener_gap_threshold` 1539, `need_fit_weight` 0.15, `need_gate_upgrade_margin` 0.

**Knob-only sweep** — `measure_gap_distribution.py` copied to scratch, extended (lateral share, centerpiece repeats, partner-favourable share, top-5 Jaccard), baseline pinned to the four prod values, `PYTHONHASHSEED=0`, **clock frozen** (G-065; unfrozen the baseline disagreed with itself by 3 cards). Determinism: two baselines byte-identical.

| Variant | Result |
|---|---|
| V1 `sweetener_gap_threshold` 1539→750 | Only variant that moved anything. Sweetened share up (12t/v3 challenger 9%→23%); gap p90 down where it works (1169.9→484.7). Top-5 Jaccard 0.959 (13/14 groups identical) — content changes, order does not. **Regression mode traced:** `close_value_gap` is all-or-nothing (`trade_optimizer.py:918/:932`); a card partially closed to 1535 at 1539 ships **unsweetened at 1825** at 750, so `>1539` share *rose* 0%→4% in one cell. Junk<450 never exceeded 15.0% (D-159 line ~20%). |
| V2 relative band `max(750, 0.12·max)` | **Needs code** — `gap_threshold` is a scalar param; one-line knob inside `close_value_gap`. |
| V3/V4 `need_fit_weight` 0.35 | **Unmeasurable here**: `need_fit_score` returned exactly 0.5 on every card — the snake-drafted fixture has no positional asymmetry. Not a null result about the knob. |
| V5 `shrink_pseudocount` | **Unmeasurable here**: never read — harness passes `confidence=None`. |
| V6 `need_gate_upgrade_margin` 0.10 | Never read at baseline (R5 fails open with no outlook). With R5 armed (`outlook=contender`, fixture extension): **+1 card in 2 of 4 cells, top-5 unchanged everywhere.** Not a lever worth a release. |
| V7 = V1 + V3 | Byte-identical to V1. |
| Partner-favourable, consensus path | **0/N on every non-challenger arm, every cell** (viewer-wins sign test, measured). Challenger: 20–43%. Consensus share of fixture cards 17–55% vs prod 84.5% — consensus effects under-weighted in this harness. |

**Pool-fit prototype** — isolated worktree `agent-a9c4c705ebb53fc71`, commit `60aa4572` off `origin/main` `ce3f443c`, knob `v3_pool_fit_extra` default 0. `pytest backend/tests` at knob 0: **4483 passed, 1 skipped** (320 s). Knob-0 golden byte-identical to main. Pre-registered failure ("pool grows, deck unchanged") **falsified**: 16t SF knob 4 → 15 of 17 divergence cards replaced, 14 of 16 carry a fit-selected asset. But: cost **2.5× / 5.5× / 11×** at N = 2/4/6 (review's 2.4× was N=2; N=4 breaches the 30 s rail on a fully-boarded 16-team league); the clean mirror 1-for-1 ranks **53,242nd of 137,558** behind 54,695 junk-stuffed siblings (trade-wide depth benchmark inflates surplus once a second asset is on a side — existing objective property); distinct give-headliners 8→4; partner-favourable share flat. Strict-xfail fixture `test_v3_pool_fit_prototype.py` encodes the mechanism. **Verdict: build differently** — fit-asymmetry *sort key* in `_generate_consensus_for_pair` (two sorts, not a prune; knob-sized; the 84.5% path) first; divergence pool N≤2 only alongside a junk-stuffing fix.

Reproduce: scratchpad `measure_knob_variants.py` / `report.py` / `probe_reads.py`; prototype `measure_fit_pool.py` / `deck_diff.py`. Levels are directional (synthetic boards); deltas are the result; all decks are no-time-pressure.

## 2026-08-31b — D-171 finder results push: built, gates green, v1.16.14

Branch `claude/finder-results-push`, cut from `main` @ `2ceff988`. Full gates, no waivers ([scope](../docs/plans/finder-results-push/scope.md) — the five 2026-08-31 operator rulings; ruling 5b shipped it LIT over the dark-flag recommendation).

- **Flags (G-062 four-file flip + FLAG_KEYS + baked defaults):** `calc.results_push` NEW true everywhere; `calc.canvas_results` true → false everywhere. `pytest backend/tests` **4483 passed, 1 skipped** (the fixture-mirror chain — release wholesale + the two one-key diffs — validates the flip; no backend behavior changed).
- **Mobile:** `npx tsc --noEmit` exit 0 · `testid-lint OK` (no testIDs added — the pushed deck reuses the classic deck's) · **all `mobile/tests/check-*.js` suites green** including the re-pinned `check-canvas-results.js` (dark pins + `landingDeckRetired` gates), `check-inline-home.js` (push-fork re-key, receipt re-pins), `check-calc-merged-behavior.js` (§10b2 plain-pop arm).
- **New guard `check-results-push.js`** (`npm run test:results-push`, ~45 assertions): push payload carries the D-153 verdict/anchor/scope/origin/label; landing mounts no browse session and dispatches nothing; pushed instance mounts no canvas and adds no dispatch site (mutate census 1 raw / 9 routed unchanged); edit-in-calculator pops with the canvasPrefill bridge, Back-to-calculator pops plain; popTo never navigate (G-056); kill-switch fallback intact; flag registration + baked default; no new analytics. **Sabotage-proven 5/5** (each red, restore green): S1 canvas remounts on the pushed instance → §4; S2 popTo→navigate → §5a/5b; S3 Back-to-calculator carries the canvas-clearing empty prefill → §5e; S4 payload drops `fairAnchor` → §3d; S5 flag flipped dark → §1.
- **Code-walk proof:** scope §6 (push hand-off, both fork paths, the one-refire consumption ordering, POP_TO params cite from routers 7.5.3 source).
- **Version:** 1.16.14 build 2 in `mobile/app.json` + `Info.plist` (D-057/G-012 pair-bump; `test_app_version_consistency` in the green suite above).
- **Owed:** the operator's 8-step TestFlight checklist (scope §7) on the v1.16.14 build — step 5's second-account "They're interested" mirror is the C1 close's runtime proof; step 8 is the kill-switch drill.

## 2026-08-31 — D-170 ✓ queue validation removed + calcq_ mirror bypass (express)

express: ✓ queue validation removed + calcq_ mirror bypass — gates skipped by operator (2026-08-31). Server-side only; no mobile build. Gates actually run: `pytest backend/tests` **4483 passed, 1 skipped** (baseline 4478 — net +5 from the re-pinned `test_calc_trade_queue.py`, now 38 tests: well-formed ⇒ `queued: true`; the old `fails_fairness_floor` package queues AND surfaces; `calcq_` likes bypass the injector's D-096 ladder and preference-list skips while a non-`calcq_` like of the identical package is still gated; roster actionability kept at mirror time; `not_league_member` is the one surviving refusal) · `npx tsc --noEmit` exit 0 · `testid-lint OK` · `node mobile/tests/check-calc-merged-behavior.js` all assertions passed (client untouched, as expected).

## 2026-08-30b — feedback batch #409/#410/#411/#412: built, dual-QA green, v1.16.13

Branch `claude/fb-410-412-trade-card-polish`, cut from `main` @ `bd83fe94`. Four tester reports filed against v1.16.12 (build 140) the morning it landed. Full gates; no waivers. Specs: [409-like-not-league-member](../docs/feedback/items/409-like-not-league-member/) · [410-found-trade-decline-position](../docs/feedback/items/410-found-trade-decline-position/) (17 requirements covering all four items).

- **#409 `11c8903c` + `14d06ba2` (backend, G-063):** `POST /api/trades/queue` resolved the CALLER out of `g_league.members`, which is caller-excluded by app-wide convention — so `caller_member` was always `None` and **every ✓ queue tap had been refused with `not_league_member` since 2026-08-22** (100% failure, invisible because the fixture put the caller inside `members`). Caller now synthesized locally from the session; `league.members` untouched (the engine, mock draft, power rankings and likes-you injector all depend on the exclusion). **+7 production-shape tests, sabotage-proven** (5 red on revert, the 2 that stay green are the no-over-permit pair). Full suite **4478/0** (baseline 4471). QA: PASS, no blocking; independently re-derived 4478 and the sabotage cycle.
- **#410/#411/#412 + #409 copy `03a90652` (mobile):** D-169 decline cell (bare ✕ during a browse session, operator ruling; Clear elsewhere; 50/30/20 untouched) closing the **browse-session data-loss defect** where Clear mid-session wrote `{[],[]}` into the browsed idea's edit map; #411 chip → meta line + compact name at 13/18 (top-100 one-line fit **1/100 → 83/100**); #412 More offers under the give column's Add; #409's refusal copy stops blaming the counterparty. **32 sabotage cycles by the builder, 27 re-proven independently by QA-A**, headline S-2 ("helpful cleanup" — decline also calling `clear()`) red in isolation.
- **Gates:** `tsc --noEmit` clean · **87/87** npm-run structural suites (88th, `check-mascot-ram.js`, has no npm script — pre-existing) · `testid-lint OK` · `pytest backend/tests` **4478 passed, 1 skipped** · QA-A verified **no green assertion was silently edited** (six pre-existing assertions changed, all six declared re-specs; `check-any-partner.js` from FB-406 byte-identical).
- **QA-B (adversarial, mobile): 17/17 PASS, 1 BLOCKING disclosure finding, 5 non-blocking.** **F-1:** the #411 tag move squeezes the meta line's team · age text to **≈1.9pt on top-tier rows** (chip 30.1 + `4+ 1sts` badge 59.5 + 8pt gaps = the whole 97.5pt line), so team and age vanish on exactly the assets the fix targeted — a cost the operator was not shown when they chose "tag move + shrink" over wrapping. Resolved by disclosure, not code: PRD §6.2b + TestFlight step 11b put it in front of them on device; reverting is chip-back-to-line-1 or a wrapping meta line. F-2 narrowed D-169's "closed" claim (one kill-switch flag combination still reaches the ghost stacked Clear); F-3/F-4/F-5 recorded in PRD §6.6 and `docs/design/design-system.md` (`title-compact` row).
- **Version:** 1.16.13 in all three files; EAS confirmed latest was 1.16.12/140 at bump time.
- **Owed:** the operator's 14-step TestFlight checklist on the new build — **step 9 (✓ queue succeeds) is the #409 proof and step 11b is the F-1 ruling**.

## 2026-08-30 — feedback batch #407 (finder forced team) + #406 (Anyone targeting): SHIPPED via PR [#250](https://github.com/mattmurf77/fantasy-trade-finder/pull/250) → `main` @ `287aed09` on green CI ×3; EAS build **140** (v1.16.12) submitted to TestFlight — build 139 errored on an EAS-side archive-upload failure and was retried

Branch `claude/new-user-feedback-5fa613` (worktree of the same name, cut from `main` @ `e89eebb0`). Full gates, no waivers beyond the written analytics/schema/flag waivers in both scope blocks (no bright-line surface touched). Specs: [407-finder-forced-team/mini-prd.md](../docs/feedback/items/407-finder-forced-team/mini-prd.md) · [406-target-any-leaguemate/prd.md](../docs/feedback/items/406-target-any-leaguemate/prd.md) (3-round dual-agent loop + targeted verification pass; every review round caught real defects — see reconciliation logs).

- **#407 fix `8f722676`** (1 production file): `opponentChosenRef` gates the Find-a-Trade payload — the calculator's auto-defaulted first-leaguemate partner no longer forces a single-team sweep on an untouched canvas; an explicit pick still scopes both forks (#384 checklist-23 preserved). Guard: `check-calc-merged-behavior` 20a-20d, 5 sabotage cycles proven red/green by the builder AND independently re-proven by QA-A (+ a full-revert probe: 3 assertions red on the pre-fix build). QA-B adversarial code-walk: APPROVE, 1 non-blocking (B-1 browse-seed prefill counted as chosen — closed by the #406 build).
- **#406 build `c138507c`** (3 production files + new guard suite): "Any league mate" sheet row (`partnerAny` + null opponentId, no sentinel), honest dropdown/receive labels, scope-truth note pinned to the exact complement of the #407 payload gate, partner-gated `ev` (closes the `placeholderData` stale-verdict leak), `seeded` prefill marker (browse-seed never counts as chosen; re-specced 20a proven two-sided). Zero backend diff — the league-wide sweep already ships (`/api/trades/fair-packages` with `opponent_user_id` omitted). D-168.
- **Batteries:** backend `pytest backend/tests` **4,471 / 0 failed** (1 skipped) on the session tree · `tsc --noEmit` clean · **87/87 npm-run structural suites** green in QA-A's clean worktree (88 files incl. new `check-any-partner`; `check-mascot-ram.js` has no npm script — pre-existing gap, follow-up queued) · `testid-lint OK` · **QA-A #406: 20 sabotage cycles** each red on the named assertion, self-satisfaction audit clean · QA-B #406: APPROVE, zero blocking (B-1 zero-result canvas-wipe corner documented + E-4 addendum; B-2 flag-kill-only stale state documented).
- **Version:** 1.16.12 in all three files (Info.plist authoritative + app.json + both stale-since-1.16.6 `MARKETING_VERSION`s aligned); EAS confirms latest is 1.16.11 build 138 — no race at bump time.
- **Ship record:** PR #250 squash → `main` @ `287aed09` (CI green ×3); docs ledger PR #252 → `1c5e6543`. **EAS build 139 ERRORED** — `SERVER_ERROR: Failed to upload application archive`, an EAS-side artifact-upload failure *after* a clean 5m39s compile (checked the one documented local cause: 27 worktrees / 26 GB free, not the 91-worktree disk-bloat mode). Retried unchanged → **build 140 FINISHED** (v1.16.12, commit `26578b99`, .ipa produced) and its attached auto-submit reached **status FINISHED** = delivered to App Store Connect. Two later manual `eas submit --latest` calls ERRORED as redundant-binary duplicates, which is the expected rejection once the auto-submit has already uploaded that build number — the FINISHED auto-submit is the authoritative signal, not the CLI's last line.
- **Owed at ship:** CI green on the pushed sha; operator TestFlight checklists — #407 6 steps ([mini-prd §checklist](../docs/feedback/items/407-finder-forced-team/mini-prd.md)) + #406 E-4 8 steps ([prd §E-4](../docs/feedback/items/406-target-any-leaguemate/prd.md)) — the only runtime evidence under D-056.

## 2026-08-29f — age-preference consensus multiplier (D-167): SHIPPED via PR [#248](https://github.com/mattmurf77/fantasy-trade-finder/pull/248) → `main` @ `750abb6a` on green CI; branch swept (docs/recovery/2026-08-29-age-pref-value-ship.md)

Branch `feat/age-pref-value` (worktree `goofy-perlman-490e49`), rebased onto `main` @ `d5c926fd`.
Scope: [docs/plans/age-pref-value/scope.md](../docs/plans/age-pref-value/scope.md) — full gates, no waivers, backend-only.

- **Backend pytest:** full suite **4,471 / 0 failed** (1 skipped — the standing `FTF_OUTLOOK_BACKTEST` opt-in) pre-rebase; combined-tree re-run post-rebase: **4,471 / 0 failed** (1 skipped) on `main` @ `d5c926fd` + this branch. CI green ×3 (backend-tests · mobile-typecheck · maestro-testid-lint) on `11c167e4`, squash-merged.
- **New tests:** `backend/tests/test_age_pref.py` — 10 tests: band boundaries (22/23/29/30 at the taste_service cut points), boost-cap engagement, cap-≤0 disable, discount-never-capped, >1.0-on-any-band capped (future-proof), exact identity at the 1.0 kill values, pick/no-age pass-through, MODEL_A_PROFILE pin (both mults 1.0, cap absent), dual-store default registration. **Sabotage-proven:** `cap-dropped` (boost-cap branch deleted) → 2 red (`test_boost_cap_engages_on_large_values`, `test_future_boost_on_30plus_band_is_capped_too`), green on revert.
- **Arm-A golden:** `test_bakeoff_arm_a_golden.py` + `test_bakeoff_challenger.py` — 45/45 green with the identity pins in place; golden **un-recaptured** (the pins are identity values, same precedent as `package_bench_trade_wide`).
- **Test-only adaptations:** the three golden-comparison files (`test_bakeoff_serving.py`, `test_breaker_seam.py`, `test_outlook_direction.py`) pin the two age mults at 1.0 in their fixtures — their goldens/premises were captured age-neutral and they guard OTHER seams; each carries a D-167 comment.
- **Mobile:** untouched (no tsc/testid surface).

## 2026-08-29e — layer-1 decline pass now carries dwell/engagement (client half of the #242 dup-pass guard) — SHIPPED via PR [#246](https://github.com/mattmurf77/fantasy-trade-finder/pull/246) → `main` @ `293b5f80` on green CI; branch swept (docs/recovery/2026-08-29-null-dwell-decline-pass-ship.md)

Branch `claude/zealous-mirzakhani-f1664e` (fix `49d3d033`, then merged post-#241/#242 main with gates re-run on the combined tree; tip `0cd2de7d`, content-verified against `origin/main`). Client companion to the 2026-08-29c guard below (`deck_pass_outcome_recorded`, PR #242): with first-pass-wins live, a layer-1 decline tile tap fires `POST /api/trades/pass-reason` before the swipe POST, so the SURVIVING pass row was the reason write's — which carried no dwell — and the swipe's dwell-bearing row dropped as `dup_pass`. Every reasoned pass going forward had NULL dwell.

- **Change (3 files):** `DeclineReasonWrite` gains optional `dwellMs`/`detailExpanded`/`calcOpened` (wire keys `dwell_ms`/`detail_expanded`/`calc_opened` — exactly what `_apply_reasoned_pass` reads at backend/server.py:13487-13489; booleans sent faithfully, no `|| undefined` drop of `false`). Populated on the FIRST tile tap only (a switch's signal already landed) at both layer-1 disposition sites: `TradesScreen.handleReasonLayer1` (gate `firstForThisCard`) and `usePresentationSignals.reasonLayer1` (gate `switchedFrom === 'none'` — both presentation screens fire reasonLayer1 before `dispatch(card,'pass')`, TodaysTradeScreen:109-113 / TradeBrowseAllScreen:119-121, so the same defect existed there; the hook's contract is byte-parity with the deck's signal rows).
- **Code-walk proof:** signal source is the SAME `signalForCard` the swipe path uses (TradesScreen.tsx `signalForCard` → `currentDwellMs` + `engagementRef`; hook's own mirror), read in the same synchronous tap handler that calls `advance('pass')`, so the reason row's values match what the (now-dropped) swipe row would have carried. Flag-off / no-impression cards: `signalForCard` returns undefined ⇒ POST body byte-identical to before. Tile switches and all layer-2 writes: unchanged (fields omitted).
- **Gates:** `npx tsc --noEmit` clean · `check-decline-reasons` / `check-presentation-v2` / `check-canvas-results` all green · `testid-lint OK`. Backend untouched (no pytest delta). No new events, no schema, no route change — three additive body fields the server already read.
- **Runtime note for the next TestFlight pass:** after this reaches an installed build, a layer-1 reasoned pass should produce ONE `deck_outcomes` pass row with non-NULL `dwell_ms` (verify via the impression spine, not the app UI).

## 2026-08-29d — propose-label spine: built, all gates green, operator bright-line YES ("PR only") → merging via PR [#241](https://github.com/mattmurf77/fantasy-trade-finder/pull/241)

Branch `claude/elastic-matsumoto-e3860c` @ `5b79a13a` (worktree `app-entry-platform-options-3e16ac`, cut from `main` @ `af91d6f8`). The analytics-event change (new `source` prop on `trade_proposed`/`match_swiped`) was put to the operator at the bright line and answered: **ship, "PR only"** — PR #241 went up with CI green ×3 on `5b79a13a`; main then moved under it (#242/#243/#244 — the dup-pass guard is the SIBLING fix from the same disposition review §4), so this merge commit re-ran the gates on the combined tree before landing. Scope block: [docs/plans/three-model-bakeoff/scope-propose-label.md](../docs/plans/three-model-bakeoff/scope-propose-label.md) (carries the full diagnosis: the zero-`propose`-outcomes mystery is the Matches send path having no impression_id to pass, not the deck dropping it — the deck mount has passed it since 2026-07-26).

- **Backend pytest:** full suite **4,456 / 0 failed** (1 skipped) — 4,450 baseline + 6 new in `test_deck_signal_v2.py` (swipe `surface` → `props.source`; unknown surface → null, never passthrough; awaiting returns the recovered `impression_id`; flag-off omits it byte-identically; `_latest_impressions_by_hash` prefers latest non-ghost ≤30d and scopes to user).
- **Mobile:** `tsc --noEmit` clean (after `npm install` — this worktree was missing `react-native-purchases`, an install gap, not a code issue) · **all 87 structural suites green** — `check-presentation-v2` updated to pin the NEW dispatch shape (4-arg `swipeTrade` + the `'today'`/`'browse'` surface mapping) · `testid-lint OK`.
- **Shipped:** merge of pre-ship main (`ce4e2779`) re-ran the gates on the combined tree — pytest **4,461 / 0** (4,450 + #242's 5 + these 6), tsc clean, presentation-v2 guard + testid-lint green — then CI green ×3 on that exact sha and squash-merge → `main` @ `1f87ec16` (PR #241, operator "Merge it"). Branch swept by content (docs/recovery/2026-08-29-propose-label-ship.md).
- **Owed (operator, runtime, NEXT mobile build):** the 3-step checklist in scope §3 (Matches send → `deck_outcomes` `action='propose'` row; browse like → `props.source='browse'`; calc ✓ → `'calculator'`). The propose leg is the three-model bake-off's strongest per-arm label — the first prod `propose` row is the success signal.

## 2026-08-29c — deck_outcomes duplicate-pass guard: built + full suite green — SHIPPED via PR [#242](https://github.com/mattmurf77/fantasy-trade-finder/pull/242) → `main` @ `e9992195` on green CI; branch swept (docs/recovery/2026-08-29-dup-pass-guard-ship.md)

Prod audit finding (operator-supplied, trade-disposition review §4): 120 of 410 passed impressions carried 2–3 `action='pass'` rows 20–90ms apart. **Root cause confirmed by code-walk:** the mobile layer-1 tile tap fires BOTH `POST /api/trades/pass-reason` (server writes the pass via `_apply_reasoned_pass` → `_save_deck_outcome_safe`, no dwell in its payload → NULL `dwell_ms`) AND `advance('pass')` → the unchanged `POST /api/trades/swipe` (dwell set) — `TradesScreen.handleReasonLayer1` + `declineReasons.ts` header vs `server.py`'s "the row that replaces what the ✕ used to write". The reason-less 10/120 are swipe double-fires (`save_trade_decision` deduped Elo but `deck_outcomes` appended anyway). **Fix:** `database.deck_pass_outcome_recorded` (live pass = more pass rows than undo rows) + a skip in `_save_deck_outcome_safe` counted as `dup_pass` on `/api/admin/analytics/health`; undone passes may re-pass; taste update skipped with the row. Elo was already safe (elo_signal_at claim + decision dedupe) — this fixes the ~30% row-count overstatement going forward. **Evidence:** 5 new pytests (both endpoint orders, layer-1 re-tap, swipe double-fire, pass→undo→pass) in `test_decline_reasons.py` + `test_deck_signal_v2.py`; full `pytest backend/tests` **4,455 / 0 failed** (was 4,450 + the 5 new). Docs: data-dictionary `deck_outcomes` exception noted. Historical prod rows not backfilled — dedupe reads on NULL-dwell twins if pre-fix windows are queried.

## 2026-08-29b — guided onboarding DISABLED (onboarding.guided_avatar off) — config flip, verified live

Operator ruling ("Disable the guided onboarding"), scoped and confirmed: the Analyst avatar experience off everywhere (`guide_v2` already off since 2026-08-28); the activation prompts (`apple_save_moment`, `quickset_prompt`) stay ON per the explicit "activation moment: yes" and run their plain avatar-free arms (the queue-path fork resolves to `maybeAskApple` directly). PR [#239](https://github.com/mattmurf77/fantasy-trade-finder/pull/239) squash → `main` @ `06a5ef67`, all three checks SUCCESS pre-merge (verified via statusCheckRollup after a network blip interrupted the watch). Full pytest on the flip: **4,450 / 0**; parity fixtures + the `test_seed_ui_test_db.py` pin updated per its deliberate-revert rule with the ruling in the docstring. **Live verification post-deploy:** guided_avatar False · guide_v2 False · apple_save_moment True · quickset_prompt True. Effect immediate for all clients; revert = the key + the pin. Consequence noted in HANDOFF: Wave B-prime shrinks to "decide if/when any guided experience returns."

## 2026-08-29 — v1.16.11 (EAS build 138): canvas-results + trades-landing + activation moments — full round, shipped

Branch `feat/canvas-results`, squash PR [#237](https://github.com/mattmurf77/fantasy-trade-finder/pull/237) → `main` @ `21989cda` on green CI. Operator rulings: canvas-results-spec.md header (deck hidden / ✕ = decline flow / edits stick) + trades-landing-ruling.md + "activation moment: yes".

- **Build:** EAS `b8cc4523-588b-4abb-8ef3-aef02ba4106d` — v1.16.11, build **138**, finished, from `21989cda` exactly (verified via `eas build:list`), auto-submitted to App Store Connect. **Flags verified LIVE post-deploy:** `calc.canvas_results` + `nav.trades_landing` both true; inert until 138 installs (no shipped client reads them).
- **What shipped:** ideas browse in the calculator (per-idea edit map + `onSidesChange`; ✓ queues the edited trade; ✕ = the two-layer decline capture on EVERY browse session; five honest empties, audit-Q5 idle-card structurally unreachable); Trades as the launch tab for all users (imperative decide-once, baked LAUNCHED_FLAG_DEFAULTS); G22 activation moments re-triggered off canvas events (+#362 standing-offer); "More offers" restored to the front door on the browsed idea; session lifecycle riding all 8 dispatch + 5 inline-reset sites (censuses suite-pinned).
- **QA:** two independent reviewers; A = spec pass with 6 defects, B = HOLD with 4 confirmed (C1 P0 invisible first-run deck — the trades-landing audience; C2 QuickSet handoff; C3 prefill attribution corruption; C4 shop entry orphaned) + 4 plausible. **All 12 fixed in one round** (`e9cd523a`); 7 sabotage cycles red→green; frozen browse ordering; flag-arrival adoption; partner locked while browsing; no-op Undo toast deleted.
- **Gates (orchestrator-run on the shipped tree):** full `pytest backend/tests` **4,450 / 0 failed** · `tsc --noEmit` clean · **all 87 `check-*.js` suites green** (check-canvas-results 104+ assertions) · `testid-lint OK` · CI green pre-merge.
- **Owed (operator, runtime, build 138):** checklist Parts D/E (steps 20–32 + 20a/22a/22b/23c) — headline steps: first-run new-user visible session (the P0's regression test), ✕ reason capture, edits-stick, More offers from the browsed idea, Trades landing on a fresh install. Plus everything still owed on 137 if unrun.
- **Queued next round:** Wave B-prime — onboarding script rebuild against the new page, then the `onboarding.guide_v2` re-light (flip flag + fixtures + the test_events_api pin together).

## 2026-08-28e — v1.16.10 (EAS build 137) BUILT + SUBMITTED; the merged tree's gates all green

- **Merge:** PR [#234](https://github.com/mattmurf77/fantasy-trade-finder/pull/234) squash-merged @ `6d9e6dc0` on green CI (backend 9m46s · typecheck · lint). Pre-push gates on the merged tree: pytest **4,450/0**, tsc clean, 86 suites, lint.
- **Build:** EAS `536d68b1-cdb0-4a3a-b05f-20f39342fac5` — v1.16.10, build **137**, finished, from `6d9e6dc0` exactly (verified via `eas build:list`), auto-submitted to App Store Connect. Earlier same day: build **136** (v1.16.9 + dark IAP, `3a73a46b`) also submitted — superseded by 137 for the checklist pass.
- **Owed (operator):** the 19-step + inserts checklist on build 137 (Parts A/B/C incl. the v1.16.9-device compat step), plus the still-unrun #384 partner-summary 8-step. **Deferred by design:** the `onboarding.guide_v2` re-light once 1.16.10 is the installed base (the branch's tour gate makes it safe; flip the flag + the `test_events_api.py` pin + the fixtures together).

## 2026-08-28d — rev-3 shop window + merged-view trim: built, QA'd twice, fixed, shipping as v1.16.10

Branch `feat/shop-window-rework-402` (ships via the v1.16.10 PR). Full arc on top of the four operator surprise-rulings (`rulings-2026-08-28b.md` + `merged-view-trim-2026-08-28.md`, both in the item folder):

- **Build commits:** `6d95a1ab` backend (swap_positions all groups + lateral_scope tier), `33ce1534` mobile (pushed ShopAssetScreen window, filters all modes, auto-widen; TradesScreen net −89), `5c510a44` scoped tour gate (one choke point in useGuide.requestStep; nothing spent, re-light-safe), `702e4d11` QA-A doc fixes + 1.16.10 bump, `a8a5e56e` QA-B backend fixes, `3545205c` QA-B mobile fixes, `2fd3b746` merged-view trim (T-1 one outlook bar · T-2 one primary · T-3 no format chips inline; page-level bar consumer audit incl. the #316 deck-summary copy made flag-aware), `afe63727` merge of main (tip-jar #233 rode in; features.json conflict resolved keeping main's lit value + both comment additions).
- **Redundant QA:** reviewer A — zero code defects, four doc defects (fixed same session), and it MATERIALIZED the merge with main and ran everything green on it. Reviewer B — 4 confirmed regressions, all fixed: field-client compat (the v1.16.9 strip sends swap_positions on the shared fetch — all-groups filtering now keys on `lateral_scope` presence, the rev-3 request signature; old wire shape byte-identical, pinned by `test_old_shape_swap_positions_filters_lateral_only`), auto-widen tick early-committing held dismisses (rendered-mode tick discipline), dismissed-tile resurrection (asset-ideas now consults the D-067 cooldown — compliance with D-067's own "every live service" rule; likes never exclude), stale kill-switch prose (rewritten; the open-window-survives-flip truth on the record). Plus: unseeded assets have no tier; chooser staleness guards; honest comment sweep.
- **Suite:** `check-shop-deck.js` at 142 assertions + trim assertions in `check-inline-home.js` §11 and `check-calc-merged-layout.js` 13c/13d; sabotage across the session: 21 more deliberate breaks, every one red-then-green with snapshot restores.
- **Gates on the MERGED tree (orchestrator-run):** `tsc --noEmit` clean · all 86 `check-*.js` suites green · `testid-lint OK` · full pytest [recorded at ship below].
- **Owed (operator, runtime, on the v1.16.10 build):** the rewritten checklist — now 19 steps + 2a/15a inserts across Parts A/B/C, incl. the multi-asset chooser race, the tier-width honesty step, the auto-widen step, the merged-view trim step, and Part C's v1.16.9-device compat check.

## 2026-08-28d — IAP enablement code half (runbook 6–7): webhook delta + RevenueCat paywall — full gates, ALL DARK

Operator-directed cross-session handoff; two Opus build subagents (backend/mobile, disjoint file ownership), lead-session review of every load-bearing hunk. Branch `claude/monetization-features-feedback-a6fe77` off `origin/main` `69dc0cae`. Scope block: [docs/plans/monetization/iap-enablement/scope.md](../docs/plans/monetization/iap-enablement/scope.md). **Zero user-visible change until the operator flips `monetize.*` flags** — no route gained `@_require_pro`, no flag changed, no schema changed.

- **Backend** (`entitlements.py`, `server.py`): `resolve_rc_identity()` alias reconciliation (`$RCAnonymousID:*` → `acct_*`, prior anon-keyed billing rows re-keyed before upsert), `TRANSFER` projected as a move (not expire/revoke), `BILLING_ISSUE` grace extension (extend-only, never perpetual rows), `_product_mapping` tolerant of the runbook's divergent SKU spellings (Q-034), new `GET /api/paywall/config` (session-authed, `monetize.paywall` off → `{"enabled": false}` only). Five `paywall_*` client events registered in taxonomy + `NON_INTENT_EVENTS` same-commit.
- **Mobile**: `react-native-purchases@10.8.1` (single-seam `api/purchases.ts`, inert without `EXPO_PUBLIC_REVENUECAT_IOS_KEY`; never calls `logOut`), `initPurchases`/`logIn` identity bridge in `useSession` (bootstrap + sign-in halves), `useEntitlements` store (server-authoritative, CustomerInfo raise-only UI cache, 72h offline grace), `PaywallScreen` root-stack modal (3.1.2-complete: price+period, 14-day trial terms, auto-renew + cancel copy, working Restore, tappable /privacy + /terms; server `enabled:false` beats stale client flags; no FeedbackFAB per #188), flag-gated `settings-pro-row` on both settings surfaces.
- **Evidence (D-056):** `pytest backend/tests` **4397 passed, 1 skipped, 0 failed** (lead-run on the combined tree; targeted new coverage: 47 entitlements + 12 paywall-config tests, 7 named backend sabotages RED-then-green) · `npx tsc --noEmit` clean · `testid-lint OK` · new `mobile/tests/check-paywall.js` **11/11** (3 mutations verified failing) · full structural suite **84 guards, 0 failing** · code-walk proof + operator sandbox checklist in [docs/plans/monetization/iap-enablement/](../docs/plans/monetization/iap-enablement/).
- **Runtime evidence OWED (operator, blocked on Apple):** [sandbox-test-checklist.md](../docs/plans/monetization/iap-enablement/sandbox-test-checklist.md) — cannot run until the Paid Apps agreement (signed 2026-08-27) is active and RevenueCat/ASC are configured (runbook steps 3–5). The mobile purchase path has **no** runtime proof until then, by design.
- **Open for the operator:** Q-034 (ASC SKU naming — recommend `ftf_*`; **closed 2026-08-28, `ftf_*` confirmed**), `REVENUECAT_WEBHOOK_SECRET` absent from `secrets.local.env` + Render, `EXPO_PUBLIC_REVENUECAT_IOS_KEY` needed in EAS env before the next build, and note the next mobile release **must be a full EAS build, not OTA** (native module).
- **Addendum (2026-08-28e, operator ruling):** monthly gains a **3-day trial** — `trial_days` 0→3 in `_PAYWALL_PRODUCTS` + test + LLD §3 + checklist P2; `pytest test_paywall_config.py + test_entitlements.py` re-run green (59 passed) on the delta; mobile untouched (trial copy is generic over `trial_days`).
- **Addendum (2026-08-28f, operator request — tip jar):** `ftf_tip_199/499/999` consumables + `TipJarScreen` modal + `settings-tip-row`, and the projector guard `entitlements.is_tip_product()` (without it, RevenueCat's activating consumable events would grant every tipper Pro via the default mapping). Evidence: targeted pytest **66 passed** (4 new tip tests in `test_entitlements.py` §h + 3 in `test_paywall_config.py` §f), **sabotage** guard-disabled → 3 red → restored green; new `mobile/tests/check-tipjar.js` **9/9** (its §7 importer-scan initially missed the lazy `require` — fixed and re-verified); full structural suite (86 guards) zero red after merging main's `check-inline-home` LIT-state fix (#232); full `pytest backend/tests` **4422 passed / 1 skipped / 0 failed** on the combined tree; `tsc --noEmit` clean; `testid-lint OK`. Checklist step 10b added (tip pays, thanks, grants NOTHING — verified server-side via the admin curl).
- **Addendum (2026-08-29, operator ruling):** trials re-set to **14d monthly / 30d annual** after the trial-conversion research (short trials = worst-converting bucket in every RevenueCat panel year). Values-only: `_PAYWALL_PRODUCTS` + tests + LLD §3 + checklist P2; targeted pytest 66 passed, `check-paywall.js` 11/11 on the delta.

## 2026-08-28c — v1.16.9 (EAS build 135) BUILT + SUBMITTED to TestFlight; trade.shop_asset LIT in prod

Release run at operator order ("push, open PR, merge, push to testflight and flip the flags on").

- **Merge:** PR [#225](https://github.com/mattmurf77/fantasy-trade-finder/pull/225) squash-merged to `main` @ `a9d96435` on green CI (backend-tests 8m52s · mobile-typecheck · testid-lint). Branch `claude/new-feedback-71436e` @ `823bfb2d` content-verified (empty diff vs main), recovery-ledgered (`docs/recovery/2026-08-28-shop-branch-ship.md`), then swept — worktree removed clean, local + remote branch deleted.
- **Flag:** `trade.shop_asset` flipped `true` in the same PR (features.json + all three mirror fixtures; mirror suite 76 passed). **Verified LIVE on prod post-deploy** via `GET /api/feature-flags`: shop_asset / asset_ideas / calc.merged_layout / finder_targeting all `true`. Inert for pre-1.16.9 clients (no code reads the flag).
- **Build:** EAS `21504c65-a3ff-4003-8dee-9e902cdf792d` — v1.16.9, build **135**, status **finished**, from git commit `a9d96435` (the merged main squash — verified via `eas build:list`, not assumed). `--auto-submit` chained: *"Submitted your app to Apple App Store Connect!"* — Apple-side processing then TestFlight availability is the only remaining step and is not ours. Version bumped in BOTH `mobile/app.json` and `Info.plist` (G-012), `plutil` clean; build number from EAS remote autoIncrement (134 → 135).
- **Owed — operator, runtime, on build 135 (this build carries BOTH):** the 14-step #402/#403 shop checklist ([docs/feedback/items/402-more-offers-shop/testflight-checklist.md](../docs/feedback/items/402-more-offers-shop/testflight-checklist.md)) — now post-flip verification per the operator's confirmed sequencing — **and** the still-unrun 8-step #384 partner-summary checklist owed "on the next EAS build" since 2026-08-27, which this is.

## 2026-08-28b — #402/#403 QA round 2: B-3, own-position chip ruling, P-1..P-4 — universal-rule fixes, gates green

Operator rulings ("Fix B3, 2. Offer it. Resolve the runtime concerns by ensuring consistent/universal approach") recorded in `docs/feedback/items/402-more-offers-shop/rulings-2026-08-28.md`; fixed in `23b0cdf6` on `claude/new-feedback-71436e` (still HELD unmerged).

- **B-3 + P-2, one mechanism:** committed dismissals are client-authoritative for the strip session — a `suppressed` set added to only on commit, cleared by nothing but the strip instance dying (Undo-safety ordering verified; commit-failure un-suppresses). Pager, 1/X, chip counts and the Clear-positions label all filter through it, closing the baselineLateralCount nit with it.
- **Own-position chip (LLD §3.4 over the mockup, ruled):** offered unselected alongside the others; own-only selection sends `swap_positions:[own]` with no special case; PICK still never offered; suite j2c INVERTED (the pre-round-2 suite run against the new code reds only on j2c — proved by executing the HEAD copy: 78/1). Mockup Same-value frame updated to shipped semantics (WR chip added, its contradictory PICK chip removed).
- **P-1:** react-don't-race pager — one `pendingScrollRef` consumed by an effect keyed on the rendered data; all four movers request-then-mutate. **P-3:** `shop_opened` emits exactly once, in `openShopStrip` (chooser pick = one event with the real position; Cancel = zero). **P-4:** `shopEnabled` = `trade.shop_asset && trade.asset_ideas && calc.merged_layout`; flag comment names the chain plus the structural `trade.finder_targeting` prerequisite; any flag dying mid-session closes an open strip.
- **Suite:** 100 assertions (21 added: exactly-one-emitter h4, flag-chain n1, suppression n2, pager n3, and reviewer A's two missing pins — Chalkline scan n4, label-source n5). Sabotage 4/4 red-then-green with byte-identical restores (`cmp`-proved; file snapshots, not `git checkout --`).
- **Gates (orchestrator re-run):** `tsc --noEmit` clean · shop suite 100/100 · all `check-*.js` zero RED · `testid-lint OK` · `features.json` valid · `pytest test_seed_ui_test_db.py + test_analytics_taxonomy_384.py` 87 passed (backend diff = one taxonomy comment).
- **Checklist updated:** step 9 covers the chip + B-3 verification; Known-open now empty. Nothing remains open from either QA reviewer.

## 2026-08-28 — #402/#403 "More offers = shop a player" — full build + redundant QA + fix round, all gates green (branch, HELD unmerged)

Built by three parallel/sequential subagents on `claude/new-feedback-71436e` (docs+mockups branch, first re-based on `origin/main` `69dc0cae` via merge `bf125dac`): `5115265b` W1 mobile (entry fork, ShopOffersStrip, chooser, flag `trade.shop_asset` dark, 4 analytics events, `check-shop-deck.js`), `4b71f036` W2 backend (`swap_positions` on `/api/trades/asset-ideas` + spike S-2), `bc21ee0f` W2 UI (position multi-select), `472f6649` QA fixes. **Operator hold: nothing merged, nothing pushed.**

- **Gates, run by the orchestrator on the combined tree (not delegated claims):** full `pytest backend/tests` → **4,377 passed / 1 skipped / 0 failed** (5:12); `npx tsc --noEmit` exit 0; **all 84 `mobile/tests/check-*.js` suites green** including the new shop suite (90 assertions after the fix round) and a byte-untouched `check-single-pin-actions.js` (R-18); `testid-lint OK`; `features.json` valid. Re-run after every commit.
- **Spike S-2 (`docs/feedback/items/402-more-offers-shop/spike-s2-yield.md`):** single-position swap selections empty 30–60% of the time (TE worst), multi-select finds a lateral 89–97% — the picker ships multi-select-first with live counts and first-class empty copy. Generator output matched the analytic ±band window in all 32 grid cells.
- **Sabotage evidence (suite falsifiability proven by every agent):** W1 9 edits / 9 red (give-side guard, Gesture.Pan import, counter decoupled, mode-map corruption, pan gate deleted, label drift, ✕→like, undo-lie, taxonomy drop); W2 backend 2 (lateral leak into upgrade → 3 red; silent invalid-position accept → 3 red); W2 UI 4 (PICK chip, analytics position-set, `[]` sent, flush dropped); fix round 4 (k1/l1/m2/l2c). All restored green.
- **Redundant static QA (2 reviewers, independent):** A (spec) — every requirement PASS, flag-OFF byte-identical proven (early-return fork, exact legacy literal, zero diff on `/api/trades/queue`); B (regression) — 4 confirmed seam bugs B-1..B-4 + 4 plausible P-1..P-4. **Operator selected B-1/B-2/B-4 → fixed in `472f6649`** (deck holds still through buttons + VoiceOver + reason tiles + flag button + a topRawId close-on-card-change effect; shop state cleared by `resetDeckForNewTargets`/`handleClearPin`/kill-switch mount gate/`key={asset.id}`; Undo toast retracted by reference on every early commit). **Open by explicit selection:** B-3 (≤60 s warm-cache resurrection of a committed dismiss), A-1 (own-position chip — mockup vs LLD §3.4 contradiction, needs a ruling), P-1..P-4, plus two unpinned mechanical guards (Chalkline scan, label-source assertion) and two doc rows (api-reference "pending" note now stale; components.md row).
- **Owed (operator, runtime):** the 14-step checklist in [docs/feedback/items/402-more-offers-shop/testflight-checklist.md](../docs/feedback/items/402-more-offers-shop/testflight-checklist.md) on the first build carrying the branch — steps 3/8/11/12 are the QA-fix regressions, Part B is the flag-off byte-identity check. Elo note for the operator: the shop ✓ moves the board by explicit ruling A.

## 2026-08-27 — #384 partner team-shape summary restored to the merged calculator layout — full gates

Live shipped regression found by the [2026-08-27 calc-vs-guided-finder parity audit](../docs/reviews/2026-08-27-calc-vs-guided-finder-audit.md) (row 24, one of its five `partial` rows). Branch `claude/calc-merged-partner-summary` off `origin/main` `30070f36`. Scope block + code-walk + TestFlight checklist: [docs/feedback/items/384-calc-finder-merge/partner-summary-regression.md](../docs/feedback/items/384-calc-finder-merge/partner-summary-regression.md).

- **The defect, and that it was a regression:** the per-partner QB/RB/WR/TE + picks shape line has been on the In-league calculator's partner chips since `fbd55611` (2026-07-27), relabelled to pick-equivalents by #306 in `780c035c`. #384 W1 (`dfcd5321`) replaced the chip row with the #333 Team dropdown + sheet and did not carry the line across — its own commit message describes the new sheet as listing leaguemates "with their R/R*/NR rank state". `calc.merged_layout` is `true` in `config/features.json`, so every user since v1.16.0 has seen handle + badge only. **Checked before fixing:** neither the ten #384 operator rulings nor the four round-2 rulings touch the partner list (6/7 remove the utility row and the subnav), and `plan.md` §15 lists `calc.partner-summary.<id>` among the controls the page already had. Omission, not ruling.
- **Structural guard — extended, and proven falsifiable.** `mobile/tests/check-calc-merged-layout.js` gains section 22 (a–h): one shared implementation, the merged sheet mounts it, fed from the same memo, the sheet row *speaks* the shape, the row can shrink so the R-badge is never pushed off, and the flag-off stacked page keeps it. Four sabotages applied to the working tree and reverted — **against `origin/main`'s component verbatim (the shipped bug): 6 FAILED**; drop the mount from the sheet only: 22d; strip the spoken shape (sighted-only restore): 22f; hand-copy a block instead of the shared helper: 22a + 22d. The guard fails on the build that shipped the defect.
- **Suites (run in this worktree after `npm ci` — no symlinked node_modules):** `npx tsc --noEmit` exit 0 · **all 84 `mobile/tests/check-*.js` guards, 0 failures** (83 pre-existing + this one's new assertions) · `bash mobile/scripts/testid-lint.sh` → `testid-lint OK`. **`pytest backend/tests` not run — backend untouched**, the diff is `InLeagueCalculator.tsx` + `check-calc-merged-layout.js` plus docs.
- **No new data cost:** `powerQ` (`getPowerRankings(leagueId, 'consensus')`) is unconditional and already feeds `needsByTeam` in the merged layout, so the summaries were being computed and discarded. No route, flag, schema, analytics event or testID added.
- **Owed (operator):** the 8-step TestFlight checklist in the scope doc §B — the shape line's presence, per-team variation, the no-picks and picks tails, Dynamic Type / landscape two-line clamp with the badge still on screen, tap-to-select, and the **VoiceOver** row announcement (the sighted-only failure mode). Runtime is the only evidence left for layout truth under D-056.

## 2026-08-26e — v1.16.8 (EAS build 134) BUILT for TestFlight

Release run by the lead session at operator instruction ("push to testflight via EAS"), following the `ops-release` pre-flight.

- **Build:** `c12643d1-a22b-4dee-9e08-611c01f70366` — v1.16.8, build **134**, status **FINISHED**, from git commit **`dd2051bc`**. `--auto-submit` chained the submission: **`c6e58906-3cbc-4418-af97-d7a39a6cc6c3`** — *"Submitted your app to Apple App Store Connect"*, uploaded via the EAS-held ASC API key (`LA9UVSTV2N`). Apple-side processing (~5–10 min) then TestFlight availability is the only remaining step and it is not ours.
- **Version bump:** 1.16.7 → 1.16.8 in `mobile/app.json` AND `ios/DTFDynastyTradeFinder/Info.plist` — [G-012] says the plist literal is what actually ships in this bare workflow, so bumping only app.json would have shipped a build labelled 1.16.7. `plutil -lint` clean. Build number from EAS remote (`appVersionSource: remote`, autoIncrement), so 134 follows the concurrent session's 133.
- **Built-tree verification (not assumed):** `git show dd2051bc:` confirmed the entry v2.1 login actions in `backend/server.py`, `signin.platform-link-btn` in `analystScript.ts`, and `1.16.8` in the plist.
- **Pre-flight gates:** main CI green at every commit in the range; release PR #217 and onboarding PR #218 each had all three checks COMPLETED/SUCCESS **before** merge (the G-062 discipline); backend suite 4,359 passed; 83 mobile structural guards, 0 failing; tsc + testid-lint clean.
- **What 134 carries beyond 133:** entry v2.1 (#215 — "sign in to ESPN/MFL" as a first-class option) and the platform-aware Analyst beat (#218). 133 already carried the entry chips (#210) and the Apple decoupling (#213).
- **Owed (operator, on 134):** the TestFlight checklists in [landing-platform-options/scope.md](../docs/plans/landing-platform-options/scope.md) §3, §V2, §V2.1 — plus a spot-check that the tour's opening beat now points at the ESPN/MFL panel button (not the hidden username field) when a non-Sleeper chip is selected.
- **Rollback without a build:** `landing.platform_options: false` + `POST /api/feature-flags/reload` kills the whole entry surface; `espn.league_picker` / `mfl.auth_link` kill just the login actions.

## 2026-08-26c — Entry v2.1: login option (Opus subagent build, lead-session review) — full gates

Scope: [docs/plans/landing-platform-options/scope.md](../docs/plans/landing-platform-options/scope.md) §V2.1 · code-walk §V2.1

- **Backend pytest:** `test_entry_platform_route.py` **13 → 23 PASS** — the two account-discovery actions (ESPN `my_leagues`, MFL `auth_leagues`): shapes, flag gates (`espn.league_picker`/`mfl.auth_link` on top of the feature flag), cookie-XOR and missing-credential 400s, bad-login 403 `mfl_bad_credentials`, `bad_action` 400, and a shared `_assert_stored_nothing` helper proving no users/credentials/leagues/sessions are created. Full suite **4,359 passed / 1 skipped** (5:38) on a tree that also carries the concurrent v1.16.7 session's tests.
- **Structural guard:** `check-landing-platform-options.js` **36 → 61 PASS** — V2.1 pins incl.: discovery calls sessionless + analytics-free, ESPN capture→sessionless my-leagues→existing picker, soft-fail keeps the manual field, `mflAuthEnabled` no longer excludes entry, entry sign-in single-select mints directly and never touches the bulk `mflAuthImport`, the in-flight password is a ref (never state) dropped before the best-effort re-store. One V2 assertion ("entry suppresses the MFL password path") deliberately superseded.
- **Typecheck** clean · **testid-lint** OK.
- **Subagent sabotage runs** (reverted): dropping the `espn.league_picker` gate and restoring `&& !entry` each turned exactly the expected test/guard assertions red.
- **Review:** lead session verified the backend serializations/signatures against the real my-leagues and auth-link routes directly, confirmed linked-mode render identity, and tightened the SignInScreen panel copy.
- **Owed (operator):** TestFlight checklist §V2.1 (3 steps) on the FIRST build after v1.16.7 — 1.16.7 carries entry v1+v2 only.

## 2026-08-26 — #360/#361 + #362 REBUILT on current main; #362 SHIPPED LIT, #360 held dark

**Branch:** `feat/jon-360-362` — the 2026-08-19 build (base `2a492b6`) merged with
`origin/main` `867c3baa` (123 commits: knockout refine D-159, full sweep, #384, package
pricing honesty #162, pick YoY floor, receipts/breaker/negmem).
This entry REPLACES the stale 2026-08-19i entry — those were the pre-rebase numbers.
Flags at ship: **`trade.standing_offers` `true`** (graduated, [D-165](DECISIONS.md)) ·
**`trade.avoid_positions` `false`** (held — [Q-031](OPEN_QUESTIONS.md) gen_v2 gap is live in
prod, [Q-032](OPEN_QUESTIONS.md) upheld). Records:
[360-avoiding-positions/](../docs/feedback/items/360-avoiding-positions/) ·
[362-standing-offer/](../docs/feedback/items/362-standing-offer/) · [D-166](DECISIONS.md).

**Gates were run THREE times and all three runs are reported here**, because the flag flip
was made between them and the middle run failed:

1. **Pre-flip (both flags dark), run by this session independently of the build agent:**
   `4336 passed, 1 skipped` in 364.57s, exit 0 — matching the build agent's reported number
   exactly. That cross-check is why the agent's other claims were taken as measured.
2. **Post-flip, first run:** `1 failed, 4335 passed, 1 skipped` (443.25s). The single failure
   was `test_standing_offers.py::test_flag_and_knobs_registered`, which asserted
   `features["trade.standing_offers"] is False, "ships dark"`. **No behavior broke — the only
   thing that failed was a pin on the dark posture itself.**
3. **Final, after updating the two dark-posture pins:** the numbers in the table below.

**Two independent guards pinned this flag dark and BOTH were changed to ship it lit** —
`mobile/tests/check-standing-offer-362.js` SC-14a ("graduation is an operator action after a
TestFlight pass on a real league") and the backend assertion above. Each now asserts `true`
and carries an in-file comment recording that graduation happened **without** the TestFlight
pass, per [D-165](DECISIONS.md). A repo-wide search found no third pin. `SC-14b` — the
`LAUNCHED_FLAG_DEFAULTS` absence check, which is the assertion that actually protects the
kill switch ([D-166](DECISIONS.md)) — was **not** touched and holds in both flag states.

| Gate | Result (final run, measured 2026-08-26 on the merged tree, flag lit) |
|---|---|
| `python3 -m pytest backend/tests -q` | **4336 passed, 1 skipped, 0 failed** (320.07s) |
| `npx tsc --noEmit` (mobile) | **exit 0, zero errors** |
| `bash mobile/scripts/testid-lint.sh` | **testid-lint OK**, exit 0 |
| all `mobile/tests/check-*.js` | **82 passed, 0 failed** (80 pre-existing + `check-avoid-positions.js` + `check-standing-offer-362.js`) |
| Sim gate | `FTF_SKIP_SIM_GATE=1` — D-056 standing posture; substitute evidence: post-merge code-walks with merged-tree line cites (`360-avoiding-positions/code-walk.md` addendum, `362-standing-offer/code-walk.md`) |
| **Runtime evidence** | **NONE. Both TestFlight checklists remain UNRUN.** |

**Three merged-tree failures found and fixed (first full run: 4333 passed / 3 failed):**
1. `test_breaker_seam::test_bulk_readers_match_the_singular_loaders` — main's breaker
   added `load_league_preferences_bulk` promising per-row shape identity with the
   singular loader; it predated `avoid_positions`. The bulk row now carries the key.
2. `test_avoid_positions::test_no_avoided_position_received[v2]` and
   `::test_avoid_qb_keeps_pick_rungs` — NOT the avoid filter: main's `d42872f2`
   ("package pricing honesty + gap auto-sweetener", #162, bisected on pristine main)
   stopped admitting 1-for-1s that lose seed value for the giver, starving the tests'
   BASELINE premise. Fixture now seeds coveted receive assets at parity (1540);
   assertions unchanged.
Also: the merge union dropped `seasonSpan`'s closing brace in `TradeCard.tsx`
(caught by `tsc`, restored).

**ID de-collisions this session** (parallel sessions took the branch's IDs on main):
D-098→**D-166**, Q-026/027/028→**Q-031/032/033**, G-053→**G-062** (+ its missing
GOTCHAS index row added), M-005→**M-006**; PRD-local decisions renumbered item-scoped
D-093…D-096→**D-360-1…D-360-4**, #362's D-093→**D-362-1** (the D-306-1 convention —
main took D-093–D-097). Every cross-reference updated; `feature_flags.py` /
`features.json` stale "ships ON" comments corrected to the Q-032 dark ruling.

**Not claimed:** that either feature behaves correctly on a device — no runtime
evidence exists until the two TestFlight checklists run with the flags lit.

## 2026-08-26b — Platform entry decoupled from Apple (D-164) — full gates

Scope: [docs/plans/landing-platform-options/scope.md](../docs/plans/landing-platform-options/scope.md) §V2 · code-walk §V2 · decision: [D-164](DECISIONS.md)

- **Backend pytest:** new `backend/tests/test_entry_platform_route.py` — **13/13 PASS** (flag gating feature+platform, bad platform, MFL preview persists/mints nothing, deterministic `entry:mfl:` mint + users row + idempotent re-claim, bad franchise 400, ESPN preview shape, cookie XOR, SWID-keyed id, #321 wrong-account 403, bad team 400, private→`espn_auth_required`, and the end-to-end proof: minted token drives the real `/api/mfl/link` import and binds the claimed franchise to the entry user in `league_members`). Full suite **4,289 passed / 1 skipped** (5:42).
- **Structural guard:** `check-landing-platform-options.js` extended to **36/36 PASS** — V2 pins: no Apple in the panel, mint-before-canonical-import in both sheets, session-dependent paths suppressed in entry mode, `account_only` entry user, token stored + signin funnel in the api layer, route sessionless + dual-gated + deterministic `entry:` ids via `_extension_build_session`.
- **Typecheck:** `npx tsc --noEmit` clean · **testid-lint:** OK.
- **Owed (operator, next TestFlight build):** checklist v2 in scope §V2 — public ESPN claim with no Apple prompt anywhere, private ESPN via the ESPN WebView, MFL claim, relaunch persistence, Sleeper flow unchanged, sign-out→re-claim recovers the board. Supersedes v1 §3 steps 2–4.

## 2026-08-26 — Landing platform options (Sleeper · ESPN · MFL entry chips) — full gates

Scope: [docs/plans/landing-platform-options/scope.md](../docs/plans/landing-platform-options/scope.md) · code-walk: [code-walk.md](../docs/plans/landing-platform-options/code-walk.md) · decision: [D-163](DECISIONS.md)

- **Structural guard:** `mobile/tests/check-landing-platform-options.js` (`npm run test:landing-platform-options`) — **20/20 PASS**. Pins the dual flag gate, per-platform chip gates + de-flag fallback, intent forwarding on both Apple branches, the s0.2 guide advance, RootNav's intent→param mapping, the MFL auto-open's #266 deferral, the auto-skip block, and the two-sided flag registration.
- **Typecheck:** `npx tsc --noEmit` (strict) — clean.
- **testid-lint:** `bash mobile/scripts/testid-lint.sh` — OK (new `signin.platform-*` ids are flow-unreferenced).
- **Backend:** `pytest backend/tests` — **4275 passed, 1 skipped** on first run with one failure (`test_release_flags_mirror_features_json` — the new flag key missing from the mirror fixtures); fixed by adding `landing.platform_options: true` to `release.json` / `profiles-on.json` / `onboarding-v2.json`, after which `test_seed_ui_test_db.py` is **76/76 PASS**. No backend behavior changed (FLAG_KEYS + fixtures only).
- **Owed (operator, next TestFlight build):** the 6-step runtime checklist in scope.md §3 — chips render, ESPN chip → Apple → ESPN sheet auto-opens un-wedged (#266 class), MFL twin, Sleeper flow unchanged, single-league auto-skip yields to the MFL intent.

## 2026-08-26 — `fix/web-phase0` merged with `origin/main`; full gate set re-run green on the merged tree

**Every number below was measured on the merge commit `b4f29220` + `6cd163a4`, on this tree.** The
stale figures carried on the branch (161/161 web checks, "backend not re-run") are superseded — do
not quote them.

Full gates, not express: the branch touches API surface and analytics, which `CLAUDE.md` marks as a
bright line ([D-163](DECISIONS.md) §D5). Express was never available here.

| Gate | Result |
|---|---|
| `pytest backend/tests` | **4286 passed, 1 skipped** in 445.16 s (includes the 10 new cases below) |
| `npx tsc --noEmit` (mobile) | **exit 0**, zero output (after `npm ci` — this worktree had no `node_modules`) |
| `mobile/scripts/testid-lint.sh` | **`testid-lint OK`** |
| `python3 qa/web/check_web_structure.py` | **173/173** — DS 80/80 · TOK 1/1 · SEO 50/50 · A11Y 38/38 · HYG 4/4 |
| `mobile/tests/check-*.js` (81 suites) | **all pass**, zero failures |

**Merge verification, not just "it applied clean".** 140 commits of `origin/main` drift since base
`50e0451d`. `backend/server.py` and `web/js/app.js` both **auto-merged**, which is exactly the case
worth distrusting, so both sides were checked present afterward by grep on the merged file: the
branch's flag-readiness fix (`FTF_FLAGS_READY`, `ftf:flags-ready`, the `pending[]` drain in
`events.js`) **and** main's `FAIRNESS_BALANCED_MIN = 0.75` cross-client invariant with its
`consensus-tag` tooltip block. Both intact. The five conflicts were all append-at-top ledger files.

**New: `backend/tests/test_prod_blocked_static.py` (10 cases).** Pins `_PROD_BLOCKED_STATIC` in both
directions — the four blocked paths 404 when `_IS_PROD_ENV`, all four still serve 200 in dev (that is
how the operator reaches the dashboard), the set is exactly those four, and `/index.html` is not
caught by an over-broad block. **Verified non-vacuous:** removing the `/admin/analytics.html` entry
turns 2 of the 10 red. This is the mechanically-checkable evidence the gates require for the
admin-block change; no code-walk proof is owed for it.

**Gotcha renumber.** The branch's `G-053` collided with `origin/main`'s `G-053`…`G-061` and was
renumbered to **[G-067](GOTCHAS.md)**. One cross-reference (`HANDOFF.md`) moved with it. No
anchor-style `#g-053-…` links existed anywhere in the tree, so the [G-054](GOTCHAS.md) trap — a
blanket ID replace that rewrites headings but not their anchors — did not apply. Checked, not assumed.

**Not run, and why:** no EAS build, no TestFlight pass, no simulator (retired, D-056). Nothing in
this merge touches mobile source — the mobile gates were run only to prove the *merge* is green, not
because mobile behavior changed. `githooks/pre-push` still enforces the retired simulator marker;
`FTF_SKIP_SIM_GATE=1` is the standing D-056 posture and the five gates above are what was run instead.

**Still owed before this ships to users:** the operator's manual pass on the live site after deploy.
The web surface has no runtime harness — `check_web_structure.py` parses source and never loads a page.

---

## 2026-08-25 — v1.16.6 (EAS build 132) BUILT + SUBMITTED to TestFlight

Carries PR #196's `via:'quickset'` tag ([D-162](DECISIONS.md)) — the first build in which the Quick Set funnel can emit anything.

| Gate | Result |
|---|---|
| Version sources (G-012) | All three iOS spots set to 1.16.6 — `app.json`, `Info.plist` `CFBundleShortVersionString` (the literal that actually ships here), both `MARKETING_VERSION` lines. Verified on the build source commit before upload |
| CI on the release sha (`cb691b25` → merged `c092f808`) | backend-tests · mobile-typecheck · testid-lint all **pass** |
| EAS build `8925880d` | **finished** — v1.16.6 (132), commit `c092f808`, profile production |
| Submission `b190d30b` | **finished** — ASC app 6771488431, auto-submit. Apple-side processing then TestFlight availability is out of our hands |
| Archive hygiene (G-022) | Built from the 561 MB worktree, NOT the 9.5 GB main checkout (5.9 GB of nested worktrees there — the condition that once failed an upload) |

**Owed runtime evidence, now runnable on 132:** the via-gap checklist ([scope §3](../docs/plans/quickset-analytics-via/scope.md)) — expect `quickset_completed` rows + `tier_save.props.via = "quickset"` for a real walk, and `via:"tiers"` with no `quickset_completed` for a plain Tiers save. Checklists **H** + **I1** (Wave A / flag-off regression) were owed on 130 and are also testable here.

## 2026-08-25 — Merge-day addendum to 2026-08-24b: main merged in, D-162 renumber, Aug-25 calendar flake pinned (G-061)

Merging `origin/main` (Group F + feedback wave + Waves A/B0 + pick YoY floor) into the via-gap branch surfaced two things. (1) Main took D-160/D-161 overnight → this branch's decision renumbered **D-162**; `via:'quickset'` verified intact alongside Group F's HOLD changes (`check-quickset-via` + `check-quickset-hold` + `tsc` green on the merged tree). (2) The merged-tree suite failed `test_notif_teardown`'s three winback tests — **because the run date was Aug 25**: the daily tick's `is_aug25` season_start fan-out skips every winback that day, so the real clock was a hidden test input ([G-061](GOTCHAS.md), the G-059 pattern). Fixed by pinning the tick clock in those tests + a new pinned `test_season_start_fanout_on_aug25`; file 19/19 green. Remaining local failure: `test_deck_signal_v2` only — **CORRECTED 2026-08-25: caused by the stale `data/trade_finder.db` in this worktree, not Python skew** (pristine data dir → passes). It reproduced on a clean git tree because `git stash` does not touch the gitignored DB, which is exactly why the clean-tree check looked like it exonerated the code.

## 2026-08-24b — Quick Set `via` gap fix — full gates, on `claude/elegant-feynman-c3689e` (D-162; held for operator)

Scope: [`docs/plans/quickset-analytics-via/scope.md`](../docs/plans/quickset-analytics-via/scope.md) · addendum [`2026-08-24-quickset-via-gap.md`](../docs/business/analytics/2026-08-24-quickset-via-gap.md). One emitter change (unscoped mobile Quick Set saves tag `via:'quickset'`); no server code change, no taxonomy registry change.

| Gate | Result |
|---|---|
| `pytest backend/tests -k "not calibration_gate"` | **4226 passed, 1 failed, 1 skipped** — the failure (`test_deck_signal_v2.py::test_flag_on_writes_impressions_in_served_order`) reproduces on the **clean origin/main tree** (`git stash` → still fails) under local Python **3.14.4**; the known 3.12-skew class (this file, 2026-08-13). Unrelated to the change; CI on the PR sha is the arbiter — and PR #196 CI came back **all green** (run 32762214700). **CORRECTED 2026-08-25:** the cause is NOT Python-version skew — it is the stale `data/trade_finder.db` in this worktree (the 2026-08-24 HANDOFF's banked sharp edge). Proven: `mv data data.bak` → the test passes on the same interpreter. The skew attribution was a guess that fit; it was wrong |
| Server branch coverage (pre-existing, all green in the run) | `test_analytics_p0.py::test_quickset_completed_fires_with_props` + `::test_quickset_event_absent_for_plain_tier_save`, `test_rookie_scope.py::test_rookie_via_tags_are_recorded_and_do_not_fire_quickset_completed`, `test_events_api.py` disjointness pins |
| New structural guard | `mobile/tests/check-quickset-via.js` (`npm run test:quickset-via`) — 13 asserts green. **Sabotage:** non-rookie save arm reverted to `undefined` (the original bug) → guard RED on exactly the pinned assert; restore → green |
| `tsc --noEmit` (strict) | green |
| `testid-lint.sh` | OK (no testIDs touched) |
| Runtime | operator TestFlight checklist in scope §3 — UNRUN, owed after the next mobile release containing this change |

## 2026-08-24 — Pick YoY floor (D-161) — full gates, live-curve verified, on `claude/pick-yoy-floor-0824`

Plan: [`docs/plans/pick-yoy-floor/`](../docs/plans/pick-yoy-floor/plan.md). One Opus builder, Fable adversarial review (verdict: approve after two one-line fixes, both applied: the Q-018 closure relocation and a `try/finally` knob restore in `test_pick_pricing_m6b`).

| Gate | Result |
|---|---|
| `pytest backend/tests` | **4275 passed, 1 skipped** (builder run 301 s, reviewer run 306 s; +37 `test_pick_yoy_floor.py`) |
| Sabotages | 8 by the builder (S1–S8, module docstring), 3 re-run independently by the reviewer (S1/S4/S6), all byte-copy restores + `__pycache__` cleared per [G-060](GOTCHAS.md) |
| Existing-test dispositions | 12 failures judged individually: market-semantics tests pinned at knob 0 (both regimes stay pinned), served-pricing tests now expect the floored value with floor-is-active side assertions, one test overturned by name (its docstring pinned the pre-ruling behavior D-161 reverses), one evener re-fixture verified to reproduce the original geometry to 4 decimals |
| **Live curve (read-only prod DP)** | 1qb r1: 2027 1,750.7 → **2,184.6** · 2028 1,459.4 → **2,184.6** · 2029 → **2,184.6** · current-year and rounds 2–4 unmoved · sf_tep floors at 2,434.0 |
| Reference case | The MangoPatti card family (A.J. Brown + depth for a player + three future firsts): the pick side reprices from ≈ 3 × 1,171–1,751 to 3 × 2,184.6 |
| Runtime | scope §3 checklist owed post-deploy: a served card carrying a 2027/2028 1st displays ≈ a current mid-first |

**Fable code-walk:** knob-0 byte-identity — at `market_r1_yoy_floor = 0`, `_r1_yoy_floored` returns the raw market value before the anchor read and before any second market lookup (loader-call counter pins 1 load at knob 0, 3 at default). Four paths untouched at every knob value: step-1 slotted picks (return before the clamp's path), rounds 2–4 (bail ahead of the anchor read — value and lookup count unchanged), `tier_ladder` (stored value before any DP read), the DP-absent fallback (stored, None-guard proven load-bearing). Anchor = DP's own earliest slotted season; a stale rung-only season cannot steal it (S8); the DP-reader seam guard still asserts the exact reader set both directions. Judgment calls ACCEPTED with reasoning: anchor-lag risk is bounded (floor too high by one year's class drift, transient on DP's 24 h TTL, and under the flat ruling the pick still serves ≈ a current mid); the [0,1] clamp mirrors `year_decay`'s for the mirrored arbitrage.

## 2026-08-24 — Feedback wave (5 groups, 11 items): full gates green on `claude/new-user-feedback-55320e`; TestFlight checklists owed

Batch: [`docs/feedback/items/346-quickset-tier-drop/plan.md`](../docs/feedback/items/346-quickset-tier-drop/plan.md).
Groups A (#376/#379/#394 outlook & filters row), B (#397/#398 tour pin), C (#395/#396 lineup impact),
D (#386/#391 guide layout notify), F (#346/#381 QuickSet HOLD, [D-160](DECISIONS.md)). All fast-track, full gates, no express.

- **Phase 1:** dual-agent plan/author/critique per group; every critique round found real defects
  (self-satisfying checklist steps in B/D, a blacklist-beatable guard spec in A, two self-satisfying
  pytest sabotages in C caught by hand-recomputation, 7 contract amendments in F). All resolved, logs in each folder.
- **Phase 2:** 7 build agents in isolated worktrees, disjoint ownership held; merges clean
  (one intended status.md both-halves conflict, resolved keep-both).
- **Phase 3 (round 1, agents A+B independently, commit `c8b0e224`):** both PASS all five groups.
  `tsc --noEmit` clean · **78/78** `mobile/tests/check-*.js` green · testid-lint OK · full
  `pytest backend/tests` **4238 passed / 1 skipped** (×3 independent clean runs) · every PRD sabotage
  mapping re-proven red→green by both agents independently (12 in A, 5+2 probes in B, 6+2 in C, 4 in D, 7+guard-13 in F)
  · `web/`+`extension/` diff empty · Group F mobile↔backend payload shape verified consistent.
  One convergent finding (F-1, minor): Group F T-2's sabotage wording overstated (conditional echo only) — PRD tightened, no code change.
- **Known environment gotcha (recorded):** `test_deck_signal_v2.py::test_flag_on_writes_impressions_in_served_order`
  fails against a `data/trade_finder.db` left by a previous full sweep in the same tree; fresh data dir passes.
  Not a code regression (bisected: same commit passes clean).
- **Version:** mobile 1.16.4 (app.json + Info.plist; `test_app_version_consistency` green).
- **Owed (the only runtime evidence, D-056):** the five operator TestFlight checklists —
  consolidated in [`docs/feedback/items/346-quickset-tier-drop/testflight-checklist-batch.md`](../docs/feedback/items/346-quickset-tier-drop/testflight-checklist-batch.md).
  CI on the pushed sha pending at entry time; ship gate = operator go/no-go.
## 2026-08-24c — Waves A + B0 SHIPPED — PRs #197/#199, EAS 1.16.4 (130) submitted

Wave A merged as `7452650` (CI green: backend 9m14s · typecheck · lint) with the Fable review's A1/A2/A4/A6 fixes on top (gates re-run on `274a0ea9`: tsc · 77/77 · lint · pytest 4230/1). Wave B0 rebased over it and merged as `14a4ce4` (CI green) with review fix B1 (MatchesScreen prefill) + the reviewer's doc-conflict resolutions (checklist H→I, steps 79–99); gates on the rebased tip: tsc · 78/78 · lint · pytest 4230/1. `git diff feat/inline-home-b0 origin/main` EMPTY at merge. EAS production **1.16.4 (130)** built and submitted to App Store Connect (submission `a7b08771`). `FTF_SKIP_SIM_GATE=1` on pushes (D-056). **Owed on 130:** checklist section H (63–78; 63–67 on a COLD league load) and I1 (79–83, flag-off regression). `calc.inline_home` stays false until Wave B.

## 2026-08-24b — Wave B0 the layout merge (`calc.inline_home`) — full gates, FLAG DARK, NOT MERGED, on `feat/inline-home-b0`

Scope: [`docs/plans/onboarding-tour-merge/scope-wave-b0.md`](../docs/plans/onboarding-tour-merge/scope-wave-b0.md) · [D-158](DECISIONS.md) · plan §3b. Branched from `origin/main` @ `ff153a0f`. **No PR, no merge.**

| Gate | Result |
|---|---|
| `mobile` `tsc --noEmit` | clean, exit 0 |
| Every `npm run test:*` guard | **78 ran, 0 failed** (77 existing + the new `test:inline-home`) |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` |
| `python3 -m pytest backend/tests -q` | **4230 passed, 1 skipped**, 336 s, exit 0 |

**New guard `mobile/tests/check-inline-home.js`** (10 sections, 46 assertions). Pins, in order: the flag ships **false** in `config/features.json` with a D-158/kill-switch comment, is mirrored false into `release.json` / `onboarding-v2.json` / `profiles-on.json`, and is registered in `backend/feature_flags.py`; **exactly one** `<TradeBuildCanvas>` mount, with `canvasHost` resolving the flag path AHEAD of the #270 experiment and the experiment's own `!firstRun && !singlePin` gates intact; the rail dies only on the flag path and `showSuggestionRail` defaults to `true`; no `onShowMeAround` reaches the inline mount; the pushed page's tour is refused at BOTH doors with the guard as an effect dep, and `utils/calcTour.ts` is untouched (Wave A owns it); the fork and the ✓ queue are each **one definition, two callers, no second emitter**; the inline search neither navigates nor writes a handoff, stamps `deckOrigin:'calculator'`, and adds no `generateMutation.mutate` site (count still 8); the receipt's **Clear IS `handleSearchAllTrades`** and both end-of-deck Search-all buttons stand aside for it; all three `navigate('TradeCalculator', {prefill})` calls survive for the flag-off path; `CHIPS` still says `Calc`.

**Existing guards updated to the new truth, none deleted:** `check-calc-merged-behavior.js` 13/13a/13b re-pointed at `utils/canvasSearch.ts` (the fork moved files, the contract did not) plus new 13c–13e; 18a–18f re-pointed at `utils/queueCalcTrade.ts` plus new 18h/18i. `check-offer-prefill-330.js` — the choke-point region/dep pattern now admits the added `canvasRunSeq` trigger, with the three original deps still required in order. `check-calc-tour.js` 15a — the auto-start dep list gained `inlineHomeOn`, the fifth guard.

**Caught by the gates, not by review:** the first full pytest run failed `test_entitlements.test_features_json_keys_known` — a new `config/features.json` key must also be registered in `backend/feature_flags.py` `FLAG_KEYS`. Fixed and re-run clean. (The three-fixture mirror was done up front; only release.json is exact-mirror-tested, but onboarding-v2/profiles-on are what other suites boot from.)

**Code-walk (flag-off byte-identity), full trace in the scope block §3.** Each behavior change is one gated site whose flag-off value is the original expression: `TradesScreen.tsx:4887` `canvasHost` collapses to the old mount condition; `:4901` `inlineAnchorShown` is unconditionally false, which makes the receipt unreachable and restores both end-of-deck conditions; `:1410/:2855/:2940` early-return above untouched `navigate` calls; `:2607`'s added dep `canvasRunSeq` is a frozen `0` (its only writer is inside a handler passed as a prop only on the flag path); `TradeCalculatorScreen.tsx:129/193/233/685/747/782` each reduce to the pre-wave expression; `TradeFinderModeBar.tsx:147` falls back to `c.label` with `CHIPS` untouched; `TradeBuildCanvas.tsx` reads no flag at all — every change is an optional prop with a today-preserving default.

**Runtime evidence: NONE, and that is the known gap.** Section **I** of [`docs/feedback/items/384-calc-finder-merge/testflight-checklist.md`](../docs/feedback/items/384-calc-finder-merge/testflight-checklist.md) is new and **unrun** — I1 is 5 flag-OFF regression steps (79–83, the pass that matters while the flag is dark) and I2 is 15 flag-ON steps (84–98). (Lettered H→I and renumbered at the Wave-A rebase; the content is unchanged.) The two things no structural guard can see: the **ordering** inside the #330 choke point when the inline search re-fires it (reset → fork → dispatch), and the **layout** of a full In-league calculator stacked above a swipe deck on a small screen. Under D-056 that checklist is the only runtime proof this can get.

**Pre-push gate:** `FTF_SKIP_SIM_GATE=1` (D-056 standing posture — the simulator marker `qa/sim-runs/last-sim-run.json` is retired); the evidence run instead is the four gates above plus the new guard.

## 2026-08-24 — Onboarding-tour Wave A — full gates green on `feat/tour-wave-a`; runtime evidence owed

Scope block: [`docs/plans/onboarding-tour-merge/scope-wave-a.md`](../docs/plans/onboarding-tour-merge/scope-wave-a.md)
(§5 carries the file:line code-walk for both new parks). Full gates, **not** express.

| Gate | Result |
|---|---|
| `pytest backend/tests` | **4230 passed, 1 skipped**, 333 s, exit 0 |
| `npx tsc --noEmit` (mobile) | clean, exit 0 |
| Every `npm run test:*` guard | **77/77 passed** (looped over `package.json`, none skipped) |
| `mobile/scripts/testid-lint.sh` | OK |
| Assertion counts on the three extended suites | `check-calc-tour` 168 ✓ · `check-guide-script` 455 PASS · `check-card-disposition` 17 PASS |
| `githooks/pre-push` simulator gate | **skipped** — `FTF_SKIP_SIM_GATE=1`, the standing posture under [D-056](DECISIONS.md). What ran instead is every other row of this table plus the scope block's §5 code-walk; `qa/sim-runs/last-sim-run.json` is deliberately not written |

**New structural coverage.** `check-calc-tour.js` §45 (a–n) pins both parks three ways each: the
park is taken at the right seam, it is **time-bounded** and expiry ends the run (an unbounded park
holds the interrupt hold and mutes every interstitial app-wide), and the resume is wired end to
end — screen prop → runner export → `requestAt`. 45c/45d/45e pin the **level** semantics of the
In-league ready signal; 45l/45m pin that the component's `inLeagueReady` predicate stays the
negation of the two early returns it derives from. §40d–40f cover n22's new target. New in
`check-card-disposition.js` §4: `trades.card-meter` is an effect registration gated on
`cardMeterMounted`, unregisters on teardown, and its wrapper is a non-collapsable `View`. New in
`check-guide-script.js` §10/§11: the ten converted beats are `cta` **with buttons**, and the only
`advance: 'tap'` beats left in the whole script are the two named exemptions (`s2.3` deprecated,
`n9` out of Wave A's scope) — the closed-set half is what catches a *new* tap beat.

**Sabotage verified (1).** Deleting the `if (inLeagueReady)` fast path from `calcTour.ts` turned
45c red; restoring it turned it green. The rest of §45 is regex-on-source and was written against
already-passing code, so it is pinned but not independently falsified.

**Two guards UPDATED to the new truth, not deleted.**
`check-guide-script.js` `8b` asserted `S.n6_1(false).ctas === undefined` — a statement about that
beat being tap-advance. Restated as the property that mattered: the router-less variant carries
exactly one plain `Next` and **none of the routing variant's buttons** (+ `8b-ii`, no lifetime
bound). `backend/tests/test_seed_ui_test_db.py::test_onboarding_v2_flags_are_release_plus_the_onboarding_surface`
asserted `landing.try_before_sync is True` in both flag files; now `is False` in both, with the
cross-file agreement — the thing that actually broke main CI on 2026-08-23a — left intact.

**Runtime evidence: ZERO, and two items genuinely need it.** New **section H** (steps 63–78) in
[the #384 checklist](../docs/feedback/items/384-calc-finder-merge/testflight-checklist.md), unrun.
Steps 63–67 must be run on a **cold** league load: both parks fix a *race*, and a warm React Query
cache is exactly what made the W8 simulator pass a false green while note 12 stayed open. Step 64
(airplane mode) is the one that proves a park that never resolves still releases the hold.

## 2026-08-24 — Knockout refine (R5/R1/R2/shape) — full gates, MEASURED on prod FFV3, on `claude/knockout-refine-0823`

Plan: [`docs/plans/knockout-refine/`](../docs/plans/knockout-refine/plan.md) · [D-159](DECISIONS.md). Built by Opus B1/B2, adversarially reviewed by a Fable reviewer (verdict: safe to merge; the D-159 renumber + two doc fixes, all done pre-merge).

| Gate | Result |
|---|---|
| Full `pytest backend/tests` | **4230 passed, 1 skipped** (lead run 454 s and reviewer run 442 s, both exit 0; +19 `test_knockout_refine.py`, +13 `test_shape_knob.py`) |
| Byte-identity at off settings | 210-pair verdict sweeps against predicates vendored from `c321958` (reviewer diffed the vendored copies against `git show` — the true old bodies) |
| Sabotages | B1: 8 · B2: 3 · reviewer re-ran 3 independently. All byte-copy restores; see [G-060](GOTCHAS.md) for the `.pyc` trap two of these hit |
| Operator invariants (reviewer, incl. scratch end-to-end) | #341 double-startable-RB strip dies at every knob setting; #304 Loveland dies with the rescue lit; a delta-2 3-for-1 that strips a position below startable depth is emitted by the optimizer and killed by R2 relief |
| **Measured (read-only prod replay, league `1312140920132497408`, 4 variants)** | baseline 280 cards / 270 ideas / 1 consolidation-family card / 18.1% sub-450 share · **bundle+raw-R1 280 / 267 / 8 / 19.4%** · bundle+adjusted-R1 275 / 260 / 8 / 17.9% · filler-0.10 276 / 263 / 10 / **27.0%** |
| Flip decision from the measurement | `filler_min_frac` **0.15** (0.10 doubles junk share) · `overpay_adjusted` **0** (adjusted killed ~7 consolidation ideas incl. 2x1s 28→21 for a 1.5pp junk benefit) · `trade_elo_gap_max` **0** · `v3_shape_max_delta` **2**. Applied via admin config API after the deploy seeds the new rows; each individually revertible |
| Runtime | scope §3 checklist owed post-flip (3-for-1s appear; no card strips a position below startable depth on either side) |

**Reviewer code-walk:** at the off settings every predicate is verdict-identical to origin/main @ c321958 — `overpay_ok` knob<1 takes the untouched raw-sum branch; `pos_net_ok` reduces to the old `all(abs(n)<=cap)` with the relief unread when the knob is 0 or ctx is None; `need_gate_ok` at knob 0 runs the refactored-but-equivalent primary-only checks; the optimizer's `SHAPE_D=int(_c(...))=1` reproduces the literal `>1`. `opp_ctx` is early-bound per member via a lambda default arg; the boarded-branch consensus fallback shares the member-scoped kwargs, so no caller sees another member's context.

## 2026-08-24 — `mascot_ram_rollout` gate verified on production

`GET /api/feature-flags` × 3, against live production:

| Request | `experiments` | overlay | base flag |
|---|---|---|---|
| allowlisted device id | `mascot_ram_rollout: treatment` | `{onboarding.mascot_ram: true}` | `false` |
| no device header | `{}` | absent | `false` |
| random device id | `{}` | absent | `false` |

**This proves the gate, not the render.** It shows the overlay reaches exactly one unit and no other. It does **not**
show a ram on a screen — the TestFlight checklist is still unrun, and section A (flag OFF is byte-identical) should be
run *before* trusting anything under flag ON.

## 2026-08-24 — v1.16.3 (129) to TestFlight: CI green on GitHub, runtime evidence still owed

**CI on the pushed sha (not just local):** `backend-tests` pass 8m58s · `mobile-typecheck` pass 1m2s ·
`maestro-testid-lint` pass 10s. Merge state `CLEAN` before squash.

**Local, post-merge, after the version bump:** pytest **4198 passed, 1 skipped**; `tsc --noEmit` clean; 77/77
`check-*.js`; testid-lint OK.

**`test_app_version_consistency` earned its place.** Bumping `app.json` to 1.16.3 without
`ios/DTFDynastyTradeFinder/Info.plist` failed immediately — exactly the bare-workflow trap D-057 documents.

**Runtime evidence: still ZERO.** The build exists and is processing at Apple, but
[the checklist](../docs/plans/ram-mascot/testflight-checklist.md) is unrun and cannot be run until the build is
installed **and** `mascot_ram_rollout` is launched. Until both, the app on TestFlight renders The Analyst — which is
itself checklist section A, and the first thing to verify.

## 2026-08-23b — `test_stud_tax_pinned_market` flake pinned: breaker wall-clock budget removed from test inputs

**Diagnosis, with a deterministic repro.** The CI failure on `8fd23e2` (run 32681703490) was the breaker's 250 ms
`breaker_ms_budget`: past the 0.6× pass-2 checkpoint (`trade_breaker.py:929`) a stamp's payload changes
(`skipped: {reason: "budget"}`, pass-2 classes emptied), so the stamp-twice-and-compare tests had wall clock as a
hidden input. Reproduced exactly (same assertion diff) by skewing `trade_breaker.time.monotonic` +12 ms/call during
the second stamp only — the asymmetry a loaded runner produces. Not fixture pollution, not iteration order. Full
write-up: [G-059](GOTCHAS.md).

**Fix + evidence.** `_env` autouse fixture in `backend/tests/test_trade_breaker.py` pins
`breaker_ms_budget = 10**9` (budget rungs keep their own coverage via `_snap_with` / fake clocks). Verified:
67/67 `test_trade_breaker.py` under a hostile clock (+12 ms on *every* `monotonic()` call — pre-fix this fails);
full suite `python3 -m pytest backend/tests -q` → **4198 passed, 1 skipped** (6m22s, local).

## 2026-08-23 — Fleeced mascot swap (`onboarding.mascot_ram`), CI green on `claude/ram-mascot-fleeced`

**Ran, and what each proved.**

| Gate | Result | What it actually proves |
|---|---|---|
| `pytest backend/tests` | **4198 passed, 1 skipped** | The new flag key registers cleanly. No server behaviour branches on it |
| `npx tsc --noEmit` | **clean** | The switch and `RamAvatar` typecheck under `strict` |
| `for f in tests/check-*.js` | **77/77 pass** | Including the new `check-mascot-ram.js`. No existing guard regressed |
| `mobile/scripts/testid-lint.sh` | **OK** | No testID moved — the `guide.avatar.<pose>` id is on the wrapper, not the avatar |

**`check-mascot-ram.js` was sabotage-tested, which is the only reason to trust it.** Forcing the gate
(`useOnboardingFeature(...) || true`) → caught. Re-exporting a sprite trimmed to its bounding box → caught, reporting
**97.9 % ink against the 70 % target**. Both reverted; guard green. The inset check decodes the PNG alpha channel
itself (RGBA8 and palette+tRNS) rather than trusting file size — and it caught its own blindness first, failing
"inset measurable" when it only handled RGBA and the sprites were palette PNGs.

**Copy pass (same day).** `check-guide-script.js` extended so `lineRam` takes the same per-class word cap as `line` — without it the ram variant would have been an uncapped side-door into the copy budget. Sabotage-tested: a 30-word `lineRam` on a `tap` beat (cap 20) → caught. `check-mascot-ram.js` gained six copy assertions; hardcoding `>The Analyst<` back into `AnalystGuide` → caught. Full re-run after the copy work: **4198 passed, 1 skipped**, `tsc` clean, 77/77 guards, testid-lint OK.

**A pre-existing CI failure was fixed, not introduced.** `test_release_flags_mirror_features_json` was **already red on
`origin/main`**: `trade.full_sweep` was lit in `config/features.json` by #182 without updating
`backend/tests/fixtures/flags/release.json`. Verified against `origin/main` before touching it — unrelated to this
feature, but it blocked the "CI green" gate for everyone.

**The drift was wider than one file, and the first fix was incomplete.** Correcting `release.json` alone then broke
`test_onboarding_v2_flags_are_release_plus_the_onboarding_surface` and `test_profiles_on_flags_turn_on_public_pages_only`,
because those fixtures assert an exact divergence set from release. #182 had updated **none of the three**. All three
now carry `trade.full_sweep: true` and the divergence sets are back to their single intended key each. Worth noting for
the next flag flip: lighting a flag in `config/features.json` means updating **three** fixtures, not one.

**NOT run — owed:** [the TestFlight checklist](../docs/plans/ram-mascot/testflight-checklist.md). It needs a build
containing `assets/mascot/ram/` (bundled sprites, no OTA channel) and the `mascot_ram_rollout` experiment running. Until
then there is **zero runtime evidence** for this change — the guard proves shape, `tsc` proves types, neither has seen a
sprite on a screen.

## 2026-08-23a — main CI red → green: full-sweep fixture mirrors flipped

The full-sweep flip (2026-08-22j, LIT at merge) updated `config/features.json` but not the fixture mirrors, so `test_seed_ui_test_db.py::test_release_flags_mirror_features_json` failed on every `main` run after it (first surfaced on docs-only PR #184). Fix: `trade.full_sweep` → `true` in `release.json` / `onboarding-v2.json` / `profiles-on.json` (`all-on`, `release-300`, `release-espn-send-off` never carried the key). `python3 -m pytest backend/tests -q` on the fix branch: **4198 passed, 1 skipped** (5:20). Reminder the mirror rule exists for: flag flips update the fixtures in the SAME commit.

## 2026-08-22j — Full sweep (`trade.full_sweep`) — full gates; LIT 2026-08-23 by operator instruction at merge

Plan + scope: [`docs/plans/full-sweep/`](../docs/plans/full-sweep/plan.md) · [D-154](DECISIONS.md). Built by Opus agents A1 (engine/flag/knobs/tests) and A2 (arm parity + docs), adversarially reviewed read-only by A3 (2 blockers, 7 should-fix, 5 nits — all closed before commit), lead-reconciled.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q -x` | **4198 passed, 1 skipped** (+17 `test_full_sweep.py`, +8 `test_arm_sweep_parity.py`; bake-off arm-A golden green with two new `_PINNED_KNOBS` rows) |
| `tsc --noEmit` / `check-*.js` / `testid-lint` | unaffected — no client change (no new testID) |
| Sabotages, `test_full_sweep.py` | unconditional `break` restored at either loop → the matching `[legacy]`/`[v2]` visit test red (loops pinned independently); time rail deleted from either loop → red; `> 0` disable inverted → both budget-0 tests red; flag dropped from the rail → the flag-off leak test red; clamp dropped at either `server.py` site, or either site reverted to the bare constant → the AST pin red. All restored from byte copies (not `git checkout --` — uncommitted branch). |
| Sabotages, `test_arm_sweep_parity.py` | `trade_gen_v2.py` break after 2 members → 3 red; `trade_gen_fit.py` 2-member break → 2 red. A3 re-ran four of the above independently and reproduced every one. |
| Runtime | **none yet** — server-side flag, no client build needed. Operator lit the flag at merge (2026-08-23), ahead of the [scope §3 TestFlight checklist](../docs/plans/full-sweep/scope.md); the checklist (≥ 9 of 11 partners; `gen_ms` recorded; kill switch proven) is now the **post-flip verification**, still owed here. |

**A3 code-walk — `trade.full_sweep` OFF produces byte-identical output to `origin/main` @ `b6e906a`.** (a) `git grep -n trade_full_sweep -- backend/ config/` → exactly two executable reads, the guarded exits in `_generate_trades_impl` and `_generate_trades_v2`; the guard is `if not FLAGS.trade_full_sweep and len(new_cards) >= global_target: break` — flag off ⇒ the identical shipped test, same position; the time rail is `if FLAGS.trade_full_sweep and …`, never evaluated flag-off. (b) No other read: no `is_enabled("trade.full_sweep")`, no import-time capture; `DEFAULT_FLAGS` derives `false` from `FLAG_KEYS`; `features.json` ships `false`. (c) `_deck_cfg` returns a float, both `server.py` reads wrap `max(1, int(...))`; executed: key present → 5, key absent → fallback constant → 5; `_split_exploration_pool(cards, 5) == split(5.0)` on a 4×9 fixture — identical partitions. (d) `FLAGS` is a process-global `_FlagsProxy` (verified at runtime), so every bake-off arm reads the same value; `model_a()`/`model_challenger()` wrap only the thread-local `_cfg_override`. (e) The one addition on the flag-off path is a single `time.monotonic()` capture per loop entry (`_sweep_t0`) — no behavioural effect; "byte-identical output", not "no added instruction". (f) `git diff origin/main -- backend/trade_service.py backend/server.py` contains nothing beyond plan §3.2/§3.3/§3.5.

**A3 findings closed:** B1 v3 pairs have no deadline → `full_sweep_budget_s` rail (30 s) + every doc corrected; B2 flag is global so arm A sweeps too → accepted + recorded in `scope-phase2.md`; S1 `bakeoff_serve_interleaved` is **1 in prod** (A3 read the local DB) → docs state the dial under both postures; S2 wrong arm-A reason → rewritten in test + scope-phase2; S3 `max(1, …)` clamps; S4 G-058/Q-030 live on the review branch (`claude/trade-model-restrictiveness-7f3975`) — **merge that PR first**; S5/S6/S7/N1/N2/N4 wording; N5 `docs/plans/ram-mascot/brief.md` also proposes D-154 — first to land on `main` keeps it.

## 2026-08-22i — #384 W8 — simulator reproduction + mobile gates, v1.16.2 (EAS 128)

**First simulator evidence since D-056** (one-off debug of a live regression; the harness stays retired). Release build, iPhone 16 / iOS 18.4, against production. Reproduced the blank-band bug on the sign-in username beat on `origin/main` (`d79f9f4`), then on the fix: username beat, n10, n11 (Set outlook), n12, n13, n15, n16 all render ring + avatar + bubble + Next/CTA. Not reached: n18 → deck (session unverified → `verification_required` on generation and outlook writes). `npx tsc --noEmit` clean · 76/76 guards (spotlight §14 a–f, calc-tour 29/41/42 new; sabotage: native driver back on / activation-keyed spring → 3 red) · `testid-lint OK`. Backend untouched.

**Second simulator pass (same branch, pre-build):** after the first-landing fixes (timer fallback, latch-on-cutout + live offset, hold-before-teardown) — launch → Acquire → Manual calc auto-starts n10 with the ring on the In-league tab and the band directly beneath it (no overlap, no deck-beat hijack); tap In league → n11 rings the outlook row, bubble above with "Set outlook"; "Show me around" replays from n10 with ring + band. Found and fixed in the same pass: auto-start with n10 capped opened on n12's degrade line (calc-tour 44/44a). Final gates on the tip: `npx tsc --noEmit` clean · 76/76 guards · `testid-lint OK`. Simulator setup trap recorded as [G-057](GOTCHAS.md) (debug Hermes under a `Release` marker → SIGSEGV at launch). **Shipped:** squash PR [#179](https://github.com/mattmurf77/fantasy-trade-finder/pull/179) → `fe77b28`; CI on the PR green (backend-tests 8m53s, typecheck, testid-lint). EAS production build **1.16.2 (128)** `59b89897` finished and was submitted to App Store Connect 2026-08-22 (submission `338a1549`); checklist §G is owed against 128.

## 2026-08-22h — #384 W7 device-feedback fixes — mobile gates, v1.16.1 (EAS 127)

Branch `fix/384-tour-device-feedback`. `npx tsc --noEmit` clean · 76/76 `check-*.js` · `testid-lint OK`. Backend untouched (pytest unchanged from 2026-08-22g). Sabotages red: fixed `top: 54` band, constant ABOVE branch, solver ignoring `insets.top`, a beat back to `advance:'tap'`, n20 losing its target, `trades.send-btn` registration deleted, calculator dropping `onContentSizeChange`, auto-start not listening for `transitionEnd`. **Runtime:** the operator's device report on build 126 IS the evidence this wave answers; checklist section G (steps 50–62) is owed against build 127. The placement *mechanism* (occlusion vs. far-from-ring) is inferred from correlation, not observed — if step 54 still shows a bare ring, suspect native-header z-order.

## 2026-08-22g — #384 SHIPPED — PR #172 `80dee42`, flags LIT, EAS build 1.16.0 (126) submitted

Pre-ship gates at `304f55a` (flags lit, fixture mirrors updated): `pytest backend/tests -q` **4173 passed / 1 skipped** · `npx tsc --noEmit` clean · 76/76 `check-*.js` · `testid-lint OK`. `FTF_SKIP_SIM_GATE=1` on push (D-056 standing posture — the evidence is the structural suite + the rewritten, now POST-ship, TestFlight checklist). CI on `main` run 32585974208: typecheck + testid-lint green; backend job still in progress when this was written. EAS production build **1.16.0 (126)** `01465dd0` finished 16:57Z and auto-submitted to App Store Connect (submission `9a89555f`). **No device run yet** — the checklist in `docs/feedback/items/384-calc-finder-merge/testflight-checklist.md` is owed against build 126.

## 2026-08-22f — #384 W6-A + W6-B — full gates, FLAG DARK, NOT MERGED, on `claude/manual-calculator-e2e-review-39a467`

W6-A (`d6c54cf`, ✓ queue contract, [D-152](DECISIONS.md)) and W6-B (fairness-only packages +
tour reshape, [D-153](DECISIONS.md)), each lead-reviewed line by line before commit.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **4173 passed, 1 skipped** (+26 `test_calc_trade_queue.py`, +19 `test_fair_packages.py`; asset-ideas + bake-off arm-A goldens untouched and green) |
| `cd mobile && npx tsc --noEmit` | clean |
| every `mobile/tests/check-*.js` (76, all `npm run`-wired) | 76 / 0 failed — `check-guide-spotlight-tracking` gained rule 10 (scroll announcement mandatory where guide targets sit in a ScrollView) |
| `bash mobile/scripts/testid-lint.sh` | OK |
| Sabotages | W6-A: 5 backend + 4 mobile red/restored · W6-B: toggle restored → red; fair anchor also arming the model → red (two guards); calculator `onScroll` dropped → red; idea give side ≠ anchor → red; random ids → red |
| Runtime | **none** — TestFlight checklist (`docs/feedback/items/384-calc-finder-merge/testflight-checklist.md`, rewritten for W6) UNRUN. Prerequisite flags incl. `onboarding.guide_v2` (false) still gate the tour |

## 2026-08-22e — #384 merged calculator W5 + guard hardening — full gates, FLAG DARK, NOT MERGED, on `claude/manual-calculator-e2e-review-39a467`

W5 answers the [2026-08-22 e2e review](../docs/feedback/items/384-calc-finder-merge/review-2026-08-22-e2e.md)
(5 P0 / 8 P1) in three build packages — `fcf3413` (analytics registration), `9dcd003` (the deck
side), `a52c91e` (the tour) — plus this evidence pass. Scope block:
[scope.md](../docs/feedback/items/384-calc-finder-merge/scope.md) (written retrospectively; gate 1
had been skipped). Decision: [D-150](DECISIONS.md), amended. Checklist:
[testflight-checklist.md](../docs/feedback/items/384-calc-finder-merge/testflight-checklist.md) —
rewritten against current behaviour, **still UNRUN**.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **4128 passed, 1 skipped** (+11 over W4 — the taxonomy/NON_INTENT registration) |
| `cd mobile && npx tsc --noEmit` | clean, exit 0 |
| every `mobile/tests/check-*.js` | **76 files, 0 failed** |
| `mobile/scripts/testid-lint.sh` | **OK** |
| `npm run test:<name>` coverage | **76 / 76** — the last 19 unscripted guards wired into `mobile/package.json` (additions only, 19 insertions / 0 deletions) |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, standing posture under [D-056](DECISIONS.md) |

**Guard hardening — 15 sabotages, all GREEN before / RED after.** The review's QA pass ran 61
cycles against W4's guards and found **12 that stayed green**. Each named case below was patched
into the real source, run against the guard as it stood at `a52c91e` **and** against the hardened
guard, then reverted (`git status --short` confirmed only `mobile/tests/` + `mobile/package.json`
modified afterwards).

| # | Sabotage | Guard | Before | After | Assertion that catches it |
|---|---|---|---|---|---|
| 1 | `const merged = useFlag('calc.merged_layout') \|\| true;` | `check-calc-merged-layout` | GREEN | RED | 4 — the flag read anchored to its whole statement incl. `;` |
| 2 | `const merged = !useFlag('calc.merged_layout');` | `check-calc-merged-layout` | GREEN | RED | 4 (same anchor) |
| 3 | `compact={true}` at both `TradeSide` mounts | `check-calc-merged-layout` | GREEN | RED | 4b — every `compact=` prop must read exactly `merged` |
| 4 | target-registration effect loses `if (!merged) return;` | `check-calc-merged-layout` | GREEN | RED | 4c — the effect body must bail; 4d pins `[merged]` deps |
| 5 | `if (give.length \|\| receive.length)` — Include OFF still pins | `check-calc-merged-behavior` | GREEN | RED | 13a — `includePlayers &&` must be IN the pin condition |
| 6 | `reasonsAsOverlay = calcMergedOn && deckOrigin === 'calculator' \|\| true;` | `check-calc-merged-behavior` | GREEN | RED | 1c — anchored to the statement terminator |
| 7 | `endTourHold: () => {}` | `check-tour-suppression` | GREEN | RED | 8 — the store is now transpiled and EXECUTED, not modelled |
| 8 | `beginTourHold: () => {}` | `check-tour-suppression` | GREEN | RED | 2a — `tourHold` read back off the real store |
| 9 | the `blocked_by:'tour'` `track()` call deleted, doc comment kept | `check-tour-suppression` | GREEN | RED | 13 — anchored on the emitter, not the phrase |
| 10 | `cursor = 0` dropped from `startCalcTour` (re-entry resumes) | `check-calc-tour` | GREEN | RED | 29a — the reset triple before `requestAt(0)` |
| 11 | auto-start effect deps `[]` | `check-calc-tour` | GREEN | RED | 15a — `[calcMergedOn, prefill, hasLeague]` |
| 12 | demo-bridge surface deleted from `TradesScreen` | `check-demo-calc-removed` | GREEN | RED | 7 — three named anchors, replacing a ≥2-FILE threshold that prose could satisfy |
| 13 | "Retry, or switch to the demo league." copy restored | `check-demo-calc-removed` | GREEN | RED | 8 — comment-stripped copy scan (new) |
| 14 | n12 loses `target`, keeps "This is your canvas" | `check-guide-script` | GREEN | RED | 5b — a `degradeLine` may exist only on a beat with a `target` |
| 15 | n22 loses `target`, keeps "Tap the meter…" | `check-guide-script` | GREEN | RED | 5b (same rule) |

`check-tour-suppression` no longer re-implements the reducer it tests: it transpiles
`useInterruptCoordinator.ts` with the project's own TypeScript and executes it against a minimal
zustand `create`, the way `check-presentation-v2.js` executes `tradePresentation.ts`. That single
change is what makes cases 7 and 8 falsifiable — the old model was green through both because
nothing in the file ever ran the source's version. `check-guide-script`'s DEIXIS vocabulary was
also widened with the calculator beats' element nouns (`canvas`, `cross`, `check`, `meter`,
`columns`, `arrows`), and the copy budget was not loosened.

**What this run does NOT prove.** Nothing has executed on a device or a simulator. The feature is
almost entirely presentation and timing — two columns at SE width, 53pt tap targets, spotlight
geometry, the rhythm of a 15-beat tour — which is the class of claim a structural guard cannot
reach. The rewritten TestFlight checklist (46 steps, A/B/C/D + a five-flag Prerequisites table) is
the only runtime evidence available, and it is unrun.

## 2026-08-22d — #384 merged calculator W0–W4 — full gates, FLAG DARK, NOT MERGED, on `feat/calc-finder-merge`

Branch cut from `origin/main` `941a36d`. Five waves, each committed with its own gate run.
Scope/plan: [docs/feedback/items/384-calc-finder-merge/](../docs/feedback/items/384-calc-finder-merge/plan.md) ·
Decision: [D-150](DECISIONS.md) · Checklist: [testflight-checklist.md](../docs/feedback/items/384-calc-finder-merge/testflight-checklist.md) (**UNRUN**).

| Gate | Result (identical at every wave boundary) |
|---|---|
| `python3 -m pytest backend/tests -q` | **4117 passed, 1 skipped, 0 failed** — unchanged from the branch point; the only backend delta is a flag registration |
| `cd mobile && ./node_modules/.bin/tsc --noEmit` | clean, exit 0 (`npm ci` in the worktree, never a symlink) |
| every `mobile/tests/check-*.js` | **76 scripts, 0 failed** (71 at branch point; +5 new) |
| `mobile/scripts/testid-lint.sh` | **OK** |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, standing posture under [D-056](DECISIONS.md) |

**New guards, all red-proofed:** `check-demo-calc-removed` (11 sabotages) ·
`check-calc-merged-layout` (9) · `check-calc-merged-behavior` (8) · `check-tour-suppression`
(7) · `check-calc-tour` (7). **42 sabotage cycles**, every one watched failing with its
intended message, every file byte-compared against a saved baseline after restore.

**Two guards do more than grep.** `check-tour-suppression` **executes** the real claim/release
reducer — assertion 6 runs the exact between-two-steps sequence W3 exists to fix — and guards
the model with named checks that the source still contains each rule it mirrors, so model and
implementation cannot drift silently. `check-calc-merged-layout` excises flag-gated regions by
brace balancing and tests the remainder, which is by construction the flag-off render.

**FIVE DEAD ASSERTIONS FOUND AND FIXED, all mine, none in the product.** This is the finding.
(1) `/isDemo/` matched `isDemoRenamed`. (2) `/onDemo/` matched `onDemoStarted`. (3) The
flag-gating check was a backwards proximity search that stayed green when the action row's own
gate was replaced with `{true ?` — it simply found the header's gate instead. (4) A fixed-size
character window read the NEXT JSX prop's body and failed on a close that was not its own.
(5) A drift detector threw an exception instead of failing a named assertion, which is red but
illegible in CI. Every one was found by sabotage, not by review.

**An existing suite broke honestly and was NOT loosened.** `check-decline-reasons.js` pinned
the ✕ condition as a literal string; W2's conjunct changed it. Rather than relax to
`disposition\.reasons[^?]*\?` — which would also accept `disposition.reasons && false ?`, the
exact defect those assertions exist to catch — the two legal shapes are enumerated. Verified
by sabotage that the updated matcher still rejects `&& false`.

**Copy budget verified BEFORE authoring, not after.** All 15 tour lines were word-counted
against their advance class up front (worst case 14/16), so `check-guide-script.js` confirmed
the budget rather than discovering a violation.

**Runtime evidence: NONE.** No device has run any of this. The two least-proven things are
named in the checklist's own "known-unverified" section: the two-column layout on a 375pt
screen (column width, the wrapped value line, and the two ~53pt action cells are all sized by
reasoning) and tour copy read beside the controls it names.

## 2026-08-22c — Feedback capture cap (2000 → 8000) + the three silences — full gates, backend SHIPPED, client awaiting a build

**Branch:** `claude/new-user-feedback-d4c47d`, cut from `origin/main` `9e1a8be` (0 ahead / 0 behind at branch time).
Operator declared **express** on the cap; I flagged the CLAUDE.md bright line (it changes a documented
API contract) and got a confirming yes for 8000 before proceeding, so **full gates ran anyway**.
Scope: [docs/plans/feedback-capture-cap/scope.md](../docs/plans/feedback-capture-cap/scope.md) ·
Decision: [D-149](DECISIONS.md) · Gotcha: [G-055](GOTCHAS.md).

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **4117 passed, 1 skipped, 0 failed** (baseline 4114 on `9e1a8be`; +3 in `test_feedback_text_cap.py`) |
| `cd mobile && ./node_modules/.bin/tsc --noEmit` | clean, exit 0 (`npm ci` in the worktree — **not** a symlink) |
| every `mobile/tests/check-*.js` | **71 scripts, 0 failed**, incl. the new `check-feedback-capture.js` (6 assertions) |
| `mobile/scripts/testid-lint.sh` | **OK** (3 new testIDs: `feedback.char-count`, `feedback.note-error`, `feedback.save-error`) |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, standing posture under [D-056](DECISIONS.md) |

**Backend sabotage evidence — 3 cycles, each RED with the intended assertion, restored and byte-verified.**
S1 cap lowered back to 2000 → `test_the_report_the_old_cap_ate_now_lands`. S2 cap check deleted →
`test_one_character_past_the_cap_is_refused`. **S3 cap made to TRUNCATE at 2000 instead of refusing**
— this is the one that matters: it returns **`201`**, so every status-code assertion passes and only
the stored-length check (`len(stored[0]["text"]) == 2001`) catches it. Silent truncation is the same
data loss wearing a success code, and a boundary suite that only checks status codes would have
blessed it.

**Client guard red-proofed in BOTH directions.** `check-feedback-capture.js` run against the pristine
defect tree (`git show 9e1a8be:<path>`): **6 of 6 RED**, each message naming the real defect. Against
the fixed tree: 6/6 green. Then **20 sabotage cycles**, one per named failure branch — every one fired
the branch it targeted, every one restored and re-verified. The cross-file assertion (client cap ==
server cap == the number the 400 reports) **fired for real mid-build** when the two halves were
briefly out of step.

**Method note worth keeping.** The QA agent did *not* sabotage the live worktree: three agents were
holding uncommitted work, so `git checkout --` would have destroyed a peer's changes rather than
restored them. It ran every cycle against isolated file replicas and byte-compared afterwards. I hit
the same trap first-hand — a `git checkout -- backend/server.py` mid-sabotage reverted my own
uncommitted fix and I had to re-apply it. **Copy the good file aside before any sabotage cycle on an
uncommitted tree.**

**Runtime evidence: NONE, and the client half has none available.** Under D-056 the only runtime proof
mobile can get is an operator TestFlight pass, and these client changes are **in no build**. The
backend half is verifiable in prod directly (a >2000-char POST now returns 201).

## 2026-08-21d — Decision-ID attribution correction (docs only) — `fix/lld-decision-id-attribution`

Docs-only change: 12 wrong decision-ID citations for per-slot pick pricing corrected to **D-146**
across `LLD.md`, `api-reference`, `config-reference`, `data-dictionary` and `cross-client-invariants`.
**Zero code, schema, route, flag or analytics files touched** — `git diff --stat origin/main` is six
`.md` files.

| Gate | Result |
|---|---|
| `pytest backend/tests` | **not run — no Python file in the diff.** Nothing to exercise. |
| `tsc --noEmit` / testid-lint | **not run — no mobile file in the diff.** |
| CI (all three jobs) | runs on the PR; expected green by construction (no source files) |
| Simulator gate | **`FTF_SKIP_SIM_GATE=1`** — standing D-056 posture, and doubly moot here: markdown has no runtime. |

**Evidence actually run**, since the failure mode is *wrong prose*, not wrong behavior:

1. **Per-site verification against `DECISIONS.md`** — every one of the 12 sites read against the
   full text of D-144, D-146, D-147 and D-148 and attributed by *what the decision decided*, not by
   date or adjacency. D-146's own Status line (*"Renumbered from the draft's D-144"*) is the
   corroborating record; D-146's body names the LLD section by title.
2. **Anchor-resolution check over `LLD.md`** — slug every `^## ` heading, assert every `](#…)`
   target resolves AND equals the slug of its own link text. **Clean**, except a pre-existing
   `#section-1` inside a fenced markdown *template* block (illustrative, not a link).
3. **Residual grep** — `git grep D-144 -- living-memory/ docs/ ':!docs/plans'` returns only sites
   that genuinely mean Receipts, plus the CHANGELOG history of the #168 renumber. `docs/plans/**`
   drafts intentionally retain the old ID.

**Not evidence:** nothing here was executed. The claim is that the citations now match
`DECISIONS.md`, and that claim is checkable by re-running items 1–3.

## 2026-08-22b — negmem SHIPPED to `main` (PR #168) — deployed dark to Render

**Merged:** squash PR [#168](https://github.com/mattmurf77/fantasy-trade-finder/pull/168) → `main` `7b7c314`; branch tip `71f63da` ledgered ([recovery](../docs/recovery/2026-08-22-negmem-ship.md)) before the remote delete.

| Gate | Result |
|---|---|
| `pytest backend/tests` (local, merged tree) | **4097 passed, 1 skipped, 0 failed** |
| CI `backend-tests` (Python 3.12.3) | **pass** (9m27s) |
| CI `mobile-typecheck` | **pass** |
| CI `maestro-testid-lint` | **pass** |
| Mobile diff vs main | **empty** — zero mobile files; no EAS/TestFlight build cut or needed |
| Simulator gate | **`FTF_SKIP_SIM_GATE=1`** — the standing D-056 posture. Evidence run instead: the full suite above + 30+ named sabotages RED-then-restored + CI. No simulator exists to run; this is the documented replacement, not a waiver of evidence. |

**Post-deploy verification:** polled `GET /api/feature-flags` on Render — `trade.negmem` moved **ABSENT → false**, which is itself the proof the new build is live (the old build did not know the key). Deployed state: flag **false**, `config/negmem_leagues.json` **empty**, `MODEL_A_PROFILE` pins `negmem_strength = 0.0`. **The ON-condition is BOTH the flag and the allowlist, so nothing generates differently for anyone.**

**Owed, unchanged by the ship:** the [TestFlight checklist](../docs/plans/negative-results-memory/testflight-checklist.md) is **UNRUN** — the feature has structural evidence only and must not be described as validated.

## 2026-08-22 — Negative-results memory v1 (leaf · registration · four seams · runner forwarding · readout pack) — full gates, FLAG DARK + ALLOWLIST EMPTY, NOT MERGED, on `claude/vigilant-spence-8583f5`

**Branch:** `claude/vigilant-spence-8583f5`, cut from `origin/main`. Not pushed, not merged.
Full gates — the operator did **not** declare express, and the change is outside the express
lane by the bright-line rule anyway (new flag surface, six `model_config` keys, a new
`features_json` key).
Spec: [LLD](../docs/plans/negative-results-memory/LLD.md) §10 (the 27-test N-plan) ·
scope [§6-RULINGS](../docs/plans/negative-results-memory/scope.md) ·
[ADR-015](../docs/adr/adr-015-negmem-soft-prior-not-fourth-filter.md) · [D-147](DECISIONS.md).

**Flag `trade.negmem` = false AND `config/negmem_leagues.json` = `[]`.** The ON-condition is
both, so nothing in this entry is runtime evidence of the feature working — it is evidence that
the feature is correctly inert and internally correct.

| Gate | Result |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest backend/tests -q` | **4025 passed, 1 skipped, 0 failed** (345 s). Wave-2 tip baseline on this tree: **4016 passed, 1 skipped**. The +9 are this wave's additions (5 through-the-runner + 4 pack-SQL); nothing removed, nothing newly skipped. Local interpreter is **3.14.4**; CI is 3.12.3 — check CI before attributing any red to this branch (the standing version-skew caveat) |
| `bash mobile/scripts/testid-lint.sh` | **testid-lint OK**. `git diff --stat -- mobile/` is **empty** — zero mobile files touched on the whole branch, so the mobile CI jobs are byte-identical to `origin/main`'s |
| `cd mobile && tsc --noEmit` · `check-*.js` | not run in this worktree (no `node_modules`); moot per the line above |
| Knob-inventory guard (`test_no_generation_knob_was_added_without_an_arm_a_decision`) + `test_model_a_profile_only_names_real_knobs` | green with all six `negmem_*` keys in `_PINNED_KNOBS` + disposition sentences, and `MODEL_A_PROFILE`'s `negmem_strength = 0.0` naming a real knob |
| Arm-A golden | **UNMOVED on first run, no recapture** (wave 2). The profile pin changes `snapshot_config` output and not deck bytes — which is the claim, asserted directly in `test_n7_serving_golden_strength0_is_stamp_inclusive_identity` |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence is this entry |

**Negmem test totals: 128** — `test_negmem.py` **87** (the leaf: admission closed list, undo
replay, decay/shrinkage worked examples incl. the five OQ-4b threshold assertions, MIN combine,
`effective_mult` invariants, netting/retraction/revive, determinism + immutability, M2 E-B
parity + feed guard, degraded taxonomy, identity hygiene, horizon/epoch boundaries, SQL
dialect, leaf-import contract, readout format) and `test_negmem_seams.py` **41** (the four
seams, the stamp trichotomy, the two goldens, T1, the relaxed pass, arm A, and this wave's
runner half).

**Sabotage discipline, by wave.** `PYTHONDONTWRITEBYTECODE=1` plus a `backend/__pycache__`
clear between every cycle — stale `.pyc` gave wave 1 a false GREEN, and that is the reason the
discipline is written down rather than assumed.

- **B1 (leaf):** 26/26 named sabotages RED-then-restored; LLD worked examples reproduced exact.
  One substitution recorded in-code: N-5's named sabotage is unreachable because the
  strength-0 short-circuit precedes the upper clamp, so an equivalent was used.
- **B2 (registration):** no behavioural sabotage — the inventory tests ARE the alarm, and they
  fail by name. Values in `_DEFAULT_CFG` and `_MODEL_CONFIG_DEFAULTS` verified identical.
- **B3 (seams):** 6 sabotage families RED-then-restored across the four seams and the stamp.
- **This wave (runner + pack):** 4 cycles, each RED then restored:
  1. delete `negmem_map = _nm` from `gen_v2_cards` → `test_runner_gen_v2_cards_forwards_the_map_and_the_m2_feed`,
     `..._carry_negmem_influence_to_arm_c` and `test_runner_bakeoff_job_carries_negmem_into_arm_c_and_arm_fit` RED;
  2. delete the `acceptance_stats` splat alone → the forwarding test RED, the rest green (the
     asymmetry is separable, which is the point of testing both);
  3. delete `negmem_map = kwargs.get("negmem")` from `gen_fit_cards` → the two fit runner tests
     + the bake-off test RED;
  4. paste `json_extract(...)` into `negmem-gr4-joint.sql`'s executable SQL → the pack
     banned-token scan RED.

**What the through-the-runner tests exist for.** `bakeoff_runner.gen_v2_cards` / `gen_fit_cards`
are the ONLY callers of their generators inside a bake-off job. Every pre-existing seam test
calls those generators directly, so a runner that dropped the forwarding would have left all 33
of them green while arms C and fit ran negmem-blind. Sabotage 1 and 3 above are the proof that
gap was real. The end-to-end test assembles the fan-out exactly as `server._run_trade_job` does
(one map, splatted into every arm's lambda) over the direct-engine world rather than the
bake-off harness world — the harness's opponents are unranked, so arms C and fit legitimately
emit zero cards there and the assertion would have been vacuous.

**Pack SQL is executed, not just scanned.** Both shipped files run against the seeded in-memory
SQLite engine with real binds, so a renamed column fails here rather than in the operator's
hands; the banned-token scan runs over the **executable** half (comments stripped) because both
files document their Postgres-only variant in a comment, per the `bakeoff_readout.sql`
convention. Comments are stripped before binding too — SQLAlchemy's `text()` harvests `:name`
binds out of comment prose, and both files name their binds there.

**Runtime evidence: NONE, and that is the honest state.** The
[TestFlight checklist](../docs/plans/negative-results-memory/testflight-checklist.md) is written
and **UNRUN**; no deck has ever been generated with this flag on for a real league. Its step 0
(the before-readout) must run before the flip or the baseline is unrecoverable.

---

## 2026-08-21c — League-surface pick-value alignment (Q-026 closed) — full gates, NOT PUSHED, on `feat/league-pick-value-alignment`

**Branch:** `feat/league-pick-value-alignment`, cut from `origin/main` @ `f01ac9f` (which contains PR #167 `3192d13`, the per-slot pricing ship this follows). Not pushed, not merged.
**`origin/main` advanced mid-build to `5472e70` (PR #168, negmem) and was MERGED IN**; every gate below was then re-run on the merged tree. That merge also forced a **D-id renumber: this ship's decision is D-148, not D-147** — PR #168 took D-147 while this branch was building. G-048, again, in the same week it was last logged.
Full gates — the operator did **not** declare express. Operator ruling: *"I want the league values to reflect the same pick values."*
Scope + code-walk + operator checklist: [docs/plans/league-pick-value-alignment/scope.md](../docs/plans/league-pick-value-alignment/scope.md) · ship-time entries **drafted, not applied**: [decisions-draft.md](../docs/plans/league-pick-value-alignment/decisions-draft.md) (D-148, Q-026 closure, new Q-027).

**No schema change, no flag change, no client change.** `git diff --name-only origin/main -- mobile web extension` = **zero files**.

**GOLDEN SET FIRST, IN ISOLATION, TWICE — the standing discipline, honoured.**

| when | files | result |
|---|---|---|
| before any source edit | `test_bakeoff_arm_a_golden` · `test_engine_quality_golden` · `test_fairness_gate_golden` · `test_rnk_elo_golden` | **29 passed** |
| after the source change, before any fixture was touched | same four | **29 passed, ZERO edits** |
| again after merging `origin/main` `5472e70` (which itself edited `test_bakeoff_arm_a_golden.py`) | same four | **29 passed, ZERO edits** |

Arm A's structural immunity (it never constructs a `draft_picks` row, so it never reaches `priced_pool_value`) was **verified, not assumed** — that is what the second isolated run is for. No tolerance widened, no golden fixture touched.

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` (pre-merge, base `f01ac9f`) | **3986 passed, 1 skipped, 0 failed** (331 s) against a measured baseline of **3969 passed, 1 skipped** (305 s) on the same tree at `f01ac9f` |
| `python3 -m pytest backend/tests -q` (**post-merge, base `5472e70` — the number that counts**) | **4114 passed, 1 skipped, 0 failed** (287 s). `origin/main` @ `5472e70` records **4097 passed, 1 skipped** in PR #168's own entry above. Delta **+17**, reconciling exactly on both baselines: **+5** from `test_league_picks_tier.py` (7 → 12) and **+12** from the new `test_league_pick_value_alignment.py`. Nothing removed, nothing newly skipped |
| `bash mobile/scripts/testid-lint.sh` | **green** (`testid-lint OK`) |
| `cd mobile && npx tsc --noEmit` · `check-*.js` | **NOT RUN in this worktree** — no `mobile/node_modules`, and `npm ci` needs network which is unavailable here. Evidence in its place: **zero mobile/web/extension diffs** against an `origin/main` whose CI is green. Asserted unaffected, **not observed — CI on the pushed sha must confirm** |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything in this entry |

**MEASURED BEFORE/AFTER — FFV3-shaped fixture** (12-team linear board, 2026 rounds 1–4 × 12 slots + 2027/2028 firsts and seconds = 96 picks, 1QB, pinned DP snapshot `dp_values_picks_2026-08-06.csv`).

Per-pick, 2026 round 1 — before → after (badge):

| 1.01 | 1.05 | 1.08 | 1.12 |
|---|---|---|---|
| 2117.0 → **4867.1** (`first_1`→`firsts_2`) | 2117.0 → 2343.2 (unmoved) | 2117.0 → 1435.5 (`first_1`→`second`) | 2117.0 → **820.8** (`first_1`→`second`) |

**Per-roster team-value pick totals** — monotonic by draft slot, which is the shape that proves the slot is reaching the price:

| roster | 1 | 2 | 3 | 6 | 9 | 12 | league |
|---|---:|---:|---:|---:|---:|---:|---:|
| before | 8590.4 | 8590.4 | 8590.4 | 8590.4 | 8590.4 | 8590.4 | 103084.8 |
| after | 9653.9 | 8722.1 | 7965.4 | 6439.9 | 5598.8 | 5124.6 | 80298.3 |
| Δ | **+12.4 %** | +1.5 % | −7.3 % | −25.0 % | −34.8 % | **−40.3 %** | **−22.1 %** |

**Badge movement: 50 of 96 picks (52 %).** 6 of the twelve 2026 firsts, 8 of the seconds, all 12 thirds, all 12 fourths, and all 12 **2028 firsts** (`first_1` → `second`). 2027 picks and the 2026 1.02–1.07 keep their badge. Bands untouched (`tier_config.json` + five client mirrors byte-identical); the inverse is still `value_to_elo` (D-088).

**Read the league row honestly: aggregate DEFLATION, not just dispersion.** The dispersion story holds within 2026 round 1; across a roster the round curve dominates because DP decays future firsts hard (2028 1st 2117.0 → 1263.0) where D-079's ladder held them flat. Those are the engine's prices as of `3192d13` — this ship stops one screen disagreeing with them, it does not create them.

**ADR-011 TIME-SERIES BOUNDARY AT THIS MERGE — named, and proven to be a boundary rather than a rewrite.** `roster_history.team_value` / `team_value_picks` are fed by `_power_picks_by_owner`, so the series steps here and is **not comparable across 2026-08-21** for any pick-holding team; the Wrapped/recap and trends consumers read across it. Nothing historical is recomputed, verified by `test_history_snapshot_reads_the_same_priced_picks_as_power_rankings`, which asserts `roster_history.py` contains no `priced_pool_value`, no `_priced_pick_value` and no `pick_pool_value` call at all — the writer is HANDED its prices and has no pricing path to re-run.

**Structural guard, sabotage-verified three ways** (`test_league_pick_value_alignment.py`, bidirectional AST walk over `server.py`). Each sabotage applied, suite run, reverted:

| # | sabotage | caught by |
|---|---|---|
| 1 | `_power_picks_by_owner` regresses to `p.get("pool_value")` — literally the pre-D-148 line | 4 tests, incl. both AST guards |
| 2 | a surface calls `priced_pool_value` directly with the **identical expression** (behaviourally a no-op) | 3 tests — proving the guard is structural, not behavioural |
| 3 | `_league_slot_order` resolved once per PICK instead of once per league | `test_power_rankings_resolves_the_draft_order_once_per_league` (48 picks, 12 rosters, asserts exactly 1 lookup) |

**Three fixture files re-derived from the pricing functions with literal inputs; no tolerance widened.**

- `test_league_picks_tier.py` (7 → 12): every badge literal re-derived. **All three original sabotages re-verified against the PRICED values** (S1 raw scale, S1b `seed_elo_for_value` inverse, S2 platform-only) — each still produces a different tier on ≥2 rows — and a fourth added (S3: leaving the stored column on the wire). The null-tier contract was re-anchored: a stored NULL now prices from the market like the engine already did, and null is reserved for "every step of the waterfall is empty".
- `test_power_rankings.py` (3 tests): **one trap had to be reshaped, not renumbered.** D-084's "u_a's one 3rd separates the literal from the dollar label scale" collapsed under the new prices — 2 seconds + 1 third is 1130.3 dollars, which rounds to ≈0.5 firsts, the same answer the literal count gives. Re-derived to **three** thirds (1654.9 ⇒ "≈1 firsts" vs literal "≈0.5 firsts"). Two thirds would not have worked (1392.6 still rounds to ≈0.5); the fixture note says so.
- `test_trade_evaluate.py` (1 test): the evener pick moved 2027 → 2028 so its priced value (1263.0) lands where the ordering assertion needs it, and the row now STORES 1005.3 so "priced, not stored" is provable rather than incidental.

**A real defect fixed in passing.** `_roster_eveners` (S4) priced sweetener candidates off the stored ladder while the `gap` they were sized against came from priced picks — both call sites are inside `_trade_evaluate_impl`. A one-tap "add their 2026 1.01" was offered as closing a 2117.0 hole the same response charged 4867.1 for.

**Two residues raised rather than buried, both needing an operator call:** pick-SHARE ratios (`_user_pick_share` + the trade job's opponent shares) stay on the legacy `pick_value` column, so the contend/rebuild classifier still weights every first alike (scope §6 waiver 3); and the Draft Room board vs engine mismatch in non-12-team leagues — a 10-team league's last first displays as 820.8 and prices as 1069.8 — pinned by a test and raised as **Q-027** (scope §6 waiver 2). 12-team leagues agree exactly, asserted slot by slot.

---
## 2026-08-21b — Gap auto-sweetener extended to bake-off arm C (`trade_gen_v2`) — full gates, NOT PUSHED, NOT MERGED, on `feat/gap-sweetener-arm-c`

**Branch:** `feat/gap-sweetener-arm-c`, **stacked on `fix/package-benchmark-sweetener` @ `480cce0`** — NOT cut from `origin/main`. `close_value_gap` does not exist on `origin/main` at all, so this work is unbuildable there; the operator chose the stacked branch over waiting for the Monday window (2026-08-21). **Merge order is load-bearing: the parent lands first, then this.**
Full gates ran — operator did **not** declare express.
Scope + code-walk: [docs/plans/package-benchmark-sweetener/scope-arm-c.md](../docs/plans/package-benchmark-sweetener/scope-arm-c.md) ·
ship-time entries **drafted, not applied**: [decisions-draft-arm-c.md](../docs/plans/package-benchmark-sweetener/decisions-draft-arm-c.md).

**No feature flag, no new knob.** Arm C reuses the parent's `sweetener_gap_threshold` (1539.0); ≤ 0 remains the deploy-free rollback and arm A's pin.

**Why it was needed, measured.** Arm C inherited the parent's trade-wide package benchmark — which WIDENS absolute consensus gaps — through `_consensus_packages` at card-build time, but did not run the closer. Its deck is card-for-card identical across the parent (the parent moves its *prices*, not its *selections*), so the entire rise is mispricing. Reproduced on this tree: **12-team 3/22 over the line (13.6 %), 16-team 2/19 (10.5 %)**, `sweetened: 0` in both, against 0–5.3 % for every other served arm.
## 2026-08-21b — Receipts (graded suggestion track record) built dark — full gates, NOT PUSHED, NOT MERGED, on `feat/receipts`

**Branch:** `feat/receipts` (worktree `agent-a60b48a57928d5895`), cut from `origin/main` at `eb9c1de`, then `plan/receipts` merged in (that merge IS the shared taxonomy's repo landing) and `origin/main` re-merged at `d42872f` after PRs #161/#162 landed mid-build. **Not pushed, not merged.**
Full gates — the operator did not declare express, and the change is outside the express lane by the bright-line rule anyway (2 new tables, 3 new routes, 2 new flags, 5 new knobs, 3 new analytics events).
Spec: [docs/plans/receipts/](../docs/plans/receipts/) (dual-agent reviewed, 3 adversarial rounds) · code-walk: [code-walk.md](../docs/plans/receipts/code-walk.md) · operator checklist: [testflight-checklist.md](../docs/plans/receipts/testflight-checklist.md).

**Everything ships dark.** `receipts.grading` and `receipts.screen` both default false; env kill switch `FTF_RECEIPTS_GRADE=0`.

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3795 passed, 1 skipped, 0 failed** (340 s). Baseline measured on this same tree at the parent tip `480cce0`: **3786 passed, 1 skipped**. The +9 are the new `test_gap_sweetener_arm_c.py`; no other delta, nothing removed, nothing newly skipped |
| `cd mobile && tsc --noEmit` · `check-*.js` · `testid-lint.sh` | **not run in this worktree** (no `node_modules`); **zero mobile files touched** — `git diff --stat <parent> -- mobile/` is empty, so the mobile CI jobs are byte-identical to the parent's |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything in this entry |

**Verify-by-revert on all nine new tests, three trees.** With `backend/trade_gen_v2.py` reverted to the parent, **8 of 9 go red**; with the *contained-pools* variant (equalizer drawn from `give_pool`/`extras` rather than the semantic universes) exactly **1 goes red** — `test_arm_c_equalizer_reaches_past_the_budget_slice`, the test that pins the §0b decision. Shipped tree: 9/9 green. The ninth test, `test_arm_c_kill_value_is_a_byte_identical_no_op`, passes on the parent **by design** — it asserts the threshold-0 deck IS the pre-sweetener deck, so a green there is the claim, not a gap in coverage. It pins the organic card's exact literals (`["G"] → ["R"]`, 10000.0 / 11600.0, band 0.862, gap 1600.0) so drift in the disabled path cannot be silently rebaselined.

**Two defects found by reading arm C rather than copying the other three hooks** (both would have shipped had this been a copy-paste; details in scope-arm-c.md §0):

1. **Placement.** The gap is only computable at the card-build call to `_consensus_packages`, but ten derived fields — `_dedup_batch` keys, `_meso_variants`, `_rationale`, `classify_package_shape` (whose `"consolidation"` label is literally `len(ids) == 1`), `card.health`'s seven entries, `mismatch_score`, `fairness_score`, `composite_score` and the Stage 6/7 exposure + tier ranking — are computed earlier from the `_Candidate`. Sweetening at the obvious site leaves every one of them describing the unsweetened trade: arm C's much larger analogue of the v3 stale-`fit_premium` defect. Fixed by hooking inside `_pair_survivors` and rebuilding the whole `_Candidate`.
2. **`past_decision_keys` was re-checkable and unchecked.** A sweetened combo is a different trade with a different key; the enumeration only ever tested the unsweetened shape. Without the re-test the pass could ship a combo the user had already rejected. Pinned by `test_arm_c_sweetened_combo_respects_past_decisions`.

**Pool containment — the round-2 lesson applied, and where it stops.** Arm C prunes in two layers and only one is semantic. `user_assets` (on BOTH boards, not untouchable) and `extras_all` (divergence-positive, not not-interested) encode real rules and are the equalizer universe. `[:gen2_give_pool]` / `[:gen2_recv_extra_pool]` are enumeration budget — documented as bounding "SEARCH BREADTH, never output length" alongside `gen2_centerpiece_top_k` — and the sweetener deliberately reaches past them. **Measured justification:** wired to the budget slices the pass fires but the deck metric does not move (3/22 and 2/19 unchanged), because **78 of 112 and 63 of 86 rejected equalizers are undershoot** — nothing in the slice is big enough — against only 8 and 13 killed by arm C's own gates. Reaching the semantic universe moves the 12-team fixture **3 → 1 over the line (13.6 % → 4.6 %), p90 1665 → 951**; the 16-team stays at 2 but its mean gap falls 551 → 488. Operator chose the widened reading with the numbers in front of them. This is NOT the `49c1d76` defect relaxed: that one crossed a semantic line (a #174 pinned "trade away G" job smuggling in an unpinned player — a broken user instruction).

**Golden disposition — re-verified deliberately, and they did NOT move. No re-capture, no kill-value pin.** The brief expected the gen2 goldens to move. Instrumented rather than assumed, with a probe counting arm-C sweetener invocations per file:

| File | `generate_league_suggestions` calls | arm-C cards | sweetener fired | verdict |
|---|---|---|---|---|
| `test_bakeoff_arm_a_golden.py` | 0 | 0 | 0 | never enters arm C — arm A is the v2/consensus path, and pins the knob at 0 besides |
| `test_engine_quality_golden.py` · `test_engine_quality.py` | 0 | 0 | 0 | never enters arm C |
| `test_bakeoff_runner.py` · `test_bakeoff_composition.py` · `test_bakeoff_challenger.py` | 0 | 0 | 0 | never enters arm C |
| `test_bakeoff_serving.py` | 10 | **0 cards** | 0 | enters, but the fixture yields empty arm-C decks |
| `test_trade_gen_v2.py` (arm C's own suite, not a golden) | 36 | 57 | **10 fired, 10 closed** | all 40 assertions still green |

Confirmed by forcing the gap line to **1.0** — a threshold every nonzero gap exceeds: still **0 invocations** in every golden file. So the goldens are stable because arm C's generator is not reached in them, not because the threshold happens to sit above their gaps. There is no baseline to re-capture and nothing to pin.

**Where the sweetener does real work, proven by the same probe on three trees** — `test_trade_gen_v2.py`, all 40 pre-existing tests green throughout:

| Tree | cards | max gap | over 1539 |
|---|---|---|---|
| parent (`480cce0`) | 58 | 1861.5 | **2** |
| contained pools | 57 | 1234.2 | 0 |
| shipped (widened) | 57 | 1234.2 | 0 |

**Known effect, deliberately accepted — for arm C the pass CAN shrink the deck by one, unlike the other three paths.** D-143 states the sweetener "narrows gaps, never shrinks the deck". That holds where it was written, but arm C is the only path with `_dedup_batch` downstream, and its bucket key is `(opponent, centerpiece, "{len(give)}x{len(recv)}")`. Sweetening changes a card's SHAPE, so it can land in an occupied bucket and the lower-ranked occupant is dropped. Diffed card-for-card on `test_trade_gen_v2.py` deck #11: parent held `u_rb1 → o_wr1` (gap 1671, over) and `u_rb2+u_wr1 → o_wr1` (gap 1861, over); shipped sweetens the first into a 2×1 (`+u_wr1`, gap 1234) which collides with the second's bucket and evicts it. Net 3 cards → 2, and **both over-the-line cards are gone**. Acceptable: the bucket rule exists precisely to stop two near-duplicate shapes serving together, and arm C emits its full survivor set with no truncation, so the loss is one near-dup rather than a suppressed idea.

**Harness determinism — see [G-053](GOTCHAS.md).** The first before/after run showed arm D moving, which cannot happen from a `trade_gen_v2` edit. Two consecutive runs on the identical tree reproduced the flip: the harness is seed-dependent. Every number in this entry was produced with `PYTHONHASHSEED=0` on both sides, verified byte-identical across two seeded runs. This retroactively qualifies single-card deltas in 2026-08-21a, which was measured unseeded.

**Not covered / owed at ship.** No runtime evidence: arm C serves quota-capped bake-off slots and rides the parent's [testflight-checklist.md](../docs/plans/package-benchmark-sweetener/testflight-checklist.md) rather than adding a second manual pass. Deck-level effects above are fixture-only and DIRECTIONAL — synthetic boards, `max_per_opponent=5` (the engine default is None, so production decks are larger than the harness's).
| `python3 -m pytest backend/tests -q` | **3951 passed, 1 skipped, 0 failed** (301 s), measured on the merged tree. Exactly **54** of those are the new `backend/tests/test_receipts_grading.py`, so the merged tree's pre-existing count is 3897 — no existing test was changed, removed, or newly skipped, and the only test file this branch adds is the receipts one. (The brief's 3651 baseline predates PRs #161/#162, which landed mid-build and brought their own suites.) |
| `cd mobile && npx tsc --noEmit` | **green** (`npm ci` first — the worktree had no `node_modules`) |
| `node tests/check-receipts.js` (`npm run test:receipts`) | **12 passed, 0 failed** |
| `bash mobile/scripts/testid-lint.sh` | **testid-lint OK** |
| Knob-inventory guard | green and **correctly silent**: the five `receipts_*` knobs are deliberately NOT in `trade_service._DEFAULT_CFG`, so `_PINNED_KNOBS` does not apply. A test asserts they never enter it, and each has an arm-A disposition sentence in `docs/plans/three-model-bakeoff/scope-phase2.md` |

**Sabotage discipline — 21 named sabotages, all confirmed RED then green on revert.**
Backend (12): edge sign flip · D-8 floor imputation dropped · serve anchor allowing a post-serve snapshot · pick weights read live from `GENERIC_PICK_SEEDS` · Wilson centre shift dropped · valuation leaking from the frozen card · ghosts entering the queue · queue ignoring existing grades · min-n gate removed · an UPDATE path on `receipts_grades` · pre-telemetry rows queued · dedup keeping the latest serve.
Mobile (9): FeedbackFAB removed from one render branch · FAB given tab-stack props · a second per-window fetch · worst call dropped while best call kept · route wrapped in the flag · entry point ungated · ledger state deleted · disclosure not rendered · give-side delta dropped.

**Six guards were BLIND on the first pass and were strengthened rather than logged as passing** — this is the part worth reading:
- **T-4 (deploy invariance)** compared two rows that BOTH became `pick_majority` under the sabotage, so a field-by-field equality check passed while proving nothing. Now pins `status == "graded"` on both sides, plus a direct assertion that the frozen weights survive `GENERIC_PICK_SEEDS` being emptied entirely.
- **T-1 (pre-telemetry)** ran against an empty cohort, so the run short-circuited and the test passed because *nothing happened at all*. Now seeds a gradeable neighbour and asserts the run did real work.
- **FAB check** passed with one of three render branches stripped — the error branch, i.e. the user with the most to report and no way to report it. Now counts mounts against render branches and prop-checks every mount.
- **Unconditional-route check** searched for the flag NAME, so `{true ? <Stack.Screen…}` slipped through. Now inspects the token before the tag.
- **Both-sides check** matched `give_delta` surviving inside a style callback after the rendered number was deleted. Now asserts the rendered value.

**Two real defects the discipline caught (not test bugs).**
1. `_dedup_earliest` was keeping the LATEST serve instead of the earliest — masked by a **stale `.pyc`**: the sabotage swapped `<`→`>`, identical byte length inside one mtime-second, so Python reused cached bytecode and `inspect.getsource` disagreed with what was actually running. Sabotage runs now clear bytecode between steps. **Worth remembering: a same-length edit inside one second is invisible to Python's import cache.**
2. The daily-tick guard serialized `receipts_grade_started` unconditionally, changing the flag-off tick payload — caught by `test_deck_replenishment`'s byte-identical assertion, fixed, and now pinned from the receipts side too.

**Backfill exercised end to end** against a synthetic fixture DB (420 impressions across 3 leagues / 2 formats / 3 users, 8 640 snapshot rows, a deliberate 2-day supply gap, 23 ghosts, 49 pre-telemetry rows): 565 resolvable → **542 graded + 23 ungradeable = 565 exactly**, terminating on two consecutive zero-work runs; re-run wrote 0; ledger showed 6 complete start/end pairs and 0 unmatched starts; **0 ghost rows graded**; 47 floor-imputed (D-8) rows retained. Win/loss landed at 283/259 on drift-only synthetic data — near the 50% null, which is what an unbiased grader should produce on random walks. `effective_window` for 28d: min 27, max 30, median 28.
The **real dev DB dry-run reports 0** and that is correct, not a failure: `data/trade_finder.db` holds zero `deck_impressions` rows, so there is nothing local to grade. The prod cohort is the P0 read, still outstanding.

**Code-ship boundary, examined rather than assumed (coordinator note).** `d42872f` (2026-08-22, package pricing + sweetener) changes package-value SEMANTICS in the engine. It does **not** affect grades: the grader reads only `player_value_history` consensus snapshots and never computes a package value, so no grade moves across that boundary — HL-4 recalibration immunity holds by construction. What it *does* affect is attribution: impressions served before and after `d42872f` come from different engine behaviour, and that is already carried by the `policy_version` slice key stamped on every impression and copied onto every grade row. No action; recorded so it is not re-examined.

**Not run:** anything on a device. Receipts has never rendered on real hardware — that is the operator's checklist above, and it is the only runtime evidence this feature will get.

---
## 2026-08-21a — Package-benchmark fix + gap auto-sweetener + ghost default, round-2 reviewed — full gates, NOT PUSHED, NOT MERGED, on `fix/package-benchmark-sweetener`

**Branch:** `fix/package-benchmark-sweetener` (worktree `agent-a8f35b1a442cb2147`), cut from `origin/main` at `eb9c1de`. **Not pushed, not merged** — the merge is the operator's Monday-boundary call (change-control rule, trade-engine-accuracy PLAN Phase 0.4).
Full gates ran — operator did **not** declare express, and the change is outside the express lane by the bright-line rule anyway (it adds three `model_config` keys and changes a shipped default).
Scope: [docs/plans/package-benchmark-sweetener/scope.md](../docs/plans/package-benchmark-sweetener/scope.md) (round-2 review in §6) ·
code-walk: [code-walk.md](../docs/plans/package-benchmark-sweetener/code-walk.md) ·
checklist: [testflight-checklist.md](../docs/plans/package-benchmark-sweetener/testflight-checklist.md) ·
ship-time entries **drafted, not applied**: [decisions-draft.md](../docs/plans/package-benchmark-sweetener/decisions-draft.md).

**No feature flag.** Knob-gated: `package_bench_trade_wide` 1.0, `package_floor_cross` 0.40, `sweetener_gap_threshold` 1539.0 — each ≤ 0 is a deploy-free rollback. Changed default: `ghost_holdout_one_in` 10 → 0.

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3786 passed, 1 skipped, 0 failed** (271 s). Baseline on the inherited tip `0e04d30`, measured on this same tree: **3782 passed, 1 skipped**. The +4 are the round-2 regression tests in `test_gap_sweetener.py`; no other delta, nothing removed, nothing skipped that was not already skipped |
| `cd mobile && tsc --noEmit` · `check-*.js` · `testid-lint.sh` | **not run in this worktree** (no `node_modules`); **zero mobile files touched** on the whole branch — `git diff --stat origin/main -- mobile/` is empty, so the mobile CI jobs are byte-identical to `origin/main`'s green |
| Knob-inventory guard (`test_no_generation_knob_was_added_without_an_arm_a_decision`) | green with all three new keys in `_PINNED_KNOBS` + disposition sentences in `docs/plans/three-model-bakeoff/scope-phase2.md` |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything in this entry |

**Round-2 adversarial review of the inherited commits — two real defects, both reproduced before they were fixed.** The operator re-delegated the sweetener for a hostile re-read. `72ecd51` (benchmark fix) came back **clean**: `v_max` verified trade-wide at all 14 constructions in `backend/`, the carve-outs verified surgical, kill-value identity verified test-proved rather than asserted. `0e04d30` (sweetener) shipped two defects, fixed in `49c1d76`:

1. **The consensus generator's pool pruning was bypassed.** `_generate_consensus_for_pair` prunes `give_pool` to the #174 pinned give players and `recv_pool` to the FB-47 pinned acquire targets / need positions, rather than gating per combo. `close_value_gap` drew from the raw rosters, so a `pinned_give_players=["G"]` job emitted `[G, X1] → [R]` with `X1` never offered up, and a WR-only acquire job could hand back an off-need RB. Fixed with optional `give_candidates`/`recv_candidates` (rosters still drive the 3.2 feasibility counts). v2 and v3 pass nothing — their pinned/position rules are per-combo and monotone under addition, verified callsite by callsite.
2. **v3 shipped a stale `fit_premium`.** `fit_premium_1for1` can only price a 1×1; the gap pass rewrote the card to a 1-for-2 and left the badge on. The v2 divergence path already nulled its `fit_paid`; v3 now does too.

**Verify-by-revert on all four new tests:** with `backend/trade_service.py` + `backend/trade_optimizer.py` stashed back to `0e04d30`, `test_helper_candidate_pools_narrow_the_equalizer_universe`, `test_consensus_sweetener_never_adds_an_unpinned_give_player`, `test_consensus_sweetener_respects_the_acquire_position_filter` and `test_v3_gap_sweetener_clears_the_stale_fit_premium` all go **red**; restored, all green. Each also carries its own non-vacuity half (the same fixture without the pin IS sweetened; the knob-off half proves the v3 organic winner really is a fit-premium 1-for-1 carrying a 1600 gap).

**Sabotage check on the extraction the predecessor claimed was byte-identical — it holds, but NOT where the commit said.** `0e04d30` pulled the v2 divergence surplus/composite math out of `_consider` into `_pair_surpluses` / `_composite_v2` and asserted the extraction was pinned by "the full suite plus the arm-A/challenger/engine-quality goldens". Sabotage: `u_max = max(uvals_give + uvals_recv)` → `max(uvals_give)` inside `_pair_surpluses`, `__pycache__` cleared. **Those three golden files all stayed GREEN** — they run with `trade_engine.v3` on, so `_generate_for_pair_v2` is never entered. The full suite DID catch it, at **`test_trade_optimizer.py::test_v3_top_card_matches_v2_on_1for1_fixture`** and **`test_trade_tier2.py::test_outlook_rebuilder_outranks_championship`** (2 failed, 3784 passed). Restored with `git checkout --`, proved restored with `git diff --quiet`, re-run green. So the claim is TRUE and the extraction is genuinely guarded — the commit message just named the wrong guards, which would have sent the next person debugging the wrong file.

**W0-style deck-size / gap-distribution measurement — `origin/main` `eb9c1de` vs this branch tip.** Fixture-only. Two constructed leagues (12-team 1QB 26-man, 16-team SF 21-man) drafted from `backend/tests/fixtures/player_pool_2026.json`, 3 owned-pick pseudo-assets per team, hash-offset synthetic boards, `fairness_threshold` 0.85, `max_per_opponent` 5, `_cfg` at code defaults, flags from `config/features.json`. Harness committed for reproducibility: [`measure_gap_distribution.py`](../docs/plans/package-benchmark-sweetener/measure_gap_distribution.py). The "before" side was produced by `git archive origin/main` into a scratch tree and running the same file there. **One deviation from the fit-challenger W0 recipe, and it is load-bearing:** W0's flat rank-ladder Elo seeds (1750 → 1250) compress the board into 286..3490 value units, where a 1539 gap is arithmetically almost unreachable — the measurement reads zero everywhere regardless of the engine. Seeds here come from the pool's own DynastyProcess values rescaled so the #1 asset lands on FTF's real top-asset price (~7737), reproducing the production value CURVE.

| League | Path | Arm | main cards | branch cards | Δ | main >1539 | branch >1539 | sweetened | main mean gap | branch mean gap |
|---|---|---|---|---|---|---|---|---|---|---|
| 12t 1QB | v2 only | B `current` | 14 | 13 | −1 (−7%) | 0 (0.0%) | 0 (0.0%) | 1 | 105.4 | 112.2 |
| 12t 1QB | v2 only | B, sweetener OFF | — | 13 | — | — | 1 (7.7%) | 0 | — | 211.5 |
| 12t 1QB | v2 only | D `challenger` | 14 | 13 | −1 (−7%) | 0 (0.0%) | 0 (0.0%) | 1 | 105.4 | 112.2 |
| 12t 1QB | v2 only | C `gen_v2` | 22 | 22 | +0 | 0 (0.0%) | **3 (13.6%)** | 0 | 427.0 | 583.5 |
| 12t 1QB | v2 only | A `baseline` | 30 | 30 | +0 | 3 (10.0%) | 3 (10.0%) | 0 | 312.4 | **312.4** |
| 12t 1QB | v3 | B `current` | 19 | 16 | −3 (−16%) | 1 (5.3%) | 0 (0.0%) | 1 | 284.9 | 393.9 |
| 12t 1QB | v3 | B, sweetener OFF | — | 16 | — | — | 1 (6.2%) | 0 | — | 492.0 |
| 12t 1QB | v3 | D `challenger` | 20 | 16 | **−4 (−20%)** | 1 (5.0%) | 0 (0.0%) | 1 | 287.3 | 379.9 |
| 12t 1QB | v3 | A `baseline` | 30 | 30 | +0 | 3 (10.0%) | 3 (10.0%) | 0 | 448.3 | **448.3** |
| 16t SF | v2 only | B `current` | 16 | 17 | +1 (+6%) | 0 (0.0%) | 0 (0.0%) | 0 | 305.9 | 125.4 |
| 16t SF | v2 only | D `challenger` | 16 | 17 | +1 (+6%) | 0 (0.0%) | 0 (0.0%) | 0 | 305.9 | 125.4 |
| 16t SF | v2 only | C `gen_v2` | 19 | 19 | +0 | 1 (5.3%) | **2 (10.5%)** | 0 | 468.3 | 551.5 |
| 16t SF | v2 only | A `baseline` | 30 | 30 | +0 | 0 (0.0%) | 0 (0.0%) | 0 | 178.5 | **178.5** |
| 16t SF | v3 | B `current` | 19 | 19 | +0 | 0 (0.0%) | 1 (5.3%) | 1 | 291.4 | 470.2 |
| 16t SF | v3 | B, sweetener OFF | — | 19 | — | — | 2 (10.5%) | 0 | — | 495.1 |
| 16t SF | v3 | D `challenger` | 19 | 19 | +0 | 0 (0.0%) | 1 (5.3%) | 1 | 284.3 | 470.2 |
| 16t SF | v3 | A `baseline` | 30 | 30 | +0 | 3 (10.0%) | 3 (10.0%) | 0 | 560.7 | **560.7** |

**Four readings.**

- **Deck shrink — the number the operator accepted in advance:** **−3.9%** across the served arm roster (B + C + D, 178 → 171 cards); **−4.4%** for arm `current` alone (68 → 65). Worst single cell **−20%** (12-team 1QB, v3, arm D: 20 → 16). No cell lost more than 4 cards.
- **Arm A is byte-identical at `origin/main` and at this branch tip** — same 30 cards, same 9 over-the-line count, same p90 and mean gaps to 0.1, on every league × path. That is LIVE evidence for the pin-instead-of-recapture choice, on top of the unit test, and it is the strongest single result in this run.
- **The sweetener works where it fires, and it fires narrowly.** The branch-only "sweetener OFF" rows isolate it from the benchmark fix: arm `current` would carry 1 / 1 / 2 over-the-line cards on the three cells where it matters, and the pass takes those to 0 / 0 / 1 — 3 of 4 closed. It sweetens roughly **one card per deck**, not a third of it.
- **Arm C gets WORSE, and this is the finding to act on.** Arm C's deck is identical card-for-card (22 and 19 on both trees) — only the DISPLAYED values moved, because it inherits `package_value_v2` through `_consensus_packages` but does not run the sweetener. Its over-the-line share goes 0 → 13.6% and 5.3 → 10.5%. Across the served roster that alone lifts the combined over-the-line share from 1.7% to 4.1%. The arm-C follow-up named in scope.md is a **priority item**, not a nicety.

**What is NOT proven, and is owed.** (a) The manual TestFlight checklist — it needs a build containing this branch, which does not exist; no runtime evidence exists for these cards yet. (b) A prod-replay half against real league boards — needs prod read access, operator item, same gap the fit W0 run had. (c) Fixture boards are synthetic (rank-drafted rosters, hash-offset personal Elo), so the LEVELS above are directional; the main-vs-branch DELTAS are the result. (d) The fixture decks carry a far lower over-the-line share (0–5% on arm B) than the 15% the CHANGELOG measured on real served cards, so the sweetener's real-world firing rate is likely HIGHER than one card per deck — read it from the checklist's readout SQL before trusting the fixture rate.

**Six operator ratification items** are listed in [scope.md §6](../docs/plans/package-benchmark-sweetener/scope.md) — headline ones: the arm-A golden was pinned rather than re-captured, and the flag-off serving golden's parity-with-the-pre-bake-off-SHA claim died with its re-capture and is now a drift detector.

### Addendum 2026-08-21b — the PROD-REPLAY half, on real boards. Owed item (b) above is now CLOSED.

Read-only prod replay of league `1312140920132497408` ("Fantasy Football Version 3", `1qb_ppr`) — the
only league with 3+ boards — against **`origin/main` `eb9c1de`** (pinned by SHA and materialized with
`git archive`, because main moves) **vs this branch tip `480cce0`**. Nothing was pushed, merged,
flagged or written; no engine file was touched by this measurement. (A concurrent session committed `e59650c` to this branch mid-run; it is docs-only — `git diff 480cce0 e59650c -- backend/ config/` is empty — so these numbers still describe the current tip.)

**Method** — the arm-B audit's recipe ([docs/reviews/2026-08-19-armb-audit-claims-3-4.md](../docs/reviews/2026-08-19-armb-audit-claims-3-4.md) §7),
extended to the full serving inputs. Prod was read **once** into a local JSON fixture and both trees
then ran against those FROZEN inputs — no per-generation prod access. Connection posture copied from
`backend/tools/prod_analytics.py`: `DATABASE_URL_PROD` from the gitignored root `secrets.local.env`,
session-level `default_transaction_read_only=on` + `statement_timeout`, SELECT only, DSN never printed.

- Pool + consensus seed: `player_value_history` @ `2026-08-21` / `1qb_ppr` (644 rows) joined to `players`.
- Each member's board: their **real** `swipe_decisions` replayed through the **real**
  `RankingService.replay_from_db` (1808 / 1080 / 956 / 175 / 120 / 42 rows), `users.tier_overrides`
  restored into `_elo_overrides` (with `__OVERRIDE_AT__` stamps), then `get_rankings()`,
  `comparison_counts()` → `confidence`, `placement_bands()` → `placements`.
- Rosters from `league_members.roster_data`; outlooks + acquire/trade-away positions from
  `league_preferences`; `asset_preferences` as untouchable/target/not-interested sets; opponent
  outlooks and pick shares assembled as `_run_trade_job` does.
- Owned picks injected exactly as `server._inject_owned_picks` does (144 rows, `picks_pool_cap`, and
  `trade.slot_pricing`'s default `tier_ladder` mode ⇒ the stored `pool_value`), with `_pick_asset_elos`
  priming every Elo map — so a pick can be an equalizer, as it is in prod.
- Prod `model_config` (185 rows) into both modules' `_cfg`; each viewer's real `stud_tax_mode` pinned;
  flags from `config/features.json`; cards from the real `TradeService.generate_trades` at the **organic
  serving parameters** (`fairness_threshold` 0.75, `max_per_opponent` 5).
- **Both trees ran against ONE shared throwaway SQLite `DATABASE_URL`** so neither could read a
  different local `experiments` / `model_config` table (the branch worktree has a populated
  `data/trade_finder.db`; the archived main tree does not — that asymmetry was found and removed).
- 6 boarded viewers × 2 paths (v3 = the live posture, and v2-only) × arms A/B/C/D, plus a branch-only
  `sweetener_gap_threshold = 0` control that isolates the sweetener from the benchmark fix.
- **Determinism proved, not assumed:** the whole branch run was repeated and the two result files are
  byte-identical.

Harness committed (DB-free half): [`replay_prod_boards.py`](../docs/plans/package-benchmark-sweetener/replay_prod_boards.py).
The prod extractor is deliberately **not** committed — it holds a prod connection helper, the same
posture the arm-B audit took with its probe scripts.

| Slice | main cards | branch cards | Δ | main >1539 | branch >1539 | sweetened | main mean gap | branch mean gap |
|---|---|---|---|---|---|---|---|---|
| **Served arm roster (B+C+D, both paths)** | 434 | 427 | **−7 (−1.6%)** | 45 (10.4%) | 33 (7.7%) | 28 | 614.0 | 568.6 |
| arm B `current`, both paths | 186 | 185 | −1 (−0.5%) | 15 (8.1%) | 7 (3.8%) | 17 | 552.6 | 486.2 |
| **arm B, v3 path — the live posture** | 105 | 106 | **+1 (+1.0%)** | 7 (6.7%) | **3 (2.8%)** | 9 | 538.1 | 501.3 |
| arm B, v2-only path | 81 | 79 | −2 (−2.5%) | 8 (9.9%) | 4 (5.1%) | 8 | 571.3 | 466.1 |
| **arm A `baseline` (pin check)** | 376 | 376 | **+0** | 71 (18.9%) | 71 (18.9%) | 0 | **835.6** | **835.6** |
| arm C `gen_v2` (inherits the fix, no sweetener) | 51 | 51 | +0 | 15 (29.4%) | **19 (37.2%)** | 0 | 1173.7 | 1253.0 |
| arm D `challenger` | 197 | 191 | −6 (−3.0%) | 15 (7.6%) | 7 (3.7%) | 11 | 527.2 | 465.7 |

By basis, arm B, both paths: **divergence** 96 → 94 cards, over-line 13 (13.5%) → 7 (7.4%), 15 sweetened;
**consensus** 90 → 91 cards, over-line 2 (2.2%) → **0 (0.0%)**, 2 sweetened. Sweetener fire rate splits
almost entirely by basis, not by path: divergence **15.9%** (v2) / **16.0%** (v3), consensus 2.9% / 1.8%.

**Fixture prediction vs real boards — four corrections and one confirmation.**

1. **Deck shrink is less than half what the fixture predicted.** Fixture: **−3.9%** served roster,
   −4.4% arm B, worst cell −20%. Real boards: **−1.6%** served roster, **−0.5%** arm B, and the live
   v3 path actually gains a card (**+1.0%**). Worst single cell is `v2_only` / arm D / MangoPatti,
   15 → 11 (−26.7%); worst arm-B cell is `v2_only` / johnstanfield, 17 → 15 (−11.8%). The operator
   accepted −3.9% in advance; the real cost is smaller than the number they accepted.
2. **The over-the-line LEVEL the fixture could not reach is confirmed, and the CHANGELOG's ~15% is
   located.** At `origin/main` on real boards: arm A **18.9%**, arm C **29.4%**, arm B **8.1%** — and
   arm B's **divergence** slice is **13.5%**. The fixture read 0–5% on arm B. So the ~15% figure is a
   divergence/mixed-arm number, not an arm-B-overall one, and the fixture was indeed measuring an
   arithmetically compressed board.
3. **The sweetener fires about twice as often as the fixture implied — confirmed as predicted.**
   Fixture: 3 sweetened cards across 65 arm-B cards (~4.6%), "roughly one card per deck". Real boards:
   **17 / 185 = 9.2%**, **1.42 cards per deck** on a mean deck of 15.4. Owed item (d) called this and
   was right.
4. **The sweetener's economics on real assets.** Mean gap **2173 → 850** (median 2010 → 814), mean
   1324 units closed. **17 of 17 sweetened cards land under the 1539 line** — when the pass fires it
   always succeeds. Equalizer came off the **give** side 14 times, the **receive** side 3, and was an
   owned **PICK** 5 of 17 (Bcork's 2027 1sts, johnstanfield's 2026 1sts) — the `close_value_gap`
   docstring correction in §6 is load-bearing in production, not theoretical. The 7 cards still over
   the line on the branch are **all unsweetened** (gaps 1648, 1648, 1812, 1876, 2171, 2547, 4105) —
   unclosable and kept, exactly as specced.
5. **NEW — the branch's two halves pull in opposite directions, and only the sweetener makes it a
   win.** The branch-only `sweetener_gap_threshold=0` control isolates them on identical decks
   (deck size is unchanged by the sweetener on real boards — every viewer's card count matches
   card-for-card between sweetener-on and sweetener-off, so the whole −1.6% deck delta is the
   BENCHMARK FIX, not the sweetener):

   | Path | main | branch, sweetener OFF | branch, sweetener ON |
   |---|---|---|---|
   | v3 | 7/105 = 6.7% | **12/106 = 11.3%** | 3/106 = **2.8%** |
   | v2-only | 8/81 = 9.9% | **12/79 = 15.2%** | 4/79 = **5.1%** |

   The benchmark fix ALONE would raise arm B's over-the-line share (6.7 → 11.3, 9.9 → 15.2) — the same
   mechanism that makes arm C worse. The sweetener then removes 9 of 12 and 8 of 12. **Shipping the
   benchmark fix without the sweetener would be a net regression on this metric**; they must ship
   together, and `sweetener_gap_threshold` is not an independent rollback lever for the benchmark fix.

**Arm A is byte-identical on REAL boards too** — 376 cards, 71 over the line, mean gap 835.6 to 0.1, on
both trees, across all six viewers and both paths. Ratification item 1 (the arm-A golden pinned rather
than re-captured) now has live-data evidence on top of the fixture and the unit test.

**Arm C is worse than the fixture said, and it is a pre-existing problem the branch deepens.** Real
boards: **29.4% → 37.2%** over the line on an identical 51-card deck (fixture: 0 → 13.6% and
5.3 → 10.5%). Most of that level is NOT this branch — jonbonjourvi's arm C is 11 of 13 over the line on
BOTH trees. Ratification item 5 stands, and the arm-C follow-up is confirmed as a priority.

**One caveat the headline numbers hide: net deck size barely moves, but deck CONTENT churns hard.**
Arm B across all 12 viewer-path decks: 107 cards common, 51 main-only, 50 branch-only — roughly a
third of the deck is different. Per-viewer worst case is Bcork on `v2_only`, 4 of 12 cards common. A
tester comparing decks before/after the merge will see much more change than "−1 card" suggests.

**Not measured here, still owed:** the manual TestFlight checklist (item (a)) — unchanged, it needs a
build. This replay covers generation only; the post-generation presentation stack (thompson, diversity,
fatigue, session rerank, first-session shaping, bake-off interleave) was not replayed, so these are
served-CANDIDATE decks, not final served decks.

**Ship recommendation: unchanged — ship.** Every headline moved in the branch's favour relative to the
fixture: less deck loss than the operator pre-accepted, a bigger over-the-line reduction on a higher
real baseline, and a sweetener that closes every gap it touches. The two findings that change anything
are (5) — the halves are not independently shippable — and the arm-C deepening, which is a follow-up,
not a blocker.

---
## 2026-08-21 — Counterparty breaker waves 1+2 (module · seam · narration · mobile element) — full gates, BOTH FLAGS DARK, NOT MERGED, on `claude/counterparty-breaker-plan`

**Branch:** `claude/counterparty-breaker-plan` (worktree `trading-engine-eval-8ab7bc`), tip `fdd1683`
(wave 1 `0b808b5` → wave 2 `9806d01` → taxonomy v1.1.1 `fdd1683`). **Not pushed, not merged.**
Full gates — the operator explicitly declared **NOT express**, and the change is outside the express
lane by the bright-line rule regardless (two new feature flags, 25 new `model_config` keys, a new
API payload field, two new `features_json` keys).
Scope: [docs/plans/counterparty-breaker/scope.md](../docs/plans/counterparty-breaker/scope.md) ·
code-walk: [code-walk.md](../docs/plans/counterparty-breaker/code-walk.md) ·
readout spec: [calibration-readout-spec.md](../docs/plans/counterparty-breaker/calibration-readout-spec.md) ·
checklist: [PRD](../docs/plans/counterparty-breaker/PRD.md) §8.3.
Decision: [D-142](DECISIONS.md).

**Flags, both default OFF and NEITHER graduated:** `trade.breaker` (compute + stamp),
`trade.breaker_narrative` (the on-card hesitation line; structurally requires the first).

**What ran, and what it proves.** Counts below were re-verified by collection in this checkout on
2026-08-21, not quoted from the commit messages.

| Gate | Result |
|---|---|
| `backend/tests/test_trade_breaker.py` | **67 collected, 67 passed** — predicates, determinism, vocabulary + evidence-key closure, degenerate inputs, tie-break, the whole rung ladder, budget, shadow, knob-snapshot freezing |
| `backend/tests/test_breaker_seam.py` | **30 collected, 30 passed** — seam placement, zero ordering effect (parametrized `bakeoff_group_size ∈ {0, N}` + organic), D-11 seam-creep grep guard, flag-off non-import + byte-identity, dark-window payload absence, the full republish matrix |
| `backend/tests/test_trade_narrative.py` | **22 collected, 22 passed** (file total; **10 of them new**) — the narration gate chain, repetition suppression, template snapshot + `brt-1` version pin, honesty (missing **or present-but-null** evidence ⇒ silence) |
| `backend/tests/test_bakeoff_serving.py` | **+4 collected rows / 3 new functions** (`test_impressions_breaker_uniform_keys` parametrized ×2, `test_midjob_flag_flip_no_crash`, `test_flag_off_features_json_carries_no_breaker_key`); file 42 passed. **Correction to the wave-2 hand-off, which said "+5"** — the true figure is 4 collected rows |
| three breaker files together, re-run 2026-08-21 | **119 passed** |
| `python3 -m pytest backend/tests -q` (full suite) | **3872 passed, 1 skipped, 0 failed** in 264 s — measured at tip `fdd1683` this session. (Wave 1 reported 3835/1, wave 2 reported 3869/1. The +3 over wave 2 is **explained**: wave 2 ran `-k "not calibration_gate"` and reported "3 deselected" — 3869 + 3 deselected = 3872 collected. Same suite, no discrepancy) |
| `mobile/tests/check-breaker-card.js` | **12 assertions, 12 passed / 0 failed**, re-run in this checkout. Sabotage-proven at build |
| `mobile/scripts/testid-lint.sh` | **OK**, re-run in this checkout (2 new testIDs: `trade-card.breaker-hesitation`, `trade-card.breaker-hesitation.body`) |
| `cd mobile && npx tsc --noEmit` | **NOT RUN LOCALLY — deferred to CI's `mobile-typecheck` job.** `mobile/node_modules` is absent in this worktree; this is pre-existing and not a property of the change |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything above plus the code-walk |

**Named sabotages that are permanent tests, not one-off cycles.** These landed as tests, so the
proof re-runs on every CI pass rather than living in a session log: `test_breaker_binding_sabotage`
(monkeypatch a `ts` knob ⇒ the next `stamp_breaker` verdict moves — T1 module-import discipline;
plus a module-attribute swap of `ts.package_value_v2` to a sentinel, which a value-binding
implementation would no-op on) · `test_knob_snapshot_frozen_within_job` (mutate `ts._cfg` between
pass 1 and pass 2 ⇒ stamps unchanged) · `test_per_class_exception_contained` (one predicate raises ⇒
that class stamps `skipped:"predicate_error"`, the other five score, card stays rung 0) ·
`test_budget_ladder_labeling` (tiny `breaker_ms_budget` + a slowed predicate ⇒ the correct rung at
each of three trip points, incl. mid-pass-2 buffered work **discarded**) · `test_exception_rungs`
(context-assembly raise ⇒ rung 4 for that card only; `stamp_breaker` monkeypatched to raise at the
seam ⇒ rung-5 marker on **every** card — `test_breaker_seam.py:111` is the injected failure) ·
`test_breaker_zero_ordering_effect` (delete-attribute variant included) ·
`test_flag_off_never_imports_breaker`. The mobile guard was likewise sabotage-proven at build
(each of its 12 assertions driven red by an edit to `TradeCard.tsx`, then restored).

**Gap in this record, stated rather than papered over:** wave 2's commit message reports "4 named
sabotages red→green" and wave 1's reports the guard as "sabotage-proven", but the **individual
wave-2 sabotage names and their red-run output were not written down in-session**. The permanent
sabotage tests above are re-runnable evidence and cover the same seams; the four cycles themselves
are not independently reconstructable from the repo. Recorded as a documentation miss.

**Not run — the load-bearing absence.** The [PRD](../docs/plans/counterparty-breaker/PRD.md) §8.3
manual TestFlight checklist (**19 numbered steps**; steps 1–4 are the dark-window sub-checklist)
is **UNRUN**. It is **operator-owed** and needs a build cut containing the hesitation element, which
does not exist. Per D-056 this checklist is the **only** runtime evidence this feature will ever get,
so as of today **no runtime evidence exists for the counterparty breaker at all** — everything above
is static. `trade.breaker_narrative` must not light before it passes.

**Also owed before `trade.breaker` lights** (preconditions, not stretch items): the TBD-operator
cells in the [calibration-readout spec](../docs/plans/counterparty-breaker/calibration-readout-spec.md)
§4.1 (per-class min n and margins), the §2.4 `fix/package-benchmark-sweetener` deploy timestamp (a
code-ship boundary that `model_config_changes` **cannot** see), the reviewed `scripts/`-style readout
SQL artifact, and the dry-run `ms` number to the operator.

## 2026-08-20f — Composite window model #372 (starter value + playoff likelihood + age at 40 %) — full gates, FLAG DARK, NOT MERGED, on `claude/372-window-composite`

**Branch:** `claude/372-window-composite`, cut from `origin/main` at `c00a9a6`. **Not pushed, not merged** — parent agent integrates.
Full gates ran — operator did **not** declare express, and the change is outside the express lane by the bright-line rule anyway (a new feature flag and new API fields).
Scope: [docs/feedback/items/372-window-composite/scope.md](../docs/feedback/items/372-window-composite/scope.md) ·
code-walk: [code-walk.md](../docs/feedback/items/372-window-composite/code-walk.md) ·
checklist: [testflight-checklist.md](../docs/feedback/items/372-window-composite/testflight-checklist.md).
Decisions: [D-140](DECISIONS.md), [D-141](DECISIONS.md).

**Flag, default OFF and NOT graduated:** `trade.outlook_composite`.

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3761 passed, 1 skipped, 0 failed** (bar was 3721 on `c00a9a6`; +38 new in `test_window_composite.py`, +2 parametrized fixture rows) |
| `cd mobile && ./node_modules/.bin/tsc --noEmit` | clean, exit 0 (`node_modules` symlinked from `jolly-leakey-d20295`) |
| every `mobile/tests/check-*.js` | **67 scripts, 0 failed**, including the new `check-window-composite.js` (14 assertions) |
| `mobile/scripts/testid-lint.sh` | **OK** (2 new testIDs: `team-review.window.starters`, `team-review.window.playoff`) |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything above plus the prod calibration below |

**Two structural guards on `origin/main` fired on this change and were answered, not silenced.** `test_no_generation_knob_was_added_without_an_arm_a_decision` caught all eight new `infer_composite_*` knobs — they are added to `_PINNED_KNOBS` with a written exclusion rationale (they cannot reach generation: the term they weight needs an applied starter signal, which needs a league-wide power-rankings call no generation path makes). `test_release_flags_mirror_features_json` caught the new flag missing from `backend/tests/fixtures/flags/release.json`, and two sibling fixtures (`onboarding-v2`, `profiles-on`) needed the same mirror.

**Sabotage evidence — 22 cycles, every one RED with the NAMED test in the failures, restored via `git checkout --`, proved restored with `git diff --quiet`, re-run GREEN. `__pycache__` cleared between every cycle.**

Backend (13, against `backend/tests/test_window_composite.py`): S1 composite branch drops the `starter_signal is not None` gate · S2 `composite` set regardless of `applied` · S3 flag gate removed · S4 `model` not re-stated at composite weights · S5 refused playoff term scored anyway · S6 starter index uncapped · S7 precedence rule deleted (band replaces AND scores) · S8 `_window` stops passing `starters` through · S9 `starter_value_signal` fakes `observed` on unreadable input · S10 age weights left at 1.00 inside the composite · S11 playoff index scale doubled · S12 starter term gated on `index != 0` instead of `applied` · S13 `index_raw` capped, so the card would print the model's number instead of the team's.

Mobile (9, against `check-window-composite.js`): M1 starter weight hardcoded · M2 `composite` derived from `st.applied` alone · M3 `lineup_unknown` copy branch removed · M4 `signals.starters` made required in the type · M5 `'composite'` dropped from the `source` union · M6 "whole model" sentence made unconditional · M7 `starterScored` gated on `st.index !== 0` · M8 playoff contribution row deleted · M9 starter card switched to the capped `index`.

**TWO DEAD ASSERTIONS FOUND AND FIXED — this is the finding, not a footnote.**

1. **S5 did not go red on the first run.** `test_a_refused_playoff_term_is_absent_from_the_score_not_a_zero` built its refused signal from `playoff_odds_signal`, which zeroes `index` whenever it refuses — so deleting the `applied` guard was a numeric no-op and the test passed against a broken function. Fixed by handing `infer_team_outlook` a refused block with a **loud** index of 0.8; only the `applied` check can now keep it out. Its starter-side sibling (`test_an_unapplied_starter_signal_with_a_LOUD_index_still_scores_nothing`, sabotage S12) was written at the same time for the same reason.
2. **M7 did not go red on the first run.** Mobile check 4 read `/starters[\s\S]{0,80}index\s*[!=]==?\s*0/` — it required the literal word "starters" within 80 characters of the comparison, but the real gate is written `st.index`. Rewritten to match the comparison itself anywhere in the beat, plus a new positive half (4b) asserting both `Scored` flags derive from `applied`.

Both were the exact class the brief warned about: an assertion that holds by accident and can never fail. They join the three found earlier the same day.

**Prod calibration — read-only, and it is the load-bearing evidence.** The #365 session concluded from `data/trade_finder.db` that this family of signal pointed the wrong way; **that corpus does not contain FFV3 at all**. Every number below comes from a read-only `DATABASE_URL_PROD` connection (`set_session(readonly=True)`) plus the league's real Sleeper lineup template.

- **`Fantasy Football Version 3` (`1312140920132497408`), `mattmurf77`: legacy `−0.4867 rebuilder` → composite `+0.2009 CONTENDER`.** His starters are worth 43,615 against a league mean of 23,963 — 82 % above average, the best starting lineup in the league — while he holds essentially no pick capital (0.004 share against an even 0.083). The league is `pre_draft`, so the playoff term is refused (`preseason` / `odds_disabled`) and the composite runs on starters, picks and down-weighted age alone.
- **The reverse sanity check:** `PaulSm3nis` is a legacy **contender** on age alone (vet share 0.65) while owning the league's *worst* starting lineup (3.2 % share) and sitting 12th of 12 in value. The composite calls him a rebuilder.
- **Across 12 prod leagues / 156 teams:** legacy = **101 rebuilder / 26 not_sure / 29 contender** (65 % rebuilder, and *zero* not_sure verdicts in FFV3 itself); composite = 62 / 40 / 54. Transitions run both ways (29 rebuilder→contender, 4 contender→rebuilder, 8 contender→not_sure), which is what a re-weighting looks like rather than a thumb on the scale. This distribution is the evidence for **leaving `infer_contender_cut` / `infer_rebuilder_cut` unmoved** (D-140).

**Not run:** the TestFlight checklist (8 numbered steps across all four flag combinations) — it needs a build containing this branch, which does not exist. No runtime mobile evidence exists for #372 yet; the flag stays dark until it does.

## 2026-08-20b — Fit challenger PR-F3 (filters + arm wiring + serve-bit) + W0 offline dry run (SHIPPED to `main` 2026-08-20)

**Branch:** `claude/trade-suggestions-review-69c9eb` (worktree), on top of PR-F2 `d8a80a5`. **Not committed, not merged** — the finishing package of the fit-challenger build ([PRD-build](../docs/plans/fit-challenger/PRD-build.md) PR-F3 + deferred docs rows).
## 2026-08-20c — Window signals #365 (net firsts) + #371 (playoff odds) — full gates, BOTH FLAGS DARK, NOT MERGED, on `worktree-agent-a3ea3b1d38e084930`

**Branch:** `worktree-agent-a3ea3b1d38e084930`, cut from `origin/main` at `bc43b6f`. **Not pushed, not merged.**
Full gates ran — operator did **not** declare express, and explicitly ruled the change outside the express lane (it adds two feature flags and two API fields).
Scope: [docs/feedback/items/365-window-signals/scope.md](../docs/feedback/items/365-window-signals/scope.md) · code-walk: [code-walk.md](../docs/feedback/items/365-window-signals/code-walk.md) · checklist: [testflight-checklist.md](../docs/feedback/items/365-window-signals/testflight-checklist.md).
Decisions: [D-110](DECISIONS.md), [D-111](DECISIONS.md).

**Flags, both default OFF and neither graduated:** `trade.outlook_net_firsts`, `trades.window_from_odds`.
## 2026-08-20e — Team Review `plan` beat rebuilt (#369) — full gates, NOT MERGED, on `worktree-agent-a7bed877f805980b0`

**Branch:** `worktree-agent-a7bed877f805980b0`, worktree at `origin/main` `bc43b6f`. **Not pushed, not merged** — parent agent integrates.
Full gates ran — operator did **not** declare express.
Scope: [docs/feedback/items/369-plan-beat/scope.md](../docs/feedback/items/369-plan-beat/scope.md) ·
Code-walk: [code-walk.md](../docs/feedback/items/369-plan-beat/code-walk.md) ·
Decisions: [D-130](DECISIONS.md), [D-131](DECISIONS.md).

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3645 passed, 1 skipped, 0 failed** (bar was ≥ 3629; +20 new fit/serving tests) |
| Knob-inventory guard (`test_no_generation_knob_was_added_without_an_arm_a_decision`) | green with **all 17** fit/bakeoff keys in `_PINNED_KNOBS` + 17 disposition sentences in scope-phase2.md |
| Organic isolation | `test_organic_never_imports_fit` (sys.modules + comment-stripped source grep) + the standing flag-off captured golden (`test_flag_off_is_byte_identical_to_the_captured_golden`) both green |
| `bash mobile/scripts/testid-lint.sh` | **OK** |
| `npx tsc --noEmit` | not run in this worktree (no `node_modules`); **zero mobile files touched** — the mobile CI jobs are byte-identical to `origin/main`'s green |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = the suite above |

**Sabotage evidence (serve-bit, both draft paths — HLD F-6).** `test_serve_fit_bit_excludes_from_draft` is parametrized over `bakeoff_group_size ∈ {0, 10}`. Sabotage: the `group_size = 0` fallback's rotation was reverted from `serving_roster` to the full `roster` (the exact F-6 leak — one line in `run_bakeoff`). Result: **`[0]` went red, `[10]` stayed green** — proving the 0-path case guards the `team_draft` fallback specifically (the W1 live path), not just `compose_deck`. Reverted, re-ran green; full suite re-run green after.
Prior sabotages standing from PR-F1/F2: T1 binding (`overpay_ok` rebind), M3 inertness (`fit_diag` delete), C7b (`test_draft_rank_only`, new in this package: one arm's composite ×100 ⇒ identical deck).

**W0 offline dry run (PLAN-v2 §5 W0) — FIXTURE-ONLY.** No prod DB access from this worktree: the replay boards for league `1312140920132497408` are a prod artifact and were NOT run — that half of the W0 contract plus the baseline M2 readout snapshot is an **operator item**. Leagues below: (a) the literal bakeoff-test fixture league (`backend/tests/support/bakeoff_harness._POOL`); (b)/(c) leagues built deterministically from the committed 340-player pool `backend/tests/fixtures/player_pool_2026.json` with rank-ladder Elo seeds (1750→1250), hash-offset synthetic boards (±120 on ~40% of assets; viewer + half the opponents boarded), and 3 owned-pick pseudo-assets per team. Script: session scratchpad `w0_dry_run.py` (throwaway, not committed). All at PRD-default knobs unless noted; viewer outlook None unless noted.

| League | Cap | ms (module) | enumerated | scored | emitted | killed (nonzero) | one_sided | both_high/mixed/you_tilt | top_q pick/junk | capped_pairs |
|---|---|---|---|---|---|---|---|---|---|---|
| (a) harness fixture (8 players, 2 opp) | 20000 | **0** | 16 | 0 | 0 | K3 6, K4 10 | — | — | — | 0 |
| (b) 12-team 1QB, 26-man+3-pick | 20000 | **8396** (repeat 5769) | 195,783 | 38,634 | 253 | K2 520 · K3 416 · **K4 133,923** · K5 15,765 · K6 6,525 | 0.480 | .045/.100/.164 | **0.699** / 0.055 | 6/11 |
| (b') same, W3 posture cap 5000 | 5000 | **1826** | 55,000 | 11,326 | 248 | K4 37,389 · K5 4,254 · K6 1,764 · K2 158 · K3 109 | 0.446 | .081/.150/.209 | 0.648 / 0.059 | 11/11 |
| (b+outlook=contender) | 20000 | 5312 (wall) | 194,913 | 33,976 | 156 | **K7 6,925** + as (b) | 0.496 | — | — | — |
| (c) 16-team SF (`sf_tep`), 21-man+3-pick | 20000 | **5772** | 227,230 | 38,090 | 333 | K4 154,455 · K5 27,703 · K6 4,971 · K3 1,391 · K2 620 | 0.417 | .142/.166/.192 | 0.682 / **0.390** | 7/15 |
| (c') same, cap 5000 | 5000 | **1374** | 70,210 | 10,637 | 294 | K4 46,900 · K5 10,449 · K6 1,449 | 0.359 | .237/.178/.187 | 0.638 / 0.375 | 14/15 |

Emitted bucket mix (b, defaults): both_high 47 · mixed 101 · them_tilt 24 · you_tilt 22 · both_ok 5 · weak 54. Post-filters: **C4 centerpiece cap is the dominant post-score filter** (38,381 of 38,634 scored dropped on (b) — small-league centerpiece concentration; `deck_headliner_cap` 2). All other `post_filtered` counters 0 (no prefs in the fixture jobs).

**Readings for the operator (the decisions this run feeds):**

- **ms fail bar (scope.md §6, blocks rostering):** 12-team defaults ≈ **5.8–8.4 s** per job; at the W3 posture (`fit_max_packages_per_pair = 5000`) ≈ **1.4–1.8 s**; 16-team SF the same shape. The cap knob is the relief valve exactly as designed — W3's 5000 first looks right.
- **R-8 volume check:** fit **253** distinct ideas vs arm B **12** (engine-default `max_per_opponent=5`, same league, 307 ms) — ratio ≈ **21×**, far above the 1.2× bar ⇒ per R-8 the build **pauses at this readout for an operator call**; no auto-roster. (Also the PRD §11.6 read: `enumerated` 195,783 ≫ arm B's emitted set.)
- **`killed[K7]` (F7 evidence):** 0 with no declared outlook (live R5 is outlook-scoped), **6,925** under `contender` — the dual-R5 debate has its number, but only on outlook-declared jobs.
- **W3 soak-bar preview:** `top_q_junk_share` 0.055 on the 12-team fixture (bar ≤ 0.10: passes) but **0.375–0.390 on the constructed 16-team SF fixture** — likely an artifact of 21-man rosters built from a 340-player pool (deep tails sit under `asset_floor_abs` 450 in the rank-ladder Elo mapping), but it is exactly the C5 flooding signature the soak bar exists for: read it on real W3 data before trusting either interpretation. `top_q_pick_share` ≈ 0.64–0.70 everywhere (picks ride high consensus percentile under R-c) — the W3 bar is relative to arm B, which this fixture cannot supply.
- **(a) harness fixture emits 0 cards** — its 4-asset rosters put every cross-value package over K4's overpay ceiling; a fixture artifact, not a generator defect (the 26-man leagues emit 250+).

**What is NOT proven, and is owed.** Prod replay boards (league `1312140920132497408`) + baseline M2 readout snapshot — operator, needs prod read access. Constructed-league Elo/boards are synthetic (rank-ladder + hash offsets), so bucket mixes and junk shares are directional, not calibrated. `bakeoff_include_fit` stays 0 (decision 4) until the operator sets the ms bar and answers R-8; `bakeoff_serve_fit` stays 0 regardless.

---
| `python3 -m pytest backend/tests -q` | **3646 passed, 1 skipped** (259 s). Baseline before this work on the same tree: **3606 passed, 1 skipped** — +40, all in the new `backend/tests/test_window_signals.py` |
| `cd mobile && ./node_modules/.bin/tsc --noEmit` | **clean** |
| `mobile/tests/check-*.js` — **65** suites (64 pre-existing + the new `check-window-signals.js`) | **0 failed**. `check-window-signals` 10/10, `check-team-review` 7/7 still green |
| `mobile/scripts/testid-lint.sh` | **OK** |
| Sabotage proof — **20 of 20** | every one turned its **named** guard red, each source restored with `git checkout --` and verified **by content** (`git diff --quiet`), `__pycache__` cleared before every run, and re-run green |

**The load-bearing evidence is the flag-off invariant, and it is a golden, not a re-derivation.**
`infer_team_outlook` feeds `outlook_alpha` for the trade engine, the mock draft and the outlook seed,
so a score change is a deck change for every user. The goldens in `test_window_signals.py` were
captured by extracting the `bc43b6f` backend tree (`git archive`) and running the same fixtures
against it — code that had never heard of the new kwarg — rather than by re-deriving the formula the
module now contains, which would have proved nothing. Two invariants pinned:
**INV-365** flag OFF ⇒ the ledger kwarg is accepted and ignored, whole tuple equal;
**INV-365b** flag ON but no ledger ⇒ score still unchanged, because only the Team Review route
builds a ledger. Together they mean lighting `trade.outlook_net_firsts` moves the window beat and
**not one deck**.

**Sabotage table — 20 cases.** Harness `scratchpad/sabotage_365_371.py`; per case: apply one targeted
revert → clear `__pycache__` → run → require red **and** require the *named* guard to be the one that
failed → `git checkout --` → `git diff --quiet` → clear `__pycache__` → re-run → require green.

| # | Behaviour reverted | Guard | Red | Clean | Green |
|---|---|---|---|---|---|
| S1 | term applies with the flag OFF | `test_flag_off_ignores_a_supplied_ledger_entirely` | yes | yes | yes |
| S2 | term applies with the flag on but no ledger | `test_flag_on_without_a_ledger_is_still_the_golden` | yes | yes | yes |
| S3 | sign flipped (hoarding reads as contending) | `test_selling_firsts_raises_the_score_and_hoarding_lowers_it` | yes | yes | yes |
| S4 | `net_share` clamp removed | `test_net_share_is_clamped_by_the_knob` | yes | yes | yes |
| S5 | uncaptured pick history scores as a confident zero | `test_a_league_with_no_recorded_trades_is_none_traded_not_a_confident_zero` | yes | yes | yes |
| S6 | empty roster still reports the term applied | `test_empty_roster_never_reports_an_applied_term` | yes | yes | yes |
| S7 | `window.model` advertises unused knobs | `test_model_carries_the_new_knobs_whenever_the_term_is_live` | yes | yes | yes |
| S8 | NULL original owner read as a trade | `test_ledger_reader_treats_a_null_original_owner_as_never_moved` | yes | yes | yes |
| S9 | ledger counts every round, not just firsts | `test_ledger_reader_splits_held_owned_traded_and_acquired` | yes | yes | yes |
| S20 | ledger stops attributing acquisitions | `test_ledger_reader_splits_held_owned_traded_and_acquired` | yes | yes | yes |
| S19 | ledger computed then not passed through | `test_window_passes_the_firsts_ledger_through_untouched` | yes | yes | yes |
| S10 | preseason odds obeyed instead of refused | `test_preseason_refuses_the_band_but_still_reports_it` | yes | yes | yes |
| S11 | empty band dict treated as a real band | `test_no_band_falls_back_and_names_it` | yes | yes | yes |
| S12 | #371 keys ship with the flag off | `test_window_is_shape_identical_when_both_flags_are_off` | yes | yes | yes |
| S13 | heuristic verdict lost when odds override | `test_window_reports_which_model_drove_and_keeps_the_other_one` | yes | yes | yes |
| S14 | beat hardcodes an age threshold again | `check-window-signals` 1 | yes | yes | yes |
| S15 | ledger shown but contribution not itemised | `check-window-signals` 2 | yes | yes | yes |
| S16 | "we ignore traded picks" becomes fixed copy | `check-window-signals` 3 | yes | yes | yes |
| S17 | `none_traded` no longer distinguished | `check-window-signals` 4 | yes | yes | yes |
| S18 | a flag-gated field made required in the type | `check-window-signals` 7 | yes | yes | yes |

**One guard in this batch was vacuous, and the sabotage is what found it — recorded because it is the
more useful finding.** `check-window-signals` claim 2 originally asserted only that the identifier
`w_net_firsts` appeared somewhere in the `Window` component. It does, unconditionally: the weight is
destructured at `TeamReviewScreen.tsx:390`. So **S15 deleted the contribution row outright and the
check stayed green.** It now requires the *product* — the weight × `net_share` on one line, with the
alias discovered from the source rather than assumed. This is the same class of failure the
2026-08-20a batch hit (`test_divergence_ignores_unjudged_players` went vacuous while passing), which
is why the harness requires the **named** guard to fail rather than merely a red run.

**Three pre-existing structural guards fired on this change and were each resolved deliberately, not
suppressed.** All three are working exactly as designed and are recorded so the resolutions are
auditable:
- `test_bakeoff_arm_a_golden::test_no_generation_knob_was_added_without_an_arm_a_decision` — two new
  `_DEFAULT_CFG` knobs. **Excluded from `MODEL_A_PROFILE`**, with the reason recorded in
  `docs/plans/three-model-bakeoff/scope-phase2.md`'s exclusion table: they cannot reach generation at
  all, because the term is gated on a ledger no generator supplies (INV-365b). Pinning a kill value
  would imply they matter to a deck; they provably do not. Arm-A golden re-run green.
- `test_pick_assignment::test_w3_02_ast_only_sanctioned_call_sites_name_source` — `_first_round_ledgers`
  is the **eighth** sanctioned `load_draft_picks` opt-in, added to `_SEVEN_READ_SITES` with the
  rationale inline: it must count the same picks `_power_picks_by_owner` prices two lines away in the
  same route, so a literal `platform` would make the card and the beat above it disagree on any ESPN
  league with `picks.assign_tradeable` on.
- `test_seed_ui_test_db` (three assertions) — the flag fixtures. Both flags added `false` to
  `release.json`, `onboarding-v2.json` and `profiles-on.json`, which are asserted to share a key set;
  deliberately **not** added to `all-on.json` (a client overlay, not a full map), matching the
  `outlook.odds` precedent.

**Calibration evidence, and the finding that cuts against the feature.** `infer_w_net_firsts = 0.10`
was set against the only real pick corpus reachable from the session (`data/trade_finder.db`): across
24 member-league pairs in the two leagues that carry round-1 provenance, `|net_share| ≤ 0.75`, so the
contribution range is ±0.075 against a `not_sure` band of ±0.08 — one bucket at most, never two,
pinned by `test_the_term_can_move_one_bucket_and_never_two`. **In both of those leagues the operator
has traded away zero of his own firsts and acquired one**, so the signal he asked for points *him*
further toward rebuilder; and **FFV3, the league in the report, has no `draft_picks` rows in that DB
at all**. Prod Postgres would settle both and was not reachable (the read was denied by the sandbox).
This is why the flag ships dark and why its graduation criterion is an operator check on prod.

**CORRECTED SAME DAY by a read-only prod query.** The local corpus was the problem, and the conclusion above is BACKWARDS for the league that filed the report. Prod carries 276 round-1 rows across 7 leagues with a traded first; in **Fantasy Football Version 3 (FFV3, `1312140920132497408`) `mattmurf77` holds ZERO firsts having sold all three of his own — **3 sold, 0 acquired, 0 still owned** — stated as counts on purpose, because the two conventions in play have opposite signs: this prose had been reading "net +3" in a sold-minus-bought sense while the CODE scores `firsts.net_share` as owned-minus-traded, i.e. **−3**. Same fact, opposite sign, and neither had stated its convention. The scoring direction is correct either way (the score subtracts `w × net_share`, so a seller gains)**, the strongest all-in reading the term produces, pointing him toward CONTENDER. His other leagues run the other way (La Resistance −5, Lakeview −1). Lesson worth keeping: *a local DB that is missing the subject league is not a small sample, it is the wrong sample* — and it produced a confident, inverted finding that would have argued against shipping the right fix.

**Not run, and owed:** the manual TestFlight pass
([testflight-checklist.md](../docs/feedback/items/365-window-signals/testflight-checklist.md)). It is
the gate on graduating either flag. Note that §C4–C6 (the odds path actually driving) **cannot be
walked until week 1 is played** — `completed_weeks == 0` today, and the refusal is the designed
behaviour, so the in-season half of #371 has no runtime evidence yet and must not be claimed.

---

## 2026-08-20d — #366 position-relative tier bands + RB Handcuff — full gates, NOT MERGED, on `worktree-agent-a4ab94c51456abb78`

**Branch:** `worktree-agent-a4ab94c51456abb78`, worktree at `origin/main` `bc43b6f`. **Not pushed, not merged.**
Full gates ran — operator did **not** declare express. Both flags ship **OFF** and are **not graduated**.
Scope: [docs/feedback/items/366-tier-ladder/scope.md](../docs/feedback/items/366-tier-ladder/scope.md).
Code-walk: [code-walk.md](../docs/feedback/items/366-tier-ladder/code-walk.md).
Decisions: [D-120](DECISIONS.md), [D-121](DECISIONS.md).

**What ran.**

| Gate | Before | After |
|---|---|---|
| `python3 -m pytest backend/tests -q` | 3606 passed, 1 skipped (356s) | **3638 passed, 1 skipped** (352s) |
| `tsc --noEmit` | clean | **clean** |
| `mobile/tests/check-*.js` (65 suites) | 64 suites, 0 failed | **65 suites, 0 failed** (new `check-team-review-depth` 8/8; `check-team-review` still 7/7) |
| `bash mobile/scripts/testid-lint.sh` | OK | **OK** |
| Sabotage proof | — | **12 of 12 turned their guard red**, restored clean, re-run green |

New tests: `backend/tests/test_position_tiers.py` (**30**), `backend/tests/test_team_review.py` (**+2**),
`mobile/tests/check-team-review-depth.js` (**8 assertions**). Net +32 backend tests (3606 → 3638).

**Sabotage table.** Every cycle: apply one targeted revert → run → require RED **and** require the
*named* guard to be the one that failed → `git checkout --` → prove restoration with
`git diff --quiet` (never with a test result) → re-run → require GREEN.
`find backend -name __pycache__ -type d -exec rm -rf {} +` ran before **every** invocation, because a
`git checkout` restore leaves the source older than the sabotage run's `.pyc` and Python will happily
serve stale bytecode — a correct tree then tests red and the whole table becomes noise.

| # | Sabotage applied | Guard that caught it | Red | Restored clean | Green again |
|---|---|---|---|---|---|
| S1 | emit the `replacement` alias unconditionally | `test_flag_off_adds_no_keys_anywhere` | ✅ | ✅ | ✅ |
| S2 | band boundary `<=` → `<` | `test_relative_band_boundaries` | ✅ | ✅ | ✅ |
| S3 | drop the superflex QB widening | `test_superflex_widens_qb_and_nothing_else` | ✅ | ✅ | ✅ |
| S4 | `_POS_TIER_MIN_POOL` 40 → 0 | `test_thin_pool_falls_back_to_absolute_cuts` | ✅ | ✅ | ✅ |
| S5 | handcuff accepts `order in (1, 2)` | `test_handcuff_rejects_everything_that_is_not_an_rb2` | ✅ | ✅ | ✅ |
| S6 | reorder so `_is_handcuff` runs before the flag check | `test_flag_off_never_touches_the_depth_chart` | ✅ | ✅ | ✅ |
| S7 | composer emits `handcuff_rb` unconditionally | `test_depth_omits_366_keys_entirely_when_the_flags_are_off` | ✅ | ✅ | ✅ |
| S8 | mobile reads `replacement ?? 0` (drops the `bench` fallback) | `check-team-review-depth` #2 | ✅ | ✅ | ✅ |
| S9 | mobile gates on `(handcuff_rb ?? 0) >= 0` | `check-team-review-depth` #4 | ✅ | ✅ | ✅ |
| S10 | TS type makes `replacement` required | `check-team-review-depth` #3a | ✅ | ✅ | ✅ |
| S11 | force `relative = True` (relative path leaks with the flag OFF) | `test_flag_off_bins_follow_the_absolute_cuts_exactly` | ✅ | ✅ | ✅ |
| S12 | drop the "Replacement" label from the beat | `check-team-review-depth` #5a | ✅ | ✅ | ✅ |

**The finding that matters more than the table: 65 existing engine tests are BLIND to this change.**
Per the standing instruction to re-read the tests that *pass*, `test_roster_profile`, `test_need_fit`,
`test_finder_targeting` and `test_presentment_rules` were re-run with `relative` forced `True` in
source. **All 65 stayed green.** The cause was then confirmed rather than assumed: disabling
`_POS_TIER_MIN_POOL` as well turns exactly **1 of 65** red, so every fixture in those files is smaller
than the small-pool guard and cannot distinguish the bands even in principle. They are evidence for
the flag-**off** path only. Consequence, recorded in the scope block and D-120:
**`trade.position_tiers` must not graduate on a green suite** — it needs `scripts/deck_eval.py` on real
leagues plus step 6 of the TestFlight checklist.

**Measurements taken during the build** (not test results — inputs to the design):
- Absolute cuts against the live pool (`data/trade_finder.db`, 2 684 players): **elite = 33 RB, 33 WR,
  17 QB, 7 TE.** The reported defect, quantified.
- The three value thresholds are exactly overall-`search_rank` cuts at **73 / 151 / 238**
  (`1 + ln(ktc_max/T)/ktc_k`, `ktc_k = 0.0126`).
- Depth-chart coverage: **149 of 603** RB rows carry a real `depth_chart_order`, matching the 32 actual
  NFL charts. The nulls are camp bodies and FAs.
- `_positional_rank_map` build cost: **1.31 ms** over 2 684 players (50 iterations); memoized on pool
  identity, so ~1 build per request rather than 13 per deck run.

**TestFlight:** checklist written
([testflight-checklist.md](../docs/feedback/items/366-tier-ladder/testflight-checklist.md), 6 steps),
**not run** — owed by the operator, and moot until a flag is lit. Step 3 deliberately checks the
handcuff tag against nfl.com rather than merely checking that something rendered.

**Not covered by anything here:** whether the new bands make decks *better*. That is a judgement call
and it is the operator's; the flags ship off so it does not have to be made today.
| `python3 -m pytest backend/tests -q` | **3606 passed, 1 skipped** (339s) — unchanged from baseline; no backend code was touched |
| `tsc --noEmit` | **clean** |
| 64 `mobile/tests/check-*.js` suites | **0 failed**; `check-team-review` went **7 → 13 assertions**, all green |
| `mobile/scripts/testid-lint.sh` | **OK** |
| Sabotage proof — 9 of 9 | **every one turned its guard red on the EXPECTED assertion**, sources restored, guard re-run green after each |

**Sabotages, individually.** (5b) render `{o.playoff_pct}` as visible text → RED;
(6) source the plan chips from `data.depth.acquire_positions`, the stale mount-time snapshot → RED;
(6b) drop `refetchOnMount: 'always'` → RED;
(7) gate a plan-beat lever on `done.current` again → RED;
(8) rename the "Trade fairness" lever off the page → RED;
(9) add a second `asset_preferences` writer to the screen → RED;
(10) remove the `team_outlook` backfill, i.e. reinstate the shipped bug → RED;
(11a) stop handing the scoped partner to the #330 store → RED;
(11b) delete the deck-side handoff consumption in `TradesScreen.tsx` → RED.

**Two findings recorded because they are worth more than the pass count.**
- **A shipped write has never once succeeded.** The depth beat posted a positions-only body and
  `POST /api/league/preferences` **400s without `team_outlook`** (`server.py:15788-15790`);
  `apiRequest` throws on non-2xx, so `done.current.add('positions_set')` on the next line never ran and
  the empty `catch` hid it. `team_review_action_taken{action:'positions_set'}` has therefore **never been
  emitted in production** — do not read its history as a baseline. Now pinned by assertion 10.
- **An existing green assertion was about to go vacuous — the same failure mode as 2026-08-20a.**
  Assertion 5b guarded "never render a bare playoff percentage" with a whole-FILE escape hatch
  (`… && !/accessibilityLabel/.test(s)`). `TeamReviewScreen.tsx` at `HEAD` contained **zero**
  `accessibilityLabel` occurrences, which is the only reason the clause held; the plan beat's chips add
  three, so from this commit the condition could never be true and 5b would have kept passing while
  proving nothing. Rewritten per-occurrence in the same commit and sabotage-proven. *Two batches
  running, two dead-test escapes — re-reading the tests that PASS is now the cheapest gate we have.*

**What is NOT proven.** The manual TestFlight checklist
([testflight-checklist.md](../docs/feedback/items/369-plan-beat/testflight-checklist.md), 9 steps) is
**UNRUN**. Under [D-056](DECISIONS.md) it is the only runtime evidence this gets, and the central claim
— that the beat shows what is *actually saved* — is a network read whose failure mode is a stale but
entirely plausible page. Steps 2, 3 and 7 are the load-bearing ones. **Requires a client release**; none
of this is in build 122.

---
## 2026-08-20a — Team Review defect batch (#364/#367/#368) — full gates, NOT MERGED, on `claude/team-outlook-experience-27a7a1`

**Branch:** `claude/team-outlook-experience-27a7a1`, worktree at `origin/main` `a76498e`. **Not pushed, not merged** *(at time of writing — since merged to `origin/main` as PR #152, `bc43b6f`)*.
Full gates ran — operator did **not** declare express.
Scope: [docs/feedback/items/364-team-review-fixes/scope.md](../docs/feedback/items/364-team-review-fixes/scope.md).
Decisions: [D-100](DECISIONS.md), [D-101](DECISIONS.md).

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `pytest backend/tests` | **3606 passed, 1 skipped** (292s) |
| `tsc --noEmit` | **clean** |
| 64 `mobile/tests/check-*.js` suites | **0 failed** (incl. `check-team-review` 7/7, `check-outlook-bands` 7/7) |
| `mobile/scripts/testid-lint.sh` | **OK** |
| Sabotage proof — 5 of 5 | **every one turned its guard red**, sources restored, full suite re-run green |

**Sabotages, individually.** (1) drop the `#368` kwargs → `test_team_review_route_passes_the_pick_capital_it_computes` FAILED;
(2) re-cross the seed ladder → `test_seed_ladder_buys_are_off_roster_and_sells_are_on_roster` FAILED;
(3) re-cross the community ladder → `test_community_ladder_maps_buys_to_higher_and_sells_to_lower` FAILED;
(4) stop shipping `model` → `test_window_ships_the_model_so_no_client_restates_a_threshold` FAILED;
(5) restore `gap = u - c` → `test_consensus_gap_sells_are_where_the_market_is_higher_than_you` FAILED.

**Two pre-existing tests were not merely re-run — they were wrong, and are recorded here because
that is the more useful finding.**
- `test_consensus_gap_sells_expose_rank_gap` **asserted the defect**: it took a player the user rated
  300 *above* the community and asserted he was an "easiest sell". Re-encoded and renamed; it now holds
  **both** roster players so it proves a *selection* (the 200-below player in, the 300-above player out).
- `test_divergence_ignores_unjudged_players` went **vacuous** under the fix — its fixture put p1
  on-roster-and-high and p2 off-roster-and-low, so under the corrected rule both lists came back empty
  and its leak assertion proved nothing **while still passing green**. Roster re-aimed, plus an explicit
  non-emptiness assertion so it cannot silently hollow out again. *A green suite was hiding a dead test.*

**Gotcha worth the note.** After a sabotage cycle, restoring a file with `cp` from a backup gives it an
**older mtime than the `.pyc` written during the sabotage run**, so Python reuses the sabotaged bytecode
and the restored tree tests red. `find backend -name __pycache__ -type d -exec rm -rf {} +` between
cycles; verify restoration with `git diff`, not with a test result.

**Post-merge, on the pushed sha.** GitHub Actions on PR #152: `backend-tests` **pass** (6m33s),
`mobile-typecheck` **pass** (52s), `maestro-testid-lint` **pass** (8s). Merged `bc43b6f`; Render deploy
**live** on that sha (verified via the Render API, not by assumption). EAS build **124** (v1.15.0,
commit `bc43b6f`) finished and was **accepted by App Store Connect**; Apple processing pending.

**What is NOT proven.** The manual TestFlight checklist
([testflight-checklist.md](../docs/feedback/items/364-team-review-fixes/testflight-checklist.md), 13 steps)
is **UNRUN** — under [D-056](DECISIONS.md) it is the only runtime evidence this gets, and **nobody has
seen the corrected divergence beat on a device**. Step 8 (the sell list contains players you are LOW on)
is the whole change. Step 13 covers the Trends screen, which moved with the upstream fix.
---
## 2026-08-19h — `outlook.odds` LIT by operator override + its replacement guard (D-094, NOT MERGED, on `claude/team-review-analysis-plan-1f91e3`)

**Branch:** `claude/team-review-analysis-plan-1f91e3`, branched from `origin/main` `50e0451`. **Not pushed, not merged.**
Operator override 2026-08-19 (*"Outlook odds should be visible. Forward PPG cut. I waive maestro"*) flipped
`outlook.odds` `false` → **`true`**, reversing the same session's [D-093](DECISIONS.md) recommendation.
Decision: [D-094](DECISIONS.md). Docs: [docs/feedback/items/357-team-review/](../docs/feedback/items/357-team-review/status.md).

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `node mobile/tests/check-outlook-bands.js` (new) | **7 passed, 0 failed** against the real shipped sources |
| Sabotage proof — all six | **6 of 6 turned the guard red**, then sources restored and `git diff` verified empty |
| `config/features.json` JSON validity after the flip | parses; `outlook.odds == True` |
| CI pickup | automatic — `ci.yml` `mobile-typecheck` globs `tests/check-*.js`; **no CI edit needed** |

**The six sabotages, each with the assertion it was required to break:**

| Sabotage | Assertion that went red |
|---|---|
| `PLAYOFF_BAND_LIKELY_MIN` 0.65 → 0.70 | 1. thresholds are 0.65 / 0.35 |
| `likely: semantic.pos` → a raw hex literal | 2a. bands use the semantic tokens |
| `playoffBand`'s `p >= LIKELY_MIN` → `p > LIKELY_MIN` | 3. boundaries belong to the higher band |
| Add a `title_pct` read to the screen | 4. `title_pct` is never read |
| `OUTLOOK_WEEK6_PERCENT_ENABLED` false → true | 5. the bare percentage stays off |
| Strip the "unrenderable" warning from `api/league.ts` | 4b. league.ts warns title_pct is unrenderable |

**MERGED 2026-08-19 (PR #142, `6a3eab3`) — the gate set completed after this entry was first written.**
The original entry recorded pytest as *not run for this change*; that was true of the flag flip alone but
became false once the flip broke three tests. Corrected, final numbers on the merged sha:

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3525 passed, 1 skipped, 0 failed** |
| `npx tsc --noEmit` | **clean (exit 0)** — run after `npm ci`, which this worktree had been missing |
| Full structural glob, `for f in tests/check-*.js` | **61 passed, 0 failed** |
| `bash mobile/scripts/testid-lint.sh` | **OK** |
| Live verification | `/api/feature-flags` on Render serves `outlook.odds: true` |

**Three tests failed on the first attempt and all three were mine** — the flip is five touches, not one:
`test_flag_is_registered_and_defaults_off_everywhere`, `test_ships_off_route_is_unreachable_and_makes_no_sleeper_call`,
and `test_release_flags_mirror_features_json`. A peer session independently hit the same wall and flagged a
fourth trap I had not yet reached and verified myself before acting: `onboarding-v2.json` and `profiles-on.json`
are each asserted to differ from `release.json` by **exactly one key**, so moving `release` alone breaks both —
a failure that only surfaces on a full suite run, one cycle after the obvious fix.

**Sabotage proof for the rewritten kill-switch test:** removing the `is_enabled("outlook.odds")` guard from
`/api/league/outlook` made `test_flag_off_still_closes_the_route` fail (200 instead of 404); `backend/server.py`
restored and `git diff` verified empty.

**Evidence posture under D-056.** The operator **waived** the Maestro flow this lighting owed
(`NEXT.md` item 7) — it was already void when D-056 retired Maestro entirely. The guard above replaces it
as the standing structural net. **No backend test was run for this change and none was needed:** the flip
touches `config/features.json` only; the `/api/league/outlook` route, the pipeline and the serializer are
unmodified and were already covered by `backend/tests/test_outlook_odds.py` and `test_outlook_calibration.py`.

**What is NOT proven, and is owed.**

- **Nobody has seen the lit surface on a device.** The League-Summary outlook strip and section have shipped
  in every build since 2026-08-11 but have never rendered, because the flag was dark. The first TestFlight
  look is owed before this reaches users, and the operator's own league is the first read.
- **`meta.priced_slot_coverage` has never been rendered by any client.** In an IDP league (7 of 15 starting
  slots priced in the operator's FFV3) the bands are an offensive-core estimate presented as a whole-lineup
  one. Team Review's plan specs the caption; League Summary has none.
- **A preseason band can be confidently wrong for an individual league** — 2 of 6 backtested league-seasons
  lose to climatology outright, one with an ordering correlation of +0.022. Bands are immune to being
  *precisely* wrong, not to being wrong.

## 2026-08-19h — likes-you injector quality gates (D-096, NOT SHIPPED, on `fix/likes-you-quality-gates`)

**Branch:** `fix/likes-you-quality-gates`, branched from `origin/main` `50e0451`. **Not pushed, not merged.**
No feature flag: `trade.likes_you` already gates the surface. Knob-only, default **ON** at
`likes_you_gate_level = 2` (its OFF state, level 0, is the defect).
Scope + code-walk + checklist: [docs/plans/likes-you-quality-gates/](../docs/plans/likes-you-quality-gates/).

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q -p no:randomly` | **3540 passed, 1 skipped, 0 failed** |
| Baseline on the same branch point (`50e0451`), before any edit | **3524 passed, 1 skipped** — reproduced exactly, in a separate detached worktree |
| `npx tsc --noEmit` / `testid-lint.sh` / `check-*.js` | **n/a — ZERO mobile files touched.** Not run, and not claimed. |
| Maestro / simulator / `screens/` captures | n/a — retired by [D-056](DECISIONS.md). |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The 10-step operator TestFlight checklist + 2-step rollback rehearsal are UNRUN.** |

**Net +16 tests, all new** (`backend/tests/test_likes_you_gates.py`): the raw-vs-package unit split
(including a guard on the fixture itself, so the file cannot silently stop proving anything), the
gate-level ladder, `likes_you_gate_level = 0` as an exact revert, directional R1 in both directions,
`filler_ok` and its documented kill switch, the no-cap-slot-consumed semantics, that a gated-out
*existing* card keeps its organic deck position, that the card's bar values are the same objects the
gate compared, knob defaults, garbage-level clamping, `likes_you_min_user_gain == user_gain_epsilon`,
and a pin that R2/R3/R5 are deliberately NOT run.

**4 pre-existing tests touched, none loosened:**
- `test_trade_match_flow.py` ×3 (`..._floor_blocks_below_threshold_injection`,
  `..._floor_passes_above_threshold_injection`, `..._floor_knob_override_respected`) — the D-055
  floor block is **kept in full** and re-pinned to `likes_you_gate_level = 0` via `_inject_floor_deck`,
  so every assertion in it now stands guard over D-096's documented revert path instead of being
  deleted. Two docstrings updated to say which level they describe.
- `test_bakeoff_arm_a_golden.py` ×1 — the two new knobs added to `_PINNED_KNOBS`. Arm A is
  **not** pinned to level 0; the exclusion and its reason are recorded in
  [`scope-phase2.md`](../docs/plans/three-model-bakeoff/scope-phase2.md) § Excluded. `bakeoff_profiles.py`
  was **not** touched (a sibling session owns it).

### Prod measurement (READ-ONLY, `SET TRANSACTION READ ONLY`, SELECT only)

Population: **198 served likes-you impressions / 51 distinct cards**, one league, 2026-08-11 → 08-19
(`trade_impressions` for the asset ids, `deck_impressions.features_json` for prod's own logged bar
values). Per-card consensus values reconstructed from `player_value_history` daily snapshots +
`draft_picks.pool_value`; **reconstruction validated at median abs error 2.9** against 83 rows where
prod logged both the assets and the bar values, and it reproduces the audit's worst card to the
decimal (−6,019.4 on the recorded values).

| Option | Impressions surviving | Distinct cards | User-pays | Worst bar delta |
|---|---|---|---|---|
| **As served today** | 198 / 198 | 51 / 51 | **115** | **−5,571** |
| Package floor ≥ 0 only (level 1) | 83 (41.9%) | 16 | 0 | +32 |
| **Package floor ≥ 0 + directional R1 + `filler_ok` (level 2, SHIPPED)** | **83 (41.9%)** | **16** | **0** | **+32** |
| Package floor ≥ 0 + **blanket** R1 | 25 (12.6%) | 9 | 0 | +32 |
| Package floor ≥ 0 + blanket R1 + fairness ≥ 0.75 | 25 (12.6%) | 9 | 0 | +32 |
| Fairness ≥ 0.75 alone | 115 (58.1%) | — | 90 | −2,436 |
| R1 (blanket) alone | 120 (60.6%) | — | 95 | −2,136 |
| `filler_ok` alone | 191 (96.5%) | — | 108 | −5,571 |

Restricted to the 145 impressions served **after** the D-055 floor went live (2026-08-15), where the
old floor was already active: as served 145, user-pays **76**, worst **−4,672**; level 2 → **69
(47.6%)**, 15 distinct, user-pays **0**. Loosening the package floor to −500 was measured and
rejected: 74 survivors instead of 69, but 60 of them still show the user paying.

**The finding that shaped the design:** blanket R1 kills 58 of the 83 floor-surviving cards and
**58 of 58 of those kills are cards where the USER is the one being overpaid** — the largest a
**+6,325 one-for-one that the counterparty had already liked**. Directional R1 kills **0** of the 83.
On the post-D-055 slice the same shape holds: 55 of 69, all 55 user-favourable, 0 killed directionally.

### Sabotage tests (D-056 requirement) — all reverted

| Mutation | Result |
|---|---|
| Floor compared against the raw delta again (undo the unit fix) | 2 failed |
| Directional guard `g > r` removed (blanket R1) | 4 failed |
| `if gate_level <= 0:` → `if False:` (level 0 stops reverting) | 4 failed, incl. all 3 re-pinned D-055 tests |
| `filler_ok` call replaced with `return True` | 1 failed |
| Reverted | 49 passed |

**Files touched:** `backend/server.py`, `backend/trade_service.py` (`_DEFAULT_CFG` only, +14 lines,
no logic), `backend/tests/test_likes_you_gates.py` (new), `backend/tests/test_trade_match_flow.py`,
`backend/tests/test_bakeoff_arm_a_golden.py`, `docs/config-reference.md`,
`docs/plans/three-model-bakeoff/scope-phase2.md`, `docs/plans/likes-you-quality-gates/` (new),
`living-memory/{DECISIONS,LLD,TEST_LEDGER,CHANGELOG,NEXT,HANDOFF}.md`.

## 2026-08-19h — The "balanced trade" claim gets a fairness gate (audit bug 2, NOT SHIPPED, on `fix/balanced-claim-fairness-gate`)

**Branch:** `fix/balanced-claim-fairness-gate`, worktree off a freshly fetched `origin/main` **`50e0451`**.
**Not pushed, not merged.** Ships **unflagged** — a flag's OFF state here would re-enable a false
statement (see [D-097](DECISIONS.md)).
Scope: [docs/plans/consensus-balance-claim/scope.md](../docs/plans/consensus-balance-claim/scope.md)
(code-walk proof §7, TestFlight checklist §8).

| Gate | Result |
|---|---|
| `mobile/tests/check-*.js` (all) | **61 / 61 passed, 0 failed** (60 pre-existing + 1 new) |
| `mobile/tests/check-consensus-balance-claim.js` (new) | **36 / 36 assertions passed** |
| `mobile/scripts/testid-lint.sh` | **OK, exit 0** |
| `npx tsc --noEmit` (mobile) | **1 error, pre-existing + environmental, NOT from this diff** — `ImportRankingsSheet.tsx(11,33): TS2307 Cannot find module 'expo-document-picker'`. `mobile/node_modules` is **empty in the main checkout**, so it was symlinked from `ftf-test-clone`, whose install predates that dependency. **Proven, not assumed:** stashing this branch's `.tsx` + `package.json` edits and re-running produced byte-identical output. My diff adds **zero** type errors. |
| `pytest backend/tests -q` | **3524 passed, 1 skipped, 0 failed** — insurance only; **zero backend files touched** (`git status -- backend/` empty). No route, schema, migration, or engine line moves. |
| Maestro / simulator | n/a — retired by [D-056](DECISIONS.md). No flow authored, none run, no `screens/` capture. |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The scope §8 operator TestFlight checklist is UNRUN.** |

**Prod measurement (read-only, `SET TRANSACTION READ ONLY`, SELECT only, `deck_impressions`).**
Reproduces the audit's 805 / 7,282 exactly; the denominator moved to 7,293 because eleven more cards
were served between the audit snapshot and this run.

| Metric | Value |
|---|---|
| Consensus cards served | **7,293** |
| …carrying a non-NULL `fairness_score` | **7,293 (100%)** — this is the proof the field reaches the clients, not an inference |
| …**below the app's own 0.75 bar** while claiming "balanced" | **805 (11.04%)** |
| …below the 0.50 generation floor | **0** |
| Fairness distribution | min **0.5010**, p10 **0.7302**, p25 0.7890, p50 **0.8590**, p90 0.9750, max 1.0000 |

**Sabotage test — the check is only evidence if it goes red without the fix.** Four independent
reverts, each applied, measured, restored; final `git diff --stat` byte-identical to pre-sabotage:

| # | Sabotage | Result |
|---|---|---|
| S1 | Revert the gate — `balanced` forced `true`, i.e. always claim balanced | **RED, 14 failures**, exit 1 |
| S2 | Flip the fail-safe — unknown fairness returns the balanced claim | **RED, 7 failures**, exit 1 |
| S3a | Fix mobile, leave web stale — web ternary collapsed to the unconditional string | **RED, 5 failures**, exit 1 |
| S3b | **The subtle one** — web keeps its gate but *drifts the wording* (`— no rankings on file.`) | **RED, 2 failures**, exit 1 |
| S4 | Re-inline the literal into `TradeCard.tsx` JSX, bypassing `consensusNote` | **RED, 2 failures**, exit 1 |
| S5 | Re-add value prose below the bar (the copy the operator struck) | **RED, 12 failures**, exit 1 |
| — | Restore all | **GREEN, exit 0**, diff byte-identical to pre-sabotage |

**What the 36 assertions pin**, rather than "the string changed": the gate at the real band edges
(0.75 → balanced; 0.7499, 0.7302 = prod p10, 0.55, 0.501 = prod min → **truncated**); the fail-safe
direction for `undefined`/`null`/`NaN`/`±Infinity`; that the function yields **exactly two** distinct
strings and only the at-or-above-bar one contains the word "balanced"; that **every** state keeps the
`hasn't ranked players yet` explanation (the fix removes the claim — it does **not** hide the line);
that **no value prose is re-added** below the bar (`priced from public values` / `even split` /
`leans` must appear nowhere — this is the assertion that holds the operator's 2026-08-19 amendment in
place); that **no** state names a winner; that all **four** spellings of 0.75 agree (`NORMAL_LOW`,
`FAIRNESS_ON_THRESHOLD`, `CONSENSUS_BALANCED_MIN`, and web's `FAIRNESS_BALANCED_MIN` parsed back out
of `web/js/app.js`).

**The cross-client half is the most valuable part and is built to survive rewording.** §3 does not
look for remembered strings: it **extracts** web's `prefix` literal and both tooltip templates from
`web/js/app.js`, expands them, and compares the results **byte for byte against the mobile module's
own output**. That is why S3b — web still gating correctly but saying something different — goes red
at all. Those assertions are deliberately **not** wrapped in an `if (extraction succeeded)` guard: a
failed extraction means web no longer has the shape the parity depends on, which is itself the
divergence being guarded against, so it must fail rather than skip.

**Note on `mobile/package.json`:** the only edit is registering
`"test:consensus-balance-claim": "node tests/check-consensus-balance-claim.js"`. No dependency added,
removed, or bumped — `living-memory/DEPENDENCIES.md` needs no entry.

**Operator amendment, same day.** The first revision of this fix put replacement copy below the bar
(*"priced from public values, not an even split"*). The operator struck it — *"We don't need to add
the copy suggested.. We already have already features that provide the value summary/snap assessment
on trade valuation"* — and is right: `TradeValueBar` already renders `favors`/`gap` on these cards.
The sub-threshold line now **truncates** to `This league-mate hasn't ranked players yet.` and stops.
The gate, the fail-safe, the constant and the cross-client parity are unchanged; the replacement prose
is gone from both clients and from the module, and S5 exists to keep it gone. Directional wording
("leans your way"/"leans theirs") is settled as duplication and should not be re-opened.

**Not tested, and deliberately so:** `tradePresentation.counterpartyStatement()` asserts partner
interest unconditionally (same defect class) but is dark behind `trades.presentation_v2: false` and
belongs to a surface under separate review. Recorded in D-097 and scope §9; **not** touched.

## 2026-08-19h — Landability challenger, bake-off arm D (D-095, NOT SHIPPED, on `feat/bakeoff-arm-a-challenger`)

**Branch:** `feat/bakeoff-arm-a-challenger`, branched from `origin/main` `50e0451`. **Not pushed, not merged.**
Spec: [docs/plans/landability-challenger/PRD.md](../docs/plans/landability-challenger/PRD.md) §5 Track A (A1–A4).
No feature flag: `trade.bakeoff` already gates the fan-out and `bakeoff_serve_interleaved` stays **0**, so the arm is dark.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3554 passed, 1 skipped, 0 failed** |
| Baseline re-measured on the same branch point before any edit | **3524 passed, 1 skipped** — reproduced exactly |
| PRD A4 done-when set | `test_bakeoff_challenger.py test_bakeoff_arm_a_golden.py test_bakeoff_composition.py test_bakeoff_runner.py test_user_gain_gate.py` — **120 passed** (the sabotage matrix ran a wider set including `test_bakeoff_serving.py`: 148) |
| `npx tsc --noEmit` / `testid-lint.sh` / `check-*.js` | **n/a — ZERO mobile files touched.** Not run, and not claimed. |
| Maestro / simulator / `screens/` captures | n/a — retired by [D-056](DECISIONS.md). |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE, and none is owed** — the arm generates and logs but is never served (PRD G7). The dark contract is asserted in tests instead: `test_the_challenger_generates_and_logs_but_is_never_served`. |

**Net +30 tests** — 25 new in `backend/tests/test_bakeoff_challenger.py`, 5 new in
`test_bakeoff_composition.py` / `test_bakeoff_serving.py`.

**The load-bearing invariant — arm B is byte-identical — is PROVED, not asserted.**
`test_bakeoff_challenger.py` carries two goldens captured by checking out `origin/main`
`50e0451` into a second worktree, copying the test file in, and running its capture mode
there: code that had never heard of the three new knobs. Today's live-defaults run must
reproduce both byte for byte. Surfaces: a full `generate_trades` deck (covers dedup, deck
caps, v2 orchestration) and `_generate_consensus_for_pair` called directly and uncapped —
the latter because deck-assembly caps hide most of the consensus path, so measured through
a deck alone the two consensus knobs would read as inert while being perfectly alive.
Backed by `test_every_new_knob_is_inert_at_its_default`, which sets each knob *explicitly*
to the value `_DEFAULT_CFG` already carries — that catches a knob inert only because some
other guard skips its code path, which a golden cannot distinguish.

**Arm A is byte-identical too**, per PRD N1: `MODEL_A_PROFILE`, `model_a()`,
`MODEL_A_REFERENCE_SHA` and the golden's captured deck are unchanged. The only edit to
`test_bakeoff_arm_a_golden.py` is five names added to `_PINNED_KNOBS` plus one sentence of
remedy text; its 10 tests pass unmodified.

**Code-walk proof** (file:line on this branch):

| Lever | Site | Live identity |
|---|---|---|
| `user_elo_shrink` | `trade_service.py:1339` — `if confidence is None or _c("user_elo_shrink") <= 0: return dict(user_elo)` | 1.0 ⇒ the early return never fires; the blend below is untouched |
| `consensus_both_ways` | `trade_service.py:5086` — `if not _both_ways and rv - gv < _c("user_gain_epsilon")` | 0.0 ⇒ `_both_ways` False ⇒ the original predicate, unchanged |
| 1-for-2 loop | `trade_service.py:5168` — `if _both_ways and len(cards) < max_cards` | 0.0 ⇒ loop never entered |
| `consensus_fairness_floor` | `trade_service.py:4998` (`_thr = max(requested, floor)`), read at `:5117` | 0.0 ⇒ `_thr is fairness_threshold` |
| profile entry point | `bakeoff_profiles.py` `model_challenger()` — `_cfg_override(MODEL_CHALLENGER_PROFILE)`, **no** `r4_bypass` | inert until entered |
| fan-out | `bakeoff_runner.py` `run_bakeoff` `elif arm == ARM_CHALLENGER:` — snapshot taken INSIDE the overlay | arm B's branch untouched |
| roster | `bakeoff_runner.arm_roster()` — `ALL_ARMS` filtered by four include knobs | `bakeoff_include_challenger` = 0 restores the pre-D-095 roster |

**Import-time binding checked, not assumed.** `trade_optimizer.py:51` and
`trade_gen_v2.py:112` import `_c` and `_shrink_user_elo` **by value**. All three knobs
are read *inside* existing function bodies rather than by wrapping or rebinding them, so
every bound site sees the change — the class of no-op that cost an audit agent a
perfect-zero measurement on a gate firing 1.17M times cannot occur here.

**Sabotage-tested: 13 deliberate breakages, 13 caught.** Each mutation applied, the A4
pytest set run, the mutation reverted:

| # | Sabotage | Caught by |
|---|---|---|
| 1 | `user_elo_shrink` ignored (shrink always off) | arm-B goldens, both shrink tests, **arm-A golden**, `test_user_gain_gate` Maye-for-Dart repro (v2 + v3) |
| 2 | sign test dropped for every arm | both arm-B goldens, `test_live_never_emits_a_card_the_user_pays_for` |
| 3 | both-ways knob never read | `test_both_ways_emits_the_user_pays_direction`, `test_one_for_two_exists_only_under_both_ways` |
| 4 | floor knob never read | 3 floor tests |
| 5 | floor OVERRIDES instead of tightening | `test_the_floor_only_ever_tightens` |
| 6 | 1-for-2 enumeration removed | `test_one_for_two_exists_only_under_both_ways` |
| 7 | overlay entered for arm B as well | 7 tests incl. both config-snapshot tests |
| 8 | `model_challenger` gains arm A's R4 bypass | `test_model_challenger_does_not_bypass_r4` |
| 9 | a challenger knob leaks into `MODEL_A_PROFILE` | **arm-A golden**, `test_the_two_profiles_do_not_collide`, `test_model_a_still_sees_the_live_identity_for_the_new_knobs` |
| 10 | tier ladder left uncompressed | both ladder tests |
| 11 | challenger dropped from the default roster | 8 tests across composition/serving/challenger |
| 12 | challenger stops being an engine arm (loses its consensus group) | 3 tests incl. the dark-mode group assertion |
| 13 | a new knob vanishes from `_PINNED_KNOBS` | the arm-A inventory guard **and** its cross-check |

**Known gap:** Track C's `measurement.md` (the offline four-cell count) is not written by
this work — C1 was run elsewhere and its numbers (0.75 both-ways = 200.5% of the one-way
baseline, 61.2% user-pays, damage capped at 25.0%) are quoted in the profile and
config-reference on that authority, not re-derived here.
## 2026-08-19j — Web Phase 2: calculator + market pulse (NOT SHIPPED, on `fix/web-phase0`)

**Branch:** `fix/web-phase0`. Not pushed, not merged. No flags, no schema, **no backend change**.

| Gate | Result |
|---|---|
| `python3 qa/web/check_web_structure.py` | **173/173 pass** (calculator.html registered in PAGES) |
| `pytest backend/tests` | not re-run — `backend/` untouched since `26d7841` (3524 passed / 1 skipped there) |
| Mobile gates | n/a — zero mobile files touched |

**Browser-verified** against a local server on this branch, with a real demo session:
search → add asset → live evaluate; a 1-for-2 priced `fair / Favors them`, gap `1,718 ≈ a
Late 1st Round Pick`, and the one-tap evener moved it to `even` — matching the same
engine's prod output for the same package. Adjustments disclosure renders the server's
`why` copy. At 375px: no horizontal overflow, sides stack, **zero tap targets under 44px**.
Market pulse verified in both states — hidden when `/api/market/movers` is empty (the real
local state), and rendering risers/fallers when fed prod-shaped rows.

**Two defects found and fixed during this pass, both mine-or-adjacent:**
1. A one-sided trade rendered **"even / Even both ways"** — the server returns
   `verdict: null` and the first draft defaulted it to `even`, stating something false.
   Now prompts for the missing side, and a null verdict never coerces.
2. `.league-list` set only `overflow-y`, which makes `overflow-x` compute to `auto` (not
   `visible`) — it reserved a scrollbar gutter and painted a light track across the league
   card. Pre-existing; fixed since it sits in a screen this work touched.

**Local-data caveats worth recording:** `/api/trade/values` returns 0 on a cold worktree
until the process restarts with the Sleeper cache warm, and `/api/market/movers` is empty
until 30 days of value snapshots exist. Neither is a code defect; both cost time to
diagnose.

---
## 2026-08-19i — Web Phase 1 foundation (NOT SHIPPED, on `fix/web-phase0`)

**Branch:** `fix/web-phase0`. **Not pushed, not merged.** No flags, no schema, no backend change.

| Gate | Result |
|---|---|
| `python3 qa/web/check_web_structure.py` | **161/161 pass** (baseline at Phase 1 start: 101/161) |
| `python -m pytest backend/tests -q` | **3524 passed, 1 skipped** at commit `26d7841`; `backend/` untouched since |
| `npx tsc --noEmit` / `testid-lint.sh` | n/a — zero mobile files touched. Not run, not claimed. |
| Maestro / simulator | n/a — retired by [D-056](DECISIONS.md) |

**New permanent gate:** `qa/web/check_web_structure.py`, wired as CI job `web-structure`.
This is the first automated coverage `web/` has ever had. Pure stdlib — Playwright was
installed and evaluated, then **not** used: the structural layer catches the entire class
of defect this phase addressed, needs no browser, and cannot flake. A browser-level smoke
(console errors, layout at 375px, axe) remains unbuilt and is the honest gap.

Browser-verified against a local server on this branch: all 11 pages 200 with exactly one
`<h1>`, a meta description, and the shared token link; `--line-strong` resolves to
`#59647A` everywhere; `index.html` has `<main>` wrapping all 7 views with the 3 overlays
correctly outside it; signed-out `positional-tiers.html` renders **real** players (Josh
Allen, Lamar Jackson, Joe Burrow) auto-tiered, where it previously rendered 45 stale
2024-era hardcoded ones.

**Caveat worth recording:** the signed-out player path could not be verified until the
worktree's throwaway DB was seeded — `/api/players` returns `[]` on an unsynced local DB,
and its `Cache-Control: max-age=300` made an early empty response persist and look like a
code bug. It was not one.

---
## 2026-08-19h — Web Phase 0 breakage fixes (NOT SHIPPED, on `fix/web-phase0`)

**Branch:** `fix/web-phase0` from `origin/main` `50e0451`. **Not pushed, not merged.** No flags added or flipped.
Scope + full evidence matrix: [`docs/plans/web-parity/scope.md`](../docs/plans/web-parity/scope.md) §3.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3524 passed, 1 skipped, 0 failed** |
| `npx tsc --noEmit` / `testid-lint.sh` | **n/a — zero mobile files touched.** Not run, not claimed. |
| Maestro / simulator / `screens/` | n/a — retired by [D-056](DECISIONS.md) |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, standing posture under D-056 |
| **Web automated tests** | **NONE EXIST.** CI never touches `web/` — no Playwright, no axe, no Lighthouse, no root `package.json`. Building one is plan item P1-2. |
| **Runtime evidence** | **Real browser against a local server running this branch.** Not a code-walk. |

Verified in-browser: `app_opened` now queues (`seq:1`) and `POST /api/events` → 200 (previously
**zero** ingest requests, `ftf.deviceId` null); CTA at 375px sits `x 155→355` inside the viewport
(was `20→400`, clipped); the demo trap shows honest copy + a working "Start over" and fires
**zero** `/api/sleeper/leagues` requests; `/nope` → HTML 404 while `/api/*` and `/og/*` stay JSON;
`_IS_PROD_ENV=True` 404s the 3 design-lab pages and leaves real pages untouched; the contact form
landed a note as `web-contact-data-request` with a `[DATA REQUEST]` prefix, anonymous. Plus an
8-case table test of the rewritten `extractUsername()` (8/8) and `node --check` on all touched JS.

**Not verified:** anything on the deployed host — this never left the branch.

---
## 2026-08-19g — Phantom draft-pick years: the league pick horizon (#355, NOT SHIPPED, on `fix/pick-horizon`)

**Branch:** `fix/pick-horizon`, branched from `origin/main` `7462c23`. **Not pushed, not merged.**
Flag `picks.league_horizon` default **ON** (its OFF state is the defect, so shipping it off ships nothing).
Scope + evidence + code-walk + checklist: [docs/feedback/items/355-phantom-pick-years/](../docs/feedback/items/355-phantom-pick-years/).

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3496 passed, 1 skipped, 0 failed** |
| Baseline on the same branch point, before any edit | **3480 passed, 1 skipped** — reproduced exactly |
| `npx tsc --noEmit` / `testid-lint.sh` / `check-*.js` | **n/a — ZERO mobile files touched.** Not run, and not claimed. |
| Maestro / simulator / `screens/` captures | n/a — retired by [D-056](DECISIONS.md). |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The 10-step operator TestFlight checklist is UNRUN.** |

**Net +16 tests, all new** (`backend/tests/test_pick_horizon.py`). Two layers: the pure helper
`draft_status.pick_horizon` (pre-draft window, post-draft roll-forward, the always-3-classes
invariant, existence-proof widening, the widening cap, garbage-input tolerance, unknown-horizon
degradation) and the grid builder `sync_draft_picks` (the operator's exact case, the post-draft case
where 2029 is *kept* because it is real, the kill switch restoring the old window, a reported far
pick pulling its whole class in, a "never widens past the legacy ceiling" safety bound, and the
#220 empty-roster guard surviving the change).

**5 pre-existing tests updated, each a deliberate encoding of the OLD 4-class window** — not
loosened to make the change pass:
- `test_owned_picks.py` ×4 — grid sizes written as `2 rosters × 4 seasons × 4 rounds = 32`. Now
  derived from `PICK_HORIZON_CLASSES` (`_GRID = 2 * PICK_HORIZON_CLASSES * 4` = 24) so the rule has
  exactly one home, plus an added explicit assertion that the classes are 2026/2027/2028.
- `test_seed_ui_test_db.py` ×1 (3 fixtures) — the flag-map mirrors. `release.json` must equal
  `config/features.json` key-for-key, and `onboarding-v2.json` / `profiles-on.json` are asserted to
  be "release plus exactly one differing key", so all three needed the new flag.

**Prod measurement (read-only, `SET TRANSACTION READ ONLY`, SELECT only)** — the numbers in
[evidence.md](../docs/feedback/items/355-phantom-pick-years/evidence.md): **339 of 2,651 served
cards (12.8 %; 23.2 % of pick-bearing cards)** carried an out-of-horizon pick, 360 mentions, all
2029, all in the operator's league. **12.9 % of the 845 recorded like/pass outcomes** landed on one,
skewed 6.7 % of likes vs 15.8 % of passes vs 21.4 % of not-interested. **The 2026-08-16 → 08-19
preference data is contaminated** and must not be cited as a clean propensity or bake-off baseline.

**What this does NOT prove.** The tests stub the Sleeper reads, so nothing here demonstrates the
horizon against live platform data — that is exactly what the TestFlight checklist is for, and it
is unrun. The rule itself was validated out-of-band by direct probes of the public Sleeper API
across every league in prod, recorded in `evidence.md`, including a positive 2029 reading on a
post-draft league so the rule is pinned at both ends rather than inferred from an absence.

## 2026-08-19g — Current-year pick slot labels (D-090); "2026 1.08", not "2026 1st"

**Branch:** `feat/pick-slot-labels`, worktree off a freshly fetched `origin/main` **`7462c23`**.
**Not pushed, not merged.** Flag `picks.slot_labels` ships **ON**.
Scope: [docs/plans/pick-slot-labels/scope.md](../docs/plans/pick-slot-labels/scope.md) (code-walk proof is §7,
TestFlight checklist §8).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` (branch) | **3508 passed, 1 skipped, 0 failed** |
| `pytest backend/tests -q` (clean `origin/main` `7462c23`, pristine worktree) | **3480 passed, 1 skipped** — the baseline, re-measured rather than assumed |
| Delta | **+28**, all in the new `backend/tests/test_pick_slot_labels.py`. No pre-existing test changed behaviour. |
| `mobile/scripts/testid-lint.sh` | **OK, exit 0** |
| `npx tsc --noEmit` (mobile) | **NOT RUN — typescript is not installed in `mobile/node_modules` on this machine** (`node_modules/.bin/tsc` absent in the main checkout too, so this is an environment gap and not a worktree artefact). The diff touches **zero** `.ts`/`.tsx` files, so it cannot move the typecheck; CI runs it on the pushed sha. Stated rather than claimed. |
| `mobile/tests/check-*.js` | not run and none added — the mobile diff is empty (see below) |
| Maestro / simulator | n/a — retired by [D-056](DECISIONS.md). |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The scope §8 operator TestFlight checklist is UNRUN.** |

**What the 28 new tests actually pin**, rather than "the label has a dot in it". Each of the two named
sabotages has a trap:

- **S1 — a slot invented where none exists.** Sleeper's pre-draft payload returns
  `slot_to_roster_id = {"1":1 … "12":12}`, an identity map that reads as a real order and is not one
  (the D5 rule in `draft_board_service`). `test_identity_slot_to_roster_is_never_read` hands the
  resolver that perfect identity map next to a NULL `draft_order` and demands `None`. The fixture's
  real order is deliberately **not** the identity — roster 1 drafts 8th — so anything falling back to
  the roster id labels `1.01` and fails every `1.08` assertion in the file.
- **S2 — a slot on a season that has no order.** `test_future_season_never_resolves_a_slot` pins `None`
  for 2027/2028/2029 *and* 2025; `test_future_year_keeps_its_round_ordinal` pins the literal strings
  `"2027 1st"` / `"2029 3rd"`.
- **The bright line.** `test_no_price_moves_with_or_without_an_order` asserts `pool_value` is not
  mutated and that every slot of a round still prices identically — the change must not creep into
  pricing (that question is [Q-023](OPEN_QUESTIONS.md)).
- **The kill switch.** `test_route_is_byte_identical_with_the_flag_off` pins a literal label map with
  the flag off, and `test_flag_off_never_reads_the_order` patches `load_draft_slot_order` to raise —
  a disabled feature must short-circuit **before** the read, not after.
- Plus: snake even-round reversal matching `PickAssignmentScreen.draftPosition` exactly, refusal on
  `reversal_round`, per-league caching (one lookup, not one per pick), degradation to generic labels on
  a raising DB, and that a slot label introduces no `' + '` (which `TradesScreen.tsx:3804` splits on).

**One pre-existing test was deliberately edited**, and it is the containment guard for this area:
`test_pick_assignment.py::test_w3_02_ast_only_sanctioned_call_sites_name_source`. It AST-enumerates every
`load_draft_picks` call site and fails on any unsanctioned `source=` opt-in — which is exactly how an
eighth site is supposed to get **decided** rather than silently added (its own docstring says so). The new
`_assigned_slot_order` is registered in `_SANCTIONED_SOURCE_CALLERS` (the assignment surface), **not** in
the seven engine sites, with the reasoning inline: it prices nothing, and numbering must not follow a
pricing flag or a trade card and the assignment screen would disagree about what "1.05" means.

**Verified against real data, not only fixtures** (2026-08-19):
- Live Sleeper read for league `1312140920132497408`: the resolver's `draft_order` × rosters composition
  reproduces Sleeper's own `slot_to_roster_id` **exactly, 12/12** — and the D5-compliant path is the one
  used, so agreement is corroboration rather than construction. The operator's own 2026 1st is the **1.08**.
- Prod Postgres, **read-only** (`SET TRANSACTION READ ONLY`, SELECT only): current-year picks appear in
  **469 of 2,651 served deck cards (17.7 %)**, 451 of them in that one league; only **3 of 12** leagues
  hold 2026 picks at all, and all three are `draft_status = not_drafted` (#228 deletes the rows at draft
  completion).

**Measured but NOT built** — what pricing by slot would do, so [Q-023](OPEN_QUESTIONS.md) can be decided on
evidence: against DynastyProcess's published 2026 curve a 1.01 is **+130 %** and a 1.12 **−61 %** versus our
flat 2117 (**5.9×** inside one round); on the operator's league that moves **48 of 48** current-year pick
values and **38 of 48** tier badges. Not shipped, not prototyped — computed with the shipped functions
against the checked-in `dp_values_picks_2026-08-06.csv`.

**Mobile evidence waived, with the reason:** the mobile diff is **empty** — `git status` shows zero files
under `mobile/`, `web/` or `extension/`. Every client renders the server's `label`/`name` verbatim
(`InLeagueCalculator.tsx:219`, `LeagueSummaryScreen.tsx:2148`, `MatchesScreen.tsx:1408/1414/1440/1446`,
deck cards via `give_players[].name`), so there is no client-side owned-pick formatter to pin structurally.

---
## 2026-08-19e — Settings IA: hub + second-level pages, sheet → page (SHIPPED to main + TestFlight)

**Branch:** `feat/settings-ia-hub`, rebased from `ecdbcb3` onto `origin/main` `28c12a0` and merged.
Flag `account.settings_hub` stays **OFF** (default false).
Plan + scope: [docs/plans/settings-ia-hub/](../docs/plans/settings-ia-hub/). Code-walk proof:
[code-walk-proof.md](../docs/plans/settings-ia-hub/code-walk-proof.md).

| Gate | Result |
|---|---|
| `npx tsc --noEmit` (mobile) | **exit 0** |
| `mobile/scripts/testid-lint.sh` | **OK, exit 0** |
| `mobile/tests/check-*.js` (whole suite) | **60 passed, 0 failed** post-rebase (59 pre-rebase; main added one) — includes the 3 new settings checks |
| `pytest backend/tests -q` | **3480 passed, 1 skipped, 0 failed** (post-rebase, final). Earlier in the session the same branch ran 3399/5-failed on base `ecdbcb3`; all 5 were pre-existing and `main` repaired them in `70d1f3b`, so the pre-ship gate is clear. |
| Maestro / simulator | n/a — retired by D-056. Replaced by the 3 structural checks + the code-walk proof. |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The plan §9 operator TestFlight checklist is UNRUN.** |

**New structural checks: 3** (`npm run test:settings-ia | test:settings-nav | test:settings-testids`).
- `check-settings-ia.js` — encodes plan §4's migration map: 12 section modules → owning page, 34 rows
  → owning module. Catches an orphaned module, a duplicated one, a row deleted from *inside* a
  surviving module, and the four IA moves.
- `check-settings-nav.js` — no settings route carries `presentation: 'modal'`; all 8 have a
  `HeaderBack`; all 8 page modules mount `FeedbackFAB aboveTabBar={false}`; 8 deep-link paths resolve.
- `check-settings-testids.js` — 11 shipped ids + 2 templated prefixes still resolve **inside
  `src/screens/settings/`** (not merely somewhere under `src` — the legacy screen would otherwise
  satisfy the search by itself); 9 new ids present; `settings.close-btn` gone from `src` **and** from
  `.maestro`.

**The checks were verified by mutation, not by reading.** Independently re-run at orchestration:
restoring `presentation: 'modal'` on the `Settings` route, swapping the Sign out / Delete account
render order, and renaming `settings.espn-disconnect` each FAIL with an accurate message. The modal
parse walks the TS AST per `<Stack.Screen>` and self-tests that it still *detects* the modal on
`FeedbackInbox` / `SleeperConnect`, so a broken walk fails loudly instead of passing forever.

**Destructive-path copy verified byte-for-byte** against `origin/main` by brace-matched extraction of
six functions (three platform disconnects, `confirmDeleteAccount`, `performDeleteAccount`,
`handleExportData`). Zero drift. Delete account keeps both `Alert` stages and both destructive
markers. An earlier fixed-line-window comparison produced false drift reports by bleeding into
adjacent functions and was discarded — the brace-matched result is the one recorded.

**Pre-existing red on `origin/main` (blocks the pre-ship gate for EVERY branch, not just this one):**
`test_seed_ui_test_db::test_release_flags_mirror_features_json` (`trade.bakeoff` set true in
`config/features.json` by `ecdbcb3` but left false in `backend/tests/fixtures/flags/release.json`),
three in `test_suggestion_telemetry.py`, and
`test_trade_decision_idempotency::test_re_posted_swipe_writes_exactly_one_set_of_swipe_decisions`
(expects Elo 1502.0 ± 0.001502, obtains 1500.0 — a re-posted swipe not applying its rating update).
Confirmed pre-existing by stashing this branch's flag change and re-running. This branch DID add the
one missing mirror entry its own flag required.

**The rebase onto `28c12a0` silently dropped phase 0, and the gate is what caught it.** `git rebase`
reported the commit as empty mid-run; it carried all 15 mobile source files plus the flag
registration. `tsc` then failed with 22 `TS2307` module-not-found errors, and the flag was left
HALF-registered — in `onboarding-v2.json`, `profiles-on.json` and `config-reference.md`, absent from
`features.json`, `FLAG_KEYS` and `release.json`. That combination would have shipped a dead flag and a
red mirror test. Recovered in `9a04ebc`: the mobile tree restored byte-identical from `4ea6895`, the
three flag files re-applied surgically (main changed them in the same window, so a wholesale restore
would have reverted 1.15.0's flag work). Parity re-checked by file set — 54 files before, 54 after,
no drops, no extras.

**A regression this branch caused, caught by running the full suite rather than trusting an earlier
run.** Registering `account.settings_hub` initially mirrored it into `backend/tests/fixtures/flags/release.json`
only. Two other fixtures — `onboarding-v2.json` and `profiles-on.json` — are asserted to be
**key-set-equal** to release (`assert set(release) == set(profiles_on)`, and the onboarding equivalent),
so the single new key broke both: 5 failures became 7. Fixed by mirroring the key into those two
fixtures as well. `all-on.json` (42 keys), `release-300.json` and `release-espn-send-off.json` (162 keys,
already missing 10 other keys) are deliberately NOT key-set-equal and no test requires them to be — they
were left alone rather than "fixed" into scope creep.

The lesson worth keeping: a new flag key is not registered until every fixture that asserts key-set
equality with `release.json` carries it. `git grep -l "account.settings_v2" backend/tests/fixtures/`
finds them.

**Correction to this branch's own record:** the phase-0 commit message claimed the full-screen
`prefsQuery.isLoading` gate "is gone". That is true only on the hub path. The gate is still live at
`SettingsScreen.tsx:746` on the flag-off flat list, which phase 0 never touched; it dies with the
legacy branch in phase 4. Corrected in the phase-1 commit message and in the code-walk proof.

---

## 2026-08-19d — Placement tier clamp (D-085); a placement now bounds PRICING, not just voting

**Branch:** `feat/placement-tier-clamp`, from `origin/main` `a130dfc`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/placement-tier-clamp/scope.md](../docs/plans/placement-tier-clamp/scope.md). Code-walk: [code-walk.md](../docs/plans/placement-tier-clamp/code-walk.md). Decision: [D-085](DECISIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3441 passed, 1 skipped (baseline at `a130dfc`) | **3463 passed, 1 skipped, 0 failed** (+22 new, all in `test_placement_tier_clamp.py`) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 34 passed | 34 passed; new knob pinned to 0 in `MODEL_A_PROFILE`, **no golden re-capture needed** (kill value is an identity on the valuation) |
| Kill-switch identity | — | `placement_tier_clamp = 0` reproduces the pre-D-085 blend for a whole populated board (`test_knob_at_zero_is_byte_identical`) |

**Evidence under D-056** (no Maestro, no simulator, no captures): 22 new unit tests plus a
written code-walk citing file:line for every hop of the path, including a
**gate-isolation proof by what the gate reads** — the range-overlap fairness gate
prices `gvals`/`rvals` from `seed_value` (consensus), so `user_value` never reaches
it and the clamp is structurally invisible to every gate. `_value_uncertainty`'s
placement-blindness is asserted via `inspect.signature`, so a future edit that adds
the parameter fails CI rather than sliding through.

**Band constants are read live from `tier_config.json`, not hardcoded.** D-084 moved
`second`.min 1400 → 1370 and `third`.max 1395 → 1365 while this work was in flight;
an earlier draft had hardcoded the old numbers and would have asserted the wrong
thing silently. `test_band_constants_match_the_shipped_config` guards the guard.

**What was measured, on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only).**
The operator's real board was rebuilt through the actual `RankingService` — 625-player
pool seeded from the latest `player_value_history` snapshot, all 624 stored
`tier_overrides` pins re-applied with stamps, all 1,679 in-pool `swipe_decisions`
replayed via `replay_from_db` — then `comparison_counts()` and `_shrink_user_elo` were
run with and without the clamp under the live configuration (`pin_tier_bounded=1.0`,
`pin_exclude_comparisons=1.0`, `shrink_pseudocount=4.0`).

- **Davante Adams, the driving case: priced 1490.8 (`second`) → 1365.0 (`third`)**, back
  into the tier he was placed in. Band [1280, 1365], consensus 1526.
- **The mechanism is not "he was barely compared".** Adams has **36 distinct comparison
  opponents** and is among the most-voted players on that board, but his live
  `comparison_counts` is **1**, because `pin_exclude_comparisons` (F1) correctly discards
  votes a tier-bounded player's band edge swallowed. `w = 0.2` ⇒ the engine priced him
  **80 % consensus** despite 36 votes and an explicit placement. An estimate from raw
  distinct-opponent counts gives `n = 36`, `w = 0.9`, and wrongly concludes the clamp is
  a no-op here. **Only the replay reveals this** — recorded so the shortcut is not retried.
- **Whole board: 162 of 615 banded placements (26 %) move**, median 32 Elo, max 343
  (Travis Hunter). Largest movers are `n = 0` players whose blend was pure consensus.
- **Placements are not rare:** 5 of 18 users have them; the three active boards carry
  547 / 644 / 737 each.

**Negative finding — the `basis: consensus` framing does not hold.** The work was
motivated by "every one of the 40 most recently served cards came back `basis:
consensus`". Prod on 2026-08-19: last 40 impressions = **30 consensus / 10 divergence
(25 %)**; last 400 = 7.8 %; all time = 12 % (1,263 of 10,550). Divergence *is* being
found. Further, `basis` is decided at `trade_service.py:4105` by
`member.has_rankings and member.elo_ratings` — a property of the **opponent's** board,
evaluated before any user value is read — or by the zero-divergence fallback at `:4175`.
The clamp can only influence the second, and the impressions table does not record which
branch fired. **This clamp must not be reported as the cause of the consensus share.**
Recommended follow-up: instrument the fallback to distinguish "opponent unboarded" from
"divergence path came back empty".

**Not covered:** `bakeoff_runner.gen_v2_cards` never passes `placements`, so the clamp is
inert on every bake-off arm and the bake-off cannot currently measure this feature.
Left that way deliberately — two sibling agents were editing `bakeoff_runner.py`
concurrently. `MODEL_A_PROFILE` pins the knob to 0 regardless.

## 2026-08-19f — Bake-off lane reallocation (D-086); the outlook lane that filled zero

**Branch:** `fix/bakeoff-outlook-lane`, from `origin/main` `a130dfc`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/three-model-bakeoff/scope-outlook-lane.md](../docs/plans/three-model-bakeoff/scope-outlook-lane.md). Decision: [D-086](DECISIONS.md). Follow-up: [Q-020](OPEN_QUESTIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3441 passed, 1 skipped (baseline at `a130dfc`) | **3448 passed, 1 skipped, 0 failed** (+7 new) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 10 passed | 10 passed; new knob added to `_PINNED_KNOBS` and excluded from `MODEL_A_PROFILE` (composition, not generation — row added to `scope-phase2.md`), **no golden re-capture needed** |
| `test_bakeoff_composition.py` | 35 passed | **38 passed** (7 added, 3 rewritten to pin the pre-D-086 path under `reallocate=False`) |

**What was measured, on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only).** All 18
`bakeoff_runs` rows of 2026-08-19 — 54 group-runs, 527 pooled cards, 3 leagues.

| Group | cards/run | `value` | `window` | `(none)` | window share | outlook slots filled |
|---|---:|---:|---:|---:|---:|---:|
| `current_divergence` | 1.3 | 23 | **0** | 0 | **0.0 %** | 0 / 90 |
| `current_consensus` | 22.5 | 291 | 114 | 0 | 28.1 % | 63 / 90 |
| `gen_v2` | 5.5 | 83 | 16 | 0 | 16.2 % | 16 / 90 |
| **all** | 29.3 | 397 | **130** | **0** | **24.7 %** | 79 / 270 |

The single number that decides the diagnosis: **`(none)` is 0 in all 54 group-runs**, so every
pooled card carried a lane and the label plumbing is healthy — `window` is 24.7 % of live supply,
not ~0 %. The zero-fill is a quota/supply result, not a missing field. Deck arithmetic per run:

| | cards/run |
|---|---:|
| target (`bakeoff_deck_limit`) | 30.0 |
| supply generated | 29.3 |
| within-group capacity `Σ min(pool, 10)` | 16.0 |
| **served (before)** | **13.8** |
| **served (after D-086)** | **16.0** |

Counterfactual replay of the same 54 pools through candidate quotas — the arithmetic that
rejected a re-tuned split in favour of reallocation:

| `bakeoff_group_value_slots` | fixed quota | with reallocation |
|---|---:|---:|
| 5 (today) | 13.8 /run | **16.0** /run |
| 6 | 14.9 | 16.0 |
| 7 | 15.6 | 16.0 |
| 8 | 15.7 | 16.0 |
| 10 | 15.0 | 16.0 |

**Evidence per D-056 (no simulator, no Maestro):** 7 new pytest cases in
`backend/tests/test_bakeoff_composition.py` — the core claim, the no-op case, both reallocation
directions, the supply ceiling, composition with `bakeoff_fill_policy`, end-to-end knob wiring,
and a regression pinned to the **real measured 10:33 pools** (7/0, 10/0, 13/3 → 18 cards before,
27 after). Plus a file:line-cited code-walk proof in §6 of the scope block, covering the two
properties no unit test can state directly: that `res.short` is written before any reallocation
statement and never rewritten, and that reallocation slices only from the receiving lane's own
bucket, so every `lane_slot` stamp remains a true statement about its card.

**Not verified at runtime, and it does not need to be:** the bake-off is dark
(`bakeoff_serve_interleaved` 0.0, **not changed by this work**), so no served deck moves for any
user. The next organic deck writes the proof itself — `filled.value + filled.outlook` should equal
`min(pool total, 10)` per group in `bakeoff_runs.groups_json`, with `short` unchanged in character.

## 2026-08-19d — Arm C (`gen_v2`) per-stage kill counts; the forfeit was a supply fact, not a bug

**Branch:** `fix/armc-gen-v2-forfeits`, from `origin/main` `a130dfc`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/three-model-bakeoff/scope-arm-c-diagnostics.md](../docs/plans/three-model-bakeoff/scope-arm-c-diagnostics.md). Decision: [D-087](DECISIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3441 passed, 1 skipped (baseline at `a130dfc`) | **3449 passed, 1 skipped, 0 failed** (+8 new) |
| `tsc --noEmit` / testid-lint | unaffected | unaffected — no TS, mobile or web file touched |

**New tests (8).** `backend/tests/test_trade_gen_v2.py` (+5): each starvation mode pinned to a distinct stage (`no_boarded_opponents`, `no_board_overlap`, `no_divergence`); the GATED case pinned to `starvation_reason is None` with the ε-gate owning the kills; the `kill_counts()` key set and order pinned as a contract. `backend/tests/test_bakeoff_serving.py` (+3): forfeits summed over an arm's groups (arm `current` no longer reports 0 when its groups forfeited), arm-C diagnostics reaching `arms_json` with the starving stage named, and drain-on-read so one run's counters cannot leak into the next.

**What was measured (read-only prod, `SET TRANSACTION READ ONLY`, SELECT only).** All 18 `bakeoff_runs` rows and 8,112 `deck_impressions`:

- Arm C's `cards=0` is **per-league, not per-time**: it happens only in `62846` and `11896`; league `1312140920132497408` returned 6–16 cards in all 11 of its runs. The reported "9 forfeits → 2 improvement overnight" was two different leagues, not one improving.
- `member_rankings`: `62846` has **zero** rows; `11896` has rows for one user — the requester himself; `1312…` has 4,416 across 6 users. Arm C is divergence-only by design, so a league with no boarded *opponent* gives it nothing.
- **Divergence supply is real but concentrated:** 96.8 % of all-time divergence impressions (1,196/1,235) come from the one league with ≥3 boards. `62846`, `11896`, and both 1-board leagues have **zero divergence impressions ever**. The 15.2 % all-time rate is not evidence arm C had input.
- **The control:** arm `current`'s own `current_divergence` group pool is **0 in all six runs** in those leagues — identical to arm C. In the boarded league arm C's pool is 6–16 (median 7) against arm `current`'s 0–7 (median 1), and arm `current` produced no divergence at all in 8 of 11 runs. **Arm C out-produces arm `current` on the divergence axis in 11 of 11 runs where input exists.**
- **Zero `gen_v2` impressions is serving, not generation:** `served_arm` is `'current'` on every run (`bakeoff_serve_interleaved = 0.0`, dark), so `server.py:3950` can only stamp `current` or NULL. Arm C already contributed 6 of 6 composed cards to the interleaved deck it does not serve.

**Local reproduction.** All four shapes (boarded+divergent / no boarded opponent / boarded with zero divergence / boarded with no overlap) reproduced on the `_base_pair` fixture. Under the OLD counters three of the four were byte-identical all-zero reports — that indistinguishability is the defect fixed.

**Not proven here.** Arm C's card *quality* — it has still never been evaluated by a user, and cannot be until `bakeoff_serve_interleaved` is lit (operator's call, deliberately untouched). Board supply, not model quality, is the binding constraint: only one production league can exercise arm C at all.

## 2026-08-19c — Pick-badge value→Elo inverse (D-088); the round-3 "overprice" was arithmetic

**Branch:** `fix/pick-round3-value`, worktree `wt-round3`, from `origin/main` `a130dfc`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/pick-badge-scale/scope.md](../docs/plans/pick-badge-scale/scope.md). Decision: [D-088](DECISIONS.md). Memo: [docs/reviews/2026-08-19-pick-badge-scale.md](../docs/reviews/2026-08-19-pick-badge-scale.md). Gotcha: [G-052](GOTCHAS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3441 passed, 1 skipped (baseline at `a130dfc`) | **3443 passed, 1 skipped, 0 failed** (+2 new tests, 5 retargeted) |
| `tsc --noEmit` | — | **clean, exit 0** (mobile diff is a JSDoc comment only) |
| `mobile/scripts/testid-lint.sh` | — | **OK** (no testIDs added or renamed) |
| `test_tier_occupancy.py` | 47 passed | **47 passed, file not opened** — no band or seed moved, so occupancy could not move |
| `test_pick_anchor.py` · `test_pin_tier_bounded.py` · `test_pick_pricing_m6b.py` · `test_slot_values.py` | green | green, **untouched** — none of them reads the badge path |

**What the tests now prove that the old ones did not.** The pre-existing pins in
`test_league_picks_tier.py` were literal Elos (`1383.5 → 'second'`) written by reading the buggy
output back, so they *confirmed* the defect rather than catching it. The replacement is a
**property**: `test_current_year_rungs_badge_their_own_round` asserts, through the route and for
all four rounds, that a current-year pick of round R badges exactly where
`GENERIC_PICK_SEEDS[(R, "Mid")]` sits — which is what `tier_config.json`'s `_calibration` already
defines to be true. No wrong inverse satisfies it for all four rounds. A second test pins that a
pick priced below the `waivers` floor carries `null` rather than a flattering rung.

**Arithmetic verified rather than quoted.** Executed against the shipped functions:

| Claim | Verified |
|---|---|
| The compression the D-084 memo cited | Real. On `dp_values_snapshot_2026-07-10.json` (641 players, `1qb_ppr`), ranks 200→300 span Elo **1262.9 → 1208.0 = 54.9 points**, vs 2.508 Elo/rank at 100–200 and 4.417 at 50–100 |
| ...but not the cause | The badge never reads the player board. `pool_value` → Elo is the whole path |
| The two maps cross once | At **Elo 1548.0** exactly (`223.130 + 0.824487·v = v` ⟹ `v = 1270.9`) |
| Badge inflation, by rung | Mid 2nd +35.2 · Mid 3rd **+63.4** · Mid 4th **+99.3** · Late 4th +109.5 Elo |
| 1383.5 reproduces end to end | `elo_to_value(1320) = 406.570` → `seed_elo_for_value(406.570) = 1383.5` (wrong) vs `value_to_elo(406.570) = 1320.0` (right) |

**Measured on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only, no writes).**

| Question | Answer |
|---|---|
| Pick rows at risk | **1,104** across **7** leagues, all with a non-NULL `pool_value` |
| Badges that change, recomputed both ways over the *actual stored* values | **600 (54.3 %)** — 538 down, 62 up |
| Named transitions | `third`→`fourth` 188 · `third`→`waivers` 152 · `second`→`third` 136 · `second`→`first_1` 62 · `third`→`null` 62 |
| Unchanged | `first_1`→`first_1` 164 · `second`→`second` 252 · `third`→`third` 88 |
| 3rd-round picks in served cards | **27 of 2,376 = 1.1 %** (1.4 % of 1,909 pick mentions) |
| 4th-round picks in served cards | **0** |
| Picks overall | 1,329 of 2,376 cards = **55.9 %**; firsts **80.9 %** of pick mentions, 2nds 17.7 % |

**Honest read of that last block:** deep picks barely touch real decks, so this was never worth a
repricing — which is the measured argument for fixing the badge and leaving the ladder alone
(and for parking [Q-021](OPEN_QUESTIONS.md)).

**Not run:** the manual TestFlight checklist (7 steps, in the scope block §3) — it needs the
operator and a build. Step 7 is the one that matters most: build a trade containing a 2026 3rd and
confirm the **values and fairness verdict are unchanged**, since any numeric movement would mean
the fix leaked out of the display layer.

---
## 2026-08-19b — Give-side headliner cap (D-082); the flood C4 could not see

**Branch:** `fix/deck-give-headliner-cap`, from `origin/main` `8b7689a`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/deck-give-headliner-cap/scope.md](../docs/plans/deck-give-headliner-cap/scope.md). Decision: [D-082](DECISIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3416 passed, 1 skipped (baseline at `8b7689a`) | **3427 passed, 1 skipped, 0 failed** (+11 new) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 10 passed | 10 passed; new knob pinned to 0 in `MODEL_A_PROFILE`, **no golden re-capture needed** (kill value returns the list unchanged) |
| `test_engine_quality_golden` byte-identity vs `origin/main` | 5 knobs killed | 6 knobs killed, still byte-identical |

**What was measured, on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only).** The defect,
on the operator's own deck `deck_job_id` 2740a7fc — 22 cards, **20 distinct `centerpiece_id`s**,
C4 killed 0, and three players supplied **17 of the 22 give sides** (6 Adams / 6 `1466` / 5
Mayfield). Then the fix, replayed over **66 `deck_candidate_sets` pools of ≥20 candidates**
(1,925 served cards) in `base_score` order:

| Cap | Cards lost | Median deck size | Per-deck max repeat (median) | Decks under `_DECK_MIN_CARDS` (5) |
|---|---|---|---|---|
| 2 | 458 (23.8 %) | 29 → 24 | 6 → 2 | 0 |
| **3 (shipped)** | **194 (10.1 %)** | **29 → 26.5** | **6 → 3** | **0** |
| 4 | 62 (3.2 %) | 29 → 28 | 6 → 4 | 0 |

At the shipped default: 19 of 66 decks unchanged, worst single deck 36 → 24, 3 decks under 20
cards, per-deck worst repeat `{3:1,4:13,5:16,6:14,7:7,8:1,9:4,10:2,11:3,12:2,13:3}` → `{3:66}`.

**Evidence per D-056 (no simulator, no Maestro):** 11 new pytest cases in
`backend/tests/test_engine_quality.py` + a file:line code-walk proof in the scope block §3.1 +
a manual TestFlight checklist for the operator (§3.2), since "how the deck reads" is the one
claim no unit test can settle.

**Proven-to-fail, both applied → observed RED → reverted.** (a) default `3.0 → 0.0`: 3 behaviour
tests fail. (b) delete the `cap_give_headliners` call from `_dedup_and_sort`: 4 fail — the three
above plus `test_both_generation_paths_apply_the_give_cap`, which is the guard that arm C
(`bakeoff_runner.gen_v2_cards`) and the `trade_gen.v2` serving branch keep their own calls; both
bypass `_dedup_and_sort` entirely, so without them the bake-off would compare arms under
different deck-assembly rules.

**One pre-existing test-fixture interaction, resolved deliberately rather than by loosening an
assertion.** Every card in the C4 flood fixture gives `hub`, so C4b bound first and 4 C4 cases
went red. `_flood_deck` and `_ORTHOGONAL_GATES_OPEN` now pin `deck_give_headliner_cap = 0`, the
same isolation technique those fixtures already used for `deck_headliner_cap` — C4b has its own
fixture (`_c4b_*`) built from the real defect shape (one player for one pick, six distinct picks).

---

## 2026-08-19 — Round-2 pick recalibration (D-084); the `second` tier floor moves with it

**Branch:** `feat/round2-pick-recalibration`, from `origin/main` `93ac695`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/round2-pick-recalibration/scope.md](../docs/plans/round2-pick-recalibration/scope.md). Memo: [docs/reviews/2026-08-19-ktc-pick-value-comparison.md](../docs/reviews/2026-08-19-ktc-pick-value-comparison.md) (carried on this branch; not on main). Decision: [D-084](DECISIONS.md). Open question: [Q-019](OPEN_QUESTIONS.md). Gotcha: [G-051](GOTCHAS.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` | **3429 passed, 1 skipped, 0 failed** — byte-identical to the `93ac695` baseline (3429/1) |
| `tsc --noEmit` (TypeScript 5.9.3, worktree-local `npm ci`) | clean, exit 0 |
| `mobile/scripts/testid-lint.sh` | `testid-lint OK` |
| `mobile/tests/check-*.js` — `calc-pick-tiers`, `anchor-labels`, `picks-subset-invariance`, `contrast` | 4/4 pass |
| `test_tier_occupancy.py` | **47 passed** — `second` peaks at 32 against its ceiling of 35, exactly as the memo predicted |
| Bake-off knob-inventory guard | untouched — **no `trade_service._DEFAULT_CFG` key added**; `trade_service.py` is not in the diff |

**The blast radius was predicted and then measured to match, exactly.** Applying the seed + band edit before retargeting anything produced **11 failed / 3418 passed** — the same eleven the memo named on a throwaway copy, no more and no fewer. Nothing outside the predicted set moved. Retargeted: `test_pick_anchor` ×2 (1460 → 1400), `test_pin_tier_bounded` ×4 (one constant, `SECOND_LO` 1400 → 1370), `test_pick_pricing_m6b` ×3, `test_league_picks_tier` ×1, `test_power_rankings` ×1. Two extras retargeted deliberately although green: `test_tier_occupancy::test_anchor_rungs_land_in_matching_tiers` asserted `1460.0 → "second"`, a seed that no longer exists, and the `pin_tier_bounded_golden.json` fixture.

**The honest scorecard moved and was rewritten, not silenced.** `test_pick_pricing_m6b::test_the_measured_reshaping_direction_is_deflation_not_inflation` measures how far our ladder sits above DynastyProcess's real market slot prices. `delta(2026, 2)` was `< -0.40`; it is now **−0.284**, and `delta(2027, 2)` **−0.244**. Both are now pinned with `pytest.approx` rather than a loose bound so drift in *either* direction must be acknowledged, with a docstring recording that the remaining ~28 % is intentional (Option B was measured and rejected). It also records that **the ranking flipped**: 2nds are no longer the biggest outlier — a 2026 3rd now deflates hardest (−0.355 vs −0.284), which is the Q-019 residue.

**The golden fixture was re-captured against pristine code, not re-derived.** `pin_tier_bounded_golden.json` pins `edge_lo` to the `second` floor, so the floor move changed its *input*. Its docstring forbids regenerating from new code, so a separate **pristine `origin/main` worktree at 93ac695** was created and the harness validated first by re-capturing at 1400 and confirming it reproduced the checked-in golden **byte-for-byte**; only then was it re-run at 1370. Seven numbers moved, all forced by the one changed input (`elo.edge_lo`, plus ripples in `free` — his opponent in six comparisons — and `quiet`).

**Production validation, read-only** (`SET TRANSACTION READ ONLY`, SELECT only, credentials read from the gitignored `secrets.local.env`, never printed). Question: *is the overpriced 2nd costing accepted trades?* **Answer: no, not measurably.** Cards containing a 2nd are liked at **34.8 % (n=46)** vs **35.2 % (n=565)** for cards with no pick at all — Fisher **p = 1.00**; 2nds appear on only **13.7 %** of 2,184 served cards. A 3-day impression-level sample points the *opposite* way (17.6 %, n=17, p=0.26); two samples disagreeing on sign is the finding. Zero of 23 free-text passes mention a 2nd. The real signal is **1sts by side** — 1st-on-give 15.6 % liked vs 1st-on-receive 47.1 % (n=128). **D-084 is justified on the rank measurement, not on acceptance data, and no lift should be expected.**

Two incidental prod findings, out of scope and not fixed here: **`backend/database.py` on `main` is stale against prod** (26 vs 13 `deck_impressions` columns; `trade_pass_reasons` missing entirely), and **`model_arm` is 97.5 % NULL with zero `gen_v2` rows** — the bake-off is not producing labelled data.

**Not yet run: the manual TestFlight checklist** (scope §8, 10 steps). It is the only runtime evidence this change gets under D-056, and step 9 deliberately points the operator at the one odd consequence — a current-year 3rd now badges "2nd".

## 2026-08-19 — Per-round draft-pick year decay (D-079); firsts stop decaying

**Branch:** `feat/pick-year-decay`, from `origin/main` `02e27dd`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/pick-year-decay/scope.md](../docs/plans/pick-year-decay/scope.md). Review: [docs/reviews/2026-08-19-pick-year-valuation.md](../docs/reviews/2026-08-19-pick-year-valuation.md). Decision: [D-079](DECISIONS.md). Open question: [Q-018](OPEN_QUESTIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3404 passed, 1 skipped (baseline at `02e27dd`) | **3416 passed, 1 skipped, 0 failed** (+12 new) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 10 passed | 10 passed, after recording the exclusion decision |

Mid-run the change produced **8 failures, every one of them the intended behaviour change** — seven
behavioural tests asserting the old round-1 discount, plus the bake-off knob-inventory guard demanding
a written decision for the four new `_DEFAULT_CFG` keys. None were suppressed. Each of the seven was
**retargeted to assert the new intent plus a still-decaying round**, so "someone flattened every round"
now fails loudly rather than passing silently: `test_owned_picks.py`, `test_dynasty_value_pick_scale.py`,
`test_league_picks_tier.py`, `test_pick_value_scaling.py`, `test_pick_pricing_m6b.py`,
`test_pick_rung_year_labels.py`, `test_pick_values_in_suggestions.py`.

**One of those retargets was a near-miss worth recording.** `test_pick_values_in_suggestions.py` seeded
its player fixture at a hard-coded Elo `1552.0`, chosen because it matched the *old* 2029 1st value
(~1300). After the repricing that literal would have quietly turned "a player against a 1st" into
"a mid player against a 1st" and the test would still have passed — measuring nothing. The seed is now
**derived** from `pick_pool_value(1, 3)`, so the fixture moves with the ladder.

**New coverage — 12 tests in `backend/tests/test_pick_year_decay.py`:** default rates; deep-round
clamping onto `_r4`; live `model_config` reads; the `[0,1]` clamp (a rate > 1 would invert the
arbitrage); **the deploy-free revert** — all four keys at 0.85 reproducing the pre-D-079 ladder on both
value scales, including the literal 1300.1 that was the bug; a 2029 1st equalling a 2027 1st; later
rounds still decaying with round ordering intact at every horizon; **zero value gradient between any
two 1sts** (the anti-swap invariant); `compute_pick_value` on the same clock; round-aware rung
relabelling; and a no-config fallback so a DB outage cannot take pricing down.

**Code-walk proof (replaces a simulator capture, per D-056).** The evidence that *served cards* change
is `trade_service.overpay_ok` (`backend/trade_service.py:1502–1521`) flipping verdict on the operator's
actual card, impression `c67c2fd1e97cb6bf`: Adams 1138.8 vs the 2029 1st at 1300.1 → gap 161.3, ratio
0.124, under both floors (500 / 0.25) → **served**, which is what prod did. At 2117.0 → gap 978.2,
ratio 0.462, over both floors → **killed**. Asserted as the gate's boolean, not as a number.

**Prod corpus measurement (read-only, `SET TRANSACTION READ ONLY`, SELECT only).** 2048
`deck_impressions` rows with `assets_json`: **58.5 %** contain a pick; firsts are **84 %** of all pick
mentions; **99 cards (4.8 %)** moved a 1st one way and a *different-year* 1st the other — the arbitrage,
counted. Re-run that query after merge; the expected post-fix count is **0**, structurally.

**NOT run:** the manual TestFlight checklist (§3 of the scope block) — it needs the operator on a build.
Nothing here is runtime evidence from a device.

## 2026-08-19 — Decline reasons: player preference under "Neither" (branch only, NOT merged)

**Branch:** `feat/decline-reason-player-pref`, from `origin/main` `02e27dd`. **Not shipped** — not pushed, not merged. Flag `feedback.decline_reasons` unchanged (already on for all users).
Scope block: [docs/plans/decline-reason-capture/scope-player-preference.md](../docs/plans/decline-reason-capture/scope-player-preference.md). Decision: [D-080](DECISIONS.md#d-080). Contract: [SPEC §2a](../docs/plans/decline-reason-capture/SPEC.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` (before) | **3404 passed, 1 skipped** — baseline at `02e27dd` |
| `pytest backend/tests -q` (after) | **3417 passed, 1 skipped, 0 failed** — +13 tests, zero regressions |
| `npx tsc --noEmit` (mobile) | **clean**, exit 0 |
| `mobile/tests/check-*.js` | **56 suites, 0 failing** (the CI `mobile-typecheck` job globs all of them) |
| `mobile/scripts/testid-lint.sh` | **testid-lint OK** |
| Maestro / simulator | n/a — retired by D-056. The two `mobile/.maestro/flows/decline-reasons-*.yaml` are historical artifacts and were **not** run or extended |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| Manual TestFlight checklist | **written, NOT run** — 8 steps in scope block §3b, awaiting the operator |

**New tests: 13.** Nine `test_player_preference_*` in `backend/tests/test_decline_reasons.py` (both codes parent to `other` and not to `value`; a foreign layer-1 is a `detail_reason_mismatch` 400 that writes nothing; a layer-2-first write derives `reason='other'` from the prefix; the two directions plus the residual free text land as three distinguishable stored answers), plus four from the `_ELO_MATRIX` parametrisation growing 8 codes → 10 across both knob positions. The two existing enumerations — `test_every_specced_code_is_accepted` and `test_pass_reason_writes_elo_rule_is_pure` — were extended rather than left to pass vacuously.

**Structural suite extended, not just kept green.** `mobile/tests/check-decline-reasons.js` gains a §6 that reads the `TILES` table through the **TypeScript AST** rather than by regex, so a re-order or re-wrap of the source cannot fake a pass. It fails on either of the two silent reversions: reverting "Neither" to free-text-only (the `freeOnly` shortcut is asserted gone), or collapsing the two player codes into one (they are asserted as a pair, each committing on tap rather than opening a text box, each carrying `trades.pass-reason.l2.<code>`, with `other_text` still free and still last).

**A check that had never once executed now does.** The suite's "transcribed codes still match SPEC §2" cross-check was guarded on `fs.existsSync(SPEC.md)` — and **SPEC.md was untracked**, present only in the main checkout's working tree and committed to no branch in the repo. The guard had always taken its SKIP branch, so the transcription had never actually been compared to the spec. SPEC.md is committed on this branch and the cross-check runs and passes. Committing it also surfaced a real spec/implementation divergence: SPEC §2 wrote the free-text step as `value_other` → a second `value_other_text` code, which does not exist and which the route 400s as `invalid_detail`. Corrected in the same amendment.

**What was NOT verified here:** runtime behaviour on a device. Under D-056 that is the manual TestFlight checklist and nothing else — it is written but unrun, so no runtime claim is made about this change. The code-walk proof in scope block §3a is a file:line trace, not evidence of execution.

## 2026-08-18f — Trade-suggestion presentation v2 (additive Acquire surface, flag OFF)

**Branch:** `feat/trade-presentation-v2`, from `origin/main` `a7f8783`. **Not shipped** — not pushed, not merged. Flag `trades.presentation_v2` ships **OFF**.
Scope block: [docs/plans/trade-presentation-v2/scope.md](../docs/plans/trade-presentation-v2/scope.md). Decision: [D-081](DECISIONS.md#d-079--the-confidence-band-is-derived-from-provenance-because-no-confidence-field-exists).

| Gate | Result |
|---|---|
| `npx tsc --noEmit` (mobile) | **clean** — baseline at `a7f8783` was also clean, so the delta is zero new errors |
| `mobile/tests/check-*.js` (all 57) | **all pass**, including the new `check-presentation-v2.js` (**87 assertions**) |
| `npm run test:presentation-v2` | **87 PASS, 0 FAIL** |
| `bash mobile/scripts/testid-lint.sh` | **OK** (8 template-literal globs added to `testid-lint-allow.txt`, each with its constructing file:line) |
| `pytest backend/tests` | **NOT RUN** — no Python environment in this worktree. Backend delta is one `FLAG_KEYS` string + one `config/features.json` entry; `test_entitlements.test_features_json_keys_known` is the covering test and **must be green on the pushed sha before merge** |
| Maestro / simulator | **Not run.** Three flows AUTHORED (`presentation-v2-hero`, `-browse-dismiss`, `-honest-empty`) because the build brief required it — which directly contradicts D-056's "do not author, extend, or execute". Each carries a banner recording the conflict. Execution, and whether authoring was correct at all, is an **operator decision** (scope.md §6 item 1) |
| Sim gate | `FTF_SKIP_SIM_GATE=1` — standing posture under D-056 |
| Manual TestFlight | **Not run** — 12-step checklist written in scope.md §3; operator action |

**What the structural guard actually proves** (not a grep-count — these are the four things that fail silently):
1. **Flag-off byte-identity.** Both `onTodaysTrade` pass sites are ternaries on the flag passing `undefined`; both components build their control list *from the handler's presence*; `'today'` is asserted **not** to be in the static `CHIPS` array; the routes are asserted registered *and* asserted **not** flag-wrapped. A no-op-handler "simplification" — which still renders the chip — fails here.
2. **Instrumentation parity.** Shared `swipeTrade` / `postDeclineReason` imports, `SwipeSignal` imported as a type, no hand-rolled `api.post`/`api.get` in the signals hook, the three event names cross-checked against `TradesScreen`'s own source, the four signal fields, the two-part `signal_v2 && impression_id` gate, boolean-only free text, explicit `platform`, and `VIEWED_MIN_MS`/`DWELL_CAP_MS` matched against `TradesScreen`'s literals.
3. **The server cache-slot agreement.** Shared fairness helpers only, no raw threshold constants, never `force: true` — so the new surface cannot kick a second generation or serve a different card set to the same user.
4. **The design laws, executed.** The pure module is transpiled and RUN: band derivation across all four provenance combinations plus the `likesYou` promotion, "no band label contains a digit", the fairness band exposing no winner/margin, `userSideBullets` naming a concrete asset and never leaking `opponent_surplus`, `counterpartyStatement` returning a number-free single string, `partitionDeck` returning **no hero** when nothing is endorsable, browse uncapped, dismissed cards excluded from hero but retained in browse, and the empty-state copy omitting an unknown roster count rather than rendering zero. Plus source-level bans: no `TradeValueBar`, no `Meter`/`fairnessColor`, no `partner_fit`, no `match_score`, no `showPercent`, no `.slice()` in browse, no `numberOfLines` anywhere on the surface.

**Not proven by anything here, and stated so it is not mistaken for covered:** that the surface renders correctly on a device. Nothing in this branch has run on a simulator or a phone. The 12-step TestFlight checklist is the only runtime evidence available under D-056 and has not been executed.

---
## 2026-08-18e — Bake-off deck composition (three groups of ten; arm A out of the roster)

**Branch:** `feat/bakeoff-composition`, from `origin/main` `217a8e1`. **Not shipped** — not pushed, not merged. Flag `trade.bakeoff` stays **OFF**.
Scope block: [docs/plans/three-model-bakeoff/scope-composition.md](../docs/plans/three-model-bakeoff/scope-composition.md). Decision: [D-078](DECISIONS.md#d-078--a-bake-off-deck-is-composed-of-groups-and-an-unfilled-quota-is-the-finding).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` (before) | **3363 passed, 1 skipped, 0 failed** — baseline at `217a8e1` |
| `pytest backend/tests -q` (after) | **3404 passed, 1 skipped, 0 failed** — +41 tests, zero regressions |
| `npx tsc --noEmit` (mobile) | n/a — zero mobile files changed |
| `check-*.js` / `testid-lint.sh` | n/a — zero mobile files changed |
| Maestro / simulator | n/a — retired by D-056; backend-only, nothing user-visible while the flag is off |
| Sim gate | Tier 4 (backend-only); `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056 |

**New tests: 41.** `backend/tests/test_bakeoff_composition.py` (31 unit) + 10 integration added to `backend/tests/test_bakeoff_serving.py` (real `server._run_trade_job`).

**Flag-off golden extended, not weakened.** `backend/tests/fixtures/bakeoff/flag_off_golden.json` is byte-for-byte unchanged and the flag-off test still asserts byte-identity against it. The four new columns (`group_key`, `group_rank`, `lane_slot`, `trade_intent`) joined Phase 3's admitted-additive list and are asserted **NULL on every row**, exactly as Phase 3's three were.

**Phase 2 verified still intact.** The arm-A golden, the R4-bypass tests and the 189-key knob-inventory guard all still pass; the four new knobs were added to `_PINNED_KNOBS`. `test_bakeoff_composition.py::test_arm_a_leaves_serving_but_phase_2_stays_intact` asserts the profile, its entry point and its knob set directly, so "arm A left by configuration, not deletion" is a tested property rather than a claim.

**Measured — three-group interleave, 500 decks (30 cards each):**

| | group 1 `current_divergence` | group 2 `current_consensus` | group 3 `gen_v2` |
|---|---|---|---|
| mean served position (of 30) | 14.48 | 14.55 | 14.48 |
| cards per deck | 10.0 | 10.0 | 10.0 |
| decks led (of 500) | 164 | 160 | 176 |

Per-lane mean served position: value 14.52, outlook (`window`) 14.48. Both distributions are flat, which is the whole point — a per-**arm** rotation instead puts arm `gen_v2` at mean position **24.5** (measured on identical inputs by `test_grouping_by_arm_would_bury_arm_c_and_the_group_draft_does_not`).

**Measured — outlook-slot under-fill** (slots left empty of 5, at the live lane ratios: divergence 80.5% value / 19.5% window, consensus 73.2% / 26.8% / 6.1% unlabelled), sweeping per-deck supply:

| surviving cards in the group's pool | divergence group | consensus group |
|---|---|---|
| 10 | 3.0 | 3.0 |
| 15 | 2.0 | 1.0 |
| 20 | 1.0 | **0.0** |
| 25 | **0.0** | 0.0 |
| 30 / 40 / 60 | 0.0 | 0.0 |

A divergence group needs ~25 surviving cards before it can expect five outlook cards; a consensus group clears at ~20. That gap is why groups 1 and 3 are the ones expected to serve short, and why the default fill policy records the hole instead of topping it up from the value lane. Pinned by `test_measured_under_fill_across_realistic_divergence_supply`.

**Two plumbing gaps closed** so the comparison is of generators, not of which post-generation steps each arm received: arm C now gets the same `_filter_by_trade_intent` and the same `classify_lane` the engine arms already get. Without the lane label, group 3's outlook quota would have under-filled **100% of the time** and read as "arm C cannot produce outlook ideas".

**Not measured here, needs Phase 4:** real per-deck supply. Every under-fill number above is from the live lane *ratios* applied to swept supply sizes, because the 3,163-card total does not say how many cards one deck's arm produces. Phase 4 dark validation writes `groups_json` on every run, so the true rate is one query away once it runs.

---
## 2026-08-18d — Three-model bake-off Phase 3 (the runner)

**Branch:** `feat/bakeoff-runner`, rebased onto `origin/main` `9d24da3` (which carries bake-off Phase 2 and tier-bounded pins). **Not shipped** — not pushed, not merged. Flag `trade.bakeoff` ships **OFF**.
Scope block: [docs/plans/three-model-bakeoff/scope-phase3.md](../docs/plans/three-model-bakeoff/scope-phase3.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` | **3363 passed, 1 skipped, 0 failed** — full suite re-run after the final rebase onto `9d24da3` AND after the fairness-threshold capture |
| `npx tsc --noEmit` (mobile) | n/a — zero mobile files changed |
| `check-*.js` / `testid-lint.sh` | n/a — zero mobile files changed |
| Maestro / simulator | n/a — retired by D-056; backend-only change with no user-visible surface |

**New tests: 49.** `backend/tests/test_bakeoff_runner.py` (35 unit) + `backend/tests/test_bakeoff_serving.py` (14 integration through the real `server._run_trade_job`).

**Third contamination channel closed (coordinator addition, same session).**
[The trade-logic archaeology review](../docs/reviews/2026-08-18-trade-logic-archaeology.md)
found `fairness_threshold` persisted **nowhere** — not a column, not one of the 28
`features_json` keys — while arriving per-request from the client (0.75 toggle on / 0.50 off).
A per-arm comparison spanning sessions with different client settings would have compared arms
AND thresholds at once. Now `deck_impressions.fairness_threshold` (a column, not a JSON key: the
analysis groups by it), written **per card** because the effective bar is card-dependent, and
per arm in `bakeoff_runs.arms_json`. `bakeoff_runs.config_json` snapshots the effective config
each arm ran under, since `model_config` has no `updated_at`.

The composition is proven, not assumed: `test_served_cards_record_the_threshold_they_were_generated_under`
runs the job at **0.75** and asserts the divergence card records **0.55**
(`min(requested, fairness_floor_divergence)`), the consensus card **0.75**, and the arm-C card
**NULL** — i.e. recording the requested value would have misdescribed two of the three.
`test_arm_a_config_snapshot_is_taken_inside_the_profile` pins that arm A's snapshot is taken
INSIDE `model_a()` (outside it the overlay is gone and arm A would be recorded as running on live
defaults). `test_threshold_clean_query_answers_itself_from_the_table` executes the documented
"was this comparison threshold-clean?" `GROUP BY`, so the query cannot rot into documentation-only.

**Flag-off byte-identity is proven by a CAPTURED golden, not an assertion.**
`backend/tests/support/bakeoff_harness.py` was copied into a **separate worktree detached at
pre-bake-off `origin/main` (9a20ca8)**, run there, and its output committed as
`backend/tests/fixtures/bakeoff/flag_off_golden.json`. With the flag off this branch reproduces it
byte for byte — identical served card payloads and identical `deck_impressions` rows. The only
admitted difference is the three additive columns (`model_arm`, `arm_rank`,
`fairness_threshold`), asserted NULL on every row. The harness deliberately imports nothing from `bakeoff_runner`, which is what let it run on
the pre-change SHA.

**§3.4 Channel 2 (the silent-failure risk) is tested, not asserted.**
`test_post_generation_rerankers_cannot_touch_the_merged_deck` turns every reordering layer ON and
replaces each with a spy that REVERSES the deck (F2 `_order_deck`, F3 fatigue multipliers, F5 taste,
F6 value model, F7 wildcard, F9 shaping), then asserts the served arm sequence is still the
interleaver's. Its mirror `test_rerankers_do_run_when_the_bakeoff_is_off` proves the same spies fire
with the flag off, so the bypass is a bake-off property and not a broken harness. F3 decline
suppression is asserted STILL LIVE (it only removes cards).

**§3.4 Channel 1** is guarded structurally: `test_every_swipe_k_multiplier_runs_through_the_elo_freeze`
scans `backend/server.py` for every `fit_congruence_mult` K site and fails if one is missing
`_bakeoff.elo_freeze_mult` — a new swipe path that forgot the freeze would contaminate the shared
board with no visible symptom.

**Real bug found and fixed while testing (would have been silent in prod):** `save_deck_impressions`
inserts the batch with SQLAlchemy `executemany`, which compiles the statement from the **first row's
keys**. Stamping `model_arm` only on attributed cards meant a deck led by an unattributed likes-you
injection dropped attribution for the **entire deck**. Both columns (and the arm-stamped
`policy_version`) are now written on every row, with a regression assertion in
`test_likes_you_injection_does_not_reorder_the_interleave`.

**Generation cost measured** on a synthetic 12-team / 168-asset league with 11 boarded opponents
(scratch harness, 5 repeats, medians):

| | ms | cards |
|---|---|---|
| single generation (today) | 3127 | 19 |
| bake-off fan-out (3 arms) | **7359 (2.35×)** | 140-card interleaved deck |
| — arm `baseline` | 4187 | 30 |
| — arm `current` | 2733 | 19 |
| — arm `gen_v2` | 424 | 105 |

Arm A is the slowest because its profile zeroes every gate, so more candidates survive. Arm C
over-produced **on this fixture only** — the synthetic boards carry gaussian noise, so divergence is
everywhere; PLAN.md §3.2 still expects it to under-produce in production, which is exactly what the
empty-arm rate is there to measure. Agreement on the fixture: `baseline+current` 14.

**Budget finding for the operator:** the per-opponent enumeration deadline is 1 s, so an 11-opponent
league's worst case is ~11 s per arm and ~33–45 s for the fan-out, against
`server._JOB_HARD_TIMEOUT = 60` s. Inside the limit but thin, with no margin for a slow Postgres.
Phase 4 must watch p95 job duration directly; `_JOB_HARD_TIMEOUT` may need raising before Phase 5.
`bakeoff_deck_limit` defaults to uncapped, so an interleaved deck is ~3× today's — set it before
Phase 5 unless a very long deck is wanted.

**Arm-A seam: real, not stubbed.** Phase 3 was built against a temporary local stub of
`backend/bakeoff_profiles.py` (Phase 2 had not yet landed), then **rebased onto `origin/main`, which carries Phase 2's real module** (`3760f12`). The stub was dropped in the rebase and
the runner now calls Phase 2's `model_a()` — the only supported entry point, because it applies the
pinned `MODEL_A_PROFILE` and the R4 bypass together. Arm A is therefore golden-tested against
reference SHA `92c31d5` by Phase 2's own tests, and the R4 bypass is really enforced
(`trade_service.r4_bypassed()`). Full suite re-run after the rebase.

---
## 2026-08-18c — G-049 caller-side finish: route-level proof + the ungated-signal decision

**Branch:** `feat/sweep-followups-2026-08-18` (continues the 2026-08-18b entry below). **Not shipped.**

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3216 passed, 1 skipped | **3219 passed, 1 skipped** |

Both `save_trade_swipes` gates (`swipe_trade`, `_apply_reasoned_pass`) were already in place from
2026-08-18b; this pass added the **runtime** evidence they lacked and settled the one open design
question.

**New coverage — 3 route-level tests** in `test_trade_decision_idempotency.py`. They POST
`/api/trades/swipe` twice through the Flask test client against an in-memory DB with the **real**
`save_trade_swipes` (only `record_event` / `create_notification` / `check_for_match` stubbed), so the
count is of rows the route actually wrote:
1. `test_re_posted_swipe_writes_exactly_one_set_of_swipe_decisions` — one `swipe_decisions` row, one
   `trade_decisions` row, and a `replay_from_db` + `_compute_elo` check that a restart sees exactly
   one application of `trade_k_pass`.
2. `test_route_replay_leaves_the_in_session_signal_doubled` — pins the accepted residual.
3. `test_route_replayed_like_still_runs_match_detection` — `check_for_match` called twice.

**Sabotage:** deleting the `if wrote_decision:` gate in `swipe_trade` turns tests 1 and 3 RED
(`assert 2 == 1` on real rows), alongside the existing source pin. The `inspect.getsource` pins alone
could not have caught a gate that was present but ineffective.

**Design question closed:** `RankingService.record_trade_signal` stays **before** the DB write and
**ungated** (D-073). `_trade_swipes` is derived state that `replay_from_db` rebuilds from
`swipe_decisions` at every `session_init`, and the persist block around it is best-effort by design —
gating it would trade a bounded, self-healing 2x overcount for an unbounded 0x undercount whenever
the DB is unreachable. `backend/database.py`'s docstring and `docs/data-dictionary.md` both said
callers "must skip both", which the shipped code never did; corrected to match.

**Not run:** `tsc --noEmit` / `check-*.js` / testid-lint — this pass touched backend and docs only.
**Count note:** the 2026-08-18b entry recorded 3191; the branch was rebased onto a newer `main`
mid-session (engine-quality wave + navdoc refresh), which brings `test_engine_quality.py` and
`test_engine_quality_golden.py` — hence 3216 as the real pre-change baseline. Nothing was lost.

## 2026-08-18c — Bake-off Phase 2: arm A pinned + golden (branch only, NOT merged)

Branch `feat/bakeoff-arm-a`, off `origin/main` @ `9a20ca8`. Scope block:
[`docs/plans/three-model-bakeoff/scope-phase2.md`](../docs/plans/three-model-bakeoff/scope-phase2.md).
Backend-only: `backend/bakeoff_profiles.py` (`MODEL_A_PROFILE`, `model_a()`), a thread-local
R4 bypass in `trade_service`, and `backend/tests/test_bakeoff_arm_a_golden.py`.
**Not pushed, not merged** — build-agent output; Phase 3 (`feat/bakeoff-runner`) consumes it.

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3267 passed, 1 skipped (3268 collected with the new file ignored) | **3277 passed, 1 skipped, 0 failed** (250s) |
| `npx tsc --noEmit` (mobile) | n/a | **not run — zero files under `mobile/`** |
| `testid-lint.sh` | n/a | **not run — no mobile files touched** |
| Simulator gate | — | **D-056 standing posture, `FTF_SKIP_SIM_GATE=1`**; backend-only, no runtime surface |

**What the golden actually proves.** Reference SHA **`92c31d5`** (`20b40db^` on `--first-parent
main` — the last commit before the G6 wave). Captured by adding a detached worktree at that SHA,
copying the test file in, and running its `__main__` capture mode. Arm A (`MODEL_A_PROFILE` + the
R4 bypass) reproduces **30 deck cards and the asset-ideas groups byte-identically**; arm B (live
defaults) on the same fixture returns **8 cards** and different ideas.

**Board-drift immunity.** The fixture pins every generation input as a literal (player table,
`seed_elo`, `user_elo`, each opponent's `elo_ratings`, confidence counts, roster, outlook,
fairness threshold) and calls `TradeService.generate_trades` directly — no DB read, no
`ranking_service` call, no `comparison_counts`, no pin resolution. So Phase 0's pin fix,
`feat/tier-bounded-pins` and premium import cannot move it: the comparison isolates generation
logic only.

**Non-vacuity, per rule** (a golden that stopped disabling anything would otherwise still pass):
arm B records kills for **R1 2822 / R2 251 / R3 513 / R5 405** on this fixture; C1, C4 and C5 each
move the deck alone; C2 moves the asset-ideas alone. **C3 (`pick_pair_strip_frac`) is the one
profile entry the deck fixture cannot reach** — no matched-pick-pair shape survives the other gates
on a realistic league (R3 kills the candidates first) — so it is asserted at its own gate
(`pick_swap_ok`), with byte-identity already pinned by `test_engine_quality_golden.py`. Recorded as
a known gap in the scope block rather than papered over.

**Both drift alarms negative-controlled** (verified by breaking them on purpose, not by inspection):
injecting a fake `_DEFAULT_CFG` key fails the inventory test naming `shiny_new_knob`; removing
`deck_headliner_cap` from the profile produces a drift report listing the 22 dropped cards.

**Not covered:** no runtime/TestFlight evidence exists or is claimed — nothing reaches a client.
The new code is unreachable in production until Phase 3 wires a caller behind `trade.bakeoff`.

**Second rebase, same session** (onto `origin/main` `9a20ca8`, picking up the bake-off Phase 0 batch
`e8ae476`): clean, no conflicts, despite that batch touching `backend/database.py`,
`backend/server.py` and `docs/data-dictionary.md` — the same three files this work edits. Re-verified
after: both `save_trade_swipes` gates present (`server.py:11010`, `:11347`), guard intact, and
**pytest 3270 passed / 1 skipped** (the +51 over 3219 is Phase 0's own
`test_force_supersedes_running_job.py` and `test_override_pin_unpin.py`). The three route-level tests
count real rows after two POSTs, so their passing is itself the evidence the guard still works — no
second sabotage run needed.

---
## 2026-08-18d — Tier-bounded voting (a pin confines a player to a tier)

**Branch:** `feat/tier-bounded-pins`, rebased onto `origin/main` `74620a7`. **Not shipped, not pushed.**
**Scope block:** [`docs/plans/three-model-bakeoff/scope-tier-bounded.md`](../docs/plans/three-model-bakeoff/scope-tier-bounded.md) · **Decision:** [D-076](DECISIONS.md).

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3280 passed, 1 skipped (`74620a7`) | **3314 passed, 1 skipped** |

The +34 is this branch's own: 33 in the new module, plus one from splitting a `test_elo_memoization.py` test in two. Suite was run green at both bases — 3267 → 3301 on `9a20ca8` before the rebase, 3280 → 3314 after it; `9a20ca8..74620a7` does not touch `ranking_service.py`, `trade_service._shrink_user_elo`/`_value_uncertainty` or `tier_config.json`, so the captured golden is unaffected by the rebase.

| `npx tsc --noEmit` (mobile) | n/a — zero files under `mobile/` in the diff | n/a |
| `mobile/scripts/testid-lint.sh` | n/a — same reason | n/a |

- **New: `backend/tests/test_pin_tier_bounded.py` — 33 tests.** The Adams scenario (pinned
  1565.28 in `second` [1400, 1575], 17 down-votes → Elo 1426.6, materially down, never outside
  the band); clamp at both edges; a pin exactly on a band boundary; a pin in a band gap; a pin
  above the top band; unranked/`None`-tier pins frozen rather than crashed or floated; a
  zero-vote pin untouched by the clamp; a clamped player climbing back into the band; both
  scoring formats plus monkeypatched bands proving the clamp reads the service's own format and
  the player's own position; the `pin_exclude_comparisons` narrowing in both directions and its
  `_value_uncertainty` sharing; monotonicity, direction-awareness, and the disclosed n=0→1
  residual; the F2 interaction both ways; the knob in both memo keys.
- **Byte identity proved by CAPTURE.** `backend/tests/fixtures/pin_tier_bounded_golden.json`
  was produced by copying the new module's own `build_service`/`snapshot` verbatim into a
  detached worktree of pristine `origin/main` (`9a20ca8`; `git diff e8ae476..9a20ca8 --
  backend/` is empty) and running it there before a line of production code changed. Asserted
  as a whole document at `pin_tier_bounded=0` + `pin_unpin_on_newer_swipe=1`. A guard test
  asserts the golden still *exhibits* the freeze (every pinned player exactly on his pin, every
  pinned count 0, the un-pinned control moved), so the proof cannot rot.
- **Mutation matrix — every guard bites.** Each mutation applied to a clean tree:
  remove the clamp → **11 fail**; drop the `min(lo,pin)`/`max(hi,pin)` widening → **2 fail**;
  let an unranked pin float free → **1 fails**; count clamped-away votes as confidence →
  **3 fail**. Restored → 33 pass.
- **Updated, not deleted:** `test_override_pin_unpin.py` (41 tests) now states the Phase 0
  configuration explicitly instead of reading today's defaults, so it keeps gating the Phase 0
  contract, which is still reachable by knob. `test_elo_memoization.py` had two tests asserting
  a pinned Elo *exactly* — that was the freeze contract; split into the memo contract
  (cold == warm, and inside the band) plus a new test asserting exactness under the kill switch.
- **Prod measured read-only** (`DATABASE_URL_PROD`, `SELECT` only under
  `default_transaction_read_only=on`), 2026-08-18. Every board replayed through the **real**
  `RankingService._compute_elo`/`_pin_bounds` via `replay_from_db`; the "today" column
  reproduces the audit's 2,721-inert figure exactly, which is what validates the replay.

  | | Comparisons | Effective | Pins | Players who move |
  |---|---|---|---|---|
  | Today (freeze) | 4,013 | 1,292 (32.2%) | 2,735 | 0 |
  | **Tier-bounded** | 4,013 | **3,938 (98.1%)** | 2,735 | **667 (24.4%)** |

  Ceiling on the second number is 739 — the pins that have ever appeared in a comparison at all
  — so **90.3% of every pin the user has ever voted on now moves**. The 72 that do not are 47
  pins below the lowest band (frozen by design) and 25 clamped hard at an edge.
- **Correction to the 2026-08-18 audit, found by the replay:** the operator's 18 Davante Adams
  comparisons are `decision_type = 'trade'`, and trade decisions have **never** entered
  `comparison_counts` for any player (`_compute_stats` walks only `_swipes`). His Elo now moves
  (1565.28 → 1530.15) but his effective value is the consensus seed 1138.8 both before and
  after. The audit's `n = 6` came from unfiltered SQL over `swipe_decisions`; it flagged its own
  confidence on that arithmetic as medium-high. The mechanism is real — the 353 → 1,666 jump in
  live *ranking* comparisons is what measures it — the per-player +12.5% is not.
- **Sim gate: Tier 4 (none, CI only).** Backend-only diff; zero files under `mobile/`.
  `qa/sim-runs/last-sim-run.json` not written — under D-056 there is nothing to run.
  `FTF_SKIP_SIM_GATE=1` is the standing posture for any push.
- **Not covered by any test here:** whether the thawed boards produce better decks. That is
  empirical and the lever is `pin_tier_bounded` — one `PUT /api/admin/config` to set and to
  undo. Also untested: the band-edge UI affordance, which is a client change and deliberately
  not built (scope §5).

---
## 2026-08-18b — Bug-sweep follow-ons (items 3/4/5) + research 6/7

**Branch:** `feat/sweep-followups-2026-08-18` (off `origin/main` `90fb19a`). **Not shipped** — awaiting operator go.

| Gate | Sweep baseline | After |
|---|---|---|
| `pytest backend/tests -q` | 3148 passed, 1 skipped | **3191 passed, 1 skipped** |
| `npx tsc --noEmit` (mobile) | clean | **clean** |
| `check-*.js` | 54 suites | **56 suites, all pass** |
| `testid-lint.sh` | OK | **OK** |

**Two false-confidence findings, both caught by sabotage rather than by review:**
1. `test_trade_decision_idempotency.py` defined its own `swipe_once()` caller, proving the *contract*
   while leaving `server.py`'s two call-site gates unpinned — both could be deleted with every test
   green. Closed with `inspect.getsource` route pins (the `test_pass_cooldown.py` idiom).
2. `check-swipe-failure-recovery.js` exempted rewinds that called `setDeck([])`. Unsound — the guard
   is a ref that outlives the deck — and its only real effect was to let the one site that forgot
   (QuickSet regen) pass. Exemption removed; scan went **4 → 9 sites**.

**Sabotage coverage:** item 3 ran 65 mutations (all RED, three initially-weak assertions rewritten
after they survived); item 4 ran 9; item 5 ran 9; the orchestrator separately sabotage-verified the
QuickSet guard clear, the picker `loading` assertion, and both new route pins.

**Prod reads (read-only, `DATABASE_URL_PROD`):** `trade_decisions` 933 rows — 40 double-writes
(0.015–0.200 s) vs 23 genuine re-decisions (147.7 s+), 738× empty band; 62 duplicate `swipe_decisions`
rows ≤1 s apart, 48 correlating with a duplicated decision.

**On-device checks owed (next build):** (1) **SignIn keyboard** — fresh install, tour on, tap the
username field: the ring must follow it up. This is the highest-value check in the batch and is a
30-second visual confirm. (2) QuickSet regen: pass a card, take the Quick-Set prompt mid-generation,
return, confirm the deck rebuilds and the card can still be passed. (3) Calculator PICK chip still
correct with the server field live.

---

## 2026-08-18 — Phase 0: board-override pins + forced regeneration (branch only, NOT merged)

Branch `feat/unpin-overrides`, rebased onto `origin/main` @ `355bddb`. Scope block:
[`docs/plans/three-model-bakeoff/scope-phase0.md`](../docs/plans/three-model-bakeoff/scope-phase0.md).
Three knobbed fixes for the defect diagnosed in
[`docs/reviews/2026-08-18-valuation-age-audit.md`](../docs/reviews/2026-08-18-valuation-age-audit.md)
plus the `force`-ignored-while-running bug from the bug-sweep ticket.
**Not pushed, not merged** — build-agent output awaiting operator review.

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3175 passed, 1 skipped | **3224 passed, 1 skipped, 0 failed** (271s) |
| `npx tsc --noEmit` (mobile) | n/a | **not run — zero files under `mobile/`** |
| `mobile/scripts/testid-lint.sh` | n/a | **not run — no testIDs touched** |

- **+49 tests, zero regressions.** `test_override_pin_unpin.py` (41) and
  `test_force_supersedes_running_job.py` (8). Every knob has a behaviour test AND a
  kill-value test.
- **Kill-value byte-identity is proven against captured output, not asserted.**
  `backend/tests/fixtures/override_pin_golden.json` was produced by running the test's
  exact fixture against pristine `origin/main` **before a line of production code
  changed**, and is compared as a whole document (elo / comparison counts / shrunk elo /
  uncertainty / effective value). A companion test asserts the golden still *exhibits*
  the defect (`value > consensus` while `elo` never moved), so the proof cannot rot into
  a tautology if the fixture drifts.
- **The fixture reproduces the audited numbers exactly**: consensus value 1138.83, pinned
  board value 1385.95, and at the kill values the effective value sits at 1215.87 —
  *above* consensus purely because the player was voted on. With F1 on it is 1138.83,
  i.e. exactly consensus.
- **Mutation-checked.** Reverting the impression gate makes
  `test_a_superseded_job_writes_no_impressions` fail with **4 orphaned impression rows**;
  reverting the route gate makes `test_forced_request_while_running_spawns_a_new_job`
  fail. A control test proves the same harness *does* write impressions normally, so the
  zero-rows assertion is not vacuous.
- **Two existing test files changed, both because the contract genuinely moved, neither
  weakened.** `test_rnk_elo_golden.py`'s "an overridden player's Elo never moves" was the
  pre-F2 contract; it is now three tests (pinned against *earlier* swipes; released by a
  *newer* one; the old contract restored by the kill switch). `test_elo_memoization.py`'s
  spy reconstructed `_elo_cache_key` by hand and needed the pin knobs added after they
  were folded into the key (so a kill pulled via `PUT /api/admin/config` takes effect on
  warm sessions immediately).
- **Prod blast radius measured read-only** (`DATABASE_URL_PROD`, `SELECT` only under
  `default_transaction_read_only=on`), 2026-08-18: 4,013 comparisons, 2,721 inert
  (67.8%); 2,735 pinned entries, 739 of them carrying at least one vote. With the shipped
  defaults live comparisons stay at **1,292/4,013 (32.2%)** — F2 is inert on legacy pins
  by design. What F1 changes immediately: **6,250 of 8,026 confidence-contributing
  player-sides (77.9%) stop counting.**
- **Sim gate: Tier 4 (none, CI only).** Backend-only diff; zero files under `mobile/`.
  `qa/sim-runs/last-sim-run.json` not written — under D-056 there is nothing to run.
  `FTF_SKIP_SIM_GATE=1` is the standing posture for any push.
- **Not covered by any test here:** whether released boards actually produce better decks.
  That is an empirical question and the named lever is `pin_legacy_at_epoch` — a single
  `PUT /api/admin/config` to set and to undo. See scope §6.

---
## 2026-08-18 — Operator bug sweep B1–B5 (five fixes, two adversarial rounds)

**Branch:** `fix/bug-sweep-2026-08-18` (off `origin/main` `90fb19a`). **Ticket:** [`docs/reviews/2026-08-18-bug-sweep/ticket.md`](../docs/reviews/2026-08-18-bug-sweep/ticket.md).

| Gate | Baseline (pre-change) | After |
|---|---|---|
| `pytest backend/tests -q` | 3125 passed, 1 skipped | **3148 passed, 1 skipped** |
| `npx tsc --noEmit` (mobile) | clean | **clean** |
| `mobile/tests/check-*.js` | 48 suites, all pass | **54 suites, all pass** |
| `mobile/scripts/testid-lint.sh` | OK | **OK** |

Baseline was captured on a clean worktree **before any edit**, so every post-change result is
attributable. Note the baseline required a real `npm ci` — an initial copied `node_modules` was
stale and produced a phantom `expo-document-picker` error that was **not** a real failure.

**Six new suites** (+23 tests): `test_pick_labels_in_matches.py` (16), `test_tier_order_roundtrip.py`
(7), `check-guide-spotlight-tracking.js`, `check-tier-move-placement.js`,
`check-picker-pick-filter.js`, `check-swipe-failure-recovery.js`. None registered in
`mobile/package.json` — CI globs `tests/check-*.js`.

**Every new test was sabotage-verified RED→GREEN.** Notable, because the first attempts were not
sound:
- `check-tier-move-placement.js` was **polarity-blind** — a reviewer inverted both direction guards (shipping the opposite of the requested behavior) and all 12 assertions stayed green. Rewritten to lift the updater bodies out of source and assert real placement; the same inversion now fires 10 assertions.
- `test_digit_only_ids_skip_the_pick_query` was **vacuous** — it raised `AssertionError` inside a block guarded by `except Exception`. Rewritten against a connection spy with a positive control. See **G-050**.
- `check-swipe-failure-recovery.js` asserted the guard clear by text containment, so keying it on `ctx.tradeId` instead of `ctx.rawId` would have passed while silently restoring the bug for edited cards. Now pins `ctx.rawId`.
- `check-guide-spotlight-tracking.js` check 8 asserted only that a viewport predicate existed, and pinned an incomplete clamp. Now executes the arithmetic.

**Simulator gate:** not run — Maestro/simulator work is retired (**D-056**, 2026-08-15);
`FTF_SKIP_SIM_GATE=1` is the standing posture. TestFlight is primary QA.

**Shipped:** `main` `60105ca` (sweep) → Render **live**; `7583358` is the final tip. TestFlight
**build 117**, submitted and processing. Note the marketing version stayed **1.14.0**, not 1.14.1:
`eas.json` sets `appVersionSource: remote` and the project has an `ios/` directory, so EAS reads
`CFBundleShortVersionString` from `Info.plist` — the `app.json` bump was inert (the #131 bare-workflow
gotcha, `docs/runbook.md:452`) and was reverted so the repo states what actually shipped. A real
version bump means editing `Info.plist` and cutting another build.

**Sim gate skipped** (`FTF_SKIP_SIM_GATE=1` on all three pushes): Maestro/simulator work is retired
per **D-056**; this is the standing posture, not a deviation.

**Not covered by automation:** B1's spotlight tracking is verified structurally only — no test
exercises a real scroll, so the visual behavior rests on review plus on-device QA. B2's client-side
ordering is now behavioral, but no flow drives the multi-select chip row (TiersScreen still exposes
only four testIDs). **On-device checks owed:** (1) analyst tour on Trades — scroll during `s2.2`,
ring must track and must vanish cleanly when the card leaves the viewport; (2) Tiers **single-position**
tab (not "All" — its per-position re-spread confounds the read), chip-move a player down, confirm top
placement, then tap the same chip again and confirm nothing moves; (3) calculator "Real values" →
PICK chip shows rungs, and RB no longer lists them; (4) Matches both segments on a Sleeper league
with traded picks — expect `2026 1st` / `2026 2nd (from Jared)`; (5) force a swipe failure and
confirm the card can still be passed afterward.

---

## 2026-08-18 — Engine quality wave (D-074, renumbered from D-068) built, NOT shipped

Branch `feat/engine-pick-and-diversity` off `origin/main` @ `90fb19a`. Five knobbed
ranking/gating fixes for the two live-corpus defects (picks buying fairness for free;
one asset flooding a whole deck). **Not pushed, not merged** — build-agent output awaiting
operator review.

- **pytest 3150 passed / 1 skipped / 0 failed** (264s) on the branch tip.
  Baseline on `origin/main` before any edit: **3125 passed / 1 skipped** — so **+25 new
  tests, zero regressions**.
- **25 tests** across `backend/tests/test_engine_quality.py` (22) and
  `backend/tests/test_engine_quality_golden.py` (3). Each of the five knobs has a
  behaviour test AND a kill-value no-op test; C1 additionally pins the brief's explicit
  property, *adding a pick to a fair package does not raise composite*, with a
  fixture-validity assertion that the defect IS live at the kill value (bare 1.554 →
  padded 1.584 uncapped; 1.554 → 1.554 with C1 on).
- **Kill-value byte-identity is proven against real pre-wave output**, not asserted:
  goldens for a deck and an asset-ideas run were captured by executing the same fixtures
  in a throwaway worktree at `origin/main` @ `90fb19a`, and `test_engine_quality_golden.py`
  asserts all-five-knobs-killed reproduces them exactly. A third test asserts the goldens
  are **not** vacuous (live defaults must differ), so the proof cannot silently rot into a
  tautology. Re-capture procedure is in that file's docstring.
- **Defect B fixture deck, before/after:** the flood source headlines **21 of 36** cards
  across three counterparties uncapped; **2** with `deck_headliner_cap=2`. The fixture
  floods ACROSS opponents on purpose — a per-opponent cap of 2 would still have served six.
- **Three existing tests moved and one guard was added as a result of the wave, all
  understood:** `test_fairness_gate_golden.py::test_v2_v3_fairness_score_parity` exposed
  that C1's ties let a padded sibling evict the bare deal (fixed by the tie-break, no test
  edit); `test_outlook_direction.py` (6 tests) exposed that an EMPTY job seed map makes
  "centerpiece" degenerate to "largest player id" (fixed by disabling the cap with no seed
  map, no test edit); `test_asset_ideas.py::test_receive_direction_mirrors_grouping`
  exposed that an absolute-gap C2 band mis-ranks a 0.572-fairness bare deal above its
  0.697 sibling (fixed by re-basing the band on fairness, no test edit). **No existing
  test was weakened to make this wave pass.**
- **Sim gate: Tier 4 (none, CI only)** per the operator's build brief — backend-only diff,
  zero files under `mobile/`. `qa/sim-runs/last-sim-run.json` not written; nothing to run.
- **Not covered by any test here:** the live-corpus effect. The five defaults are reasoned
  from fixtures, not fitted to the 563-impression corpus — each knob is the named tuning
  lever and a re-run of the corpus query is the measurement.

## 2026-08-18 — Dismiss cooldown (D-067) shipped

- **pytest 3125 passed / 1 skipped / 0 failed** on the merged tree (`505ca2c`), run pre-push.
- **15 tests** in `backend/tests/test_pass_cooldown.py`; **8 named sabotages** applied → RED → reverted: `shrink-window`, `unbounded-window`, `one-window`, `fail-open`, `db-only`, `alias-only`, `ignore-amnesty`, `amnesty-everything`, `amnesty-likes`. `alias-only` REDs **only** the format-switch test — that test earns its place catching the alias trap rather than duplicating its neighbour.
- Two-sided bars included by design: the cooldown must **expire** (a 20-day dismiss returns) and the amnesty must be a **boundary** (a post-cutoff dismiss still suppresses).
- **Sim gate: n/a per D-057** (Maestro/simulator retired). No TestFlight build cut — backend-only change; mobile identical to v1.14.0 build 116.
- Deploy verified **by content** (`pass_cooldown_days` present in prod `/api/admin/config`), not by uptime.


## 2026-08-17 — Decline reason capture SHIPPED + v1.14.0 build 116 to TestFlight

**Code.** Two squash merges: backend `feat/decline-reasons-backend` @ `5056d1e`, mobile
`feat/decline-reasons-mobile` @ `4d57aae` (main `b97744c..8082aa2`), plus the gen-v2 G6 knob
reconciliation `92d2358`. Flag `feedback.decline_reasons` ships **true for all users**.

- **Merged-state backend suite: 3110 passed / 1 skipped / 0 failed** (254s), incl. 58 new tests in
  `test_decline_reasons.py` — gate + kill-switch byte-identity, progressive-write idempotency,
  impression_id fallback matrix, the mobile payload verbatim, the per-code Elo matrix with the knob
  on AND off, analytics props.
- **Mobile:** `tsc --noEmit` **clean** and `testid-lint OK` on a worktree at `main` after `npm ci`
  from main's lockfile. 38/38 mobile check suites green on the branch tip; merged mobile files were
  verified byte-identical to that tip, so the result carries.
- **Correction to an earlier claim:** the `ImportRankingsSheet.tsx` → `expo-document-picker` TS error
  previously recorded as "pre-existing on origin/main" is **not a real defect** — it is an artifact of
  a stale shared `node_modules`. A correct install yields zero TS errors.

**SIM GATE: WAIVED by operator, 2026-08-17.** Tier-1-class mobile screen change; operator waived the
requirement and accepted "green on touched flows + documented notes on the rest". The two Maestro
flows (`decline-reasons-fixed-option.yaml`, `decline-reasons-other-free-text.yaml`) were **authored
but never executed** — they were blocked on the all-on flag fixture, which this merge supplies, so
they are runnable from now on with no passing run behind them. Pushed with `FTF_SKIP_SIM_GATE=1`.
**TestFlight is the only runtime evidence this feature has.** Not covered by any executed test: the
on-device keyboard/send-button interaction, and the real device → route write path.

**Release.** EAS build `d57f593e` = **v1.14.0 build 116**, production profile, built from a clean
worktree at `main` @ `67b54f6`; status `finished`; `eas submit` uploaded to App Store Connect
(submission `e834b0bf`) during an active EAS Submit partial outage — build and submit were
deliberately decoupled for that reason.

- **Build-source trap caught (worth remembering).** The first attempt, build `e26e0fc6`/115, was
  **cancelled**: `eas build` archives the *local working directory*, and this repo's main checkout sits
  on `session-2026-08-13-notif-ship`, **141 commits behind main**. That archive contained neither
  `DeclineReasonPanel.tsx` nor `declineReasons.ts` and carried version 1.13.2 — it would have shipped
  the feature-less old app to TestFlight labelled as a downgrade. Always build from a checkout you have
  confirmed contains the feature files.
- **Prod flags verified live** post-deploy via `GET /api/feature-flags`: `feedback.decline_reasons: true`,
  `trade_gen.v2: false`, `trade.presentment_rules: true`.

---

## 2026-08-17 — 2026-08-16 feedback wave shipped (17 items, v1.13.5 build 114)

- **Merged-tree gates (orchestrator-run, integration branch):** pytest **3050 passed / 1 skipped / 0 failed**; `tsc --noEmit` clean; **48/48** `check-*.js` structural suites; `testid-lint.sh` OK.
- **Sabotage discipline:** every new behavioral test across all 7 groups proven RED on its named sabotage then green on revert (G6 14/14, G5 13/13, G3 8 sabotage classes, G2 T-P1..T-S10, G4 U-1..U-4 + BT-1, G9 U-1..U-5 + S-10a..e, G1 backend 4 + mobile 7). Phase-4 added 5 more; two of them (F-5 consensus `_emit`, F-7 hide-sites) REDded **only** the new test while the pre-existing suite stayed green — the coverage gaps were real.
- **Cross-group tripwire:** G4's `test_offer_hard_lock_330.py` (BT-1) green against G6's rewritten engine on the merged tree — the single-pin hard lock survived the presentment rewrite.
- **Sim gate: NOT run — n/a per D-056** (Maestro/simulator retired). Runtime evidence for this wave is the per-group operator TestFlight checklists on **build 114**, still owed.
- **Deploy verified by content:** `trade.presentment_rules = True` in prod `/api/feature-flags` (170 flags). Render auto-deploy did NOT fire; deploy triggered explicitly (see `docs/recovery/2026-08-16-feedback-wave-sweep.md`).
- **Owed:** operator prod-DB deck-eval replay (G6 bands on divergence boards + real like history); #339 `pick_gap_frac` tuning (no pick-carrying candidates in any corpus); TestFlight checklists; first-week `presentment-tripwire` watch.



## 2026-08-13 — Notification inbox growth surface phase 1 (SHIPPED to `main`)

- **Change:** five commits, rebased onto `3b64a44` and merged to `main` on the operator's ship directive (which also resolved the `counter_offer` four-not-five question and ratified the two adjacent dead-tap fixes). Taxonomy registration → backend inbox rows + coalescing + server-side dismiss → both clients (glyphs, routing, instrumentation, empty state) → docs. `express`-equivalent gate posture: **sim gate SKIPPED, `FTF_SKIP_SIM_GATE=1`**, per D-P1-08 restated in the build brief.
- **Backend:** `pytest backend/tests -q` → **2685 passed / 6 failed / 1 skipped**. The 6 failures are all in `test_rookie_scope.py`, are **pre-existing on `origin/main`** (verified by `git stash`-ing every change and re-running that file alone, which failed identically), and are **local-only**: CI runs Python 3.12 and is green on `main` (`gh run list --workflow ci.yml`); local is 3.14. **Not caused by this work, and not fixed by it.**
- **New:** `backend/tests/test_notif_inbox_growth.py` — 13 tests over the three things whose failure mode is silent: GD-8 coalescing (one row per league per UTC day, incl. the yesterday boundary and the dismissed-row-is-not-a-target case), the `match_expiring` idempotency gate (incl. cross-type metadata comparison and the fail-closed path), and server-side dismissal (retention, per-user scoping, and that clearing is point-in-time rather than a mute).
- **Mobile:** `npx tsc --noEmit` exit 0; `bash scripts/testid-lint.sh` OK; `node tests/check-notif-glyphs.js` **5/5**.
- **`check-notif-glyphs.js` earned its keep on its first run.** It failed immediately on `trade_accepted` / `trade_declined` — the DB writes `f"trade_{outcome}"` while only the push kind `match_accepted` was in `V2_MATCH_KINDS`, so two of the four ORIGINAL inbox types had a glyph and a dead tap. Code review had not caught it; the test did, before any of this shipped.
- **Web:** `node --check web/js/app.js` clean. **No web test harness exists**, so web's glyph map, tap router and the new `dismiss-all` call are covered only by the parity test's source-text assertions. The `switchView('matches')` fix and the dismiss round-trip have **never executed in a browser**.
- **NOT verified anywhere:** every row template, the new empty state, the empty-state invite gate, and all three analytics emitters. Nothing has rendered on a simulator or a device. The four backend write sites have not fired against a real DB — their tests exercise the DB helpers directly, not the routes.
- **Simulator gate + Maestro: WAIVED** under **D-P1-08**, restated by the operator in the build brief. No `qa/sim-runs/last-sim-run.json` written — **not fabricated**.
- **Standing caveat, unchanged and now one suite worse:** no `check-*.js` suite runs in CI (`.github/workflows/ci.yml` runs pytest, `tsc`, and testid-lint only). `check-notif-glyphs.js` therefore **gates nothing**, on a cross-client enum whose whole failure mode is silence.

---

## 2026-08-12 — Feedback #300 (position-scoped trade candidates), shipped LIT with gates waived

- **Change:** `5139b45` (PR #112), v1.13.1 **build 106**, both flags **ON**. Backend `medians` field on `/api/league/power-rankings`; mobile divider + Buyer/Seller bands + stacked-roster drill-in + Offer/Target handoff; rules A and B removed ([D-044](DECISIONS.md)); two analytics events.
- **Verified on the merged tree, re-run by the orchestrator rather than taken from agent reports:** `pytest backend/tests -q` **2610 passed / 1 skipped**; `tsc --noEmit` exit 0; `testid-lint OK`; `check-league-drill-in` 29; `check-analytics-297-302` 35; `check-single-pin-actions` 17; `check-league-candidates-300` 67; `check-picks-subset-invariance` 72; `check-analytics-300` 51. **271 structural assertions.**
- **Falsification:** 40 + 12 + 42 sabotages executed across the three build rounds. **One genuine false pass found and fixed** (S21: dropping `if (!query.isFetched) return` left the suite green because the assertion matched an identifier that also appears in the dep array). That is the **fifth** false-passing test caught in this session across five independently authored suites.
- **Simulator gate: WAIVED by operator. Maestro execution: WAIVED by operator.** `06-position-trade-candidates.yaml` is authored and **has never run**. No `last-sim-run.json` written — not fabricated. **The 44pt hit-slop treatment, the divider and the rule-A removal have never executed on a device or simulator.** The operator confirmed the shipped build behaves in TestFlight, which is the only runtime evidence in existence for this feature.
- **Analytics verified in production.** Deploy-then-probe run post-merge: 4 events posted, `{"accepted":4,"dropped":0,"rejected":[]}`, then every property read back out of `user_events.props` — both `league_pos_candidates_viewed` rows and both `league_candidate_pinned` mirror combinations `(offer, below)` / `(target, above)`. Note the trap this gate exists for: without `X-Device-Id` the response is `{"accepted":0,"dropped":0,"rejected":[{"reason":"no_identity"}]}`, which has `dropped == 0` and reads as a pass.
- **Still true and worth repeating:** none of the six `check-*.js` suites run in CI. They are `npm run`-only, so **none of the 271 assertions gate anything**.

---

## 2026-08-12 — P1 audit remediation shipped (sim gate retired by operator, not waived)

- **`express`: P1 remediation shipped — simulator gate SKIPPED, `FTF_SKIP_SIM_GATE=1`.** Not a
  one-off waiver: operator decision **D-P1-08** retires the Maestro/simulator/screenshot
  apparatus as standing policy — it consumed more budget than it returned and its quality
  degraded as the surface grew. **TestFlight is now the primary QA method.** No
  `qa/sim-runs/last-sim-run.json` written — **not fabricated**. The pre-push hook fired and was
  overridden deliberately, with the operator's explicit go. `CLAUDE.md`, `githooks/pre-push` and
  `docs/runbook.md` still describe the old policy and are **owed an update** (D-P1-08).
- **Verified instead:** full backend suite **2663 passed / 1 skipped** (3m51s) on the rebased
  tree; `npx tsc --noEmit` clean against a fresh in-worktree `npm ci`; `testid-lint` exit 0;
  `check-anchor-labels.js` 20/20; `check-invite-social-proof.js` 13/13. Baselines measured on
  this tree before editing, never quoted from another branch: 2467 → 2504 (P1-7) → 2663 (after
  rebase onto `main` plus the two pre-ship fixes).
- **NOT verified on device.** Five changed anchor rung labels, the anchor progress hint, both new
  invite surfaces and the share-image footer are visual and have never rendered on a simulator or
  a phone. This is the accepted cost of D-P1-08 and is owed on the TestFlight pass.
- **Sabotage-proven guards.** The anchor-label AST walker **false-passed on its first cut** — it
  inspected only the root of each initializer, so `key === '1_second' ? '1 2nd' : anchorLabel(key)`
  slipped through; fixed to walk the whole subtree, all five mutations now fail as intended. The
  tier-route 404 was proven to come from the flag guard rather than a missing route (body shape +
  `url_map` membership). The `league_id` scrub exemption was proven narrow three ways: an email
  under the same key is still redacted, a long digit run under any other key is still redacted,
  and the allowlist is exact-key rather than substring.
- **Analytics NOT yet proven end-to-end.** T1 registration ships in this push, but the corrected
  probe (**HLD §H-6**: `X-Device-Id`, valid envelope, `accepted > 0` **and** `dropped == 0`, then
  a read-back of `user_events.props`) runs against production **after** the Render deploy. Until
  it passes, treat every new event as unproven — the endpoint returns 200 while dropping. The
  original probe spec in this round would have passed against a broken build; that is why it was
  corrected before use.
- **Not shipped, deliberately:** email capture (built, then **reverted in full** — flag, policy,
  docs and living-memory — by operator decision: the sequencing was backwards and no
  email-sending infrastructure exists to consume it), P1-9 trade push and P1-10 Sleeper analytics
  (both still hold unanswered build-blocking decisions), P1-11 (dropped, D-P1-01).

---

## 2026-08-12 — Send in MFL + Send in ESPN shipped live (sim gate WAIVED all session, CI never ran)

- **`express`: Send in MFL + Send in ESPN + platform unlink + ESPN credential verification shipped — gates skipped by operator.** `FTF_SKIP_SIM_GATE=1` on every push (warning emitted each time); **no `qa/sim-runs/last-sim-run.json` written — not fabricated**. CI never ran: the operator directed direct-to-`main` pushes rather than PRs. `main` moved `3293f4a` → `cad99fb`.
- **Verified instead of CI**, per push: targeted backend suites (178 → 135 → 123 → 122 depending on surface), 12→18 `mobile/tests/check-*.js` including main's own P0-6/P0-7 pins, `testid-lint` exit 0, `tsc --noEmit` clean on a fresh in-worktree `npm ci`. The full ~2,400-test suite was **deliberately not run** — it stalled four separate agents mid-session.
- **Sabotage-proven guards** (each failed first, then restored): MFL pick hard-block (guard removed ⇒ the mocked write was reached with the pick silently dropped); ESPN pick + unmapped-asset hard-blocks; **cross-user unlink isolation** (removing the `WHERE user_id` clause made another user's row deletable — the security property that mattered most).
- **TestFlight 1.13.0 builds 102/103/104/105, then 1.13.1 build 107.** Every status read from `eas-cli build:list --json`, never the exit code — **`eas build` exits 0 even when the remote build ERRORED** (a concurrent session lost builds 99/100 that way). Build 106 was another session's. **Build-ordering lesson: flags are server-side, so `espn.send` could not be enabled until a build containing the lazy send-triggered auth existed (103) — enabling a flag whose client code is absent from the installed build *degrades* it.**
- **Live production verification, by content not by uptime:** `/api/feature-flags` serves `trade.send_in_mfl: true` and `espn.send: true` (neither key existed before); `DELETE /api/espn/link` and `DELETE /api/mfl/auth-link` both return 401 unauthenticated (route live and auth-gated, not 405).
- **MFL write path LIVE-VERIFIED** — a real 2-for-2 proposal succeeded from the app (`trade_sent {platform:"mfl", outcome:"proposed"}`). Because the adapter **refuses ambiguous success**, that outcome is positive evidence the real import response parsed unambiguously. `pendingTrades` also read live: field vocabulary confirmed, `FP_0002_2028_2` confirms the pick encoder against a real trade.
- **ESPN write validated without spending a real trade** — negative probes with a nonexistent `relatedTransactionId` returned 409 `TRAN_NOT_FOUND` for both `TRADE_ACCEPT` and `TRADE_DECLINE`, and `items:[]` returned 409 `TRAN_INVALID_TRADE_TEAM_COUNT` for propose. Both are validation-class errors only reachable *after* auth, so auth + envelope + `type` are all confirmed while nothing real was touched. **No real ESPN send has been made from the app — that remains owed.**
- **Sleeper iOS reachability probe: PASS 4/4** (Chrome-spoofed and honest headers × Wi-Fi and cellular, all HTTP 200), run from TestFlight build 107 and reported via `sleeper_probe_result` analytics rather than transcription. Probe shipped, run, and **deleted the same day**; result in `../docs/plans/sleeper-ios-reachability-probe-result-2026-08-12.md`.
- **Analytics correctness checked, not assumed:** `trade_sent`'s NULL top-level `platform` column initially looked like a repeat of the NULL-`platform` incident. It is not — that column is the *emitter* (`ios`/`server`), the fantasy platform lives in `props.platform`, and `sleeper_send_succeeded` behaves identically. New event names were added to `NON_INTENT_EVENTS` in the same commit that registered them.
- **Flag-mirror trap fired twice.** Any new key in `config/features.json` must be mirrored into `release.json`, `onboarding-v2.json`, and `profiles-on.json` or `test_seed_ui_test_db.py` fails (69 tests). Caught both times before push.
## 2026-08-11 — P1-7 anchor + manual unlock, derived rung labels (NOT merged, branch-only)

- **Change:** branch `p1-remediation-2026-08-11`, three commits. (1) Per-method unlock ladder — `'anchor'` gains its first arm (audit A-16: it could never unlock), `'manual'` loses its unconditional `True` (A-17), both reading `RankingService.board_override_count()`; `_tiers_rule()` extracted; `database.backfill_anchor_unlocked_formats` added as the first-unlock fan-out suppression; additive `anchor_count`/`anchor_required` on `GET /api/rankings/progress`. (2) Anchor rung labels derived from `TIER_LABEL` (five of eight had drifted, not the two the audit found) + `mobile/tests/check-anchor-labels.js` + the wizard's unlock hint + `anchors.rung.*` testIDs. (3) The `anchors-done` seed profile and its `app_user.anchors` seeder handler.
- **Verified (this worktree, re-run after every commit):** `pytest backend/tests -q` **2504 passed / 1 skipped**, against a **2467 / 1 baseline measured on this same tree before the first edit**. The +37 is fully accounted for and contains no pre-existing failures: `test_anchor_unlock.py` **29 new** (one case parametrized ×2), `test_pick_anchor.py` 17 → **18** (the D15 lane-separation assertion), `test_seed_ui_test_db.py` 69 → **76**. `npx tsc --noEmit` exit 0, no output; `testid-lint.sh` → `testid-lint OK`; `check-anchor-labels.js` **20/20**.
- **Falsification — and it earned its keep.** Every assertion in `check-anchor-labels.js` was run against a deliberately sabotaged tree. **The first cut false-passed on the single most important mutation:** re-typing a label as `label: key === '1_second' ? '1 2nd' : anchorLabel(key)` — the original defect wearing a ternary — because the assertion inspected only the *root* of each `label` initializer. This is exactly the case the design cited as the reason an AST walk beats a grep, and the AST walk fell into it anyway. Fixed to search the whole initializer subtree and to whitelist two exact initializer shapes; all five mutations (ternary, template literal, indirection through another function, `no_value → 'waivers'`, inlined `BELOW_LADDER_LABEL`, dropped `ANCHOR_TIER` key) now fail as intended. Same family as [G-035](GOTCHAS.md).
- **The seed fixture proves the unlock rather than assuming it.** `anchors-done.json` seeds `unlocked: false` deliberately — a seeded `unlocked_formats` row satisfies the monotonic floor *before* the new branch is consulted, so the obvious fixture would have gone green with the fix reverted ([G-037](GOTCHAS.md)). `_validate_anchors` now **refuses** the incoherent shape, and `test_anchors_done_actually_clears_the_unlock_bar` builds a real `RankingService` from the seeded board and asserts it clears the bar — so the fixture and the branch are proven to meet, not assumed to.
- **Sim run: none.** Per [D-P1-08](../docs/plans/audit-p1-remediation/DECISIONS-p1.md) the Maestro/simulator apparatus is retired and TestFlight is primary QA. No `last-sim-run.json` written — **not fabricated**.
- **Not verified on device, and it should be:** the wizard's new unlock hint (`anchors.unlock-hint`) and the five changed rung labels are visual changes no automated gate here can see. `check-anchor-labels.js` proves the labels are *derived*; it cannot prove they *render*. **Owed on the next TestFlight pass.**
- **Same pre-existing gap as the batch below:** none of the `mobile/tests/check-*.js` scripts run in `.github/workflows/ci.yml`, so `check-anchor-labels.js` **gates nothing** until that job is wired. It is a `npm run test:anchor-labels` a human has to remember.

## 2026-08-11 — Feedback #297/#298/#299/#302 + batch analytics (sim gate DEFERRED, operator-directed)

- **Change:** branch `feedback-integration-v2`, cut from `origin/main` @ `f65bab7`, merging `feedback-build-league-299-302` and `feedback-build-trades-297-298` plus an analytics round. #297 honest-empty lineup row; #298 single-pin deck recovery (V1) + the team-pill regenerate defect; #299 32pt League roster tiles (−47%, 728pt reclaimed on a 26-man roster, 4 → 8 players above the fold); #302 stack-header drill-in exit + the first Android `BackHandler` on that screen. Analytics: two new client events (`lineup_impact_unavailable`, `league_team_closed`), three widened props (`mode` on `find_trades_tapped` + `trade_card_viewed`, `source` on `find_trades_tapped` — the last a **bug fix**, that prop had been sent into an empty registry and popped on every row since #257).
- **Verified (merged tree, this worktree, re-run by the orchestrator — not taken from agent reports):** `pytest backend/tests -q` **2452 passed / 1 skipped**; `npx tsc --noEmit` exit 0, no output; `testid-lint.sh` → `testid-lint OK`; `check-single-pin-actions.js` **17/17**; `check-league-drill-in.js` **29/29**; `check-analytics-297-302.js` **35/35**. 81 structural assertions total.
- **Falsification:** every behavioural assertion was run against a deliberately sabotaged tree — 30 (league) + 9 (trades, four aimed at the seam #169 created) + 20 (analytics). **Four false-passing tests were caught this way and fixed**, in four independently authored suites: an ancestor-walking JSX gate check ([G-035](GOTCHAS.md)); a first-element-only testID lookup; a platform assertion that survived a sabotage leaving the lookup line in place; and three raw-source scans matched by comments naming the constructs they forbade. Treat "my test passes" as unproven here until a sabotage fails it.
- **Sim run: DEFERRED by operator** ("Good to signoff that we ship without a flag & defer the sim gate"), after the bright-line disclosure that the batch touches analytics surfaces. **No `last-sim-run.json` written — not fabricated.** Two Maestro flows authored but **NOT executed**: `mobile/.maestro/flows/league/05-drill-in-back-affordance.yaml` and `mobile/.maestro/flows/smoke/12-trades-single-pin.yaml`.
- **The Android hardware `BackHandler` was WITHDRAWN from this ship, not verified** (operator, 2026-08-11) — precisely because no Android device or emulator was involved at any point and TestFlight is iOS-only. Removing it is what closes the batch's largest unverified-code gap. Two assertions now pin the withdrawal (a live registration turns both suites red), and both were **sabotage-proven** by re-adding the effect and confirming each suite fails. `'hardware_back'` remains a reserved analytics value with no emitter. **Owed with the first non-App-Store release:** restore the effect, flip both assertions in the same commit, and exercise it on a real Android device.
- **Owed at ship, not skippable by the sim-gate deferral — the deploy-then-probe gate.** After merge + Render deploy, hand-roll one `POST /api/events` per new name with its **full** property set and assert both `dropped == 0` **and** every property echoed back out of `user_events.props`. Name-survival and prop-survival are separate silent failures: `analytics_ingest.py` pops unregistered props with only a counter bump, and `trade_card_shared.landing` is a live in-tree example of a registered name whose prop is discarded. **Do not substitute `GET /api/admin/analytics/health`** — its counters are in-process and reset on deploy.
- **Pre-existing gap, now three times larger:** none of the ten `mobile/tests/check-*.js` scripts run in `.github/workflows/ci.yml`; they are `npm run`-only. **None of the 81 assertions above gate anything** until that is wired. Proposed job in `docs/feedback/items/297-lineup-impact-single-pin/status.md` §5.5.

## 2026-08-11 — P0 remediation batch (sim gate SKIPPED, operator-directed express)

- **Change:** branch `p0-remediation-2026-08-10` — eight P0 launch blockers from the 2026-08-09 mobile UX audit (P0-1/2/3/5/6/7/8 + P0-9 test-prep), 15 code commits + merge of #169. Full corpus in `docs/plans/audit-p0-remediation/`.
- **Verified (merged tree, this worktree):** `pytest backend/tests -q` **2448 passed / 1 skipped / 0 failed** (clean worktree — the 6 environmental `test_rookie_scope` failures of the data-carrying main checkout do not reproduce here, consistent with G-030[#169]); `npx tsc --noEmit` clean; `testid-lint.sh` OK; `check-trade-text.js` 28/28; `check-card-disposition.js` 10/10; taxonomy registration verified name-by-name (16 client + 1 server, zero unregistered emissions — grep table in the W2-P07 build record).
- **Sim run: tier-1 SKIPPED entirely** (operator: "proceed without the sim gate — eating up too much usage", confirmed after bright-line disclosure: batch touches route + flag + analytics surfaces). Push via `FTF_SKIP_SIM_GATE=1`; **no `last-sim-run.json` written (not fabricated)**. Pre-skip on-sim work: app built green (Release, localhost-pinned), dedicated simulator created, pre-flight of all six new flows (every copy string + testID resolves in source), control-run evidence prepared (`git grep` at ab9368f proves the new testIDs absent pre-fix, so the flows fail by construction on the unfixed tree). Runs were blocked twice by another session holding :7001/:5001 before the operator called the skip.
- **Tier decision (recorded for the record): tier 1**, not 2 — the batch adds a screen, changes navigation, and changes rendered state on six screens; tier 2 is "mobile logic, no UI change".
- **Owed at next sim session:** the full tier-1 set + the batch's six new flows (`p0-1-quickset-unlock`, `p0-5-account-only-picker`, `p0-6-espn-copy-trade`, `trades-generation-failure`, `guide-no-false-signoff@release`, `league/invite-join`) + modified captures (`trades`, `matches@espn`, `league@quickset-done`, `leagues@account-only`, `onboarding-tour@fresh`); the P0-9 flag-pinned beat validation incl. the s5.1 proof (use the now-registered `deck_regenerated` row); analytics destination checks; re-captures + freshness sweep (note: TabNav changes are analytics-only — PNGs stay visually accurate, hash-staleness flags under the corrected manifest are false positives).
- **Toolchain gotcha (load-bearing for every future worktree build):** the standing convention of symlinking `mobile/node_modules` from the main checkout makes the app UNBUILDABLE — expo's CLI branches on whether its own directory resolves inside the project root and then requires `metro-runtime`, which is not top-level in this lockfile. Real in-worktree `npm ci` + `pod install` required; `rm -rf mobile/ios/build` also deletes RN codegen sources, so re-run `pod install` before rebuilding.

## 2026-08-11 — #169 frame E + card frame C (sim gate DEVIATION mid-run, operator-directed)

- **Change:** branch `feedback-169-e-and-card` — League Summary collapsed outlook strip (flag-dark, `outlook.odds`) + Pass/Like moved inside the top deck card + `outlook_strip_toggled` analytics event (taxonomy + tracking plan; operator rejected the dark-flag analytics waiver). Doc set (plan/HLD/LLD/PRD/scope rev 2, adversarially reviewed, 21 findings applied) in `docs/feedback/items/169-outlook-league-summary/`.
- **Verified (merged tree):** `npx tsc --noEmit` clean; `testid-lint.sh` OK; `check-card-disposition.js` 10/10 **with double sabotage proof** (guard flip → FAIL; reintroduced TradesScreen testID → FAIL; restored → pass); taxonomy test 18/18 **with sabotage proof** (event removed from allowlist → FAIL → restored). Full `pytest backend/tests -q`: **2371 passed / 6 failed / 1 skipped** — all 6 in `test_rookie_scope.py`, **proven pre-existing and environmental** (fail with origin/main-identical backend bytes in the data-carrying main checkout; 34/34 pass in a clean worktree of the same commit; G-028, fix chip filed). CI on the PR is the clean-environment authority.
- **Sim run: Tier-1 HALTED mid-gate by operator** ("proceed without sim testing — eating up too much usage"); push via `FTF_SKIP_SIM_GATE=1`; no `last-sim-run.json` written (not fabricated). **Partial on-sim evidence before the halt:** extended `06-trades-deck` positional `childOf` asserts PASSED (both disposition buttons proven inside `trades.card-top`, no scroll — fails by construction on the old layout); screenshot proof of the operator's layout; `01-signin` full pass in the final harness config; manual launch-health check. Suite-level failures across 4 attempts were ALL environmental, diagnosed in sequence: `# flags: release` fixture not loaded (guided-avatar tour overlay swallowed taps), backend process reaped by shell teardown, **disk exhaustion to 0 bytes** (25 launch crash-loops in Hermes init — G-027 adjacent; ~4 GB freed), stale Maestro XCTest driver after `simctl erase`. None traced to the change under test.
- **Owed at next sim session:** green full-suite run; post-overlay like/pass tap-through of `06-trades-deck`; the four re-captures (`trades`, `matches`, `sheets-trade-dna`, `league-summary`) + `screen-freshness.sh` sweep; on-sim verification of the three re-derived `onboarding-tour@fresh` anchors.

## 2026-08-10 — Screen-library capture suite (sim gate tier-2 evidence)

- Full consolidated sweep on FTF-iOS18 (iOS 18.4): 43 capture flows, 7 cells
  (5 profiles × release/onboarding-v2), **102 captures, rails all zero in every
  cell** (vcr_misses / sleeper_live_egress_attempts / completed_proposes /
  propose_route_hits). One flaky flow (trios@near-unlock, tab-race — settle fix
  applied, still ~50% per run) recaptured green individually. tsc clean,
  testid-lint green, screen-freshness green ×25, backend suite 2207 passed
  (fixtures commit). Mobile app-code delta this branch: testRouteEntry.ts +
  one RootNav line — exercised by every launch-arg capture cell above.
## 2026-08-10 — Feedback batch #289-#294 (sim gate DEVIATION, operator-directed bypass)

- **SHIPPED 2026-08-10.** Squash-merged as `6c304c7` via PR #103; CI green (backend-tests, mobile-typecheck, maestro-testid-lint). Render deploy **verified by content**, not by uptime: `/api/feature-flags` serves `league.picks_always_counted = true` (155 flags), which only the new build can produce. iOS **1.12.0 build 98** uploaded to App Store Connect (submission `0095a36f`).
- **Version-bump trap, cost one wasted build.** `mobile/app.json` was bumped to 1.12.0 and **build 97 still shipped as 1.11.0**. This is a bare workflow — `mobile/ios/` is tracked — so EAS reads the version from the native Xcode project and ignores the Expo config. `eas build:version:set` manages the **build number** only. The three values that actually ship are two `MARKETING_VERSION` entries in `project.pbxproj` and the literal `CFBundleShortVersionString` in `Info.plist` (PR #104, `7553874`). Bumping `app.json` is necessary for the JS layer and **not sufficient for the binary**.

- **Change:** six feedback items in three groups on branch `feedback-289-294` (base `origin/main` @ `16b1dcb`), 16 commits, 51 files, +15,738/−106. **G1 #289** MFL Draft Room resolves franchise *and* player names (four ordered tiers, never a bare id). **G2 #290/#291/#292** value-aware mock run model + `need_pressure` + mock lifecycle (`abandon_completed_mock_drafts`) + pick affordance before tap + MFL owner names in the mock. **G3 #293/#294** draft-pick value counted in every subset and position filter, behind new flag `league.picks_always_counted`, **graduated to ON at ship by operator direction** ("293/294 ship live") together with its `LAUNCHED_FLAG_DEFAULTS` entry so it is visible from first paint; the flag remains the kill switch. Plus: `mobile/scripts/sim-run.sh` flag-pin repairs, five stale "mock is OFF" doc locations corrected, D-022/D-023/D-024.
- **Suite:** baseline `2308 passed / 1 skipped` after G1+G3 → **2326 passed / 1 skipped**, exit 0 (+18, all new). `npx tsc --noEmit` **exit 0** (real `npm ci` in-worktree — the main checkout's `node_modules` is ~190 commits stale and lacks `@react-native-cookies/cookies`, which yields a phantom error). `testid-lint.sh` **exit 0**. **All nine** `mobile/tests/check-*.js` pass, including two new ones (`check-picks-subset-invariance.js` 71 assertions, `check-mock-lifecycle.js` 52).
- **Sim run: NOT PERFORMED** — operator-directed bypass (`FTF_SKIP_SIM_GATE=1`) after being presented with the coverage gap and choosing it explicitly. **This is a Tier-1 deviation and the batch's largest change is the least covered:** G2's mock engine ships with unit + distributional evidence only and **no end-to-end run**. **Both groups ship live.** G3 was built dark and graduated to ON at ship on operator direction; it keeps a per-feature kill switch (`league.picks_always_counted` -> false, no redeploy). G2 has no per-change switch — `draft.mock` was already ON and the engine change is unflagged — so its only lever turns off the whole mock feature. G2 is therefore the largest change, the least covered, AND the least reversible.
- **Why the mock flow could not run:** `d3-mock-draft-loop.yaml` was authored but is unrunnable — `backend/tests/fixtures/profiles/standard.json` declares one league (`990000000000000001`) while d1/d2/d3 all target `1312140920132497408`, which is in no profile, and the seeder writes **nothing** for `mock_drafts` or draft status. The build agent's "one `leagues[]` entry" estimate was checked and does not hold; this is real seeder work. Pre-existing, unfixed, named.
- **Uncovered by any automated test** (do not read a green suite as covering these): G3 **R-5** and **R-0.4**, and the kill-switch drill **T-S6c** (manual). G1 has **no Maestro flow at all** by design — its acceptance surface is a live check against the operator's Dependables MFL league (62846), also not yet performed.
- **Harness findings — the gate had never actually run.** Every prior ledger entry since the gate's introduction reads "NOT PERFORMED", which is why three defects survived: `--flags` *replaced* the seeded flag map instead of merging; `--flags @file` was documented but unimplemented (the literal string was exported, JSON parsing failed with a stdout warning only, and the run continued with flags OFF); and the handshake fetched `/api/feature-flags` but **only archived it, never asserting** — so a flag-ON tier could assert flag-OFF behavior and exit 0. Additionally `$!` captured the subshell rather than python under bash 3.2 (macOS system bash), so the stale-Flask assertion fired on a clear port **every time** and the EXIT trap orphaned Flask on the port for the next run to talk to. All repaired and each proven by constructing the failure first; nine consecutive runs left no orphan.
- **Failing-first evidence captured** for every behavioral test (G2 T-290-04/10/11/14, T-292-01, D-16 keying; G1 T-289-06; G3 assertions 13/14). Three separate lanes found tests that **passed on the very defect they named** — G1's collision test (its stub raised on the triggering input), G2's one-sided distributional bars (a fully collapsed `sf_tep` board scored *higher* variety than a healthy one), and G3's atomicity assertions (`picksAlwaysCounted={false}` satisfied all twelve). G2's mobile agent also found two of its own first-cut assertions passing on their defects — one because the JSX comment explaining the behavior contained the string it was grepping for.
- **G2 measured results at pinned N=1500, both formats** (`1qb_ppr` / `sf_tep`): P(#1 at 1.01) 0.4553 / 0.6380; P(#1 past pick 3) 0.0893 / 0.0420 (shipped 0.1553); P(#7 at pick ≤4) 0.0000 / 0.0000 (shipped 0.1147); median run size 5.0 / 5.0. Calibration tripwire `test_w2_16` **did not fire**.
- **Fixed in passing:** two G2 tests used fixed user+league ids against the persistent SQLite DB and accumulated rows across runs (second full run reported `cleared 5 rows, expected 3`) — would have surfaced in QA as an unreproducible failure on any machine that had run the suite before. Both now self-clear.

## 2026-08-10 — Outlook: seed-type + IDP-coverage wiring, combined post-fix calibration (NOT merged, no flag change)

- **Change:** two wiring gaps closed, then one combined re-measurement. (1) `scripts/outlook_calibration_backtest.py` gains `seed_type(fx)` and threads `playoff_seed_type` into every `run_outlook` / `get_playoff_format` call, plus a **BUG-3 A/B block** mirroring the existing BUG-1 one; same wiring in `scripts/outlook_preseason_backtest.py`. (2) `pipeline.run_outlook` now calls `strength.lineup_pricing()` and `serialize.py` emits `meta.priced_slot_coverage = {fraction, total_slots, priced_slots, unpriced_slots[], affects_strength}`. `outlook.odds` untouched, `config/features.json` untouched, no `model_config` key, mobile diff is a **type-only** addition (`OutlookPricedSlotCoverage` in `mobile/src/api/league.ts`) with no UI/behaviour change.
- **Suite:** baseline on a fresh `origin/main` reset (`234a018`) **2284 passed / 1 skipped / 0 xfailed** (301 s) → **2297 passed / 1 skipped**, exit 0 (+13). `npx tsc --noEmit` clean (node_modules symlinked from a sibling worktree, removed after). New coverage: 4 payload/coverage tests in `test_outlook_odds.py` (fraction + named unpriced slots, full-coverage league, `affects_strength` false on `trailing_scores`, **prediction-neutrality vs a run serialized without the instrument**), 9 in `test_outlook_playoff_seed_type.py` (an **AST guard** that fails if any `run_outlook`/`get_playoff_format` call in either script omits the setting, the per-fixture seed-type helper, and a load-bearing check that fixed vs reseed brackets give different title distributions and identical playoff odds), plus the `meta` contract pin in `test_outlook_route_cache.py`.
- **Sim run: NOT PERFORMED** — measurement + dark-surface wiring with zero user-visible change (`outlook.odds` false everywhere, mobile diff is a type declaration); branch left unmerged for operator review.
- **Result — in-season, 6 league-seasons / 288 team-week predictions, 10k sims:** playoff Brier **0.0997** vs climatology 0.2500 (**+60.1 %**, cluster-bootstrap 90 % CI [+47.6, +72.2] — excludes 0); title Brier **0.0732** vs 0.0764 (**+4.2 %**, CI [−13.1, +20.0] — **includes 0**). Per week 0.2012 / 0.1065 / 0.0538 / 0.0372. Split by league: all six beat climatology on playoff, **three of six lose to climatology on title**.
- **Result — preseason (week 0), 72 team-seasons:** playoff Brier **0.1968** (+21.3 %, CI **[+2.9, +39.1]**); title 0.0746 (+2.3 %, CI [−18.9, +24.5]). Preseason − week-3 paired Δ **−0.0043** (CI spans 0) — preseason still nominally better than the week-3 model. Median-match leagues 0.2326, H2H 0.1789.
- **Result — the BUG-3 wiring in isolation:** pooled title Brier **0.0733 → 0.0732**; fixed-bracket leagues only 0.0817 → 0.0815; **playoff Brier bit-identical (max \|Δ\| = 0.000000)** and `playoff_seed_type: 1` leagues **bit-identical** (value 1 == reseed == pre-fix behaviour). The bracket rule was wrong for 4 of 6 league-seasons and correcting it moved the pooled title number by 0.0001 — **a null, reported as one.**
- **Over-confidence SURVIVED the fix wave.** Preseason top bucket 0.947 predicted → **0.778** realized (n = 9; was 0.949 → 0.750, n = 8); bottom bucket 0.034 → 0.167. In-season populated buckets stay inside ±0.05 (n = 99 and n = 100). Preseason skill lower CI bound moved the **wrong** way: +4.1 % → **+2.9 %**.
- **Also re-confirmed unchanged:** bye-week μ multiplier still NO-SHIP (Δ +0.0031, CI [−0.0054, +0.0125]; mechanism OLS slope −0.218 vs the naive −1.000); random-re-pairing fallback still costs ~7 % of playoff Brier.
- **Verdict:** (1) **bands, not percentages — stands, and is better supported than before**; a 5 %-rounded playoff percentage from week 6 is an operator risk call, not a validated result (calibration is pooled, not week-stratified). (2) **Gate numbers at week 6, allow bands from week 0, never gate at week 3** — week 3 is dominated by both neighbours and is the only week where title odds lose to a constant 1/12. Report: `docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`; dated corrections issued to the three prior #169 reports.

## 2026-08-10 — Combined post-fix outlook calibration (sim gate DEVIATION, standing operator bypass)

- **Change:** seed-type + coverage wiring and the definitive combined calibration. Mobile diff is **type-only** (`mobile/src/api/league.ts` gains the `priced_slot_coverage` payload field) — no UI, no behaviour, `outlook.odds` false everywhere.
- **Sim run: NOT PERFORMED** — `FTF_SKIP_SIM_GATE=1` under standing operator authority; the smoke suite still doesn't exist and this change class renders nothing.
- **Verified:** full suite **2297 passed / 1 skipped**, exit 0; `tsc --noEmit` clean. Deliverable `docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`.

## 2026-08-09 — ESPN numeric-id guard fix (backend-only, merged to main)

- **Change:** `server._fetch_sleeper_league_meta` + `trade_block_service.sync_league_trade_block` now pair their `isdigit()` guard with `database.is_linked_platform_league`, so ESPN/MFL/Fleaflicker-imported leagues (numeric native ids) no longer fire Sleeper requests that 404 on `/api/session/init` (prod noise + false `vcr_misses` in FTF_TEST_MODE). Same convention as the #149/#150 proxy fix. Commit `e7d0da7`.
- **Suite:** full `pytest backend/tests -q` → **2219 passed / 1 skipped / 1 xfailed**, exit 0 (562 s) — +2 regression tests in `test_espn_link_route.py` pinning both helpers to zero Sleeper calls on a linked ESPN league.
- **Sim run: NOT PERFORMED** — backend-only, no mobile diff, no schema/API/flag surface; pre-push hook gate not triggered (no `mobile/src/` change).
- **Follow-up:** revert the two harness workarounds in worktree `~/ftf-worktrees/screens-wt` (espn.json `sleeper.trade_block:false` pin; 404-cassette sentinel + gap-guard carve-out) once that branch rebases onto this fix.

## 2026-08-09 — BUG-5: IDP/K starting slots are unpriced (fix + backtest, NOT merged, no flag change)

- **Change:** `backend/outlook/strength.py` only — IDP slot eligibility in `select_starting_lineup()` (a `DL` slot now accepts DE/DT/NT, `DB` accepts CB/S/SS/FS, `IDP_FLEX` accepts any defender) plus a new `lineup_pricing()` instrument. New `scripts/outlook_idp_pricing_backtest.py`, `backend/tests/test_outlook_idp_pricing.py`, and one records fixture. No flag, no `config/features.json`, no `model_config` key, no mobile diff; `outlook.odds` still dark.
- **Suite:** baseline on a fresh `origin/main` reset (`359a0ff`) **2217 passed / 1 skipped / 1 xfailed** (706 s) → **2247 passed / 1 skipped / 1 xfailed**, exit 0 (+30). New file alone: 30 passed in 4.8 s.
- **Sim run: NOT PERFORMED** — validation-plus-neutral-fix change class with zero user-visible surface (`outlook.odds` false everywhere, no mobile diff), branch left unmerged for operator review.
- **Damage measured:** the DynastyProcess board carries QB/RB/WR/TE only, so in the operator's **FFv3** league **8 of 15 starting slots price at exactly 0.0** — **53.3 % of slots**, covering **33.0–34.3 % of the points those teams actually scored** (Sleeper `starters_points`, weeks 1–14). FFv3 is **4 of the 6 backtested league-seasons**; Lakeview is 0 %. The unpriced third is weakly differentiating: sd 58–65 season points vs 160–211 for the priced slots.
- **Result — five-variant preseason backtest, 10k sims, split by league.** V0 status quo reproduces the published baseline exactly (pooled playoff Brier **0.1959**, +21.6 %; FFv3 0.1789; Lakeview 0.2298). **Eligibility fix: 0 of 72 predictions moved** (asserted, not assumed). **League-mean fallback Δ +0.0005** (CI [−0.0056, +0.0061]); **coverage attenuation √ Δ −0.0019** (CI [−0.0167, +0.0070]), **linear Δ +0.0042**. Lakeview bit-identical under every variant.
- **Verdict: real defect, no available fix beats the status quo.** No license-clean dynasty IDP board exists (DynastyProcess, nflverse, FantasyCalc, KTC, Sleeper `search_rank` all checked). Shipped the correctness fix + the coverage instrument; the pricing gap is documented, not papered over. Preseason ship verdict unchanged; IDP-league odds must be **labelled offence-only** before the flag lights. Report: `docs/feedback/items/169-outlook-league-summary/idp-pricing-2026-08-09.md`; gotcha G-026.

## 2026-08-09 — Dated DP value boards + preseason-source revalidation (validation only, NOT merged, no flag change)

- **Change:** no product behaviour touched. New `backend/dp_values_history.py` (research-only dated DynastyProcess boards), 24 committed board fixtures + index in `backend/tests/fixtures/dp-values-history/` (484 KB), three scripts (`scripts/dp_values_history_capture.py` — the only one that uses the network, `scripts/outlook_preseason_backtest.py`, `scripts/outlook_pick_capital_dated_values.py`), and two test files. `backend/outlook/` unchanged, `config/features.json` unchanged, `outlook.odds` still dark, no mobile diff.
- **Suite:** baseline on a fresh `origin/main` reset (`ea19d4b`) **2194 passed / 1 skipped / 1 xfailed** (151 s) → **2217 passed / 1 skipped / 1 xfailed**, exit 0 (+23). New files alone: `test_dp_values_history.py` 15 passed, `test_outlook_preseason_source.py` 8 passed, 0.5 s combined.
- **New coverage:** commit resolution (`until=`/`path=` query shape, empty-result `LookupError`), raw-URL sha pinning, `slim_csv` filtering, all three crosswalk join tiers + position-strictness, scoring-column selection, **offline path asserted against an opener that raises on any network call**, refusal-not-substitution for an uncaptured date, fixture-index integrity, **no-look-ahead invariant** (`scrape_date <= key` on all 24 boards), roster rewind to real week-1 rosters, `auto` → `roster_value` at week 0, board-is-load-bearing check, and four re-scoring guards on the committed per-team records (including a deliberate assertion that preseason title odds do **not** beat climatology, so the null cannot rot away).
- **Sim run: NOT PERFORMED** — validation-only change class with zero user-visible surface (`outlook.odds` false everywhere, no mobile diff), and the branch is left unmerged for operator review.
- **Result — preseason `roster_value`, as-of week 0, 6 league-seasons / 72 team-seasons / 6 champion events:** playoff Brier **0.1959** vs climatology 0.2500 (**+21.6 %**, cluster-bootstrap 90 % CI **[+4.1, +38.3]** — excludes 0); title Brier 0.0740 vs 0.0764 (+3.1 %, CI [−17.7, +24.9] — **includes 0, no skill**). Indistinguishable from the week-3 model (paired delta −0.0013, CI [−0.0573, +0.0470]). Over-confident at the extremes (0.9–1.0 bucket: 0.949 predicted, 0.750 realized, n = 8); beats climatology in 4/6 league-seasons. Board coverage 96.8–99.3 % roster, 100 % starting-slot; unmatched DP rows 0.2–1.8 %.
- **Result — hypothesis 1b re-test:** sub-test (i) −0.113 → **+0.076, CI spanning zero**; confound −0.349 → **−0.415**; (ii)/(iii)/buy:sell bit-identical. Verdict **WEAKENED**.
- **Verdict:** preseason **title** odds — do not render. Preseason **playoff** odds — conditional go, banded not precise, BUG-1 (G-024) first. Report: `docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md`.

## 2026-08-09 — Outlook odds calibration backtest (validation only, no ship, no flag change)

- **Change:** no product code touched. Added `backend/tests/test_outlook_calibration.py` (22 permanent invariant/fixture tests + 1 strict `xfail` tracking BUG-1), two offline analysis scripts (`scripts/outlook_calibration_backtest.py`, `scripts/outlook_strength_source_compare.py`), 9 committed Sleeper fixtures, and the calibration report. `outlook.odds` remains dark.
- **Suite:** baseline **2136 passed / 1 skipped** → **2158 passed / 1 skipped / 1 xfailed**, exit 0 (142 s). New file alone: 22 passed / 1 xfailed in 3.6 s.
- **Sim run: NOT PERFORMED for the wave push** (`FTF_SKIP_SIM_GATE=1`, standing operator bypass) — the mobile diff is dark-flagged contract/nullability fixes only (`outlook.odds` false everywhere); zero user-visible change.
- **Backtest result:** as-of weeks 3/6/9/12 over 6 real captured Sleeper seasons (72 team-seasons, 6 champion events). Playoff Brier **0.1113** vs climatology 0.2500 (**+55.5 %** skill, cluster-bootstrap 90 % CI [+44.5, +65.9] — excludes 0). Title Brier **0.0725** vs 0.0764 (**+5.1 %**, CI [−13.2, +22.3] — **includes 0, no demonstrated skill**).
- **Verdict:** MARGINAL PASS, conditional — playoff odds ship-worthy after BUG-1 (median-match ingestion, G-024) is fixed; title odds not validated. Report: `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md`.

## 2026-08-09 — ESPN round-2 ship (sim gate DEVIATION, standing operator bypass)

- **Change:** cold-load login warm-up reload + reload control + wedge hint; league picker (`espn.league_picker` ON, `GET /api/espn/my-leagues`). Push `89c61b4`, build 96.
- **Sim run: NOT PERFORMED** (`FTF_SKIP_SIM_GATE=1`, standing authority). Maestro flow WAS extended (reload control) but not executed — no runnable dev client.
- **What WAS verified:** 2136 passed / 1 skipped, exit 0 (+27); tsc clean; testid-lint OK; **fan-API shape live-verified against an authenticated fetch on the operator's real ESPN session** — caught the lowercase-"ffl" filter bug (real abbrev is "FFL") pre-merge; fixture now mirrors the real payload. Round-1 fixes field-validated by the operator's successful private-league link (league_read 200 in events, 22:44 UTC).

## 2026-08-09 — ESPN-fix + morning-batch + observability ship (sim gate DEVIATION, standing operator bypass)

- **Change:** the wave below (ESPN webview fixes, #285, #286-288, integrations docs, api_observability) merged and pushed as one; combined suite **2109 passed / 1 skipped, exit 0**, tsc clean on final branch. `FTF_SKIP_SIM_GATE=1` under standing operator authority; ESPN fix's REAL validation is the operator's TestFlight walkthrough with the private league (checklist in `docs/feedback/items/espn-webview-escape/status.md`) — build 95.

## 2026-08-09 — API observability build (flag `obs.api_events` ON; worktree agent, merged/shipped same day — see entry above)

- **Change:** operator-directed observability program (`docs/feedback/items/api-observability/status.md`): `backend/api_observability.py` — outbound wrapper around every external egress chokepoint (Sleeper REST/GraphQL incl. the 3 documented bypass sites, ESPN, MFL, Fleaflicker, DP CSVs, KTC, Anthropic, Expo, Apple/Google) + inbound Flask hooks; events land in `user_events` (`api_call`/`api_request`, `user_id='system:api'`), errors always + successes 1-in-10 sampled (`model_config obs_success_sample_n`), 30 d retention purge, admin report `GET /api/admin/analytics/apihealth`. Backend + docs only; no mobile/web changes.
- **Sim run: NOT PERFORMED** — backend-only change class, and the branch is deliberately left unmerged for operator review (build agent has no merge authority; sim gate applies at ship).
- **What WAS verified:** baseline `pytest backend/tests -q` on the release base → **2086 passed / 1 skipped, exit 0**; after build → **2109 passed / 1 skipped, exit 0** (+23 in `backend/tests/test_api_observability.py`: per-service wrapper capture with cookie/JWT-never-stored redaction assertions, inbound hook capture + exclusions, 1-in-N sampling vs errors-always, kill-switch zero-writes, poisoned-event-store failure isolation, retention purge, apihealth report + `service` filter). `tsc --noEmit` n/a (no mobile diff).

## 2026-08-09 — Design-decision batch (#270/#272 A/B, #169, #279) (sim gate DEVIATION, standing operator bypass)

- **Change:** experiment `trades_home_inline` (strip/canvas variants, operator on strip), flag `trade.position_impact` ON, experiment `aggregate_tier_labels` (operator-only), two mock-lab revisions. Batched at operator direction ("Don't push E1 until we resolve these other two items too").
- **Sim run: NOT PERFORMED.** Standing bypass (`FTF_SKIP_SIM_GATE=1`). Both experiment builds carry explicit Maestro waivers (allowlist-gated to one real account, invisible to the QA harness identity).
- **What WAS verified:** `pytest backend/tests -q` → 2072 passed / 1 skipped, exit 0 (+8 new: experiment assignment/byte-identity ×2 builds, starter_impact tier/rank ×4 incl. tie-break determinism and the pure-weight-revise switch test); `tsc --noEmit` clean on the final combined branch; testid-lint OK; config-reference merge conflict union-resolved and re-gated.

## 2026-08-09 — Feedback wave 3 (#277/#278/#280/#281, #273-275, #269/#276) (sim gate DEVIATION, standing operator bypass)

- **Change:** tier labels app-wide (+3 routes gain additive `tier`), PickAssignment future-year/sheet fixes, sheet targeting (flag `trades.sheet_targeting` ON), scroll-to-trade, inline-home mockup lab. #282 held unmerged pending operator sign-off on prod-name fixtures.
- **Sim run: NOT PERFORMED.** Standing operator bypass (`FTF_SKIP_SIM_GATE=1`); smoke suite still doesn't exist.
- **What WAS verified:** `pytest backend/tests -q` → 2059 passed / 1 skipped, exit 0 (+6 tier-route tests); `tsc --noEmit` clean after every merge and post deferred-fix; flag mirror + testid-lint green; per-branch review before each merge.

## 2026-08-08 — Feedback wave #268/#267/#265/#263/#260/#257/#172 (sim gate DEVIATION, standing operator bypass)

- **Change:** 6 fixes/features + 2 mockup labs (see CHANGELOG same date). Two new flags ON (`trades.edit_full_sheet`, `trades.intent_modes`); one additive API field (`tier` on GET /api/trade/values); intent field in trade prefs.
- **Sim run: NOT PERFORMED.** Smoke suite still doesn't exist; standing operator bypass ("You can bypass the gate and push live to testflight", 2026-08-08) via `FTF_SKIP_SIM_GATE=1`.
- **What WAS verified:** `pytest backend/tests -q` → 2053 passed / 1 skipped, exit 0 (+12 new: #268 repro, 11 intent-mode tests); `tsc --noEmit` clean after each merge and on the final combined branch; flag mirror tests green; `testid-lint.sh` OK; node tests (league-unlocks 4/4); per-branch code review before every merge. #268's fix carries a test that reproduces the exact pre-fix client request (405) and proves the corrected URL (200).

## 2026-08-08 — Context-slim batch (sim gate SKIP, express-class: docs/config only)

- express: context-overload remediation (branch `context-slim-2026-08-08`) — gates skipped by operator direction. Diff touches `mobile/src/**/CLAUDE.md` (docs), living-memory, docs/, skills, hook config — zero app code. `FTF_SKIP_SIM_GATE=1` used for the push; CI (pytest + tsc + testid-lint) is the verification gate.

## 2026-08-08 — Feedback #266/#258 fixes (sim gate DEVIATION, standing operator bypass)

- **Change:** #266 ESPN-path link buttons dead on LeaguePicker (transition-settled auto-open) + #258 MFL team-name HTML entities (startup backfill of pre-#210 stored rows). Merge `b682ee2`.
- **Sim run: NOT PERFORMED.** Same blocker as the two entries below: the 11-flow smoke suite doesn't exist. Bypass is now STANDING operator authority ("You can bypass the gate and push live to testflight", 2026-08-08) until the flows land; exercised via `FTF_SKIP_SIM_GATE=1`.
- **What WAS verified:** `pytest backend/tests -q` → 2041 passed / 1 skipped, exit 0 (+4 new backfill tests, verified failing-first); `tsc --noEmit` clean under fresh `npm ci` (includes tonight's `@react-native-cookies/cookies` dep); fix-agent reproduced both root causes in code before changing anything.

## 2026-08-08 — ESPN Connect WebView ship (sim gate DEVIATION, recorded)

- **Change:** Phase 1b ESPN cookie capture (`EspnConnectScreen`, `EspnLinkSheet` auth-error self-serve, League-tab re-sync recovery), flag `espn.webview_capture` shipped ON. Commits `989343f`/`365e815`/`81a16a2` → pushed to `main` @ `d745146`.
- **Sim run: NOT PERFORMED.** Declared tier 2, waived by operator order at merge ("Merge now and push to testflight with the flag on" + explicit gate-bypass confirmation, 2026-08-08), exercised via `FTF_SKIP_SIM_GATE=1`. Same underlying blocker as the entry below: the new native dep (`@react-native-cookies/cookies`) needs a rebuilt dev client before any Maestro run, and the smoke flows don't exist yet.
- **What WAS verified:** `tsc --noEmit` clean (post-rebase); `node tests/check-espn-cookies.js` 14/14; `pytest -k "flag or feature or taxonomy"` 149 passed (post-rebase, flag ON + release-mirror green); manual testID cross-check (flow + registry + source agree); independent adversarial review — security clean, 8 findings fixed in `365e815`.
- **Compensating control:** EAS build 90 (v1.11.0) auto-submitted to TestFlight; QA checklist in `docs/plans/espn-connect-webview/scope.md` §3 (fresh capture / OTP hint / auth-recovery, real private league 493554) is the validation gate, with the flag flip-off as rollback.

## 2026-08-08 — ESPN auto-derived draft order (sim gate DEVIATION, recorded)

- **Change:** `suggested_order` prefill on PickAssignmentScreen (+ espn_service derivation). Tier 1 by the matrix (mobile screen change).
- **Sim run: NOT PERFORMED — the required artifact cannot exist yet.** The gate's tier-1 requirement is the 11-flow smoke suite; `mobile/maestro/` contains zero flows (the mobile-testing program has built seams/scripts/testIDs, not the flows). Maestro itself IS installed.
- **Deviation authority:** operator directive to ship ("Pick up and finish 3", 2026-08-08), exercised via the documented `FTF_SKIP_SIM_GATE=1` override. Receipts per the gate spec: this entry + the deviation note in `docs/plans/draft-extensions/build-espn-auto-order.md`.
- **What WAS verified:** `pytest backend/tests -q` → 2037 passed / 1 skipped, exit 0 (+42 new tests incl. the live-captured league-11896 fixture pinning the operator's inverse-regular-season decision); `tsc --noEmit` clean; all 4 mobile AST/behaviour check scripts pass. The mobile delta is a prefill of an existing editable list — no new writes.
- **Follow-up owed:** the 11 smoke flows are now the gate's own blocking dependency — until they exist, every tier-1/2 push needs this same override. Build them or re-tier the gate.

## Table of Contents
- [2026-09-08 — Feedback batch #422/#423/#424/#425/#426/#427/#428: five groups QA-green on `feat/feedback-2026-09-08`](#2026-09-08--feedback-batch-422423424425426427428-five-groups-qa-green-on-featfeedback-2026-09-08)
- [2026-09-08 — Team overhaul: device-found card-shape bug (blank chips, two crashes) fixed](#2026-09-08--team-overhaul-device-found-card-shape-bug-blank-chips-two-crashes-fixed)
- [2026-09-08 — Team overhaul flag flipped ON; production verified](#2026-09-08--team-overhaul-flag-flipped-on-production-verified)
- [2026-09-07 — Team overhaul: sends on MFL and ESPN (owner D1 revision), branch evidence](#2026-09-07--team-overhaul-sends-on-mfl-and-espn-owner-d1-revision-branch-evidence)
- [2026-09-07 — Team overhaul v1 build (branch, flag off): full backend suite green](#2026-09-07--team-overhaul-v1-build-branch-flag-off-full-backend-suite-green)

- [2026-09-06 — Feedback release CI, merge and delivery](#2026-09-06--feedback-release-ci-merge-and-delivery)
- [2026-09-06 — Feedback 419–421 implementation checkpoints, not release evidence](#2026-09-06--feedback-419421-implementation-checkpoints-not-release-evidence)
- [2026-09-05 — Experimental personal-market policy activation verified](#2026-09-05--experimental-personal-market-policy-activation-verified)
- [2026-09-05 — Security follow-up independently reviewed: Python 3.12 and PostgreSQL pass; native runtime pending](#2026-09-05--security-follow-up-independently-reviewed-python-312-and-postgresql-pass-native-runtime-pending)
- [2026-09-04 — Security findings 1–5: initial local implementation, not deployed](#2026-09-04--security-findings-15-initial-local-implementation-not-deployed)
- [2026-09-04 — Operator-approved revised-input evaluation completed](#2026-09-04--operator-approved-revised-input-evaluation-completed)
- [2026-09-04 — Historical Sleeper outcome collection and calibration readiness](#2026-09-04--historical-sleeper-outcome-collection-and-calibration-readiness)
- [2026-09-04 — Trade model/scoring-context integration](#2026-09-04--trade-modelscoring-context-integration)
- [2026-09-04 — Trade activation validation and original items 2/3](#2026-09-04--trade-activation-validation-and-original-items-23)
- [2026-09-04 — Scoring execution context: local prerequisite built, unmerged](#2026-09-04--scoring-execution-context-local-prerequisite-built-unmerged)
- [2026-09-04 — Win Now implementation reviewed; backend and client verification](#2026-09-04--win-now-implementation-reviewed-backend-and-client-verification)
- [2026-09-04 — Personal-market policy built DARK (D-180/D-181): 87 new tests, full suite green, flag-off byte identity proved three ways](#2026-09-04--personal-market-policy-built-dark-d-180d-181-87-new-tests-full-suite-green-flag-off-byte-identity-proved-three-ways)
- [2026-09-03d — Web ESPN sign-in-primary (D-179): web gate 175/175, entry route 25/25, browser E2E both flag states + live-ESPN 403](#2026-09-03d--web-espn-sign-in-primary-d-179-web-gate-175175-entry-route-2525-browser-e2e-both-flag-states--live-espn-403)
- [2026-09-03c — API audit fixes (D-178): merged branch green — pytest 4617 / 1 skipped, tsc 0, testid-lint OK, web 175/175](#2026-09-03c--api-audit-fixes-d-177-merged-branch-green--pytest-4617--1-skipped-tsc-0-testid-lint-ok-web-175175)
- [2026-09-03b — Web landing platform entry (PR #272): web gate 175/175, entry-route suite 25/25, browser E2E both platforms; sim gate skipped (D-056 posture)](#2026-09-03b--web-landing-platform-entry-pr-272-web-gate-175175-entry-route-suite-2525-browser-e2e-both-platforms-sim-gate-skipped-d-056-posture)
- [2026-09-03 — #413 SHIPPED: PR #270 squash → `main` @ `5c83e8cd`, CI ×4 green, Render live, EAS build 144 / v1.16.15 submitted](#2026-09-03--413-shipped-pr-270-squash--main--5c83e8cd-ci-4-green-render-live-eas-build-144--v11615-submitted)
- [2026-09-02 — feedback #413 Sleeper pick-send fix: built, dual-QA green, shipped 2026-09-02 (see the merged-tree entry above)](#2026-09-02--feedback-413-sleeper-pick-send-fix-built-dual-qa-green-shipped-2026-09-02-see-the-merged-tree-entry-above)
- [2026-08-28d — IAP enablement code half (runbook 6–7): webhook delta + RevenueCat paywall — full gates, ALL DARK](#2026-08-28d--iap-enablement-code-half-runbook-67-webhook-delta--revenuecat-paywall--full-gates-all-dark)
- [2026-08-28c — v1.16.9 (EAS build 135) BUILT + SUBMITTED to TestFlight; trade.shop_asset LIT in prod](#2026-08-28c--v1169-eas-build-135-built--submitted-to-testflight-tradeshop_asset-lit-in-prod)
- [2026-08-28b — #402/#403 QA round 2: B-3, own-position chip ruling, P-1..P-4 — universal-rule fixes, gates green](#2026-08-28b--402403-qa-round-2-b-3-own-position-chip-ruling-p-1p-4--universal-rule-fixes-gates-green)
- [2026-08-28 — #402/#403 "More offers = shop a player" — full build + redundant QA + fix round, all gates green (branch, HELD unmerged)](#2026-08-28--402403-more-offers--shop-a-player--full-build--redundant-qa--fix-round-all-gates-green-branch-held-unmerged)
- [2026-08-27 — #384 partner team-shape summary restored to the merged calculator layout — full gates](#2026-08-27--384-partner-team-shape-summary-restored-to-the-merged-calculator-layout--full-gates)
- [2026-08-26e — v1.16.8 (EAS build 134) BUILT for TestFlight](#2026-08-26e--v1168-eas-build-134-built-for-testflight)
- [2026-08-26c — Entry v2.1: login option (Opus subagent build, lead-session review) — full gates](#2026-08-26c--entry-v21-login-option-opus-subagent-build-lead-session-review--full-gates)
- [2026-08-26b — Platform entry decoupled from Apple (D-164) — full gates](#2026-08-26b--platform-entry-decoupled-from-apple-d-164--full-gates)
- [2026-08-26 — Landing platform options (Sleeper · ESPN · MFL entry chips) — full gates](#2026-08-26--landing-platform-options-sleeper--espn--mfl-entry-chips--full-gates)
- [2026-08-25 — v1.16.6 (EAS build 132) BUILT + SUBMITTED to TestFlight](#2026-08-25--v1166-eas-build-132-built--submitted-to-testflight)
- [2026-08-24c — Waves A + B0 SHIPPED — PRs #197/#199, EAS 1.16.4 (130) submitted](#2026-08-24c--waves-a--b0-shipped--prs-197199-eas-1164-130-submitted)
- [2026-08-24b — Wave B0 the layout merge (`calc.inline_home`) — full gates, FLAG DARK, NOT MERGED](#2026-08-24b--wave-b0-the-layout-merge-calcinline_home--full-gates-flag-dark-not-merged-on-featinline-home-b0)
- [2026-08-24 — Onboarding-tour Wave A — full gates green on `feat/tour-wave-a`; runtime evidence owed](#2026-08-24--onboarding-tour-wave-a--full-gates-green-on-feattour-wave-a;-runtime-evidence-owed)
- [2026-08-23b — `test_stud_tax_pinned_market` flake pinned: breaker wall-clock budget removed from test inputs](#2026-08-23b--test_stud_tax_pinned_market-flake-pinned-breaker-wall-clock-budget-removed-from-test-inputs)
- [2026-08-23a — main CI red → green: full-sweep fixture mirrors flipped](#2026-08-23a--main-ci-red--green-full-sweep-fixture-mirrors-flipped)
- [2026-08-22j — Full sweep — full gates; LIT at merge](#2026-08-22j--full-sweep-tradefull_sweep--full-gates-lit-2026-08-23-by-operator-instruction-at-merge)
- [2026-08-22i — #384 W8 — simulator reproduction, v1.16.2 (EAS 128)](#2026-08-22i--384-w8--simulator-reproduction--mobile-gates-v1162-eas-128)
- [2026-08-22h — #384 W7 device-feedback fixes — v1.16.1 (EAS 127)](#2026-08-22h--384-w7-device-feedback-fixes--mobile-gates-v1161-eas-127)
- [2026-08-22g — #384 SHIPPED — PR #172, flags LIT, EAS 1.16.0 (126)](#2026-08-22g--384-shipped--pr-172-80dee42-flags-lit-eas-build-1160-126-submitted)
- [2026-08-22f — #384 W6-A + W6-B — full gates, FLAG DARK, NOT MERGED](#2026-08-22f--384-w6-a--w6-b--full-gates-flag-dark-not-merged-on-claudemanual-calculator-e2e-review-39a467)
- [2026-08-22e — #384 merged calculator W5 + guard hardening — full gates, FLAG DARK, NOT MERGED, on `claude/manual-calculator-e2e-review-39a467`](#2026-08-22e--384-merged-calculator-w5--guard-hardening--full-gates-flag-dark-not-merged-on-claudemanual-calculator-e2e-review-39a467)
- [2026-08-22d — #384 merged calculator W0–W4 — full gates, FLAG DARK, NOT MERGED, on `feat/calc-finder-merge`](#2026-08-22d--384-merged-calculator-w0w4--full-gates-flag-dark-not-merged-on-featcalc-finder-merge)
- [2026-08-22c — Feedback capture cap (2000 → 8000) + the three silences — full gates, backend SHIPPED, client awaiting a build](#2026-08-22c--feedback-capture-cap-2000--8000--the-three-silences--full-gates-backend-shipped-client-awaiting-a-build)
- [2026-08-20b — Fit challenger PR-F3 (filters + arm wiring + serve-bit) + W0 offline dry run](#2026-08-20b--fit-challenger-pr-f3-filters--arm-wiring--serve-bit--w0-offline-dry-run-not-merged-worktree-claudetrade-suggestions-review-69c9eb)
- [2026-08-20a — Team Review defect batch (#364/#367/#368) — full gates](#2026-08-20a--team-review-defect-batch-364367368--full-gates-not-merged-on-claudeteam-outlook-experience-27a7a1)
- [2026-08-20d — #366 position-relative tier bands + RB Handcuff — full gates, NOT MERGED, on `worktree-agent-a4ab94c51456abb78`](#2026-08-20d--366-position-relative-tier-bands--rb-handcuff--full-gates-not-merged-on-worktree-agent-a4ab94c51456abb78)
- [2026-08-20e — Team Review `plan` beat rebuilt (#369) — full gates, NOT MERGED, on `worktree-agent-a7bed877f805980b0`](#2026-08-20e--team-review-plan-beat-rebuilt-369--full-gates-not-merged-on-worktree-agent-a7bed877f805980b0)
- [2026-08-20a — Team Review defect batch (#364/#367/#368) — full gates, NOT MERGED, on `claude/team-outlook-experience-27a7a1`](#2026-08-20a--team-review-defect-batch-364367368--full-gates-not-merged-on-claudeteam-outlook-experience-27a7a1)
- [2026-08-19h — `outlook.odds` LIT by operator override + its replacement guard (D-094, NOT MERGED, on `claude/team-review-analysis-plan-1f91e3`)](#2026-08-19h--outlookodds-lit-by-operator-override--its-replacement-guard-d-094-not-merged-on-claudeteam-review-analysis-plan-1f91e3)
- [2026-08-08](#2026-08-08)
- [2026-07-04](#2026-07-04)
- [2026-06-11](#2026-06-11)
- [Archive: pre-2026-06 entries](archive/TEST_LEDGER-pre-2026-06.md)
- [Manual Verification History](#manual-verification-history)
- [Custom-Skill Benchmarks](#custom-skill-benchmarks)
- [Tests Planned but Not Yet Run](#tests-planned-but-not-yet-run)
- [Verification Discipline](#verification-discipline)

---

## 2026-08-08

### ESPN Connect WebView build (worktree `espn-webview-capture` off `origin/main` @ `cb6aacb`)
- **`cd mobile && npx tsc --noEmit` → clean, exit 0** (run after both the feature commit and the review-fix commit).
- **`node mobile/tests/check-espn-cookies.js` → 14/14 checks pass** — pure extractor `pickEspnCookies` (pair/half-pair/trim/braces/multi-bag), `readEspnCookies` polls both ESPN domains, `clearEspnCookies` clears 2 names × 2 domains × 2 native stores (the fresh-login guarantee).
- **`python3 -m pytest backend/tests/ -q -k "flag or feature"` → 148 passed**; broader `-k "taxonomy or analytics or events or flag or feature or seed_ui"` → **320 passed** (new flag `espn.webview_capture` in registry + release-mirror; 4 `espn_connect_*` events in the taxonomy with prop entries).
- **testID cross-check (manual):** every id referenced by `mobile/.maestro/flows/espn-connect-capture.yaml` and the components CLAUDE.md registry resolves in `mobile/src/`. `mobile/scripts/testid-lint.sh` does not exist on this branch (`mobile/scripts/` is gitignored — see below); a tracked lint script is a separate task.
- **NOT run:** the Maestro flow itself (needs a rebuilt dev client carrying the new `@react-native-cookies/cookies` native pod) and the in-WebView login leg (waived per scope §3 — live third-party page; covered by the scope block's TestFlight QA checklist). `pod install` fails on this machine (CocoaPods 1.16.2/Ruby 4.0.3 `Unicode Normalization not appropriate for ASCII-8BIT` on the spaces-in-path repo); the EAS build regenerates the lockfile.

### Suite trajectory, 2026-07-09 → 2026-08-06
- **252 → 1466.** Reconstructed from commit messages during the living-memory revival pass; each figure is the count the committing session reported. Checkpoints: 272 → 285 → 382 → 521 (accounts P1/P2) → 558 → 632 → 781 (v1.9.0) → 855 (analytics P3/P4) → 937 (teardown W2) → 979 (owned picks) → 998 → 1025 → 1209 → 1336 (deck engine) → 1359 → 1378 → 1405 → 1445 → 1455.
- **Counts are not strictly monotonic in log order.** Parallel worktree agents committed against different baselines — the 1414/1415 pair on 2026-08-03 is the clearest example. Treat a lower count in a later commit as a branch artifact, not a regression.

### Measured live on 2026-08-08 (this checkout, `teardown-remediation` @ `30492ac`)
- **`python3 -m pytest backend/tests/ -q` → 1466 passed, 1 skipped, 41.7s.**
- **`cd mobile && npx tsc --noEmit` → clean, exit 0.**
- ⚠️ **This is the 62-commits-behind base, not the project's test posture.** The rookie-draft QA handoff cites **1685 passed / 1 skipped on `origin/main` @ `cee4324`**. Quote the origin/main number when describing the project; quote this one only when describing this checkout.
- The 1466 includes two untracked test files not yet committed: `test_espn_pick_assignment.py` (6 tests), `test_finder_config_consolidated.py` (5 tests).

### Practices worth keeping (observed in this window)
- **Failing-first is used and stated in commit messages** — `#238` lineup before/after and the `market.movers` work both note tests written failing-first; several 07-25 fixes note the regression shape was "verified failing pre-fix via stash".
- **Flag-gated waves re-run the suite twice** — once as built, then again with flags ON as a separate gate. The deck-engine waves all did this.
- **A contrast guard runs in CI-shape** — `mobile/scripts/check-contrast.js` over 13 token pairs, `npm run test:contrast`.
- **`mobile/scripts/` is gitignored**, so JS regression checks live in `mobile/tests/` instead.

## 2026-07-04

### TC-API-001 — Manual Trade Calculator endpoints (/api/trade/evaluate, /api/trade/values)
- **Test:** 8 pytest cases over an injected universal pool ([backend/tests/test_trade_evaluate.py](../backend/tests/test_trade_evaluate.py)): symmetric→even, lopsided→unfair+favors, per-player values match `elo_to_value` exactly, unknown-id graceful drop, one-sided packages (no verdict), empty→400, bogus format→default, values-endpoint shape + ETag 304.
- **Result:** **PASS 8/8**; full suite **252 green**. Real-pool smoke (local Flask, live DP data): 671 valued players; top-vs-mid → `unfair/favors: give/ratio 0.008`; mirror trade → `even/1.0`.
- **Also verified:** mobile live mode end-to-end in Expo web with a contract-shaped fetch stub (backend has no CORS, so browser-origin calls can't hit it — native is unaffected); demo mode unchanged (Bijan parity scenario byte-identical since 07-02: 2,536/2,874, +9%/+12%).
- **Not yet run:** live mode against prod from a real device (needs deploy).

### TC-API-002 — Send in Sleeper error-contract hardening (/api/sleeper/link, /api/trades/propose)
- **Test:** +6 route tests ([backend/tests/test_sleeper_write_route.py](../backend/tests/test_sleeper_write_route.py)) locking each branch the mobile `SendInSleeperButton` depends on: no-key→503 `sleeper_unconfigured`; `bad_request` (non-numeric league / no counterparty); pre-flight **expired stored token**→409 `sleeper_expired` + credential dropped (the #1 real reconnect trigger, distinct from the mid-call auth-error branch); non-auth write failure→502 `sleeper_write_failed`; rosters-fetch exception degrades to 400 `roster_not_found` (never an unhandled 500); GET surfaces `expired:true`.
- **Result:** **PASS 14/14** in the file (8 prior + 6 new); full backend suite **258 green**; mobile tsc clean. These run the real Flask handlers against a real in-memory DB + real Fernet key, mocking only the Sleeper network — so they double as the local route smoke.
- **Reviewed, no code change needed:** runtime paths already fail safe (`_fetch_league_rosters` catches all → None → structured 400; adapter maps auth vs generic failures correctly). Hardening was coverage, not bug-fixing.
- **Still deferred by design:** slice-4 calculator Send surface (needs a real counterparty); flag `trade.send_in_sleeper` stays OFF; on-device link→propose against real Sleeper (needs a full EAS build — `react-native-webview` is native — + throwaway account).

## 2026-06-11

### TC-ENG-004 — 3-team cycle clearing (find_three_team_cycles)
- **Test:** 4 pytest goldens for the dark/uncovered kidney-exchange 3-team cycle clearer — Pareto A→B→C→A detection, no-benefit→empty, <3 members→empty, lineup-feasibility blocks a roster-breaking handoff.
- **Result:** **PASS 4/4** ([backend/tests/test_three_team_cycles.py](../backend/tests/test_three_team_cycles.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Findings:** **F-1 (P3 dead code)** `find_three_team_cycles` is implemented + exported but **never called** (no caller; trade.three_team flag only in a comment). Correct + now tested — a product decision away from wiring on.
- **Artifacts:** [`qa/results/TC-ENG-004.md`](../qa/results/TC-ENG-004.md).

### TC-DB-002 — DB concurrency, write integrity, recency
- **Test:** concurrent member_rankings upserts (atomic replace), concurrent distinct trade decisions (no loss), concurrent ranking swipes (WAL under contention), check_for_match 90-day recency bound. Threaded against scratch DB.
- **Result:** **PASS 5/5.** 8 concurrent upserts → exactly 20 rows (atomic), 16 decisions all persisted, 24 swipe rows no lock errors, stale (>90d) like excluded.
- **Findings:** none at thread scale. Postgres multi-process pool saturation remains a pre-scale Render load-test follow-up (not reproducible with threads on SQLite).
- **Artifacts:** [`qa/db/tc_db_002.py`](../qa/db/tc_db_002.py), [`qa/db/_concurrency_probe.py`](../qa/db/_concurrency_probe.py), [`qa/results/TC-DB-002.md`](../qa/results/TC-DB-002.md).

### TC-INT-001 — Sleeper-boundary input handling (G-003..G-008)
- **Test:** session_init defensive handling of null roster slots, int IDs, garbage IDs, empty roster, dup IDs; passthrough error handling (bad username, parse-url).
- **Result:** **PASS 8/8.** Nulls filtered, int IDs coerced, garbage filtered, empty roster degrades gracefully, bad username → 404 (not 500).
- **Findings:** F-1 (P3) duplicate roster IDs not deduped (3→6); harmless today, one-line `dict.fromkeys` fix.
- **Artifacts:** [`qa/sec/tc_int_001.py`](../qa/sec/tc_int_001.py), [`qa/results/TC-INT-001.md`](../qa/results/TC-INT-001.md).

### TC-CFG-001 — feature flags + model_config live-tuning contract
- **Test:** flag map + FTF_FLAGS env precedence; admin config auth (401)/unknown(404)/badval(400); live write→reload→readback; reload endpoint auth.
- **Result:** **PASS 11/11.** FTF_FLAGS override wins; config write persists + reloads (v3 reads same live _cfg).
- **Findings:** **F-1 (P3 operational)** surplus floors gate *divergence* cards only — *consensus-basis* decks (cold/low-coverage leagues) are fairness-gated, so cranking surplus floors has NO effect there (use fairness_threshold/consensus_score_scale). F-2 (P3) marginal flag makes min_side_surplus_marginal the live floor. Documented in config-reference.md.
- **Artifacts:** [`qa/api/tc_cfg_001.py`](../qa/api/tc_cfg_001.py), [`qa/results/TC-CFG-001.md`](../qa/results/TC-CFG-001.md).

### TC-PERF-001 — performance: cold-start, warm latency, concurrent load
- **Test:** measured backend vs charter budgets — cold boot, cold/warm session_init, warm GET p50/p95, generate end-to-end, per-opponent enumeration bound, 8-way concurrent init+generate, error-free-under-load.
- **Result:** **PASS 9/9.** Cold boot 1.0s; warm GET p50/p95 = 20/58ms; generate 31 cards in 1.28s; 8 concurrent users 0 errors. All within budget at local scale.
- **Caveats (honest):** concurrency test shares the trade-job cache (same fixture user) → proves session/cache thread-safety, not N independent generations. Real prod risks (cold Sleeper fetch in session_init, v3 enumeration on large league) NOT exercised locally — flagged for a Render-side load test.
- **Artifacts:** [`qa/perf/tc_perf_001.py`](../qa/perf/tc_perf_001.py), [`qa/results/TC-PERF-001.md`](../qa/results/TC-PERF-001.md).

### TC-ENG-003 — engine gate config-responsiveness (admin tuning surface)
- **Test:** 4 pytest goldens proving the tuning knobs are monotone/predictable — min_side_surplus (↑→fewer cards), trade_elo_gap_max knife-edge, waiver_slot_cost erodes extra-player side, tier_mult_elite scales composite.
- **Result:** **PASS 4/4** ([backend/tests/test_engine_gates_config.py](../backend/tests/test_engine_gates_config.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Observation:** the legacy parity fixture yields 4 cards legacy / 0 v2 — v2 correctly rejects one-sided trades legacy surfaced (reinforces "kill-switch is a real downgrade").
- **Artifacts:** [`qa/results/TC-ENG-003.md`](../qa/results/TC-ENG-003.md).

### TC-API-002 — public-route auth-intent audit
- **Test:** classify all public routes read vs mutating; allowlist-check public mutations; empty/garbage-body robustness; CORS posture.
- **Result:** **PASS 4/4.** 13 public /api routes (8 read, 5 mutating); all 5 mutations intentional (session/init, demo, feedback, extension/auth, parse-url). No 5xx on garbage; CORS same-origin-only. **No unauthenticated state-mutating routes** — recon "44 none-auth" concern resolved.
- **Findings:** F-1 (P3) no rate limiting on pre-auth mutations (session/init, extension/auth); F-2 (P3 process) new `_require_initialized_session` gate (25 routes) added since TC-API-001 → those counts stale.
- **Artifacts:** [`qa/api/tc_api_002.py`](../qa/api/tc_api_002.py), [`qa/results/TC-API-002.md`](../qa/results/TC-API-002.md).

### TC-E2E-004 — cross-league flow + cross-league disposition
- **Test:** matches/all across leagues; awaiting; portfolio over 2 leagues; create match in league A, switch session to league B, disposition the A match (cross-league branch).
- **Result:** **PASS 9/9.** Cross-league accept (session on B, match in A) → 200, decision persisted on the match's own league, Elo signal queued for replay. Correctly league-scoped.
- **Findings:** none. Observation: match fires on whichever swipe completes the mirror (locate by DB state, not response id).
- **Artifacts:** [`qa/e2e/tc_e2e_004.py`](../qa/e2e/tc_e2e_004.py), [`qa/results/TC-E2E-004.md`](../qa/results/TC-E2E-004.md).

### TC-RNK-001 — Elo math golden fixtures (engine input quality)
- **Test:** 6 pytest goldens for the Elo update — exact pairwise math (K=32 → ±16), K-factor by decision type (rank 32 / like 8 / pass 4, linear), zero-sum conservation, 3-player decomposition + order preservation, override pinning, replay determinism.
- **Result:** **PASS 6/6** ([backend/tests/test_rnk_elo_golden.py](../backend/tests/test_rnk_elo_golden.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Observation:** displayed Elo is rounded to 1 decimal in `get_rankings`, and that rounded value is what's published to member_rankings + fed to `elo_to_value` — whole valuation pipeline runs at 0.1-Elo precision. Zero-sum only holds without tier overrides.
- **Artifacts:** [`qa/results/TC-RNK-001.md`](../qa/results/TC-RNK-001.md).

### TC-E2E-003 — superflex (sf_tep) format path + isolation
- **Test:** sf_tep trio→rank3→generate via X-Scoring-Format header; format-partitioned persistence; 1qb_ppr isolation; per-format independent Elo; sf_tep card validity.
- **Result:** **PASS 8/8.** +9 sf_tep rank rows, 1qb_ppr unchanged (222→222, isolated), sf_tep member_rankings 0→685, sf_tep generate → 31 valid cards. **Same player 1qb=1605 vs sf=1800 Elo** (QB premium in superflex working as intended).
- **Artifacts:** [`qa/e2e/tc_e2e_003.py`](../qa/e2e/tc_e2e_003.py), [`qa/results/TC-E2E-003.md`](../qa/results/TC-E2E-003.md).

### TC-API-001 — API consistency + doc-drift audit
- **Test:** static analysis of all 92 server.py routes (naming, error-shape taxonomy, auth-gate distribution) + doc-drift vs api-reference.md + live envelope/error-contract sampling.
- **Result:** **COMPLETE 7/8** (the 1 FAIL is the surfaced naming finding). Error contracts solid (every error body has an `error` key; 401/404/400 correct). Auth gates: session 35 / none 44 / cron 13 / bearer 1.
- **Findings:** F-1 (P2) 39 `jsonify({"error": str(e)})` raw-exception leaks; F-2 (P3) error-value vocabulary split (42 code-style vs 44 sentence-style vs 23 code+message); F-3 (P3) 2 undocumented routes (`/api/feedback/admin`, `/api/tiers/copy-from-format`); F-4 (P3) lone snake_case segment `/api/sleeper/league_users`; F-5 (P3) no envelope standard / no version prefix.
- **Docs updated this cycle:** added `/api/trades/awaiting` + stochastic-deck-order note to api-reference.md; v3-feasibility "no trades" failure mode to runbook.md.
- **Artifacts:** [`qa/api/tc_api_001.py`](../qa/api/tc_api_001.py), [`qa/results/TC-API-001.md`](../qa/results/TC-API-001.md).

### TC-E2E-002 — restart resilience (in-memory session + job loss)
- **Test:** generate a deck, restart the server process against the same DB, verify graceful degradation: stale token→401, stale job→404 (no hang), data survives, FB-46 swipe of a pre-restart card reconstructs + persists, new session fully functional.
- **Result:** **PASS 9/9.** Old job 404 in 0.00s; 646 member_rankings survived; FB-46 swipe persisted +1 decision; post-restart generate → 31 cards.
- **Findings:** none. In-memory job/session loss is a graceful degradation, not a failure mode; recon operability concern closed.
- **Artifacts:** [`qa/e2e/tc_e2e_002.py`](../qa/e2e/tc_e2e_002.py), [`qa/results/TC-E2E-002.md`](../qa/results/TC-E2E-002.md).

### TC-DB-001 — schema integrity, migration idempotency, SQLite↔Postgres parity
- **Test:** fresh-init schema parity on SQLite AND a real local Postgres (table set + per-table columns), `_migrate_db()` idempotency on both, dialect-branched upsert smoke (leagues/league_members/member_rankings/skips + the F-1 second-member upsert), and a read-only live-DB quality audit (orphans, enum domains, ISO timestamps, boolean storage, dup guards).
- **Result:** **PASS 24/24** incl. Postgres plane. Exact 24-table/all-column parity; migrations idempotent both dialects; **F-1 fix verified cross-dialect** (works on Postgres too, leagues stays 1 row).
- **Findings:** the 41 orphaned `league_members` (recon "HIGH, fix before scale") are **benign** — 0 have rankings, 0 in trade_matches; never-logged-in leaguemates. Recon item downgraded P3. data-dictionary.md confirmed in sync (24 tables; recon "22/23" was a miscount).
- **Env note:** `psycopg2-binary` (declared dep) was missing locally; installed to run the PG plane. Throwaway PG db `ftf_qa_parity` created + dropped.
- **Artifacts:** [`qa/db/tc_db_001.py`](../qa/db/tc_db_001.py), [`qa/db/_dialect_probe.py`](../qa/db/_dialect_probe.py), [`qa/results/TC-DB-001.md`](../qa/results/TC-DB-001.md), `qa/db/scratch/TC-DB-001-run.json`.

### F-1 (TC-E2E-001) RESOLVED — verified
- Commit `ddf67df` fixed the second-member `upsert_league` UNIQUE-constraint crash (dialect-aware `on_conflict_do_update` on the `sleeper_league_id` PK) + added `backend/tests/test_league_upsert.py` (3 tests). Re-verified: IntegrityError gone, TC-E2E-001 back to 67/67, regression test passes. E2E harness allowlist updated (no longer masks the error; now allowlists only the synthetic-league Sleeper 404).

### TC-SEC-001 — operator-endpoint auth enforcement
- **Test:** sweep all 8 operator routes (`/api/admin/*`, `/api/feedback/admin*`, `/api/debug/log`, `/api/feature-flags/reload`, `/api/cron/*`) across CRON_SECRET set/unset; in-proc test of `_require_cron_auth` prod branch (fail-closed) without a real Postgres; session-gate control on mutating routes.
- **Result:** **PASS 35/35.** Cron-gate enforces (401 missing/wrong/near-miss, success on match); prod fails closed (503 when secret unset); session routes 401 tokenless/bogus.
- **Refutes recon:** the discovery report's "5 unprotected admin endpoints (P0)" is **FALSE** — every route calls `_require_cron_auth()`. Lesson: recon findings are hypotheses until a TC verifies them.
- **Findings:** **F-1 (P2)** `run.py` binds `0.0.0.0` + `debug=True` with no local CRON_SECRET → operator routes exposed on LAN for local/self-host runs (prod on Render unaffected: fail-closed).
- **Artifacts:** [`qa/sec/tc_sec_001.py`](../qa/sec/tc_sec_001.py), [`qa/results/TC-SEC-001.md`](../qa/results/TC-SEC-001.md), `qa/sec/scratch/TC-SEC-001-run.json`.

### TC-ENG-002 — fairness-gate golden fixtures (1-for-1 gate + package-discount watch item)
- **Test:** 8 pytest golden fixtures in `backend/tests/` covering `package_value_v2` discount math (exact + monotone in `package_adj_gamma`), 1-for-1 gate config-driven knife-edge, discount→`fairness_score` propagation, FR8 outlook market-neutrality, and v2↔v3 fairness-floor parity + monotonicity. Self-calibrating where exact propagation is hard to hand-predict.
- **Result:** **PASS 8/8**, stable ×3; full backend suite now **178 passed** with the new file (no pollution). Graduated into the pytest suite — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job.
- **Findings:** **F-1 (P3)** `_fairness_v3` is a hand-copied mirror of v2 `_fairness` (standing TODO) — drift risk; this test now guards parity, but a shared `score_trade` extraction is the real fix (already planned in competitor-top20/03).
- **Key observation:** v3 lineup-feasibility is all-or-nothing — a roster that can't field a full QB1/RB2/WR2/TE1 lineup gets ZERO v3 cards (v2 still serves). Sharp edge worth a runbook note for "no trades" diagnosis.
- **Artifacts:** [`backend/tests/test_fairness_gate_golden.py`](../backend/tests/test_fairness_gate_golden.py), [`qa/results/TC-ENG-002.md`](../qa/results/TC-ENG-002.md).

### TC-ENG-001 — trade-engine kill-switch regression (legacy/v2/v3)
- **Test:** three FTF_FLAGS-pinned server instances (legacy / v2 / v3), ordering flags off; per-engine card-validity battery, flag-routing proof, legacy≠v2 divergence, v2→v3 top-card stability. Same user+league.
- **Result:** **PASS 30/30**, stable across 3 runs. Deck sizes legacy 13 / v2 33 / v3 33; all roster-ownership + fairness checks clean on all engines. v2's #1 trade always survives into v3; v2 top-10 → v3 overlap a deterministic 5/10.
- **Findings:** none. Observations: legacy fallback is a real UX downgrade (random opp Elo, smaller deck) not a transparent swap; v2→v3 top-10 continuity is exactly 50% (watch item if product wants tighter migration continuity).
- **Artifacts:** [`qa/eng/tc_eng_001.py`](../qa/eng/tc_eng_001.py), [`qa/results/TC-ENG-001.md`](../qa/results/TC-ENG-001.md), `qa/eng/scratch/TC-ENG-001-run.json`.

### TC-E2E-001 — full-stack happy path (automated harness)
- **Test:** session_init → trio/rank3 ×3 → trade generate (async job) → swipe → mirrored-like match (likes_you instant + two-session two-step) → disposition lifecycle (accept/accept → accepted, 409 repeat, 404 unknown, 400 bad input) → DB integrity sweep. Driven via HTTP against a local Flask on a scratch copy of `data/trade_finder.db`; mobile client timeout budgets as pass bar. Flags: v3 engine + all Tier 2 trade flags on.
- **Result:** **PASS 67/67 checks**, reproducible across runs. 31 cards in 0.8–1.5 s; cache-hit re-generate ≤4 ms; all calls within mobile budget.
- **Findings:** **F-1 (P1)** `upsert_league` keys on `(league_id, user_id)` but PK is league_id alone → IntegrityError swallowed on every second-member session_init, their league row never persisted. **F-2 (P2)** 7-day card-dedup vs unbounded match-dedup mismatch → already-accepted trade re-served then silently no-ops on like.
- **Artifacts:** harness [`qa/e2e/tc_e2e_001.py`](../qa/e2e/tc_e2e_001.py), report [`qa/results/TC-E2E-001.md`](../qa/results/TC-E2E-001.md), machine-readable run `qa/e2e/scratch/TC-E2E-001-run.json`.
- **Planned variants:** TC-E2E-002 restart-resilience, TC-E2E-003 sf_tep format, TC-E2E-004 Postgres parity.

## Manual Verification History

*Historical — predates the pytest suite. As of 2026-08-08 the project has a pytest suite of ~2000 tests (`backend/tests/`, run in CI's `backend-tests` job per `.github/workflows/ci.yml`); the ad-hoc methods below were the verification approach before that suite existed and are largely superseded. The 2026-05-21 entry that used to open this file (living-memory layer adoption, status pending) is archived in [`archive/TEST_LEDGER-pre-2026-06.md`](archive/TEST_LEDGER-pre-2026-06.md).*

| Verification artifact | What it tests |
|---|---|
| [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) | Expected trade matches for a test league configuration |
| [`Trade_Matches.xlsx`](../Trade_Matches.xlsx) | Reference trade-match output for validation |
| `dump_mismatches.py` | DynastyProcess ↔ Sleeper player-name mismatches |
| `tmp_check_db.py`, `tmp_check_db2.py` | Ad-hoc DB integrity scripts |
| `GET /api/debug/log?n=100` | In-memory ring-buffer log (last 200 entries) for forensic checks |
| Manual smoke: `python3 run.py` → web client login → roster import → swipe → trade card | End-to-end happy-path verification |

**Caveat (historical):** at the time this table was written there was no automated regression suite, so a change that broke one of these flows was detectable only by manual re-run. That gap is closed — see the pytest suite note above. [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-002 (pytest adoption) is resolved.

## Custom-Skill Benchmarks

| Skill | Benchmark | Result |
|---|---|---|
| **`project-reorganizer.skill`** | 6-phase methodology (scan, propose, cross-reference, execute, update imports, verify) vs ad-hoc reorganization | ~83% pass rate WITH skill vs ~43% WITHOUT (+40pp improvement). See [`project-reorganizer-eval-review.html`](../project-reorganizer-eval-review.html) |
| **`feature-evaluator.skill`** | Evaluates code across 7 dimensions (structure, readability, performance, error handling, security, testability, maintainability); produces severity-rated reports | Used in-repo for ongoing code review; no formal pass/fail benchmark yet |

---

## Tests Planned but Not Yet Run

See [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) and [`NEXT.md`](NEXT.md). High-priority:

- **Pytest suite for backend services** — `ranking_service.py`, `trade_service.py`, and `data_loader.py` would benefit most. Currently zero coverage.
- **Integration test for full Sleeper flow** — mock Sleeper API responses; verify session/league/roster import.
- **Elo regression test** — golden-file comparison: given a fixed sequence of swipe inputs, verify Elo outputs match a recorded baseline.
- **Trade-card generation regression** — given a fixed league snapshot, verify trade cards generated.
- **Tiered matchup engine A/B** — compare global-Elo vs tier-prioritized matchup selection on information gain per swipe.
- **Postgres migration smoke test** — `DATABASE_URL` pointing at local Postgres; run through full flow.
- **Mobile client Elo parity** — verify mobile and web compute the same Elo values for the same swipe sequence.

---

## Verification Discipline

Rules of evidence for this ledger:
- **No claim without a verification artifact.** Either a docs file, a script output, a manual screenshot, or a recorded test run.
- **State the input set.** "Tested on test-league X with N players" beats "tested it."
- **Distinguish smoke from regression.** Smoke = "it ran"; regression = "the output matches a saved baseline."
- **When manual: name the path.** Click sequence in mobile? Curl call in web? Specifics make it reproducible.
- **When fixing a bug: capture the failing input.** Add to verification artifacts.

## 2026-09-20 — App-open trade preparation

116 focused backend tests passed; 39 executable native session/lifecycle checks passed, including persisted startup fairness transport. Shared fairness, ownership guards, TypeScript and web 195/195 passed. Release/full-suite evidence: [app-open status](../docs/plans/app-open-trades/status.md). Device cold-open/foreground/league-switch checklist remains unrun. No three-second latency claim.
