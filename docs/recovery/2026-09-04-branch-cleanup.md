# Branch cleanup recovery ledger — September 4, 2026

## Batch 1: record before deletion

Status at entry creation: prepared; deletion completion will be appended below.

User authorization: clean up old worktrees and branches. This batch contains 255 local branch refs, each without a registered worktree. Current/main/worktree-owned branches are excluded. No remote branches or working-directory files are included in this batch.

Verification baseline: live origin/main `606e512cd87f692eced3b92ccadb4f0192ea3449`. The complete tree object and exact tip commit of every listed branch are retained in this main history, so removing these names loses no committed content. This is a positive content-preservation proof; it does not use a squash-merge branch's ahead count as a reason to discard unique changes. Execution rechecks tip SHA, tree SHA, history membership and worktree ownership, then deletes refs in one expected-SHA transaction.

Evidence: [complete audit](../../WORKTREE_BRANCH_CLEANUP_AUDIT.md), [batch manifest](2026-09-04-branch-cleanup-batch1.json). The dated manifest records each exact ref, tip, tree and commit date before deletion. The audit may be completed after this pre-deletion entry.

Recovery: `git branch <name> <sha>` using a row below. These objects remain reachable through main history and do not depend solely on reflog retention.

| Tip SHA | Branch name | Complete tree SHA preserved in main history |
| --- | --- | --- |
| `45a2520c36778771190ba3e6cf34e96cc6bbaf41` | `audit/armb-claims-1-2` | `d5041043ecb4876368c3fe846633ce0ecf08d45c` |
| `b2e794f94ba1f0dc37105e09d3ba61289f7d286d` | `audit/armb-claims-3-4` | `48b597ff2336ae5e16fe220bc158567b4265ff30` |
| `238cc3ee0963175f257d681cb1dfdd2000162ff3` | `audit/armb-claims-5-6` | `0d499b1381a9987761c3ce89ef1c52d7045cfe59` |
| `d6b324194f7efad0878237bf6d0fa1133186eb00` | `audit/armb-remedy-bucket-a` | `8a87d95231fd106135ae0f0b64d2d5d7af0fd8ac` |
| `79f7cc3ebdd994e9c8def2980574ff316becdfaf` | `audit/armb-remedy-bucket-b` | `b2d84bd2a83d1e52c9a6cd20d7d1a53bee06c11b` |
| `e873966e474746d127e41fb70c4a52da63e33582` | `audit/armb-remedy-bucket-c` | `27656d726de5c258c2ed1c27bfcd1849bec93a63` |
| `7cb9a25b6809770d8d08406773d9cc1572cb5d2f` | `audit/claim-7-armb` | `3d1213c37a561ffbb26544d7f3754214956b5c4b` |
| `9026da7702fcf4fc117c903c92dddd6f7c226cfa` | `audit/consensus-gate-matrix` | `2500b47ac089e6634fc2c134742166c549efdeeb` |
| `307b8f8e120e60b912d6eed7d21dbef32595821a` | `audit/knockout-waterfall` | `a9225385b6c58967c0e475be08083cf4859f40d2` |
| `63d2965d9d569f57aa4c480c5568239e6efb6cbd` | `build-staging` | `40142c7dfab3412b4c9b5c00e6b57caf19dd9940` |
| `02e27dda7446dcf5289c2168776694d86d73395a` | `chore/bakeoff-serve-interleaved` | `8692ad580f42b335efdc5bc9ebf2af8b11a573bf` |
| `4340b60473bc1ab6d39fd80f3d312ad4a6e8c778` | `chore/session-wrapup` | `697c439818ceb3faf6cfb55b727904a5d690409e` |
| `ba4a6ad1446acddbac468d94e52faf38036b46c8` | `claude/372-window-composite` | `f6320ae6ce12803d0ebff47db9385319881c66bd` |
| `eb9c1dee7029a301d4bda535f12b380b8f80ddbc` | `claude/agitated-sanderson-d9eaf9` | `23391a2d0d7d5655e703015b0ccc8708198271c2` |
| `968d9a8e13a3ba9d730bb542498f5b8d4aea299f` | `claude/awesome-northcutt-0a5093` | `431ef729f1cf5002b5032e54de63258eebc68ad5` |
| `18f15f7ad36ca988ef364fc4d0041218f7313a52` | `claude/busy-swartz-521ff5` | `544630af4d5d18e72ee6fb412f4e192e49eb6b5e` |
| `0edc7de7351a30fe0d4b8ee3068df31874bcda2d` | `claude/clever-euler-49a334` | `47f7616f0c5f1fac6ab0828533e1bfd09691fce5` |
| `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | `claude/compassionate-goldstine-410636` | `3213580b201a8b25de83a09f8e25dd243b1f90d4` |
| `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | `claude/condescending-jemison-61ad0a` | `3213580b201a8b25de83a09f8e25dd243b1f90d4` |
| `37d74b2bd15174e35ebfa6381b97af14232e9389` | `claude/cool-hermann` | `f144614882ad3ee48bedec9549efa469704a698e` |
| `0ad2fe9bc1c9f7cd69daf58aa0fdaa5de2a70c02` | `claude/cranky-hofstadter-251429` | `342c0543d82ce342d9d174c284f1666abdf71bd4` |
| `bc340607b6f0a78e434cae2552f1ae31d94c4c52` | `claude/crazy-noyce-6cdea0` | `915d07973a538bebf3a7b495a448114ceb140665` |
| `e92f95c16034101f1d1f925b6e90b27273d62d4a` | `claude/driver-setup-step-7-b50718` | `f3f7a76ecf7a00bb007ba94bb67405bed373ec44` |
| `9e1a8be1a6612ef2e6b6be99ef96bf46b2d33f27` | `claude/elastic-kapitsa-c75ce7` | `9e498480763593fb8b3bd468ec30bbb9e705e9a0` |
| `74cd664030ed2a3603a7d8a5f384e5fff7f3d836` | `claude/exciting-bardeen-3a477c` | `c8cb24b20ee725e57a2fb52a4500abeb168f21f7` |
| `cfe930018ee5ca66d5d67d679e8155d266f5d869` | `claude/festive-mccarthy-b10c3a` | `8156e9a8bfcc4f19012fd62bd5c6801e89c54d4d` |
| `867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee` | `claude/finished-unmerged-worktrees-48b67b` | `aa4596dae9cdd8d874e7828a418aeb7fdc9b4e3c` |
| `af91d6f8225d662110e67188adee1705ce219d64` | `claude/ftf-file-continuation-c9185e` | `c0e372099deb61582926514c624ebb2697cca560` |
| `c321958d77dd799087d1c556835dca0de4321b93` | `claude/gifted-sanderson-0d3ca0` | `fa3009a54c3544ecbf3dd316008988b537955e39` |
| `69dc0cae7db1cd41a522dfb7d33f280038d318c2` | `claude/goofy-perlman-490e49` | `db1666864f5e59b3a8cd9bf31ccbc759c7e97e88` |
| `d3fe3acbde5a4ce4dda42206cd2a9a848e6ee15b` | `claude/hungry-bhaskara-0e11b2` | `d721c9cc0b955d53cfbad66077635e35e5412bc1` |
| `dd893b85823614762f5d67ca269ccb4ad673f8c0` | `claude/jolly-leakey-d20295` | `e9e962cbe161498c410ba84e97c295be1076d150` |
| `355bddb3d044d502dbb86587188cd27859b7d342` | `claude/jovial-meninsky-8bf0a0` | `9eab14d276cbd0e1dd0e4382e8a608d7dd4c2d01` |
| `16a9b51d4ab84b37f3f8d4e1e98e7bbc8f64a67b` | `claude/keen-varahamihira-8986d4` | `73598ce57a72730e0492e0832d02fdedd4c7645e` |
| `e92f95c16034101f1d1f925b6e90b27273d62d4a` | `claude/league-mate-invite-sharing-26a697` | `f3f7a76ecf7a00bb007ba94bb67405bed373ec44` |
| `33496d8217e946c517f87a3526db0dfa9dd0a344` | `claude/magical-cerf-7cfaca` | `a61e7928079b4e19b28f1d736151558e1d5c2e5b` |
| `0ad2fe9bc1c9f7cd69daf58aa0fdaa5de2a70c02` | `claude/magical-hofstadter-40cf12` | `342c0543d82ce342d9d174c284f1666abdf71bd4` |
| `5dcf29f00f42ceca2351aa130074012ae7ea8e0f` | `claude/modest-albattani-138a2d` | `f60f2f7197f78a11ffaeff0fa21dc4972ba76bec` |
| `2f88aaba4cd565de335ee3ded2f9cc339b4cf089` | `claude/mystifying-williamson-4595ad` | `16725f746905c8a0a0a8b178ab1dec9fa3107169` |
| `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | `claude/nice-lovelace-83e5e8` | `3213580b201a8b25de83a09f8e25dd243b1f90d4` |
| `a40eee89abe4ed0585e0bd5a58a43aa84bbd2385` | `claude/nifty-shtern-6dbae1` | `e671c3dac75e999a72b9a8f9da52de8e89488401` |
| `628f7b6001e78c2c1fc9f264af6e4723b87aad64` | `claude/notif-crons` | `6f22aa6ce1037d561cdb470b95c73a8dda0fe603` |
| `1dd94681ebd748d99e4233486df86ed0212aee6a` | `claude/notif-events` | `4c4ae8ecba4762a2bb5455e9b9c06c615098b082` |
| `c7e756662f82fe6d48a0e03e6f73240b2d34fbd5` | `claude/open-feedback-summary-b43796` | `081ac48384349a1e591c7924a18f85fd9a7c446f` |
| `e92f95c16034101f1d1f925b6e90b27273d62d4a` | `claude/outstanding-work-summary-b10a36` | `f3f7a76ecf7a00bb007ba94bb67405bed373ec44` |
| `2529bef953c2a3f116fffe7b71fb4f4173695225` | `claude/peaceful-lumiere-e2a25b` | `3ba23b3d55f9ab0114bb678d9d53ab862a47f2ef` |
| `0edc7de7351a30fe0d4b8ee3068df31874bcda2d` | `claude/pensive-kilby-d53555` | `47f7616f0c5f1fac6ab0828533e1bfd09691fce5` |
| `5e758d66433a6ca5613b235eba6cc3c1e678627c` | `claude/reverent-gagarin-ff2b57` | `74cbdfcb12a7da8a4f10df1ef76273b1dfca0562` |
| `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | `claude/sad-brown-d5ef76` | `3213580b201a8b25de83a09f8e25dd243b1f90d4` |
| `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | `claude/sharp-hamilton-2ec655` | `3213580b201a8b25de83a09f8e25dd243b1f90d4` |
| `e89eebb0fbedba03584b4cc99d0399f38ccf96e6` | `claude/shoprite-grocery-cart-de3c37` | `1879146521e9ec5afb2350ab6619b8834538e903` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `claude/strange-jang-5fb4b7` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `3e7e25cff497f006826664de4f2d187a59771748` | `claude/team-outlook-experience-27a7a1` | `d434a673bbfdd3f949c06d76d2c3f7c90863126c` |
| `9e1a8be1a6612ef2e6b6be99ef96bf46b2d33f27` | `claude/trade-decisions-review-6786b1` | `9e498480763593fb8b3bd468ec30bbb9e705e9a0` |
| `af91d6f8225d662110e67188adee1705ce219d64` | `claude/trade-disposition-review-89a94b` | `c0e372099deb61582926514c624ebb2697cca560` |
| `867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee` | `claude/trade-verdict-elo-discrepancy-6e5606` | `aa4596dae9cdd8d874e7828a418aeb7fdc9b4e3c` |
| `451d2ebd714033a3b1f6bba3fc1b939f9d086efb` | `claude/trading-engine-eval-8ab7bc` | `697c439818ceb3faf6cfb55b727904a5d690409e` |
| `30070f3692cc08cd5dde8c96da2877642f4f73ca` | `claude/vibrant-allen-023c8f` | `6b44245d0efb4286228525cd3406bc8b128987f7` |
| `33496d8217e946c517f87a3526db0dfa9dd0a344` | `claude/vigilant-wozniak-382289` | `a61e7928079b4e19b28f1d736151558e1d5c2e5b` |
| `867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee` | `claude/wait-instructions-ef2095` | `aa4596dae9cdd8d874e7828a418aeb7fdc9b4e3c` |
| `a93e5d861d94d220c423457afb4a88f8efb5eeb9` | `claude/zealous-rubin` | `5691b5bf035b133de63673a9b79b5da380ad6e89` |
| `606e512cd87f692eced3b92ccadb4f0192ea3449` | `codex/security-data-hardening-20260904` | `ad663e32c2049ad5a46bdfaac38aa245d98b1aa6` |
| `950fc9795951114aae6fb51e67e6dd78d522a24f` | `docs/armb-audit-consolidated` | `534f58288a76e15bd09a375f473dcf2b5d834443` |
| `613a34c3f55d4bd060c5b5ddf6a59a6f74e52bba` | `docs/auditor-handoff` | `b866d97f1b9a4e893a52cd555fe52e5511240dde` |
| `4c0213b2a52f20e9aea7817aacffb703da39a9e7` | `docs/session-memory-writeback` | `8a41119d6a84f9825795b9a8ebcd99865c329b0a` |
| `38806e0328792f9fae70345244112ea8b661bb34` | `feat/bakeoff-arm-a-challenger` | `b4d7bc2511a16b40271f1c2cb06ceed9537c1ee6` |
| `bcee58a2c699bd004a28f226abe2e44ae2aea66a` | `feat/decline-reason-player-pref` | `d0d0741949921c6bb8deb0ae469a599e8fec4bee` |
| `2fa1ff24f0ceb143d7b23b79ed5ea874a218a619` | `feat/espn-credential-verify` | `9b7aff83ba0ae5ea5dab828913d080ab42d33374` |
| `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` | `feat/feedback-backend-route` | `547ed15e6843b09c31cc393921fd9a1d8d81efa7` |
| `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` | `feat/feedback-mobile-sync` | `547ed15e6843b09c31cc393921fd9a1d8d81efa7` |
| `23b19cb527c5693be797f87f6bfb0e2d1044299d` | `feat/fleeced-identity` | `8e09b834b3765687aa0b677a8a3a0827ff565f94` |
| `a362a15ad810b579d73940ffa0a485d1ec55ce86` | `feat/light-tier-flags` | `ec73c5faefcbc62421b44970399a48e3f9742644` |
| `3af201ac7ddd3f18c58fe0f6d7c7fd39c9ccfd4e` | `feat/mfl-send-integrated` | `307a9cf736726aaf30bd4b3fa4a15d4f28b0d87b` |
| `0e0095f22ac1516543c643194b11e5a9d3baa0ca` | `feat/mfl-trade-lifecycle` | `046e5128326547795f57928836efcf48d7fc88ba` |
| `2105d53ba54ff16518631065c704dd868b3e6fc0` | `feat/pick-slot-labels` | `5c8482bd16c89b32240fa4a9084ba2c5b6931394` |
| `8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4` | `feat/pick-year-decay` | `ce756d3692f885439eaf53f65c6ad8086001f367` |
| `8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4` | `feat/pin-tier-clamp` | `ce756d3692f885439eaf53f65c6ad8086001f367` |
| `7f16217bf223b4307ecced5e074334d915478f2f` | `feat/placement-tier-clamp` | `31fb10f1c70faec50a40d32faea1ff0a6ceb4760` |
| `3293f4aa1a9f6cddacce998ea0793578e31422ae` | `feat/platform-unlink` | `4cd925be5b8fe746995c388003266c3832486a32` |
| `e1532a71ac8d4e82f8c2e5d6c745153dc169376b` | `feat/round2-pick-recalibration` | `f8819054b3014cab76cf67c40b872e237fcb6719` |
| `7315d8c62ec30ad47f2a27fdc7d6cbf5ef84aa05` | `feat/send-auth-lazy` | `371965165755be35a66e3aeb86b1677c1958707f` |
| `f89d8805c4ebd436705f5d59da1edc4fa9c2c82f` | `feat/send-in-espn` | `0a8d54cb088b8c5cd675e40605137b27f3001e41` |
| `5cde107fd79b4753e02c3f14d80b6ab0d322b856` | `feat/send-in-mfl` | `e5f320a5bcac3724332b2a9240e98629f0feb3e0` |
| `45fb2cada5645f430d3b5241d77a11e78a6bb531` | `feat/send-in-mfl-followups` | `6a558290b1b217f7cb6c93df108ea756f734e6e7` |
| `3b64a4406d7fb9877169f9ae5ed87bbc7f4d1d3c` | `feat/sleeper-reachability-probe` | `dc6b2d7620cd9507a2d84502fdd24e25f7ad5726` |
| `f56216e5931d336051648b889c23700ce74a1398` | `feat/team-review-batch-2` | `a6e17a6812e2e6ae070b7dbf1b4a23940c0427c2` |
| `e423f602d8b795c442535b87eed6fdadbe83883f` | `feat/trade-presentation-v2` | `e515cf35b176e353e58d04cd0e07db64e967fdbe` |
| `bbc2e4b166925c4417bb5ec559a9241354b1b9fb` | `feat/window-composite` | `c52ce7fe948401be894289311e32cf58882832cd` |
| `c21c52071a0b7e89c317d2cd6d7b7643cd77bd62` | `feedback-batch-2-base` | `befee60b6c6f02eda18b4a1f677be455387e8658` |
| `bcd64e8f15abf70a2c33d8b8589ceb61b85b5c29` | `feedback-fixes-2026-08-08` | `1333100ebbcf1f6b506be284f2f55eb373e2069a` |
| `31793d2326c549a17975afe9c0269b386f1967a2` | `fix/armc-gen-v2-forfeits` | `a2c79aa551503e77b7812ee979520b565960de58` |
| `6f8daf407c51680188ada8063ab04cba24eb1cb5` | `fix/bakeoff-outlook-lane` | `f16f4dd0341ea3c57705cffc10d67350613231f7` |
| `d755b3b95a62db2d8c186ff2392758d298c3a60a` | `fix/balanced-claim-fairness-gate` | `2aa139f8ea163f102f046e34ec851af382ff19b8` |
| `a53b14259f94ef0d0eee487ff91b05879ce831e6` | `fix/deck-give-headliner-cap` | `fe54d99f62a87971f0c296eded1aa06cf98b9ae3` |
| `7dfcd168d5e7fe0609e2533d779a691c41e09a43` | `fix/espn-verification-oracle` | `af9dab764ef855cc423390e1c9a0fc53cb56cc4f` |
| `bda0d51844b289dc509f84c71c8a44a15f742fac` | `fix/finder-conditions-and-partners-copy` | `40142c7dfab3412b4c9b5c00e6b57caf19dd9940` |
| `c451065c583d7313bc72dd73ea9df2dfca0037af` | `fix/launch-privacy-legal` | `3338763228976ee8ed40e188c399d839d7629693` |
| `7110af216b5037e1b2105bae149a4bf8ac66e208` | `fix/likes-you-quality-gates` | `04ae08b81e9044996b719c300fd28c93064b8dad` |
| `fc260dea52f39590f4e8b3ac100e83a0d4a5c424` | `fix/pick-assignment-missing-user-team-clean` | `5c138af3a1ce940ac7811f37958044a854908dda` |
| `2009de5996ed103530245ef8f695715c838bb885` | `fix/pick-horizon` | `fca6273c3df4825a75176929adaf921bf80fa697` |
| `e777e9d4f1165d5aebf4877a7b101fdc60153929` | `fix/pick-round3-value` | `7046ae170f673bce451ea2e116e487c82db2ba9a` |
| `50e0451d4db14f91535479c84ae9a42113037900` | `perf/dp-single-fetch` | `7325868a227d1b7bad9595f8fdd13651c3d765ee` |
| `33a51831a3d52f14a6b6661ea30432417ce95508` | `rookie-draft/qa-flag-flip` | `da2f2c02d6dc13547cce1c45f47ee73022f12813` |
| `ab9368f81aa580a007cc49c91240754206d3e1ec` | `session-2026-08-10` | `38f5709dd126a783f2e48010099061a1c942ed4e` |
| `ffd55f84ade5f8d248cfefd9c1e306830aca186d` | `session-2026-08-11-169` | `75f1bd3645f821b81b91c7ade0d0c9177f4c6c44` |
| `fe191f6605d23a2a5252d8c445769ba20a321864` | `ship/analysis` | `9658bdd220c2df333e03208f2d4aa39c4cdf0190` |
| `24be3956f98d7c4cd4c4bd9285b64f9f8a6fd7f7` | `ship/armed` | `e77e9879d3b3c64168bd26f533f799d4fc581694` |
| `579a9e3db984a77b592bf0dc6966442bc47622b7` | `ship/bakeoff-dark` | `7a8a7d3dcfdc66a7f6cb7f2805e79c78edd66d30` |
| `a12240657e6d7442acc309766a6e8312e7ef8af1` | `ship/bakeoff-interleave-on` | `2e42f2704191430f4d4d3239ea8dcf8aa08b4a2b` |
| `1bf064572ee79db11c7ee7ad84be6e4de6efb5b2` | `ship/co-owner-ledger` | `1289bcf2da349d1ba8f51adc018a725dab3767a7` |
| `a7f8783ee1ae84a942b21025a3065704ef616cf6` | `ship/composition` | `ee067957abac3c6445fe617a0bf5a3f4cc124715` |
| `a12240657e6d7442acc309766a6e8312e7ef8af1` | `ship/disable-presentation` | `2e42f2704191430f4d4d3239ea8dcf8aa08b4a2b` |
| `a130dfc2e4b0679f3479f1ba84c5fbd77fa366dd` | `ship/engine-batch` | `93b4d4da48d407d9db0146e544281d6ade8b504f` |
| `28c12a0a6b71212cf7f957d716c1f9360b6a5984` | `ship/four-fixes` | `bac5774dfe5b7dd28f429283cc15b2297c7e21ae` |
| `19f6fe87ec5103307541f53cad43268e93dec29d` | `ship/mobile-1150` | `60aca79dfe0b083a03b9fa996eb88a10f30daece` |
| `16d277f5c12a8d1c36b36534b74ac1cabe0df0a3` | `ship/pick-fixes` | `98f3467dbc6a96d2f77a6597a2720b81f547808b` |
| `8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4` | `ship/pickyear` | `ce756d3692f885439eaf53f65c6ad8086001f367` |
| `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` | `sync-main-temp` | `547ed15e6843b09c31cc393921fd9a1d8d81efa7` |
| `ca2b26aad6c695a662895fee8c5108fd291af200` | `trade-engine-v2` | `ef9a1f2e42fd55de996cfec8dd437512ae877a0a` |
| `bb3636ea69c88b515b942f22b4065cc6cc1e220d` | `verify-batch-2` | `2138311a6ef9b4a74d62a24f8414cdc4e19fcd4d` |
| `1580064cb88cb2f86f0264b03f76d500e2266984` | `worktree-agent-a064c586eb5fd3310` | `75e40d2ea6aaf0ad556e6b00dbb3e7bed1822f12` |
| `791a6df3e4307530e7e823be60183a647b298425` | `worktree-agent-a06e7515c090bf5ca` | `d5b41b8227d7c4c690e86cec339de10888b8f384` |
| `ab9368f81aa580a007cc49c91240754206d3e1ec` | `worktree-agent-a073f9cfc8b08f4a0` | `38f5709dd126a783f2e48010099061a1c942ed4e` |
| `26f76f3baf7827ea49dfb001a4418f1ca669508f` | `worktree-agent-a09286dd2a0cefc88` | `ab8da31fae6f5053d77e5d4cbe75db1bbec2d2f8` |
| `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | `worktree-agent-a099babc74eec6d1a` | `e5533e4907df0480314ff1f963619d9f481c7c8e` |
| `f65bab75adf3a949c82402a4f0c6767166bcb142` | `worktree-agent-a0bc3ef65ca534b5c` | `789ea1f8df9ead38ea4dd664dd0c6cdca4324db6` |
| `35b63fc1dba4948ee7afb908cfaf401bbdc92e56` | `worktree-agent-a0bdfe68ec9ca11b4` | `5a41487cd4ed9a92a9ab18a5be319070b8b70e93` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-a0c99997` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `7d259d43936cf840b8c5987714162975e1308eac` | `worktree-agent-a0d2eb20f30acda42` | `033e15cc847d11093131c18ec2b449082c1285e2` |
| `3612d4331921c1e05dfe885a8dcd5c857db606ea` | `worktree-agent-a13566f6f2eae60c6` | `eefd55cac3dcd26169e434eae68846d507afae6d` |
| `09a157620e25bfd9e0d8a9279787594012f692fb` | `worktree-agent-a144f20a6bab9803f` | `dc62b9c256d92ff92f772532ac06106bd260e612` |
| `77b4a5033009c956f8eca557b920b401bdcbeb76` | `worktree-agent-a150542a25adbf68e` | `37cf3e2aaddb86fa73713fc0c83b3b7549df579d` |
| `36618be8e1644047fd2e6037e359fde567c5d889` | `worktree-agent-a16b8c9e20f110454` | `9ab5374a28bb3c05b91b4152f76b5c5dce507f47` |
| `bb56c592bb76ce475e61f59ec9a53e06efbc82f9` | `worktree-agent-a1de9f7cdca7d4cc9` | `5c83d0b22d4d99d39f3b5759dc531ffe3a6d3b94` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-a209b4b5` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-a2472651` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `31c77310f4c19a9574bfa8954dd9b5cb06599df7` | `worktree-agent-a25635d5055222d04` | `34a69a0ef1eeade44c29135963cb6d0915c83de9` |
| `ab9368f81aa580a007cc49c91240754206d3e1ec` | `worktree-agent-a2831e3434378f02f` | `38f5709dd126a783f2e48010099061a1c942ed4e` |
| `ffda9af2860eefd74534a1e52be4d7d50c727e7d` | `worktree-agent-a28505c47f2b4ed52` | `81ca978d0aeb8e2251f1e8df5e52c25cb43ba96c` |
| `0eb1061b16c1bcf1ccdc6568ef4fc11cfe605f1b` | `worktree-agent-a28555e49939cb179` | `c1a75b6c4e2e17331d337124948c5e91222fc674` |
| `deaa6b27fcf3d084b0ef1f3fa3c0af3b295d6db6` | `worktree-agent-a28a3f476f5095e4e` | `9ac4934f6ca8402896962c4673cc4051fcbe6e38` |
| `bcd64e8f15abf70a2c33d8b8589ceb61b85b5c29` | `worktree-agent-a28d45a9c473696b2` | `1333100ebbcf1f6b506be284f2f55eb373e2069a` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-a2953877` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `68920c3fa0c2195b6b9ea78c52e224dfadfc3f3c` | `worktree-agent-a2a643a810416fc64` | `99005be637b23893f93fc67a54940f39a861966a` |
| `6c008c31db12662fa8a453e7d88390920a1d42a6` | `worktree-agent-a2c3e26232f8d0fd3` | `90ab9b0d3de200e562f3df5c9b6c3cdf427f8736` |
| `0106aba4847ecc0a90241411390b2516d3f20fb8` | `worktree-agent-a2eaddb5b4dcb9f75` | `86a5099e1ef92181cffa77ed089698fcbc6c39ef` |
| `023f747a7f5d8fd7590fab82ff836b1f9d6706d8` | `worktree-agent-a302dd30809085cce` | `e62d6729e95119e62447c5bdfdd3c6712553931b` |
| `62ff8d68221ce126f405e0fefbe9bb90b28cce45` | `worktree-agent-a3079a842e541927e` | `6e4972544cd95e64682ebd636f1876ac6c07d8cc` |
| `048e918c7cea52acfc8ffddae089d7655c994b1d` | `worktree-agent-a30c874ee2bdc0aa2` | `bd9ee2438ba0ae70f013ea322ee11402615d910f` |
| `78d4bb399fb51ad1e10f1b9236debe84642f00a6` | `worktree-agent-a323bd5a940b685f9` | `343b3d5c74b21100e871c23b0b55e0bca1059627` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-a3373f13` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `f01ac9f80e8b2bdd8e799fc22ad9cd945229bde6` | `worktree-agent-a3528c7ae653aa236` | `a745df8d3f5b9890748ad8c662d597c3d8cb5e9c` |
| `e263490f46e38a6bb15754fda14f04db6f6a58d9` | `worktree-agent-a368c8b0276754b90` | `62a30d58c771579c396232a5023eb8307ebcc593` |
| `fc260dea52f39590f4e8b3ac100e83a0d4a5c424` | `worktree-agent-a36aaf8ad623b3be3` | `5c138af3a1ce940ac7811f37958044a854908dda` |
| `b2bd07894a6dd67c25f21f0c2dc036332a75afc4` | `worktree-agent-a37f0a74fe2ac8b03` | `0cd5e792349882fe9c3f0492f54448ae4f6a2c49` |
| `ec25407535357f4ddf16aa8f1f9a97bb1cbe6cdf` | `worktree-agent-a38bf08560c27a579` | `b62135956f331ad6a94a12a3e67219565f1487ac` |
| `f7430c407fff14638ca771107efeee3466a71c0a` | `worktree-agent-a3ea3b1d38e084930` | `b383e524637e6664a823cb4320069fcf505ac442` |
| `572f5aa26d96e9fe75c1f643832ca824c827b921` | `worktree-agent-a3f099488f9a82ed1` | `93b092b88e5738c23a6ec8030429422576307efd` |
| `7758a13c437c1267b261535e80e659a44835e87e` | `worktree-agent-a3ff0ef740318af5e` | `05c45d0f52104ca67e7d09a2374a65bcacfa3e81` |
| `5ccffbe91fd4eb24601c7a677770824924976da0` | `worktree-agent-a4ab94c51456abb78` | `1171030ba16be6283b5300f3f7b92ff41ebc6c28` |
| `57bd316aa980e7f76d760e2439751046d027a0d8` | `worktree-agent-a4b70cbf41800d5ca` | `732606df7aa7cb6dd8aaf2b5502f6a50b7b054fa` |
| `a1c1c26bfb7196734e944a62dd9820992914131e` | `worktree-agent-a4d512969948551d8` | `4eaccb1c67c3ed38a5ac82ad436a964ecfd5c240` |
| `d6e867d2cf3e45b5748856abfa3f865f56fc4aba` | `worktree-agent-a5287232297d9fc77` | `d0899a8566ab5baff46e78745e3894abe4a744fa` |
| `c198e61253f71c908462e267803425bb02f561f7` | `worktree-agent-a52b467fa9f45f7da` | `8f07a43897c67de7481eaf851cc3be0070151b78` |
| `4f3b1fe63876ce664722131ff873a04ef759d30a` | `worktree-agent-a5391ce09098b9c73` | `9ddd09c3cdc87e8205c130ebd94c41df4533d93d` |
| `715017882b6fbb79f3fd9f86bf97796ea3f02b24` | `worktree-agent-a53fe1fe4f7a84b07` | `3fecd49ee4d940e2648e41af7ef908d910356533` |
| `a3152d48b66c8f28b953cf6d46adfa96a071acc2` | `worktree-agent-a54190da471e3ddf9` | `d9a8e7e51ddca9b77d810fac824ab6c142df2e6a` |
| `2b8eccaf636217155f4cd94f3046d7cd5ee0d280` | `worktree-agent-a556441520fcd3c9c` | `34432c49b8f076fc8c9e267101eb70fe68981be9` |
| `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | `worktree-agent-a55e79db9100f2290` | `e5533e4907df0480314ff1f963619d9f481c7c8e` |
| `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | `worktree-agent-a59705cabd6f6c62d` | `e5533e4907df0480314ff1f963619d9f481c7c8e` |
| `f5e8ae5f76af54b98c06dc7b52c3eeade6f6c3d0` | `worktree-agent-a5a06a944cf8dedbd` | `2271efd7988006ae782bc04668a639dc662c1abf` |
| `ba78631e1562ddcf45ad6358ce047289bcd342ae` | `worktree-agent-a5c128404456a4b8e` | `e4178d2e5111f926a72bb3202e63f392f3fc1ad9` |
| `b5242ea33c47b90353a3adc4e554d4ed80a94746` | `worktree-agent-a5c3d72a8892d8be8` | `ae37cbe3bf01dafa81497b7293b7864812b5ebf7` |
| `54e199ea22450e77563959de266ac79534bbc2dd` | `worktree-agent-a5c985a3fe89fb27d` | `a4ec2962a420813ca2fed48732fc601e72ff2599` |
| `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | `worktree-agent-a5cd4e9707c993055` | `e5533e4907df0480314ff1f963619d9f481c7c8e` |
| `2e4ca17aae1421f2f032c616dd28a4fd8c32ecbd` | `worktree-agent-a5dbf1a5a83fba809` | `95507406cec77e653911aeef7d68c525157ea3ea` |
| `eb9c1dee7029a301d4bda535f12b380b8f80ddbc` | `worktree-agent-a60b48a57928d5895` | `23391a2d0d7d5655e703015b0ccc8708198271c2` |
| `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | `worktree-agent-a6190fadbdb2acebe` | `e5533e4907df0480314ff1f963619d9f481c7c8e` |
| `33636ec12a9a6ea02bb434a6b49097fae0dfe0a8` | `worktree-agent-a670c42a14aa79fba` | `a8960e84fa93820c005c57d878123963feea3d4e` |
| `93229e3d09baeb2a86059769c166a8220436a0f4` | `worktree-agent-a6a9a0b3a6b20d104` | `e60230fa34b25f8e384daeb36bc102f9ce595aeb` |
| `c22e7311d2bc3a575077a69ac444ce24ffb640ab` | `worktree-agent-a6f676d19f96310cd` | `c8f866dce00de3b9d79d3d31de618e7ae6106995` |
| `5ae45f2bb31cbef0a540ea106b9ee3343bfa8c37` | `worktree-agent-a6ffa39f8ba6a8814` | `238a5b8e0b9418557efa1e491674b48144bcfdee` |
| `332d9b551d449a48a98535d85dea25eb4a249fb5` | `worktree-agent-a7071f4335335f4f5` | `5e8946fae0c84b234380534d89491475e3b3f603` |
| `53bd19f696f7dfd3be01fef8aea248bba49c80d5` | `worktree-agent-a717758e4fb09729a` | `c4a7990c8805ac6a7495a8e403f3dcb5ffed651c` |
| `01962ce656c3f9f461bf259b0b67d5cca167a50f` | `worktree-agent-a745688e80fa5caa9` | `2699f079128fd8069847136597693a81759130c2` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-a75a01fb` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `6577668859c6d97f2412eb2f856ec9dd4d01777b` | `worktree-agent-a762a0a5e278cb792` | `3157d1640203f88e3064f539006aab679de63669` |
| `03e3e38c91039cb57f5703323a729c04a4ff2225` | `worktree-agent-a77c43dcc4f3b0197` | `12c5d5ebb2a38ab97478981d6e79fd43437db974` |
| `6f2ac9566a99fc921f9cee022643e77e8c9ccf40` | `worktree-agent-a781bda1e318a3477` | `b38786cb2fb11047ac02378c91db1210f85e2a96` |
| `19ccf9e811782064d66eea65b070d88880cffb39` | `worktree-agent-a795927256b2f29e7` | `76e4cbb0d12bd45a2deeda73aa2fed835ce6081d` |
| `bcbc46f2e5576b7f3e5e5868ae38b94fba3694e2` | `worktree-agent-a7a973b4596ade6b1` | `ee457b4661a86d26e6b43608d99bab4c23f68b47` |
| `0a7f791abb96b79fc361ce5cd4fe10b621143595` | `worktree-agent-a7bed877f805980b0` | `649de274384651daf882c86c6fc032a0beba4eda` |
| `0bc98ffc868e964aa212de0007e85cb683a8c4ed` | `worktree-agent-a7e7c39e9775a0f73` | `ee83b67c939e8b05248b550f0e19227bb9316fce` |
| `affd0869a4bbaccc69b4dd8a0e574560ab0b856b` | `worktree-agent-a7f0838e43f31b457` | `1a1a8ebfce323024aa1b9842747170720eec8859` |
| `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | `worktree-agent-a8194dbbf32434db9` | `e5533e4907df0480314ff1f963619d9f481c7c8e` |
| `a8898a7a7d9cc67f5cf3b81d451c64ed698a86cf` | `worktree-agent-a8213859c9ad5c121` | `340b10d3c7eb76d35c20c8809e7e8913f3ef5518` |
| `4795a219030523cb83614b241548ee1ef0a7ec9d` | `worktree-agent-a838fcfecbdc8645b` | `95feb85048a16b9bac6b5126bce333aaa47a7164` |
| `ab9368f81aa580a007cc49c91240754206d3e1ec` | `worktree-agent-a840269e071c723d0` | `38f5709dd126a783f2e48010099061a1c942ed4e` |
| `19dc31b40529ef1c828ed8e52d6839aa817d2751` | `worktree-agent-a874d90a1a9da98d0` | `566cb9f009ce7315f82e4cd19ecbb7dc17833726` |
| `53bd19f696f7dfd3be01fef8aea248bba49c80d5` | `worktree-agent-a8c67b5203e41c78e` | `c4a7990c8805ac6a7495a8e403f3dcb5ffed651c` |
| `5b2dc5f8b3515cbe231bfe24d3fea22bf1cd17e8` | `worktree-agent-a8e7a7cd54b0167e9` | `2017f339cd2715115a85e479082e79eedc5d7698` |
| `eb9c1dee7029a301d4bda535f12b380b8f80ddbc` | `worktree-agent-a8f35b1a442cb2147` | `23391a2d0d7d5655e703015b0ccc8708198271c2` |
| `bcc54af21b97bc723890f9684fbff083b72cf441` | `worktree-agent-a9064f78118fe3182` | `e85618107945faf41d2cc73e05b142aa6e904f4e` |
| `4d7184aeaec8f2a768406b4872b4daede1228b17` | `worktree-agent-a93ea1c02c0aa67a6` | `1bbb8ce5fcd7e8e8d35b1c643e24f17d0c7f6439` |
| `da09db224cc3ecdd9d3a23ae2cc405e56ee9cd67` | `worktree-agent-a94f79872cf3c2956` | `25c90b861eab486bf6609e10df127062d10d75d6` |
| `5ec0f6a4119ce23a0a4ce4790d839e173d2514d3` | `worktree-agent-a9929996116eab11d` | `c61f8a37bee985f20d328d28e8ddf49c3216c8f4` |
| `53bd19f696f7dfd3be01fef8aea248bba49c80d5` | `worktree-agent-a9a2270cdf24df420` | `c4a7990c8805ac6a7495a8e403f3dcb5ffed651c` |
| `fefe72fe5d6cd72e71b7fbc6b7f1ec0484f22821` | `worktree-agent-a9b538e94beefb1bb` | `4b060a7f3f4099436c79644a594930a010ef7451` |
| `9e7dfd4ca6a1b2f4608d38eebac4b6940919234b` | `worktree-agent-a9e7150a335178db6` | `06a6b974d4d433b62a95b2dbd0ca0106a6096e9a` |
| `cce3895fcaafec47dd4a1c4dd9b8588fec9cedcb` | `worktree-agent-aa22a939b267fbed4` | `f7a12bdadc9baa706d2e75b209ceefbffaa3b41d` |
| `5b01e397a152e62b9b4d0101d05c989fc49d512d` | `worktree-agent-aa44d177d8f47b9fc` | `772b5324437970d230f1bc783bb60a6f366eb88e` |
| `67b4a439fd59bca4080af1ac424d8928fe5f0c9c` | `worktree-agent-aa51708f12ba44358` | `91aa6f274eca6f297930d619d64dc15d68a5fe45` |
| `ab9368f81aa580a007cc49c91240754206d3e1ec` | `worktree-agent-aa9087fcaaa04e2ac` | `38f5709dd126a783f2e48010099061a1c942ed4e` |
| `2e3f61f5096a9e53f172bbf886f0a8ca42054bed` | `worktree-agent-aa9f436167ca0131a` | `436a01527d3e1d768f03292d544e2e8ad7255acc` |
| `c0e99ba4e324e9bee2bc3a8d8e9c1c8ea8029d69` | `worktree-agent-aab1fb2eaf05f2174` | `90a2af42ca33586df116fdc10fd363bd1da4bd77` |
| `fbad804ac30324c280313fcd593a10c6f256b19d` | `worktree-agent-aac10f493d748fa5c` | `ad85fa2506fa93ad14dcd45660165f08cdab7ffd` |
| `3b785f9d4ec172e3f30bb16e5d445c358ca85b47` | `worktree-agent-aacfbf4446690cbea` | `69cf43ed5fd77afda0be195077c77b7c86d00382` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-ab0fb0a7` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `22d3ad872bc71cd02fe16e3cd3b97c08b229d38a` | `worktree-agent-ab1657e4739bfb5ad` | `764867741196fe0c13054040a00c103064551587` |
| `4a4b6718f8d69c692138a1fdc7e41b5abeb77c89` | `worktree-agent-ab2f89d27bbf14bde` | `51726257ba5ce728e88a6a8d3a6f1c6d38d1b2dc` |
| `ed0c4539207ec34ef428cff45bfb7ee64490ec56` | `worktree-agent-ab454ff44a5679193` | `c2e24e5a7c5eaa4db2aa4ad28a2f218b1bd90fd9` |
| `53bd19f696f7dfd3be01fef8aea248bba49c80d5` | `worktree-agent-ab7db2284f1a23a25` | `c4a7990c8805ac6a7495a8e403f3dcb5ffed651c` |
| `d94988a86d635cbeaebfcbf11af4e97c2260d83b` | `worktree-agent-ab82847f1df895787` | `35b600d7d67d9684d737e6ce96fac38f77318803` |
| `0d8d7bbed9b204704b4f9a02c996cc6a268b7472` | `worktree-agent-abf2d752f509e445b` | `4d3499937b60261537c1ac48a662c027168f3e97` |
| `0e997243358ea5db090a4fe44bbef9d7d7902e09` | `worktree-agent-abf3b3a8687622967` | `04b98b959ddc600c78e4c5589bc899e0c988828b` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-ac1556ef` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `8b44a5db9893cb768102b316fa55e7a28166ef09` | `worktree-agent-ac51ccfd88e45a7e0` | `f5d6f85c9a708966b822ef339e4a2be25c065db4` |
| `fbd556116724e10726899e43a4d7d084f96f5669` | `worktree-agent-ac625c4f4e8d21b0e` | `e71284b890bfbff9f8cb2a0f0cfd2128c0279c5e` |
| `d89a4ad3b82cf194b62b15be7774b58482f252b2` | `worktree-agent-ac67214a25c77896d` | `8ad13a93521cad200d74a9e4c296e4a20cd0bb80` |
| `18f84288d9ba126e46c834ab34ba9a000cb820ba` | `worktree-agent-ac81596c5b45c68c9` | `5c2f0924afbba7778c8992b1bcbd23175f129769` |
| `d44200f23f9f4cd65633f3ff5407098d31c2b334` | `worktree-agent-ac919199823a00f48` | `813ce6e2911677349247ef10d2327975e7d5a472` |
| `ea19d4b75cc9de1bf33d48d615678b8bd8356715` | `worktree-agent-ac98e8e8cf1e59684` | `9171318b1ff283af3b3cada781117ca267adb8c0` |
| `0e6cffa966f4edbcd5ac49ac5b47ab7e0d91aa44` | `worktree-agent-acc5272eb7eb24e4e` | `757601415a32afac725ad0c89fb7ac489ba6c418` |
| `e1309beb8437bfb2b0e8a34446c86a86efc44e74` | `worktree-agent-acce1e33b7aef0abe` | `25b058c164cd2ecafecfb985e18eedac275f0b4d` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-acfd5ca9` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `f65bab75adf3a949c82402a4f0c6767166bcb142` | `worktree-agent-acfebfb1bbb7e02af` | `789ea1f8df9ead38ea4dd664dd0c6cdca4324db6` |
| `0848edd907c3bf5bf0982e9bf28a651e11e88ea8` | `worktree-agent-ad5be481f59c206d2` | `090e60635637b78f0fb2a6c6c1c6e357ebc00479` |
| `0dd3b0e4d34dcea27e0568b74932c8a82e4babc6` | `worktree-agent-ad81d6d15fc57b088` | `67ba931456af90d02b32d78231ebeb56697d7140` |
| `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | `worktree-agent-ad8eb8ca` | `21eb490403ad078c7f9c4656bb4fe1f81ac067b4` |
| `be56567ec52efe4a92647bfd0b2d200e78c251bb` | `worktree-agent-adb355036fe847189` | `b16614f21e67708645757cab35e19c2468e2fa5d` |
| `16b1dcb3fe9b4d4e20bc18eb9fc4dfb2c9c20510` | `worktree-agent-adec00ae3a2e7dccc` | `0326294de4f9c79b605e74db1950cd2a091a7663` |
| `c5f6f9c4aa274acac261d7fd77fb82d6db3854cb` | `worktree-agent-adfd16bf190678bcd` | `f4bacaa16557b3d52ad2e6adb181241f4527959f` |
| `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` | `worktree-agent-ae06d26a381e039cc` | `547ed15e6843b09c31cc393921fd9a1d8d81efa7` |
| `e297ea860f72d91d1bb567943143834bb5ab5551` | `worktree-agent-ae2f8898ea0b703a7` | `f2d4e13fda448935724f2f33eab1598b36913cc7` |
| `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | `worktree-agent-ae3050bc4e4ca4e49` | `e5533e4907df0480314ff1f963619d9f481c7c8e` |
| `52be577e7320b69116215b57505d3c076c2577c4` | `worktree-agent-ae33eec5a00d24264` | `35275ea623b8938a8f1c978b88d30cc94a2e3db9` |
| `618a3d18313b347c234b847eec3f5d780bf6a6dd` | `worktree-agent-ae9d48bf5dc036db8` | `5f1debcccbb11956c122a70a9ba815c371d58c86` |
| `69a8ff8e4a17f941f318f5cd9936a58090696e28` | `worktree-agent-aece02885ca19e959` | `271dbc1f7e3d63408fe21000f074ba9ec4fb0194` |
| `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | `worktree-agent-aecf5fa60c4ffcaea` | `e5533e4907df0480314ff1f963619d9f481c7c8e` |
| `db007c311a987c35d27b306ec051565fc8da79ab` | `worktree-agent-aef0655458c9f55b9` | `d481e2bce1ed7c38987e0a4e6545a46aabd44bcf` |
| `4ac6673690ad50408b78bcf3cc87ab3a635f05bd` | `worktree-agent-af4b9c0445be5f5a5` | `63e094fe715eba46ff9842f6bee8454b8cc887f5` |
| `451d2ebd714033a3b1f6bba3fc1b939f9d086efb` | `worktree-agent-af95ea98f982612d6` | `697c439818ceb3faf6cfb55b727904a5d690409e` |
| `676f96d1c4ccf4d75094d4a0dd2d015a3e1b58d0` | `worktree-agent-afa591a17c448320e` | `46b45723706f8cc9486a6091323d9a0cc60fb03d` |
| `e5df03e6b8e3754a3c6f8a62dc4797b5b9773a21` | `worktree-agent-afa6d1c4926e46d77` | `b916830e3cbb37e9e8cd6891a215e1265773d9a0` |
| `e98560a698804aaacbbe07fbf2bd4d86bb1aeb9f` | `worktree-agent-afae520a937d45e74` | `bccb9ac8fee00eacc7e5e6a36fad3223d663a219` |

### Preflight correction — September 4, 2026

The first preflight aborted without deleting anything: `codex/security-data-hardening-20260904` acquired a new worktree at `/private/tmp/ftf-security-hardening-20260904` after the audit snapshot. It is excluded and retained. The immutable original manifest above has 255 entries; the executable batch is 254 entries after this explicit exclusion. Execution will recheck every other ref and worktree assignment.

## Worktree batch 2: record before deletion

| Tip SHA | Branch name | Worktree path |
| --- | --- | --- |
| `dc781ff5495f35f06ce5f5214f25f941fb188c50` | `feat/mobile-b5-trade-queue` | `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/agent-ae3050bc4e4ca4e49` |

Content proof: QueueChip and useTradeQueue are byte-identical at the squash integration `247d9b5e` (PR #40). Current useTradeQueue is still identical; QueueChip has the later intentional Chalkline reskin (`fed3a3be` / `1580064c`). Current `types.ts` retains QueuedTrade and `TradesScreen.tsx` retains queue state helpers and QueueChip rendering. Full evidence is in the linked audit. Preflight status shows no tracked changes and no ignored files; the only untracked entry is `mobile/node_modules`, a symlink to the primary project's `mobile/node_modules`. No independent dependency files exist in this worktree. No lock or process ownership was found in the audit. Removal may need `--force` solely to unlink this inspected symlink; its target must remain intact.

Recovery: `git branch feat/mobile-b5-trade-queue dc781ff5495f35f06ce5f5214f25f941fb188c50`, then `git worktree add <new-path> feat/mobile-b5-trade-queue`. Unlike batch 1, the original unsquashed tip needs a retained recovery ref or bundle to survive future pruning; create it before deleting the branch.

### Completion — September 4, 2026

Batch 1: 254 refs deleted in one expected-SHA transaction; all absent on verification. The excluded security-hardening branch remains. No remote refs or working files were touched by batch 1.

Worktree batch 2: removed the recorded trade-queue worktree and branch. `--force` was required only for the inspected untracked dependency symlink; no tracked edits or independent dependency files were discarded. The shared dependency directory's device/inode remained unchanged. Original commit is retained by `refs/recovery/2026-09-04/mobile-b5-trade-queue` for durable recovery.

## Batch 3: stale worktree registrations, recorded before pruning

Both worktree directories are already absent. Dry-run identifies only `worktrees/wt-d178` and `worktrees/wt-417` as stale administrative records. This operation removes those two Git registrations, not files, commits or branches. Their branches are retained for the separate content audit.

| Tip SHA | Branch | Former worktree path |
| --- | --- | --- |
| `6cd5c4902ffa49e85f748969d58a5b48f82aafcc` | `feat/fb417-pushed-deck-research` | `/private/tmp/claude-501/-Users-teresadickens-Documents-Claude-Projects-Fantasy-Trade-Finder--claude-worktrees-happy-golick-345cf1/f75cd725-9d48-417e-a928-f0ff331ef022/scratchpad/wt-417` |
| `77a4e33b1c08acda487892d77a9e204290ccd3ec` | `feat/fb418-backend-like-exclusion` | `/private/tmp/claude-501/-Users-teresadickens-Documents-Claude-Projects-Fantasy-Trade-Finder--claude-worktrees-happy-golick-345cf1/f75cd725-9d48-417e-a928-f0ff331ef022/scratchpad/wt-d178` |

Recovery: `git branch <name> <sha>` if a branch is subsequently removed, then `git worktree add <new-path> <name>`. Pruning cannot recover files that were already absent before this cleanup.

### Batch 3 completion — September 4, 2026

Exactly the two recorded stale registrations were pruned. A second dry-run returned no remaining stale registrations. Their branches remain.

## Batch 4: additional local branches, recorded before deletion

111 local candidates. Full immutable evidence: [batch 4 manifest](2026-09-04-branch-cleanup-batch4.json). Each is unpinned at audit time and either has all changed-path blobs equal to current main, or its aggregate branch diff matches a squash commit in main. A final check will verify current ownership and SHAs, recheck the content proof, and create `refs/recovery/2026-09-04/local/<branch-name>` before deleting each original branch name. Whitespace-preserving patch comparison will supplement stable patch IDs; mismatches will be held and reported.

Recovery: `git branch <name> <sha>`. Recovery refs preserve original commits through garbage collection. See the [full audit](../../WORKTREE_BRANCH_CLEANUP_AUDIT.md) for classification details.

| Tip SHA | Ref | Content evidence |
| --- | --- | --- |
| `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | `refs/heads/agent-16-league-switcher` | SQUASH_PATCH_EQUIVALENT; main `d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca` |
| `739b8da416bb5930f5b467a8f9b449397c9a47f6` | `refs/heads/chore/breaker-calibration-boundary-pin` | CURRENT_SCOPE_EQUAL; main `bb56c592bb76ce475e61f59ec9a53e06efbc82f9` |
| `76c24247004c39afc0ee84747056e8b3d2edf393` | `refs/heads/chore/breaker-sweep-ledger` | CURRENT_SCOPE_EQUAL; main `9c44329bd8a9daa46619794263b58a4ddd88f894` |
| `e00940d8c4ce36be2d082f985c76c99bb2c49e11` | `refs/heads/chore/commit-docs-and-claude-tree` | SQUASH_PATCH_EQUIVALENT; main `56fcf91d79623087f1a4cfefecc11759cef3cec8` |
| `8353ec3075826d6db89efbf4231e86d137450959` | `refs/heads/chore/eas-submit-ascappid` | CURRENT_SCOPE_EQUAL; main `a5c6306f59697e1378dd2abcc3226fd0b74ac44f` |
| `b8c8dd598e5d5302b240a4fc3e78b9265bd76ede` | `refs/heads/claude/api-audit-redundancies-9a6075` | SQUASH_PATCH_EQUIVALENT; main `c2775fe03fcd6d47824e17fa444681b0cc3628c0` |
| `4f8c05073a1fc2b5bbb1bdd02dab89f7e8cfee4d` | `refs/heads/claude/app-entry-platform-options-3e16ac` | SQUASH_PATCH_EQUIVALENT; main `20ac27f3da0e366ad11a0bb26abab4fdf7e2efbc` |
| `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | `refs/heads/claude/busy-cohen-7530c5` | SQUASH_PATCH_EQUIVALENT; main `eedcd2444808213374e62c83b70d7de8eccded3f` |
| `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | `refs/heads/claude/busy-hodgkin-b23fda` | SQUASH_PATCH_EQUIVALENT; main `eedcd2444808213374e62c83b70d7de8eccded3f` |
| `ad96131861d96a7486a941227781baecc1b10453` | `refs/heads/claude/ci-gotchas` | SQUASH_PATCH_EQUIVALENT; main `ae6b9be52d547e38a0ef9941d7352bd42c5305d6` |
| `bec25bbf1f08e9a1083a448e4c2a4892e55239cb` | `refs/heads/claude/compressed-board-ship-record` | SQUASH_PATCH_EQUIVALENT; main `f8b51be7b8c3ba75db05d99904db0147af1dc881` |
| `c265a8af0779b40486b04e9c16a3d3239bc8c748` | `refs/heads/claude/counterparty-breaker-plan` | SQUASH_PATCH_EQUIVALENT; main `15b13986a1936da15fd3f13092d8d8b3cbf61d95` |
| `55f06384ed5e944b4e61fe1b8ce23057f9d952a7` | `refs/heads/claude/entry-platform-login-option` | SQUASH_PATCH_EQUIVALENT; main `8ea8177bc007256a9117a0d7a28c91a70d1b2d19` |
| `3f5af51c3e496c48a958171425933177cf9f9691` | `refs/heads/claude/finder-gap-analysis-writeback` | SQUASH_PATCH_EQUIVALENT; main `2ceff988b41268753546d284466f070e3d0c3bca` |
| `a12ca6809add360e7e54a335b415cbd30024735a` | `refs/heads/claude/iap-enablement-writeback` | SQUASH_PATCH_EQUIVALENT; main `aacc1229c1e4515917b9385edad3350d2a5dafec` |
| `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | `refs/heads/claude/jolly-khorana-945330` | SQUASH_PATCH_EQUIVALENT; main `eedcd2444808213374e62c83b70d7de8eccded3f` |
| `491427a631711958692c07785fca86ddcf1105da` | `refs/heads/claude/monthly-trial-3d` | SQUASH_PATCH_EQUIVALENT; main `5a01450c9a462136fc07f9cb3e71dca34e3e2a50` |
| `f7833d566f9fddf1c320e7f217a843ce7435a1e0` | `refs/heads/claude/new-user-feedback-55320e` | SQUASH_PATCH_EQUIVALENT; main `fa945925d995e8895e78285661f792f0c12f044d` |
| `a08019768e39539d0eccdc03125bdfcfe7d71016` | `refs/heads/claude/platform-entry-decouple-apple` | SQUASH_PATCH_EQUIVALENT; main `3edbc33d4f9338ce42b8926aaf502aef47c6ad5a` |
| `f7885524c22e648c9941061c58ebb665dd2623fc` | `refs/heads/claude/propose-label-writeback` | SQUASH_PATCH_EQUIVALENT; main `6b4fd64a5a05ffb1b2c3142fad2c60ce976b4ff5` |
| `5189a14e07fef703c1eb029f5472d5a26e3e85f5` | `refs/heads/claude/q034-sku-ruling` | SQUASH_PATCH_EQUIVALENT; main `70189f1c8ce8c42ea7af5d50550975bafb48a5bd` |
| `832d9ca1e34f3808ecebef3c3ceb7a1910e626e4` | `refs/heads/claude/q035-q036-operator-answers` | SQUASH_PATCH_EQUIVALENT; main `02d2eac2564872ce32c3ae2dd76eed5fb945e696` |
| `a9b86950dad2975976f383cd1fa8beb242425f02` | `refs/heads/claude/ram-mascot-fleeced` | SQUASH_PATCH_EQUIVALENT; main `7ac7869ea69b936e246c7e1f82edf4df023bc6bb` |
| `31f757297d5d40ac5a2bcdf1171e7468391e9a77` | `refs/heads/claude/sentry-wizard` | SQUASH_PATCH_EQUIVALENT; main `f379c8127ad668ac5b6cb1366c877b4c1c7b41ef` |
| `bf92d4eea6e211305589636ee2a61a218fca4f42` | `refs/heads/claude/tip-jar` | SQUASH_PATCH_EQUIVALENT; main `b0782d803445235d6ec0aec52bf513285a2ea469` |
| `32d95767dd6a16acccae07669a50f7884371d4cb` | `refs/heads/claude/trade-model-restrictiveness-7f3975` | SQUASH_PATCH_EQUIVALENT; main `23b8c8061852fb9cd52c5f146eac8dd4ba2222c7` |
| `6ac1e8a36c7a058e156b4a632e2e05fcb704fd5b` | `refs/heads/claude/trade-suggestions-review-69c9eb` | SQUASH_PATCH_EQUIVALENT; main `c6e6c3c052d01e732cfc186956939df358cafb08` |
| `0bad37ca8b5672629339a15e0d70caf8a7bb9160` | `refs/heads/claude/trial-lengths-v2` | SQUASH_PATCH_EQUIVALENT; main `209b10bae1ea81af982db4726f0a418246fc641f` |
| `71f63da347d72d3cec95192a6a4dbf66166ac2c9` | `refs/heads/claude/vigilant-spence-8583f5` | SQUASH_PATCH_EQUIVALENT; main `7b7c3146dec419d6e212cff3464070eb27de28a1` |
| `b59951c984db0318946e11c798b67788ff929f0a` | `refs/heads/docs/feedback-batch-2-prds` | CURRENT_SCOPE_EQUAL; main `c21c52071a0b7e89c317d2cd6d7b7643cd77bd62` |
| `80bb318c0b6e31db48f155edd1eaca4cbb8e3412` | `refs/heads/docs/null-dwell-writeback` | SQUASH_PATCH_EQUIVALENT; main `d5c926fd7d2a3efc2af918560c612bd3967a2102` |
| `cf5ef852c6771a7a04242abe4c1aa970ba1256b4` | `refs/heads/docs/qa-reports-feedback-wave-0824` | SQUASH_PATCH_EQUIVALENT; main `c37910518beef212847d5140f87cc3ae290fdf71` |
| `1d49d5fc8a8fcad4291becf9eb412e48533978e3` | `refs/heads/feat/bakeoff-composition` | SQUASH_PATCH_EQUIVALENT; main `a7f8783ee1ae84a942b21025a3065704ef616cf6` |
| `6d60d955cf432bf09c98798a6a8f7329b398b0da` | `refs/heads/feat/celeb-once-and-copy-tiers` | SQUASH_PATCH_EQUIVALENT; main `7325c26eba2a4f661e59ae5dfdf4ec8f6d95eb08` |
| `4a8722959d4c20ab7a324292eff4e3042de0727b` | `refs/heads/feat/datetime-utcnow-cleanup` | SQUASH_PATCH_EQUIVALENT; main `86448a6f5ffcc67d01086ee798326114881294e3` |
| `fa9979bda197ca601b919f938fec55d2fd9a6314` | `refs/heads/feat/fb-07-trios-cleanup` | SQUASH_PATCH_EQUIVALENT; main `bb3636ea69c88b515b942f22b4065cc6cc1e220d` |
| `8eabe6c3d111b83fe97fdbe9a20e4bb42356fa4e` | `refs/heads/feat/feedback-admin-list` | SQUASH_PATCH_EQUIVALENT; main `8bdba1245d85b961e228b5a2542cc6914ff9d134` |
| `1d3ffca88de44f41a62e45bf3d3d43437d018785` | `refs/heads/feat/feedback-batch-4-polish` | SQUASH_PATCH_EQUIVALENT; main `7a05f4e6294bc347e9d12c03b06774450249c596` |
| `f4b3bfb5eb45b95ffc19da8724f1ea3fd80c43d8` | `refs/heads/feat/guided-onboarding-platform-aware` | SQUASH_PATCH_EQUIVALENT; main `dd2051bc21e876db370ba3b3785de9fd33c84052` |
| `2cb2ce792269736d2f41817c54eac77031170334` | `refs/heads/feat/init10-player-view-param` | SQUASH_PATCH_EQUIVALENT; main `2dcac6e3fe317b385b4e518fc71393d4512c6637` |
| `482b07dd9b86438c20e4593570fd8eeb87d07273` | `refs/heads/feat/jon-360-362` | SQUASH_PATCH_EQUIVALENT; main `9d983be480f5646b8b9f584220579ecff77c05cd` |
| `b1a5024a6ef238d2b9fb30606c25548e2f386bae` | `refs/heads/feat/league-pick-value-alignment` | SQUASH_PATCH_EQUIVALENT; main `70ae4f4319ea68b0dc22195220928348afaeb481` |
| `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | `refs/heads/feat/notifications-clear-button` | SQUASH_PATCH_EQUIVALENT; main `d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca` |
| `21ad574b9871e0837a9e9ef6fa6cbc5c92818966` | `refs/heads/feat/receipts` | SQUASH_PATCH_EQUIVALENT; main `93f1fd0ebbae28fc8fdca78f504648aa5c00ec98` |
| `95709751e22c7ac3f08bc131c4adb57361ff53a8` | `refs/heads/feat/slot-pricing-unconditional` | SQUASH_PATCH_EQUIVALENT; main `3192d1380128d71fc05ffe99e5127c25580fb1fc` |
| `692e6fe4b863cd370929e6244b2fba52e2663254` | `refs/heads/feat/tier-config-and-bench-fixes` | SQUASH_PATCH_EQUIVALENT; main `a339a243c34bdd1bc50c394cc4a46c995c78095c` |
| `c92141b386a0039510fda80b37005256c9d3b428` | `refs/heads/feat/tiers-multiselect` | SQUASH_PATCH_EQUIVALENT; main `7757f5c5c3c52dfa5ce7931f47e729c1f4eaf810` |
| `f248197bbd348fd6790506c51fc6d474c7acb1a5` | `refs/heads/feat/wave1-perf-code` | SQUASH_PATCH_EQUIVALENT; main `464a7a2758c0d11edb41b5aa3701d0e76dfe676b` |
| `8c2b5ec37c42e4aded02dfd7bb06bd6fd7fc4575` | `refs/heads/feat/wave2-init08-client` | SQUASH_PATCH_EQUIVALENT; main `38b127f883a761e8ae349708c759d6bb4954a496` |
| `bec210780d0049e28c9f91c6f1c3cb4e3688c927` | `refs/heads/feat/wave2-init09-trade-prune` | SQUASH_PATCH_EQUIVALENT; main `04cdc058522e3a44c2ef08692a6fa52675e0b646` |
| `040188162b92af41f980d1694d47f69ca0f0ab8c` | `refs/heads/feat/wave2-init11a-13` | SQUASH_PATCH_EQUIVALENT; main `debfa4f2781b50bfc0372276e007b57f747128b9` |
| `20bebe4ceb3065752f954c24d97b259a0bffe158` | `refs/heads/feat/wave2-init12b` | SQUASH_PATCH_EQUIVALENT; main `b2117edd8987d7877e08d44aba5aae6cdaff108c` |
| `cd1248c2b314c536e119c3b130e4b1157bd7f9cf` | `refs/heads/feat/wave2-init14b-db-hygiene` | SQUASH_PATCH_EQUIVALENT; main `b8583f63fbbff2649699a9b9eaad6e78e44e995d` |
| `a75ba55a6cf00d6f8a9714764e980f913bceb2f5` | `refs/heads/feat/wave2-init15-docs` | SQUASH_PATCH_EQUIVALENT; main `7e33cba313fb1badcae53961ae0ed5b61e65b46a` |
| `a8e5ef81597b1fc0dd09449a39668eeb5f6bf4d8` | `refs/heads/fix/384-tour-device-feedback` | SQUASH_PATCH_EQUIVALENT; main `ff9fcbd5d3dc6d678bb189e5774320b001dfb5fb` |
| `4df39bef29971e01bc05882b5f069eccd50f74bd` | `refs/heads/fix/copy-tiers-include-seed-only-players` | SQUASH_PATCH_EQUIVALENT; main `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` |
| `973ad489cda2b18880fb623eab269bd7bff921e9` | `refs/heads/fix/feedback-qc-trio-throttle` | SQUASH_PATCH_EQUIVALENT; main `bd5a733ea100112b89f4d6de9dd506cce8926634` |
| `cacde8af44ab65befae2b3941ccb777d617915a3` | `refs/heads/fix/feedback-rehydrate-unsynced` | SQUASH_PATCH_EQUIVALENT; main `e52a8dcd208a9f3847d0c2883865df8857e18826` |
| `c693581795c7b62138a348d4b60d0c4d9003b247` | `refs/heads/fix/feedback-tiers-ux` | SQUASH_PATCH_EQUIVALENT; main `807fa66bcd999c7ea2c071296626af603ce7f527` |
| `317e42969a449c3ec34920d9e8540f65eed24114` | `refs/heads/fix/feedback-trade-match-100` | SQUASH_PATCH_EQUIVALENT; main `c8a1f651bb83003f1ca356d4050b6b389aaa9fac` |
| `cdeb130914e8f72916216764910caaeaf77ab1ab` | `refs/heads/fix/feedback-trios-polish` | SQUASH_PATCH_EQUIVALENT; main `4356795eedc3bf69d9c4bf6b9793e7fb6421ab87` |
| `ccb08e21bfc0e9b0c845a99bcf3e36f8eb74b4d3` | `refs/heads/fix/guide-band-entry-animation` | SQUASH_PATCH_EQUIVALENT; main `fe77b287a462bed5dfa7bbe4a591aeedeaf59147` |
| `3e80e8af408a250d56668a99208840af40349a7e` | `refs/heads/fix/lift-top80-cap` | SQUASH_PATCH_EQUIVALENT; main `d158e50d844125aaae38c8ad283b6e4ac12545ce` |
| `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | `refs/heads/fix/manual-rankings-remove-kebab-column` | SQUASH_PATCH_EQUIVALENT; main `d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca` |
| `5e52cdac886deae8fa12fa4a314ddb72d28bd8de` | `refs/heads/fix/mobile-warm-player-cache-on-init` | SQUASH_PATCH_EQUIVALENT; main `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` |
| `7fe1e9b61eb1685e2709c918c34cc79ce460f947` | `refs/heads/fix/package-benchmark-sweetener` | SQUASH_PATCH_EQUIVALENT; main `d42872f214628b4bd162f115666966a4eba641d5` |
| `7b9df5db0327e8a86c7319282579407c2749cddf` | `refs/heads/fix/pick-assignment-missing-user-team` | SQUASH_PATCH_EQUIVALENT; main `fc260dea52f39590f4e8b3ac100e83a0d4a5c424` |
| `a726995d872952d0425f7098ae69405b47bd07f1` | `refs/heads/fix/preserve-tier-overrides` | SQUASH_PATCH_EQUIVALENT; main `ff8a116b487fb4aa351543b065d72f53affd092f` |
| `2dd277e77f0b6f2d54a4be17c5a2b0d737fade18` | `refs/heads/fix/rankings-progress-monotonic-unlock` | SQUASH_PATCH_EQUIVALENT; main `67e5a27bfd9a5a7b5aaf6001f85947a634d286b0` |
| `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | `refs/heads/fix/remove-trios-info-icon` | SQUASH_PATCH_EQUIVALENT; main `d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca` |
| `8c3a5550b63a53f27af467bbfac280266f41df76` | `refs/heads/fix/review-batch-backend-perf` | SQUASH_PATCH_EQUIVALENT; main `4f83805d7d50006b2718464ae6e9b9d857787b12` |
| `9d99ab81efec8e35f3a1f5aa08f3a931b850f325` | `refs/heads/fix/review-cache-and-mutations` | SQUASH_PATCH_EQUIVALENT; main `a1142da0c20d3492d12b6234ae2e082816de249b` |
| `78b1568fa9275544bb2b32220b169816d208825d` | `refs/heads/fix/review-flags-and-notifications` | SQUASH_PATCH_EQUIVALENT; main `ae029bce29b9bf987db77522c72c0417e6dff4bb` |
| `5e1a5a879b6cad551b4e0d38f35c51dddd47fef4` | `refs/heads/fix/session-init-parallelization` | SQUASH_PATCH_EQUIVALENT; main `b9187716ab9181444cf4d38b6fa0ce2b43e8000a` |
| `be9afbd4482fbd432bb2c283bf778d2eafa970a5` | `refs/heads/fix/test-user-logins` | SQUASH_PATCH_EQUIVALENT; main `33496d8217e946c517f87a3526db0dfa9dd0a344` |
| `34b8d4c3eeaf835efd4bcae94721cf30ae126965` | `refs/heads/fix/test-user-logins-tev2` | SQUASH_PATCH_EQUIVALENT; main `33496d8217e946c517f87a3526db0dfa9dd0a344` |
| `1b4a9a4ce866d8cd7f5c72badd14cf8da0e2099a` | `refs/heads/fix/tier-arrows-edge-detection` | SQUASH_PATCH_EQUIVALENT; main `6f908746c52ff10494606ea04a0cced2304ebaeb` |
| `97a29130fa31cd5c861d5f0acc299eadc4d2fa36` | `refs/heads/fix/tier-overrides-survive-swipes` | SQUASH_PATCH_EQUIVALENT; main `595e770b174a12cad468cad4f4d2461d2e21f055` |
| `ee8c48b5ca0db2d80a9ae0d0f61cb34b709a03f1` | `refs/heads/fix/tiers-drag-worklet-crash` | SQUASH_PATCH_EQUIVALENT; main `f5c8bc3dbe20417e188de771c7aa3329abde4b5a` |
| `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | `refs/heads/fix/tiers-drop-coord-space` | SQUASH_PATCH_EQUIVALENT; main `eedcd2444808213374e62c83b70d7de8eccded3f` |
| `b68c193de946f389a778fe151b566202d788c385` | `refs/heads/fix/tiers-format-sync` | SQUASH_PATCH_EQUIVALENT; main `b29e6e37843d80b59a8259fb72854dbf1b9753b1` |
| `ad8471b51f6d92b6c35871c42055061dbd2d32c9` | `refs/heads/fix/tiers-multiselect` | SQUASH_PATCH_EQUIVALENT; main `ba647dedf3c5abaec84a45531819257ad9e03146` |
| `6a5a08d92decd7524e561bb0b6ff97c55db5ba1e` | `refs/heads/fix/trade-job-fmt-undefined` | SQUASH_PATCH_EQUIVALENT; main `e6695b5ee087fad76728ac20c716ca9737cd12a4` |
| `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | `refs/heads/fix/trios-remove-college-2026-04-26` | SQUASH_PATCH_EQUIVALENT; main `d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca` |
| `e5fc5cf6887172e04d58da3c5a215d739821756d` | `refs/heads/fix/web-trades-snapshot-poller` | SQUASH_PATCH_EQUIVALENT; main `28213dfae86324e17d953bc8c2aa9a443b47ffbf` |
| `f949fec2639dc509d92af217d5c84be52ea76f75` | `refs/heads/living-memory-revival` | SQUASH_PATCH_EQUIVALENT; main `f714f52589c32970c193c2a11454790aca3871af` |
| `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | `refs/heads/mobile/independent-followups` | SQUASH_PATCH_EQUIVALENT; main `d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca` |
| `2a5ca54a518b60de307988ea153851295823c4aa` | `refs/heads/mobile/session-expired-recovery` | SQUASH_PATCH_EQUIVALENT; main `1e4afd85ac2b02f5ad47224ece7490cc5edd7a1a` |
| `a834d383d68ff0a945bda7cb0803cf7e2342f904` | `refs/heads/mobile/tiers-persistence-parity` | SQUASH_PATCH_EQUIVALENT; main `57a8fd265f87e068f58490547e365b9fc5c5b3d0` |
| `f5446bbade03074b88d0c5f5a3adcad78b8a3e02` | `refs/heads/mobile/web-parity-2026-04-29` | SQUASH_PATCH_EQUIVALENT; main `4f45d261306215a5f678af627fa70b9f354205a7` |
| `dc83ce41ff684f396c3ad05c1791e334aa96cad2` | `refs/heads/perf/find-a-trade-faster-pregen` | SQUASH_PATCH_EQUIVALENT; main `d9d17e05cb08a76898f4f44b2d6a18a621d4409b` |
| `b5f1f39eafdfb786d1f811d42305fedabf36869e` | `refs/heads/perf/find-a-trade-tighter-cap` | SQUASH_PATCH_EQUIVALENT; main `1091f3605f8370fdf1134c227550fc1135e2a94b` |
| `9a3475dfae187d8c7de27170a17de9c651b3e086` | `refs/heads/perf/league-matches-progressive-paint` | SQUASH_PATCH_EQUIVALENT; main `2bf4484c4a4ec29255a708b32f2d63c9ca4b3bea` |
| `b12488d25c2454b461d4b830d0ed79415d08fed0` | `refs/heads/perf/trade-tier-priority` | SQUASH_PATCH_EQUIVALENT; main `6aa1255d2f79fc003a5e5ac28bd6e7776f003712` |
| `dd8f95b0d2d5d433ac42c3492c549a1a0eab3163` | `refs/heads/perf/trios-fast-load` | SQUASH_PATCH_EQUIVALENT; main `827add1570ad9434bbb9067d067e33f9bf232eca` |
| `0eca3c4e003a90578a3ed6f0e3a4bc64f478bd05` | `refs/heads/perf/warm-endpoint-and-boot-ping` | SQUASH_PATCH_EQUIVALENT; main `71ba9b1edcd577ec64b8c19ba9fd7f953df38fdf` |
| `557260400630dc6fac14161a7cf1d5c37967e3cf` | `refs/heads/plan/receipts` | CURRENT_SCOPE_EQUAL |
| `8dca63c33b1a1ae6a7ce3a35fd25b5335c923c9a` | `refs/heads/recovery/ledger-entry-login-option` | SQUASH_PATCH_EQUIVALENT; main `6c8d2c86bcdf406771d9d904ee8201ef956657fa` |
| `81001c272140fdd41277bdbc71cfa0a886888036` | `refs/heads/recovery/ledger-landing-platform-options` | SQUASH_PATCH_EQUIVALENT; main `ec031f91a4883574fea4544da451711b7ef9b93f` |
| `141546aec74a4845d7567ba4149bd0445b99f091` | `refs/heads/recovery/ledger-platform-entry-decouple` | SQUASH_PATCH_EQUIVALENT; main `5a413df5a61eac0bad19daf81fa5c5537054e95f` |
| `20b1d22a7d8db1b8d9fb1c4753174a834b140a28` | `refs/heads/recovery/ledger-v1168-sweep` | CURRENT_SCOPE_EQUAL; main `30070f3692cc08cd5dde8c96da2877642f4f73ca` |
| `364d8d7cdd97d90793f273f6411f134d77fbf3f7` | `refs/heads/release/v1.16.8` | SQUASH_PATCH_EQUIVALENT; main `0f0a8a32670ea9736a6f7880f42eb7376f46dca1` |
| `96e48ed7a0809c86c2653c83d74613c07d203e67` | `refs/heads/release/v1.16.8-record` | SQUASH_PATCH_EQUIVALENT; main `56ee2994c199453b6e5a46ca1a1dfefa86854bca` |
| `be9237b23e0f42aaf41a8a69cd5a0441824dfc38` | `refs/heads/research/ktc-pick-comparison` | SQUASH_PATCH_EQUIVALENT; main `77cce9b6f6561682995ad5eedd52355b0d1a7745` |
| `45406790e073c10457978e0dc2c3e29913ecd08d` | `refs/heads/ship/armc-sweetener` | SQUASH_PATCH_EQUIVALENT; main `3df71c06bd001bff7bfcd825a6a2dc4773fa125c` |
| `6a152bf52b72d13f91e6a89ee2d69f1f92696f74` | `refs/heads/web/tiers-within-tier-reorder` | SQUASH_PATCH_EQUIVALENT; main `39b8c3e57bf001fe1a344734d28bf9ec58d7821f` |
| `1c04bc3ab3b072604400bc1425a193ff4f5b2172` | `refs/heads/worktree-agent-a1666e74f3763e0a7` | SQUASH_PATCH_EQUIVALENT; main `d683fe8afed68ccb51b489faffe4d85045d66a18` |
| `6da7747089ba1c8a77a8dd0232e2ef985bceebfc` | `refs/heads/worktree-agent-a23ba874f1881182e` | SQUASH_PATCH_EQUIVALENT; main `38b85777a87b12d41a51e62fb24ffe7a37392fcc` |
| `b2127cee5d425cd6cda9806732d604cc91be1557` | `refs/heads/worktree-agent-a3f23e0d54808496f` | SQUASH_PATCH_EQUIVALENT; main `a3f178bba1ab51dc7ec40cfd80709d6df834e331` |
| `7633561ec801e9a521e65ebb30dd22bb6f02f532` | `refs/heads/worktree-agent-adc544906c182a442` | SQUASH_PATCH_EQUIVALENT; main `c4f8bf77499b9c51e75d4981f207a7810c606a41` |
| `2d6d4f7940f751481f336e473b1e7e3278b8fa4d` | `refs/heads/worktree-agent-aec3f38caa8be282f` | SQUASH_PATCH_EQUIVALENT; main `031099a81df16476bff66aba2efd530029953fa2` |

## Batch 5: obsolete remote heads, recorded before deletion

76 origin candidates. Full immutable evidence: [batch 5 manifest](2026-09-04-branch-cleanup-batch5.json). The audit excluded main, every registered worktree owner and all 11 open PR heads. Each candidate is positively content-preserved in main history, has a matching aggregate squash patch, or has all changed-path blobs equal to current main. Execution will recheck open PRs, worktree owners and live remote SHAs; use atomic deletion with an explicit expected-SHA lease for each head; and keep `refs/recovery/2026-09-04/remote/<branch-name>` locally. Changed or mismatched candidates will be held.

Recovery: `git branch <name> <sha>`, then `git push origin <name>` when restoring a remote branch is desired. This is the only batch that mutates origin. No open PR is to be closed by this cleanup.

| Tip SHA | Remote-tracking ref identifying the origin head | Content evidence |
| --- | --- | --- |
| `0b6487163b14990af330612a6b1818ca31da6d2d` | `refs/remotes/origin/analytics-300` | SQUASH_PATCH_EQUIVALENT; main `5139b459ea2b1594ab0c85a4881931bdeca870bf` |
| `e00940d8c4ce36be2d082f985c76c99bb2c49e11` | `refs/remotes/origin/chore/commit-docs-and-claude-tree` | SQUASH_PATCH_EQUIVALENT; main `56fcf91d79623087f1a4cfefecc11759cef3cec8` |
| `8353ec3075826d6db89efbf4231e86d137450959` | `refs/remotes/origin/chore/eas-submit-ascappid` | CURRENT_SCOPE_EQUAL; main `a5c6306f59697e1378dd2abcc3226fd0b74ac44f` |
| `4340b60473bc1ab6d39fd80f3d312ad4a6e8c778` | `refs/remotes/origin/chore/session-wrapup` | ANCESTOR |
| `b8c8dd598e5d5302b240a4fc3e78b9265bd76ede` | `refs/remotes/origin/claude/api-audit-redundancies-9a6075` | SQUASH_PATCH_EQUIVALENT; main `c2775fe03fcd6d47824e17fa444681b0cc3628c0` |
| `18f15f7ad36ca988ef364fc4d0041218f7313a52` | `refs/remotes/origin/claude/busy-swartz-521ff5` | ANCESTOR |
| `3f5af51c3e496c48a958171425933177cf9f9691` | `refs/remotes/origin/claude/finder-gap-analysis-writeback` | SQUASH_PATCH_EQUIVALENT; main `2ceff988b41268753546d284466f070e3d0c3bca` |
| `5adc848474f4b766101f2f1d56127577d066ab88` | `refs/remotes/origin/claude/ftf-file-continuation-c9185e` | SQUASH_PATCH_EQUIVALENT; main `80f08db600fd1d0cc8f8289ca558177957f04e24` |
| `f7833d566f9fddf1c320e7f217a843ce7435a1e0` | `refs/remotes/origin/claude/new-user-feedback-55320e` | SQUASH_PATCH_EQUIVALENT; main `fa945925d995e8895e78285661f792f0c12f044d` |
| `62bd658f65639772a8ca70f92bb74f769b1f2389` | `refs/remotes/origin/claude/new-user-feedback-d4c47d` | SQUASH_PATCH_EQUIVALENT; main `941a36d66539bb7b0fd59075dab8ba1ae0949e2d` |
| `f7885524c22e648c9941061c58ebb665dd2623fc` | `refs/remotes/origin/claude/propose-label-writeback` | SQUASH_PATCH_EQUIVALENT; main `6b4fd64a5a05ffb1b2c3142fad2c60ce976b4ff5` |
| `832d9ca1e34f3808ecebef3c3ceb7a1910e626e4` | `refs/remotes/origin/claude/q035-q036-operator-answers` | SQUASH_PATCH_EQUIVALENT; main `02d2eac2564872ce32c3ae2dd76eed5fb945e696` |
| `a9b86950dad2975976f383cd1fa8beb242425f02` | `refs/remotes/origin/claude/ram-mascot-fleeced` | SQUASH_PATCH_EQUIVALENT; main `7ac7869ea69b936e246c7e1f82edf4df023bc6bb` |
| `b3f7d92bd20a68cd7af9eb36da0d463a69326b9a` | `refs/remotes/origin/claude/team-outlook-experience-27a7a1` | ANCESTOR |
| `aaa98449d4fdcb4c2c351018f03b1a7613c7dc88` | `refs/remotes/origin/closeout-mock-draft` | SQUASH_PATCH_EQUIVALENT; main `60fccc75d2344910cb5fafb75cfaf3f94e5ea9a2` |
| `68e0b4dfc6ca28bc52d0279344f7e805e283f112` | `refs/remotes/origin/closeout-wave` | SQUASH_PATCH_EQUIVALENT; main `2f0fcbb0823499b0e21913e57751d768cc9be929` |
| `4a381f7eefd535a02018f0b2c7587175c66d9f0f` | `refs/remotes/origin/context-slim-2026-08-08` | SQUASH_PATCH_EQUIVALENT; main `e907c9321ee209d1371028c8cddad8a5c74a8b98` |
| `7f7524c3822d4feaf3e86223cc204626d3961a2b` | `refs/remotes/origin/docs-297-302-artifacts` | SQUASH_PATCH_EQUIVALENT; main `62ff8d68221ce126f405e0fefbe9bb90b28cce45` |
| `b59951c984db0318946e11c798b67788ff929f0a` | `refs/remotes/origin/docs/feedback-batch-2-prds` | CURRENT_SCOPE_EQUAL; main `c21c52071a0b7e89c317d2cd6d7b7643cd77bd62` |
| `38a989c88b054ac2d90f443e4866a4faa10f96a3` | `refs/remotes/origin/docs/navdoc-refresh-2026-08-18` | SQUASH_PATCH_EQUIVALENT; main `686c429ddef5a1aab7e9fb9b6969610b476cd1e8` |
| `80bb318c0b6e31db48f155edd1eaca4cbb8e3412` | `refs/remotes/origin/docs/null-dwell-writeback` | SQUASH_PATCH_EQUIVALENT; main `d5c926fd7d2a3efc2af918560c612bd3967a2102` |
| `4a8722959d4c20ab7a324292eff4e3042de0727b` | `refs/remotes/origin/feat/datetime-utcnow-cleanup` | SQUASH_PATCH_EQUIVALENT; main `86448a6f5ffcc67d01086ee798326114881294e3` |
| `2fa1ff24f0ceb143d7b23b79ed5ea874a218a619` | `refs/remotes/origin/feat/espn-credential-verify` | ANCESTOR |
| `fa9979bda197ca601b919f938fec55d2fd9a6314` | `refs/remotes/origin/feat/fb-07-trios-cleanup` | SQUASH_PATCH_EQUIVALENT; main `bb3636ea69c88b515b942f22b4065cc6cc1e220d` |
| `8eabe6c3d111b83fe97fdbe9a20e4bb42356fa4e` | `refs/remotes/origin/feat/feedback-admin-list` | SQUASH_PATCH_EQUIVALENT; main `8bdba1245d85b961e228b5a2542cc6914ff9d134` |
| `1d3ffca88de44f41a62e45bf3d3d43437d018785` | `refs/remotes/origin/feat/feedback-batch-4-polish` | SQUASH_PATCH_EQUIVALENT; main `7a05f4e6294bc347e9d12c03b06774450249c596` |
| `8026b7fbc32c3c2a7ddd69aa7585eaf20d94979f` | `refs/remotes/origin/feat/feedback-liked-trades-waiting` | SQUASH_PATCH_EQUIVALENT; main `c22e7311d2bc3a575077a69ac444ce24ffb640ab` |
| `2cb2ce792269736d2f41817c54eac77031170334` | `refs/remotes/origin/feat/init10-player-view-param` | SQUASH_PATCH_EQUIVALENT; main `2dcac6e3fe317b385b4e518fc71393d4512c6637` |
| `482b07dd9b86438c20e4593570fd8eeb87d07273` | `refs/remotes/origin/feat/jon-360-362` | SQUASH_PATCH_EQUIVALENT; main `9d983be480f5646b8b9f584220579ecff77c05cd` |
| `a362a15ad810b579d73940ffa0a485d1ec55ce86` | `refs/remotes/origin/feat/light-tier-flags` | ANCESTOR |
| `3af201ac7ddd3f18c58fe0f6d7c7fd39c9ccfd4e` | `refs/remotes/origin/feat/mfl-send-integrated` | ANCESTOR |
| `7315d8c62ec30ad47f2a27fdc7d6cbf5ef84aa05` | `refs/remotes/origin/feat/send-auth-lazy` | ANCESTOR |
| `f89d8805c4ebd436705f5d59da1edc4fa9c2c82f` | `refs/remotes/origin/feat/send-in-espn` | ANCESTOR |
| `1f349bd3cbb7742ff3e4301e77e8e7c296eff72d` | `refs/remotes/origin/feat/sleeper-reachability-probe` | ANCESTOR |
| `f56216e5931d336051648b889c23700ce74a1398` | `refs/remotes/origin/feat/team-review-batch-2` | ANCESTOR |
| `f248197bbd348fd6790506c51fc6d474c7acb1a5` | `refs/remotes/origin/feat/wave1-perf-code` | SQUASH_PATCH_EQUIVALENT; main `464a7a2758c0d11edb41b5aa3701d0e76dfe676b` |
| `241f2232fc4030e410a902433d69de43fb6ff792` | `refs/remotes/origin/feat/wave2-init07` | SQUASH_PATCH_EQUIVALENT; main `b55dfabd3f7e69a8bd515393603d67dbe997fa7b` |
| `8c2b5ec37c42e4aded02dfd7bb06bd6fd7fc4575` | `refs/remotes/origin/feat/wave2-init08-client` | SQUASH_PATCH_EQUIVALENT; main `38b127f883a761e8ae349708c759d6bb4954a496` |
| `bec210780d0049e28c9f91c6f1c3cb4e3688c927` | `refs/remotes/origin/feat/wave2-init09-trade-prune` | SQUASH_PATCH_EQUIVALENT; main `04cdc058522e3a44c2ef08692a6fa52675e0b646` |
| `040188162b92af41f980d1694d47f69ca0f0ab8c` | `refs/remotes/origin/feat/wave2-init11a-13` | SQUASH_PATCH_EQUIVALENT; main `debfa4f2781b50bfc0372276e007b57f747128b9` |
| `20bebe4ceb3065752f954c24d97b259a0bffe158` | `refs/remotes/origin/feat/wave2-init12b` | SQUASH_PATCH_EQUIVALENT; main `b2117edd8987d7877e08d44aba5aae6cdaff108c` |
| `cd1248c2b314c536e119c3b130e4b1157bd7f9cf` | `refs/remotes/origin/feat/wave2-init14b-db-hygiene` | SQUASH_PATCH_EQUIVALENT; main `b8583f63fbbff2649699a9b9eaad6e78e44e995d` |
| `a75ba55a6cf00d6f8a9714764e980f913bceb2f5` | `refs/remotes/origin/feat/wave2-init15-docs` | SQUASH_PATCH_EQUIVALENT; main `7e33cba313fb1badcae53961ae0ed5b61e65b46a` |
| `bbc2e4b166925c4417bb5ec559a9241354b1b9fb` | `refs/remotes/origin/feat/window-composite` | ANCESTOR |
| `660004c13c74e18d3ef2054e87bb925091c97cd1` | `refs/remotes/origin/feedback-289-294` | SQUASH_PATCH_EQUIVALENT; main `6c304c7bde576721210366835d2d3d0da445afde` |
| `8cbedf8c6927d0f1413146b2e7a3d4b248ef1174` | `refs/remotes/origin/feedback-integration-v2` | SQUASH_PATCH_EQUIVALENT; main `f8acd7159f1a9f63e86309eb19916cbd7be0e5b0` |
| `978910a4741dc511358931c5de337ec35aea9497` | `refs/remotes/origin/fix-easignore-screens` | CURRENT_SCOPE_EQUAL; main `53bd19f696f7dfd3be01fef8aea248bba49c80d5` |
| `973ad489cda2b18880fb623eab269bd7bff921e9` | `refs/remotes/origin/fix/feedback-qc-trio-throttle` | SQUASH_PATCH_EQUIVALENT; main `bd5a733ea100112b89f4d6de9dd506cce8926634` |
| `cacde8af44ab65befae2b3941ccb777d617915a3` | `refs/remotes/origin/fix/feedback-rehydrate-unsynced` | SQUASH_PATCH_EQUIVALENT; main `e52a8dcd208a9f3847d0c2883865df8857e18826` |
| `c693581795c7b62138a348d4b60d0c4d9003b247` | `refs/remotes/origin/fix/feedback-tiers-ux` | SQUASH_PATCH_EQUIVALENT; main `807fa66bcd999c7ea2c071296626af603ce7f527` |
| `317e42969a449c3ec34920d9e8540f65eed24114` | `refs/remotes/origin/fix/feedback-trade-match-100` | SQUASH_PATCH_EQUIVALENT; main `c8a1f651bb83003f1ca356d4050b6b389aaa9fac` |
| `cdeb130914e8f72916216764910caaeaf77ab1ab` | `refs/remotes/origin/fix/feedback-trios-polish` | SQUASH_PATCH_EQUIVALENT; main `4356795eedc3bf69d9c4bf6b9793e7fb6421ab87` |
| `bda0d51844b289dc509f84c71c8a44a15f742fac` | `refs/remotes/origin/fix/finder-conditions-and-partners-copy` | ANCESTOR |
| `fc260dea52f39590f4e8b3ac100e83a0d4a5c424` | `refs/remotes/origin/fix/pick-assignment-missing-user-team-clean` | ANCESTOR |
| `8c3a5550b63a53f27af467bbfac280266f41df76` | `refs/remotes/origin/fix/review-batch-backend-perf` | SQUASH_PATCH_EQUIVALENT; main `4f83805d7d50006b2718464ae6e9b9d857787b12` |
| `9d99ab81efec8e35f3a1f5aa08f3a931b850f325` | `refs/remotes/origin/fix/review-cache-and-mutations` | SQUASH_PATCH_EQUIVALENT; main `a1142da0c20d3492d12b6234ae2e082816de249b` |
| `78b1568fa9275544bb2b32220b169816d208825d` | `refs/remotes/origin/fix/review-flags-and-notifications` | SQUASH_PATCH_EQUIVALENT; main `ae029bce29b9bf987db77522c72c0417e6dff4bb` |
| `5e1a5a879b6cad551b4e0d38f35c51dddd47fef4` | `refs/remotes/origin/fix/session-init-parallelization` | SQUASH_PATCH_EQUIVALENT; main `b9187716ab9181444cf4d38b6fa0ce2b43e8000a` |
| `be9afbd4482fbd432bb2c283bf778d2eafa970a5` | `refs/remotes/origin/fix/test-user-logins` | SQUASH_PATCH_EQUIVALENT; main `33496d8217e946c517f87a3526db0dfa9dd0a344` |
| `34b8d4c3eeaf835efd4bcae94721cf30ae126965` | `refs/remotes/origin/fix/test-user-logins-tev2` | SQUASH_PATCH_EQUIVALENT; main `33496d8217e946c517f87a3526db0dfa9dd0a344` |
| `ee8c48b5ca0db2d80a9ae0d0f61cb34b709a03f1` | `refs/remotes/origin/fix/tiers-drag-worklet-crash` | SQUASH_PATCH_EQUIVALENT; main `f5c8bc3dbe20417e188de771c7aa3329abde4b5a` |
| `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | `refs/remotes/origin/fix/tiers-drop-coord-space` | SQUASH_PATCH_EQUIVALENT; main `eedcd2444808213374e62c83b70d7de8eccded3f` |
| `ad8471b51f6d92b6c35871c42055061dbd2d32c9` | `refs/remotes/origin/fix/tiers-multiselect` | SQUASH_PATCH_EQUIVALENT; main `ba647dedf3c5abaec84a45531819257ad9e03146` |
| `3f073a57543b0cb1b76319d80aca6040fa02bd2c` | `refs/remotes/origin/living-memory-2026-08-10` | SQUASH_PATCH_EQUIVALENT; main `2e0b2c71988d2679994dfddccd322f4b6dc5d618` |
| `f949fec2639dc509d92af217d5c84be52ea76f75` | `refs/remotes/origin/living-memory-revival` | SQUASH_PATCH_EQUIVALENT; main `f714f52589c32970c193c2a11454790aca3871af` |
| `c65493dec2b847ef08ad0a7f08bf8217ed90630c` | `refs/remotes/origin/mobile-version-1.12.0` | SQUASH_PATCH_EQUIVALENT; main `7553874f6eaede94351049b024e980f0a90411b5` |
| `258940ff7a41b8c3fca9f56eb3e7f393a77993ce` | `refs/remotes/origin/mock-draft-fix` | SQUASH_PATCH_EQUIVALENT; main `e71a6541659553fab02c41d35355b6529118a1d3` |
| `9a3475dfae187d8c7de27170a17de9c651b3e086` | `refs/remotes/origin/perf/league-matches-progressive-paint` | SQUASH_PATCH_EQUIVALENT; main `2bf4484c4a4ec29255a708b32f2d63c9ca4b3bea` |
| `b12488d25c2454b461d4b830d0ed79415d08fed0` | `refs/remotes/origin/perf/trade-tier-priority` | SQUASH_PATCH_EQUIVALENT; main `6aa1255d2f79fc003a5e5ac28bd6e7776f003712` |
| `dd8f95b0d2d5d433ac42c3492c549a1a0eab3163` | `refs/remotes/origin/perf/trios-fast-load` | SQUASH_PATCH_EQUIVALENT; main `827add1570ad9434bbb9067d067e33f9bf232eca` |
| `0eca3c4e003a90578a3ed6f0e3a4bc64f478bd05` | `refs/remotes/origin/perf/warm-endpoint-and-boot-ping` | SQUASH_PATCH_EQUIVALENT; main `71ba9b1edcd577ec64b8c19ba9fd7f953df38fdf` |
| `dc91a91bd4a88e08f5a9c4e907e698fded436785` | `refs/remotes/origin/screen-library-2026-08-09` | SQUASH_PATCH_EQUIVALENT; main `6b8270b418f30c84d105d0510292bc280b505137` |
| `bc5521f713a05feecbd230027ce183e8330f877f` | `refs/remotes/origin/session-closeout-2026-08-12` | SQUASH_PATCH_EQUIVALENT; main `4a4b6718f8d69c692138a1fdc7e41b5abeb77c89` |
| `2c10f4cc22bdb8dda49957ac7b6e92c76bee99a8` | `refs/remotes/origin/teardown-remediation` | ANCESTOR |
| `ca2b26aad6c695a662895fee8c5108fd291af200` | `refs/remotes/origin/trade-engine-v2` | ANCESTOR |
| `11e468bb852404c7e26a88b3acea60b05f7b5ca8` | `refs/remotes/origin/wave-integration` | SQUASH_PATCH_EQUIVALENT; main `7057d8612d208e739b53cec285b3c06e2fda7f41` |

