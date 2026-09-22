# Runbook — silent prepared trade inventory

Implementation runbook; release, live activation and initial sweep are **pending**.
Use [validation](validation.md) and [status](status.md), not this procedure, as evidence.

## Preconditions

Use only the reviewed exact release head after full/hosted verification. Keep the
existing exclusive Bilateral revision 2 selection and all fairness/offer settings
unchanged. The capability is `trade.prepared_inventory`; actual preparation and
adoption require numeric `prepared_trade_inventory_enabled=1` (default 0).
Use the existing audited admin-config workflow and authenticated readback, never a
direct database knob update. There is no new infrastructure or paid-provider setup.

The cohort is verified existing app identities and already known current-season
linked leagues. It is independent of 30-day activity. Imported opponents are not
new app users. Sleeper coowners retain separate personal inventories and one canonical
team; imported platforms require an unambiguous retained/verified team binding.
Missing binding/authentication, unavailable source, unsupported format and valid
empty leagues are distinct outcomes. A resolved target is not a ready artifact.

## Operator sequence

All operations use existing `X-Cron-Secret` authorization. Keep its value in the
existing secure credential mechanism, never a committed command or report.

1. `POST /api/admin/prepared-trades` with a new nonempty `idempotency_key` and
   `dry_run:true`. Optional `user_id` / `league_id` restrict a canary. Discovery
   performs fresh read-only provider requests; it is not a zero-load operation.
   It does not import leagues, write shown offers or notify users.
2. Inspect cohort aggregate reasons and `discovery_complete`. Save sanitized
   coverage separately from resolved-target counts. A source failure can leave
   membership unresolved; do not invent a count of successfully cached teams.
3. After approved activation/readback, submit a small scoped non-dry-run canary.
   Poll `GET /api/admin/prepared-trades`; once assigned, use `?sweep_id=<id>` for
   durable progress. POST is asynchronous; its response does not mean preparation
   completed. Reusing an idempotency key requires the same frozen target cohort.
4. Verify ordinary Find adopts only the exact user/team/format/fairness/input
   scope, with evidence committed before each public batch. Verify an input change
   falls back to ordinary fresh generation, without repricing old likes or proofs.
5. Run the authorized unscoped all-user sweep. Record target states, unresolved
   cohort reasons, unexpired artifacts, and separately observed current-source
   validation. Do not relabel `unexpired_artifacts` as fresh-ready coverage.
6. Check silent maintenance refresh/resume after restart on the final release.
   The scheduler resumes unfinished durable sweeps before creating a new hourly
   cohort; delayed retry availability does not mean a sweep is complete.
   Work is sequential and defers admission while interactive work runs; it is
   cooperative priority, not hard CPU preemption of a running constructor.

Preparation stores the full eligible inventory, including a genuine empty result.
Fixed zlib/base64 storage permits at most 64 MiB logical JSON and 2 MiB encoded SQL
value, including its codec prefix. Both safety limits reject oversized artifacts
rather than truncating offers; the previous valid artifact survives a failed save.
The logical checksum remains independent of compression, and bounded decoding
rejects corrupt/truncated/trailing streams. Do not increase the encoded limit to
work around an oversize failure without PostgreSQL memory/statement validation:
the former large deck-insert outage is why the whole artifact cannot be one
unbounded JSON bind. No generated-offer cap is introduced. The artifact lasts at most 24 hours;
read/adoption never renews that original expiry, and original card expiry can end
usability earlier. Adopted memory jobs retain their existing 30-minute bound.

Scoring uses the saved league format; database NULL means the existing native
`1qb_ppr` default and is labeled as such. Preparation uses the latest observed
in-memory fairness setting when available, otherwise the native 0.5 default;
a different actual request must miss. This is not a claim that every client's
locally stored setting has been synchronized to the backend.

## Failure and rollback

Provider credentials stay in existing secure readers. Do not invoke reconnect
notifications or the unrelated daily/weekly notification tick to warm inventory.
Refresh source/pick data only through the known-league quiet path. Source failures
must not overwrite an authoritative ledger with an invented empty response.
Fleaflicker's source does not attest a season; ESPN/Fleaflicker do not provide the
owned-pick ledger. Retained platform/user assertions keep their declared authority,
never become stronger provider evidence merely because preparation ran.

To stop one sweep: `DELETE /api/admin/prepared-trades` with its `sweep_id`. This
revokes outstanding preparation claims and retains already durable records; it is
not the global adoption kill switch. For global rollback, set
`prepared_trade_inventory_enabled=0` through the audited config endpoint and read
back the result. Ordinary fresh generation remains available. Do not delete
historical likes/matches/impressions or change another model knob. Re-enable only
after the failed invariant and final regression evidence have been reviewed.

No live operation, production ready count, or physical-device latency is established
by this document. Parent owns the release receipt and initial production sweep.
