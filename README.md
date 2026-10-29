# FinVeritas

FinVeritas is the frozen Task 1 and Task 3 system described in **“FinVeritas at FinReason Cup 2026: Exact Program Execution for Verifiable Financial Reasoning and XBRL Audit Verification.”** It binds financial question text to executable programs, evaluates exact intermediate values, and verifies XBRL numeric facts with source-bound rule programs and native Xule/Arelle fallbacks. The release reproduces the submitted system; it is not a general financial-audit service.

| Official Test result | FinVeritas |
| --- | --- |
| Task 1 | 927/928 correct; joint 2nd of 27 teams |
| Task 3 | 97.79% accuracy; joint 1st of 23 teams |

Read the [Working Notes paper](paper/FinVeritas_Working_Notes.pdf).

The results above are the final competition results reported with the paper. Reproducing the submission establishes output identity, not an independent measurement against hidden answers.

## Install

The verified environment is **Windows, CPython 3.11.14, Arelle 2.46.1**. Task 1 uses only the Python standard library. Task 3 needs the pinned packages in `requirements.txt`; no model weights, accelerator, credentials, or inference service are needed for the official inputs. Native subprocess launch flags are Windows-specific; other operating systems have not been validated.

From the repository root, in PowerShell:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv/Scripts/python.exe scripts/setup_runtime.py
.venv/Scripts/python.exe task3/verify_runtime.py
```

If the Windows launcher does not find your Python 3.11 installation (including some uv-managed installations), invoke that installation's Python executable directly with `-m venv .venv` instead of `py -3.11`.

Setup retrieves one DQC support workbook from a pinned official source, verifies its SHA-256, and installs the two runtime copies. This workbook is excluded from Git because its upstream Office metadata contains the original author's local saved-file path; its contents and license are preserved unchanged. No competition cases or answers are downloaded. Setup requires network access, or you can supply an official download with `scripts/setup_runtime.py --source-file PATH_TO_WORKBOOK`. Prediction runs offline after setup.

You can place the new environment outside the repository and substitute its Python executable in these commands. Keep question files and output directories outside the repository. Use a short checkout path if your Windows installation does not support long paths. Allow several GB of temporary disk space: Task 3 creates native bundles, compilation caches, and execution logs in each chosen output directory.

## Obtain the official inputs

Download data directly from the organizer's [Task 1 participant hub](https://the-finai.github.io/IEEE-bigdata-cup/task1/) and [Task 3 participant hub](https://the-finai.github.io/IEEE-bigdata-cup/task3/). Follow the release and data-use notices linked there. Official question JSONL packages, gold/answer files, question manifests, submitted predictions, and organizer scoring programs are not bundled.

The Task 1 implementation contains question-derived wording: `task1_registry.json` has 320 normalized training-template keys with numeric literals replaced by `#`; the contract sidecar contains question-derived contract descriptions; matching routines and hidden-stratum scenario programs retain recognition phrases from released questions. These are frozen template and recognition assets, rather than submitted answer records. Source-derived wording is attributed to the published Task 1 release under its CC BY 4.0 scope; original program logic remains separately MIT-licensed. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Task 1 Development means **`leaderboard_questions.jsonl` (580 questions)**, not `dev_questions.jsonl` (290 questions). Task 1 Test is `test_questions.jsonl` (928 questions). Each Task 3 Development/Test input file has 680 records.

## Run Task 1

Use your downloaded question file. These examples assume you keep it in a sibling `official-data` directory:

```powershell
.venv/Scripts/python.exe task1/run_task1.py --questions ../official-data/task1/leaderboard_questions.jsonl --output ../finveritas-outputs/task1-development.jsonl --verify
.venv/Scripts/python.exe task1/run_task1.py --questions ../official-data/task1/test_questions.jsonl --output ../finveritas-outputs/task1-test.jsonl --json-spacing standard --verify
```

Each full split takes a few seconds. An audit JSONL is written alongside the predictions. Official format validation is enabled by default, using the bundled Apache-licensed starter-kit contract module. No official scorer is bundled.