### Final execution record — September 4, 2026

Batch 4: all 111 local candidates passed the stricter final proof and were deleted atomically. No candidate was held. Every original tip has a durable `refs/recovery/2026-09-04/local/<branch>` ref. See [batch 4 result](2026-09-04-branch-cleanup-batch4-result.json) for exact final evidence per branch.

Totals completed: **366 local branches** removed (254 + 111 + 1 queue branch), **one physical worktree** removed, and **two already-missing worktree registrations** pruned. Final local snapshot: 84 branches and 22 registered worktrees, including the concurrent security task. Primary checkout branch and HEAD remain unchanged.

Batch 5: all 76 remote candidates passed fresh live-tip, open-PR, worktree-ownership and stricter content checks. Their recovery refs were created locally, but **no remote branch was deleted**. GitHub rejected the atomic push with HTTP 403: the authenticated account `meghanmurphyenglund` has only `READ` permission for `mattmurf77/fantasy-trade-finder`. The GitHub CLI identity and `viewerPermission` check confirmed the same account/permission, so execution stopped without changing authentication or seeking alternate credentials.

Remote cleanup requires an authorized account with write permission. After authentication is corrected, the [guarded runner](2026-09-04-branch-cleanup-runner.cjs) can be rerun as `node docs/recovery/2026-09-04-branch-cleanup-runner.cjs remote apply`. It rechecks current main, every candidate, open PRs, worktree ownership and expected remote SHAs before an atomic leased deletion. Do not substitute an unguarded bulk delete.

