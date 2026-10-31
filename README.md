# FinVeritas

Code for **“FinVeritas at FinReason Cup 2026: Exact Program Execution for Verifiable Financial Reasoning and XBRL Audit Verification”** ([paper](paper/FinVeritas_Working_Notes.pdf)). FinVeritas binds financial question text to executable programs, computes every intermediate value exactly, and verifies XBRL facts with rule programs and native Arelle/Xule fallbacks. No language model runs at inference.

| Official Test result | FinVeritas |
| --- | --- |
| Task 1 | 927/928 correct; joint 2nd of 27 teams |
| Task 3 | 97.79% accuracy; joint 1st of 23 teams |

This repository reproduces the submitted system. It is not a general financial-audit service.

## Install

Tested on Windows with CPython 3.11.14 and Arelle 2.46.1. Other operating systems have not been validated. Run from the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv/Scripts/python.exe scripts/setup_runtime.py
.venv/Scripts/python.exe task3/verify_runtime.py
```

- `setup_runtime.py` downloads one pinned DQC workbook and verifies its SHA-256. To install it offline, pass `--source-file PATH_TO_WORKBOOK`. Prediction itself runs offline.
- Keep the checkout, the virtual environment and the output directories on short paths unless Windows long paths are enabled.
- Keep question files and outputs outside the repository, and allow several GB of disk space for Task 3.

## Data

Download the inputs from the [Task 1](https://the-finai.github.io/IEEE-bigdata-cup/task1/) and [Task 3](https://the-finai.github.io/IEEE-bigdata-cup/task3/) hubs. Questions, answers, submitted predictions and the official scorers are not included.

| Split | File | Records |
| --- | --- | --- |
| Task 1 Development | `leaderboard_questions.jsonl` (not `dev_questions.jsonl`) | 580 |
| Task 1 Test | `test_questions.jsonl` | 928 |
| Task 3 Development | `development_inputs.jsonl` | 680 |
| Task 3 Test | `test_inputs.jsonl` | 680 |

## Run

The examples below keep inputs in a sibling `official-data` directory.

**Task 1** takes a few seconds per split:

```powershell
.venv/Scripts/python.exe task1/run_task1.py --questions ../official-data/task1/leaderboard_questions.jsonl --output ../finveritas-outputs/task1-development.jsonl --verify
.venv/Scripts/python.exe task1/run_task1.py --questions ../official-data/task1/test_questions.jsonl --output ../finveritas-outputs/task1-test.jsonl --json-spacing standard --verify
```

`--verify` writes a `.verification.json` report and re-executes the induced and reviewed programs with a second interpreter. `--json-spacing standard` reproduces the Test submission bytes; the default reproduces the Development submission bytes.

**Task 3** takes about 13 minutes per split for the source stage, plus native rule compilation and re-examination:

```powershell
.venv/Scripts/python.exe task3/predict.py --inputs ../official-data/task3/development_inputs.jsonl --output ../finveritas-outputs/task3-development
.venv/Scripts/python.exe task3/predict.py --inputs ../official-data/task3/test_inputs.jsonl --output ../finveritas-outputs/task3-test
```

The output directory must not exist. The result is `<output>/predictions.jsonl`. Values equal the submitted ones under `Decimal`; the submission files added thousands separators.

## Check outputs

Run a task twice into different outputs, then compare them:

```powershell
.venv/Scripts/python.exe task1/run_task1.py --questions ../official-data/task1/test_questions.jsonl --output ../finveritas-outputs/task1-test-repeat.jsonl --json-spacing standard --verify
.venv/Scripts/python.exe scripts/verify_outputs.py --task task1 --questions ../official-data/task1/test_questions.jsonl --predictions ../finveritas-outputs/task1-test.jsonl --repeat-predictions ../finveritas-outputs/task1-test-repeat.jsonl

.venv/Scripts/python.exe task3/predict.py --inputs ../official-data/task3/test_inputs.jsonl --output ../finveritas-outputs/task3-test-repeat
.venv/Scripts/python.exe scripts/verify_outputs.py --task task3 --questions ../official-data/task3/test_inputs.jsonl --predictions ../finveritas-outputs/task3-test/predictions.jsonl --repeat-predictions ../finveritas-outputs/task3-test-repeat/predictions.jsonl
```

`verify_outputs.py` checks format, ID coverage and byte equality of the two runs; it does not score answers. Add `--reference PATH` to compare against a JSONL or ZIP you already have, and `--reference-numeric` for Task 3 submission files.

## Paper-to-code map

Task 3 paths are under `task3/runtime/runs/`, except parsing, which is under `task3/runtime/core/source/`.

| Paper component | Implementation |
| --- | --- |
| Task 1 binding | `task1/src/task1/templates.py` |
| Task 1 induction and frozen programs | `task1/src/task1/induction.py`, `task1/data/processed/task1_registry.json` |
| Task 1 reviewed graphs | `task1/src/task1/formulas.py` |
| Task 1 policy and explicit formulas | `task1/src/task1/policy_solver.py`, `document_policy.py`, `explicit_solver.py` |
| Task 1 scenario programs | `task1/src/task1/hidden_solver.py` |
| Task 1 execution | `task1/src/common/arithmetic.py`, `task1/src/task1/hidden_program.py` |
| Task 1 verifier | `task1/src/task1/verifier.py`, `program_reexecution.py`, `registry_contracts.py` |
| Task 3 parsing and exact arithmetic | `src/task3/parser.py`, `xml_core.py`, `exact_arithmetic.py` |
| Task 3 rule programs and consensus gate | `rule_programs/programs/`, `source_engine/common_core.py`, `integrated_engine/pipeline.py` |
| Task 3 native fallback | `native_runtime/native.py`, `native_runtime/source_config/`, `namespace_bindings/` |
| Task 3 other fallbacks | `strategy_engine/`, `source_candidates/`, `calculation_semantics/`, `partial_source/` |
| Task 3 selection rules | `focus_selection/`, `focus_domains/`, `focus_transfer/`, `scope_selection/`, `equation_priority/` |
| Task 3 re-examination | `reexamination/pipeline_v6.py`, `retention_fallback.py`, `relabel.py` |
| Task 3 structural documents | `structural_documents/metadata_catalog/`, `reexamination/build_full_structure.py` |
| Task 3 entry point | `task3/predict.py`, `orchestration/entrypoint/predict.py` |

Versioned names such as `round6_*`, `source_rules_v5.py` and `pipeline_v6.py` are live dependencies of the submitted system.

## Limitations

- The 116 Task 1 scenario programs were specified from the unlabeled Test questions with AI coding assistants, so they do not show generalization to unseen families.
- Task 3 selection rules were developed with Development feedback, and some are issuer-specific. They changed 17 Development answers and no Test answers.
- Task 3 re-examination was built for the Test submission and changed 17 Test answers.
- The bundled catalog holds schema and linkbase documents from 36 SEC filings (16 Development, 20 Test). They are not shipped with the competition cases. Each `manifest.json` records the SEC URLs and hashes.
- Task 1 fallback routes in the code, including the optional local-model route in `best_effort.py`, answer no Development or Test question and are outside the reproduction guarantee.

## License

Original code, program expressions and documentation are copyright (c) 2026 Chin-Hao Hsu and MIT-licensed. The Working Notes paper is copyright (c) 2026 Chin-Hao Hsu and is excluded from the MIT license. Question-derived wording in the Task 1 registries and matching routines comes from the published Task 1 release and stays under its CC BY 4.0 terms. Third-party code, rules, taxonomy files and filing structures keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

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
