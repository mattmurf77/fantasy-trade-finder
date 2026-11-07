# Validation and remaining limits

Runtime freeze: outlook_calibration.py SHA256 `b8eabc327fe9305dee721915ffbc70e159c26caaf58af567c074876d4e8d0b72`; outlook_calibration_adapter.py `69c26a1c5f40aa85cf553cf58f84cbccea2f746fe9ca5d940fba051a24ff1a45`. No server/model math changes.

## Focused correctness

Initial affected suite: 53 passed in 7.46 s, including actual full paired-arm output/proof/order equality under repeated synthetic pressure. Only generator elapsed_seconds is excluded from diagnostic comparison; all limits/counts and gate results remain. The captured input remains unchanged. Independent reviewer: 9 passed in 0.57 s, covering throttling, release, clock/sleep/pressure failures, shutdown propagation, real queue→both-arm completion and lease expiry preventing private publication. These nine controls are retained durably.

The minimum 100 ms work interval is monotonic elapsed time without scheduler sleeps, not a guarantee of CPU service by the OS/GIL. Provider/SQL and non-checkpointed individual gates remain non-preemptible. Scheduling errors fail open into full computation, while existing model/lease failures retain their behavior.

## Mixed workload evidence

A synthetic 12-team × 20-player actual organic worker runs alongside both complete Calibration arms in separate Python threads. The trade uses real strict route admission and all continuation pages; complete native/fresh-final/public/durable outputs are hashed. Calibration uses its actual captured adapter and all final gates; its provider capture, durable queue and heartbeat are tested separately rather than benchmarked. Seven runtime file hashes are recorded before/after. The inherited trade fixture disables auxiliary exploration/first-session/likes-you/taste/fatigue/diversity/Thompson helpers; the owner search, full fresh evaluation and actual serving/persistence gates remain. Calibration source/history is synthetic. No production load or device network is involved.

The initial pair ran candidate then baseline. Foreground first publication was 26.114 s versus 98.430 s; all 6,430 trade native/final/public/strict/durable outputs matched. Calibration counts and all non-time diagnostics matched, but the combined owner/roster proof digest differed while the fixture independently stamped each roster capture's observed_at. Those captured inputs were not identical, so the initial aggregate digest cannot establish full-arm parity. That pair is not accepted as exact full-arm proof parity. Its unmodified raw artifacts remain retained.

The corrected pair pins the synthetic capture timestamp and preserves it in the proofs. Both complete decompressed arm payloads matched byte for byte (394 v2 and 390 v3 cards), including proof and ordering fields. All 6,430 trade cards matched at native, fresh-final, public, strict-serving and durable checkpoints. First publication moved from 82.857 s to 31.353 s, trade completion from 106.166 s to 40.846 s, and Calibration completion from 98.689 s to 109.619 s. Overall elapsed time was 110.458 s and 109.692 s respectively. Peak memory was 836.0 MiB and 763.95 MiB. This single local pair measures a mixed synthetic workload. Hosted and device timing still need separate verification.

Final affected run: 212 passed in 20.29 s, including Calibration routes, service, adapter, queue, independent scheduler controls, grading lock order and existing grading suites.

Public trade normalization excludes exactly trade_id, expires_at and impression_id. Calibration diagnostic comparison excludes only generator.elapsed_seconds. The raw benchmark field first_response_cards was populated after strict pagination and reflects the last page; it is not used for first-card claims. First publication is measured independently at the actual committed publication callback.

## Remaining resource work

The reused pressure predicate includes passive prewarm, session-init pregeneration and old-league jobs. A real-tap search_id is not yet stored as an attended job lease; status polling does not carry that search ID. This patch does not cancel old work, serialize all worker classes, or solve an unseen-context cold calculation. Mixed projection+Calibration+trade capacity and physical-device delivery remain separate qualification. Root coordinates release and re-prepares affected unexposed Calibration comparisons under the new backend code identity.