Remaining worktrees and branches are retained for the concrete reasons in the audit: current tasks/open PRs, local changes or ignored data/credentials requiring preservation, or committed content not yet proven redundant. Their retention is not a claim that all are still needed.

### Authorized account correction — September 4, 2026, before remote retry

The user confirmed that both GitHub accounts are available and explicitly authorized removing the 76 remote candidates. The existing stored `mattmurf77` account was verified as repository ADMIN. The retry will select its credentials only within the cleanup process and route Git authentication through that same account. No global GitHub account or credential settings are changed. All original pre-deletion manifest entries, recovery refs, live-tip/open-PR/worktree/content checks and expected-SHA leases still apply.

### Remote cleanup completed — September 4, 2026

All **76 remote branches** passed the fresh checks and were deleted in one atomic push with explicit expected-SHA leases, using the already stored `mattmurf77` account scoped to this process. No candidates were held. A subsequent live origin query confirmed all 76 target heads absent. The global active account was not switched. All 76 original tip SHAs remain under `refs/recovery/2026-09-04/remote/<branch-name>` and in the original manifest; see [exact completion receipt](2026-09-04-branch-cleanup-batch5-result.json).

This completes the previously blocked remote batch. Combined completed cleanup: 366 local branch names, 76 remote branch names, one physical worktree, and two stale registrations. The local and remote counts overlap in underlying work and must not be described as 442 separate implementations. Unresolved or active work retained by the audit remains outside this verified deletion batch.

Recovery: `git branch <name> <sha>`, then `git push origin <name>:refs/heads/<name>` using a write-authorized account if remote restoration is needed. Do not rerun the completed remote deletion batch.
