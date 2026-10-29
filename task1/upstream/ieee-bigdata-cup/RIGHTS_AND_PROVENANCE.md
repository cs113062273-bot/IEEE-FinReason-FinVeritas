# FinReason Task 1 rights, license scope, and provenance

Canonical public release URL: [FinReason Cup Task 1 participant hub](https://the-finai.github.io/IEEE-bigdata-cup/task1/)

## Organizer confirmation

Zhuohan Xie, acting in the capacity of FinReason Cup organizer, confirmed the exact release scope below on 2 September 2026 UTC. The complete attestation remains private. Its public SHA-256 digest is `470b2f7c981cf4b952bf7f3ba98ccb004cfc2f2078febfec6bdde2a8782d5afb`, recorded at private commit `b4ee1f99a21a4e95021d344492a1f4ce11a281ed`.

The public organizer display name is The Fin AI. This notice does not represent The Fin AI as a separate legal entity and does not imply that IEEE or an affiliated university authored or endorsed this license notice.

## Data provenance

The released data are organizer-original synthetic financial-reasoning material. Dataset implementation commit `b3c3cc913281f4dc324324907645b8010ea3fb2a` defines the frozen Task 1 V4 data contract. Pinned FinChain commit `146eaa8225bf867fe7386c2d4727b59e03170235` is a provenance and novelty reference only. Referenced upstream functions were not executed or used as a gold oracle. No upstream FinChain source is included or relicensed here.

The rotated test release identity is `task1-v4-test-questions-20260901-r2`. It contains 928 questions and replaces the withdrawn earlier snapshot. No test answer, gold, receipt, private reference, or rehearsal archive is part of this public release.

## CC BY 4.0 exact data allowlist

Creative Commons Attribution 4.0 International applies only to these files:

- `public/task1/data/development/train_questions.jsonl`
- `public/task1/data/development/train_gold.jsonl`
- `public/task1/data/development/train_manifest.jsonl`
- `public/task1/data/development/train_targets.jsonl`
- `public/task1/data/development/dev_questions.jsonl`
- `public/task1/data/development/dev_gold.jsonl`
- `public/task1/data/development/dev_manifest.jsonl`
- `public/task1/data/development/dev_targets.jsonl`
- `public/task1/data/development/leaderboard_questions.jsonl`
- `public/task1/data/development/leaderboard_expected_ids.json`
- `public/task1/data/development/sample_b0_predictions.jsonl`
- `public/task1/data/development/sample_b0_submission.zip`
- `public/task1/data/development/release_manifest.json`
- `public/task1/data/test/test_questions.jsonl`
- `public/task1/data/test/test_expected_ids.json`
- `public/task1/data/test/test_release_manifest.json`

The unmodified license text is `public/task1/licenses/CC-BY-4.0.txt`. Attribution should identify the published FinReason Cup Task 1 release, link to the canonical URL above and the [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/), and indicate whether changes were made.

## Apache 2.0 exact code allowlist

Apache License, Version 2.0 applies only to these six organizer-owned participant-tool files:

- `finreason_task1/admission.py`
- `finreason_task1/baseline_b1.py`
- `finreason_task1/contracts.py`
- `finreason_task1/leaderboard.py`
- `finreason_task1/scoring.py`
- `scripts/task1_cli.py`

The unmodified license text is `public/task1/licenses/Apache-2.0.txt`.

## Exclusions

No license is granted here for any unlisted path. In particular, the scope excludes website and workflow orchestration code, private evaluator artifacts, private keys, test answers, private evaluation data, raw participant submissions, encrypted submission archives, receipts, logs, operational evidence, trademarks, names, likenesses, and third-party dependencies. Participant submissions remain owned by their submitters subject to the Terms of Participation.
