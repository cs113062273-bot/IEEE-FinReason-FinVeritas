# Ownership and third-party notices

## Ownership and license scope

| Content | Copyright attribution | License scope |
| --- | --- | --- |
| Original FinVeritas source code, executable program expressions, and original repository documentation | Copyright (c) 2026 Chin-Hao Hsu. FinVeritas is the project/team name. | MIT, as stated in the root `LICENSE`; excludes source-derived question wording, other third-party material, and the paper. |
| Question-derived wording in Task 1 registries, contract descriptions, and recognition phrases | Published FinReason Cup 2026 Task 1 release, by its organizers. | CC BY 4.0 under the organizer's published data scope. Original FinVeritas program logic has a separate MIT grant. |
| Working Notes paper in `paper/` | Copyright (c) 2026 Chin-Hao Hsu, the paper's author. | Not covered by the MIT software license. No separate redistribution or adaptation license is granted for the paper by this repository. |
| Bundled third-party code, DQC rule sources, taxonomy files, and filing structures | Their respective copyright holders, as identified by the original notices and source records below. | Their own licenses and notices; inclusion does not transfer ownership to Chin-Hao Hsu or FinVeritas. |

The root copyright notice covers original FinVeritas contributions only. It makes no ownership claim over the organizer's validator, Xule/Arelle, DQC rules, standard taxonomies, or issuer-authored filing structures. The university affiliation in the paper identifies the author; this repository does not attribute ownership to the university, IEEE, or the competition organizers.

## Third-party materials

The materials below retain their own notices. Relocation and path-string edits do not relicense third-party content. Copyright-holder and publisher names below identify upstream sources, not participating teams.

| Material | Source and terms | Retained notice |
| --- | --- | --- |
| Task 1 format validator (`contracts.py`) | [Organizer source repository](https://github.com/The-FinAI/IEEE-bigdata-cup); the organizer's [exact code scope notice](https://the-finai.github.io/IEEE-bigdata-cup/task1/RIGHTS_AND_PROVENANCE.md) explicitly includes this file under Apache 2.0 | `task1/upstream/ieee-bigdata-cup/LICENSE` and `RIGHTS_AND_PROVENANCE.md` |
| Task 3 organizer JSONL I/O and schema-validation helpers | [Organizer Task 3 MIT license](https://github.com/The-FinAI/IEEE-bigdata-cup/blob/5eeff16edf84f56f429a01c2163e859d190c0ec9/finreason_task3/LICENSE) | `task3/runtime/core/source/upstream/ieee-bigdata-cup/finreason_task3/LICENSE`; helper modules are under its `task3_core/` directory. No organizer scoring engine is included. |
| Task 1 question-derived wording | [Published Task 1 release](https://the-finai.github.io/IEEE-bigdata-cup/task1/), covered by the data allowlist in the [scope notice](https://the-finai.github.io/IEEE-bigdata-cup/task1/RIGHTS_AND_PROVENANCE.md); [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | The existing `RIGHTS_AND_PROVENANCE.md` preserves the source and license scope. Numeric literals were masked with `#` in training-template keys, surface spelling/whitespace was normalized, and recognition phrases were transcribed into matching routines. No official question JSONL package or answer file is redistributed. |
| Data Quality Committee rule programs and support tables | [DQC US rules](https://github.com/DataQualityCommittee/dqc_us_rules); XBRL US/DQC copyright and copying terms in each `License.md` | Under `task3/runtime/core/source/resources/task3_dqc*/`, `task3_round4_dqc/`, and the native `source_config/resources/` copies |
| Xule Arelle plug-in and model indexer | [Xule](https://github.com/xbrlus/xule); Apache 2.0, with the bundled patent notice and DQC notice | `task3/runtime/core/source/resources/task3_xule_runtime/LICENSE`, `PatentNotice.md`, `License.md`; code is under `task3/runtime/runs/native_runtime/source_config/upstream/desktop_xule_generic/plugin/xule/`, with an additional indexer copy at `task3/runtime/core/source/resources/task3_round6_xule/XuleModelIndexer.py` |
| Arelle runtime package | [Arelle](https://github.com/Arelle/Arelle), installed as `arelle-release==2.46.1`; Apache 2.0 | `third_party/ARELLE_LICENSE.md` copied from the installed 2.46.1 distribution; package notices remain in its installation |
| US GAAP taxonomy cache | [FASB authorized uses](https://xbrl.fasb.org/terms/TaxonomiesTermsConditions.html); unchanged taxonomy components incorporated to assist implementation | Embedded notices remain in the XML/XSD files; the complete authorized-uses notice is preserved in `third_party/FASB_AUTHORIZED_USES.html` |
| SEC/XBRL base schemas and linkbases | Original `xbrl.sec.gov`, `www.xbrl.org`, and `xbrl.org` URLs encoded in the cache paths | Embedded copyright, permission, and third-party notices are preserved verbatim |
| Structural catalog for 36 SEC filings | Original [SEC EDGAR](https://www.sec.gov/edgar) filing structures, used only for schema/linkbase context | Every filing's `manifest.json` preserves original document URLs, accession identity, and SHA-256 values; original XML/XSD notices remain intact |

The organizer repository has no repository-wide license grant. The Task 1 validator is redistributed under its specific Apache 2.0 allowlist, the Task 1 source-derived wording under the published CC BY 4.0 data scope, and the Task 3 I/O/schema helpers under the Task 3 MIT notice. Other Task 1 starter-kit files, website code, and official scoring engines are not redistributed.

The DQC and taxonomy notices impose conditions separate from the root MIT license, including retention of notices and restrictions on modifying the upstream documents. Bundled rule and taxonomy bytes are preserved. Python path edits affect original integration code; the Xule plug-in source remains unchanged. Python dependencies installed from `requirements.txt` carry their individual distribution licenses, available with the installed packages.

The DQC member-exclusion workbook is obtained separately by `scripts/setup_runtime.py` from the pinned official DQC source and verified against its original SHA-256. It is not redistributed in this repository because its upstream Office metadata contains the original author's local saved-file path. Setup keeps the original workbook bytes and DQC license unchanged; generated runtime copies are excluded by `.gitignore`.

The catalog is not an answer table: it contains filing structures, not external instance facts or published findings. Public accessibility alone does not grant a blanket license over every issuer-authored text fragment. Original notices and precise provenance are preserved; no claim of ownership or MIT relicensing is made for issuer content.