`--verify` also invokes `verifier.py` after inference and writes an adjacent `.verification.json` report. It checks every row for finite values, checkpoint completeness and binding provenance, and independently reexecutes the learned/reviewed DAG expressions. It does not independently prove the semantics of policy, explicit-formula or hidden-scenario routes. Verification does not change prediction values; a failed check stops the command before predictions are written.

`--json-spacing` changes JSON whitespace only. The default `compact` reproduces the Development submission bytes. `standard` reproduces the Test submission bytes, whose original archive used spaced JSON. The release entrypoint adds serialization selection and opt-in post-hoc verification; the inference logic is unchanged.

## Run Task 3

Use the same command for either split, changing only the input and fresh output directory:

```powershell
.venv/Scripts/python.exe task3/predict.py --inputs ../official-data/task3/development_inputs.jsonl --output ../finveritas-outputs/task3-development
.venv/Scripts/python.exe task3/predict.py --inputs ../official-data/task3/test_inputs.jsonl --output ../finveritas-outputs/task3-test
```

A 680-record source stage took approximately 13 minutes in the original environment; allow additional time for native rule compilation and re-examination. Traced or concurrent runs can take longer. The output directory must not exist. The final result is `<output>/predictions.jsonl`; `source/`, `retention/`, logs, and manifests provide execution evidence. The pipeline runs offline on the bundled structural dependencies. Its optional resume argument accepts only a fresh input/hash-bound source run produced by this runtime.

Task 3 retains the original numeric serialization without thousands separators. Values are exactly equal under `Decimal` to the submission ZIPs, which added thousands grouping. No submitted answer file is needed to run either task.

## Check format and determinism

Run a command a second time into a different output file/directory, then compare the two independent runs:

```powershell
.venv/Scripts/python.exe task1/run_task1.py --questions ../official-data/task1/test_questions.jsonl --output ../finveritas-outputs/task1-test-repeat.jsonl --json-spacing standard --verify
.venv/Scripts/python.exe scripts/verify_outputs.py --task task1 --questions ../official-data/task1/test_questions.jsonl --predictions ../finveritas-outputs/task1-test.jsonl --repeat-predictions ../finveritas-outputs/task1-test-repeat.jsonl

.venv/Scripts/python.exe task3/predict.py --inputs ../official-data/task3/test_inputs.jsonl --output ../finveritas-outputs/task3-test-repeat
.venv/Scripts/python.exe scripts/verify_outputs.py --task task3 --questions ../official-data/task3/test_inputs.jsonl --predictions ../finveritas-outputs/task3-test/predictions.jsonl --repeat-predictions ../finveritas-outputs/task3-test-repeat/predictions.jsonl
```

The verifier checks JSONL structure, duplicate keys/IDs, complete question-ID coverage, Task 1's official format contract, finite Task 3 numeric strings, and byte-for-byte equality of the two outputs. It does not score answer correctness. To compare a reference you already possess, add `--reference path/to/predictions.jsonl` or a ZIP containing only `predictions.jsonl`. For Task 3's thousands-grouped submission format, also add `--reference-numeric`; both numeric fields are then compared by exact `Decimal` equality for every ID.

## Paper-to-code map

Paths below are relative to the repository. Task 3 component paths are under `task3/runtime/runs/`; shared parsing modules are under `task3/runtime/core/source/`.

| Paper component | Implementation |
| --- | --- |
| Task 1 binding | `task1/src/task1/templates.py` |
| Task 1 induction and frozen programs | `task1/src/task1/induction.py`, `task1/data/processed/task1_registry.json` |
| Task 1 reviewed graphs | `task1/src/task1/formulas.py` |
| Task 1 policy / explicit formulas | `task1/src/task1/policy_solver.py`, `document_policy.py`, `explicit_solver.py` |
| Task 1 hidden-stratum scenario programs | `task1/src/task1/hidden_solver.py` |
| Task 1 execution | `task1/src/common/arithmetic.py`, `task1/src/task1/hidden_program.py` |
| Task 1 verifier and program re-execution | `task1/src/task1/verifier.py`, `program_reexecution.py`, `registry_contracts.py` |
| Task 3 parsing / exact arithmetic | `src/task3/parser.py`, `xml_core.py`, `exact_arithmetic.py` under the shared core; native XML preparation is under `native_runtime/source_config/` |
| Task 3 rule programs and consensus gate | `rule_programs/programs/source_rules*.py`, `source_engine/common_core.py`, `integrated_engine/pipeline.py` |
| Task 3 native fallback | `native_runtime/native.py`, `native_runtime/source_config/`, `namespace_bindings/` |
| Task 3 source fallbacks | `strategy_engine/`, `source_candidates/`, `calculation_semantics/`, `partial_source/` |
| Task 3 selection rules | `focus_selection/`, `focus_domains/`, `focus_transfer/`, `scope_selection/`, `equation_priority/` |
| Task 3 orchestration | `orchestration/entrypoint/predict.py`, `task3/predict.py` |
| Task 3 re-examination | `reexamination/pipeline_v6.py`, `retention_fallback.py`, `relabel.py` |
| Task 3 external structural documents | `structural_documents/metadata_catalog/`, `calculation_semantics/normalized_metadata.py`, `reexamination/build_full_structure.py` |

Directory names describe their functions. The nested `round4`, `round5`, and `round6` names inside rule programs preserve the original import layers; `source_rules_v2.py` through `source_rules_v5.py` and `pipeline_v6.py` are executed dependencies, not discarded candidate versions. Other original module filenames are retained to preserve dynamic imports and module precedence.

## Development choices and limits

Task 1's **116 hidden-stratum scenario programs were handwritten from the unlabeled Test question text**. They are not a claim of unseen-template generalization. On the 928 official Test questions the routes are fictional policy (40), explicit formula (70), reviewed financial DAG (158), induced symbolic program (312), and hidden-stratum question formula (348).

Some Task 3 selection rules were developed using Development feedback. Relative to their earlier baseline, those choices changed **17 Development answers and 0 Test answers**. Task 3 still includes heuristic focus choices, reduced-metadata native fallbacks, Disclosure-to-Statement role relabeling, and a conditional simulated path; a finite output is not a proof of full audit correctness.

The bundled catalog covers **36 SEC filings**. Each filing's `manifest.json` records the original SEC URLs, filing identity, document sections, and SHA-256 hashes. Only schema and presentation/calculation/definition/label structures are present; external financial instance facts and published data-quality findings are excluded. The runtime joins by entity, namespace, and schema reference, hash-checks selected structures, and keeps the supplied instance facts. This disclosure describes the implementation and is not an organizer ruling on data-use eligibility.

Task 1 retains dormant fallback implementations: semantic routing, equation fallback, linear systems, financial and currency graphs, rate relations, series programs, and the optional local-model/retrieval route in `best_effort.py`. These fallback routes did not supply an answer on either official evaluation split. `best_effort.py` is preserved unchanged; its 343 cached model outputs are excluded. The report-percentage experiment is called before other routes but returns `None` for official questions. Dormant fallback behavior on other inputs is not part of the official reproduction guarantee.

## Licenses and citation

Original FinVeritas source code, executable program expressions, and original repository documentation are copyright (c) 2026 Chin-Hao Hsu and MIT-licensed. Question-derived wording in Task 1 registries and matching routines retains the published data release's CC BY 4.0 attribution and license. FinVeritas is the project/team name. The Working Notes paper is copyright (c) 2026 Chin-Hao Hsu and is excluded from the MIT software license; this repository grants no separate license to redistribute or adapt the paper. Third-party code, rules, taxonomy files, and issuer-authored filing structures retain their respective ownership, licenses, and notices; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). SEC provenance remains in the structural manifests.

```bibtex
@misc{hsu2026finveritas,
  title = {FinVeritas at FinReason Cup 2026: Exact Program Execution for
           Verifiable Financial Reasoning and XBRL Audit Verification},
  author = {Hsu, Chin-Hao},
  year = {2026},
  howpublished = {FinReason Cup 2026 Working Notes},
  note = {National Tsing Hua University (NTHU)}
}
```
