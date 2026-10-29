"""Public FinMR practice replay with physically separated inference and scoring.

`infer` accepts only an input-only file and has no gold argument. It invokes
frozen solvers on query alone, completes and hashes every prediction, and runs
the organizer format validator. `score` loads those frozen predictions and
public gold in a separate process; it imports no solver modules. No network or
paid model calls are made. Production solvers and submissions remain untouched.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "upstream/ieee-bigdata-cup/finreason_task3"
METHODS = ("official_dummy", "official_rule_full", "official_rule_extract",
           "official_rule_negate", "Decimal", "A", "B", "C", "D",
           "round2_dimension_zero", "round2_dimension_dqc", "R4_0117", "R4_0126", "R4_0117_0126",
           "R4_engine", "R4_engine_source_first", "R4_engine_uri", "R4_engine_uri_axis")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def save(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rows(path: Path):
    with path.open(encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{line_number}: record is not an object")
                yield value


def sources() -> dict:
    files = list((ROOT / "src/task3").glob("*.py"))
    files += [Path(__file__).resolve(), ROOT / "scripts/task3_round3_trials.py",
              ROOT / "scripts/task3_round3_priority_trial.py", ROOT / "scripts/task3_compare_namespace.py"]
    files += list((OFFICIAL / "baselines").glob("*.py"))
    for resource in ("task3_dqc0015", "task3_dqc0117", "task3_dqc0126", "task3_round4_dqc"):
        files += [p for p in (ROOT / "resources" / resource).glob("*") if p.is_file()]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(files))}


def group_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def group_metadata(case_id: str, query_sha: str, filing) -> dict:
    """Deterministic input-only grouping, suitable for later grouped validation.

    Five folds are assigned by group hash, with no label stratification. These
    are prospective protocol metadata, not an already trained held-out result.
    """
    instance = filing.document_sha256.get("Instance document", query_sha)
    entities = sorted({(c.scheme, c.entity) for c in filing.contexts.values() if c.entity and c.scheme})
    target_contexts = [filing.contexts[f.context] for f in filing.facts
                       if f.concept == filing.target and f.context in filing.contexts]
    axes = sorted({axis for context in target_contexts for axis, _ in context.dimensions})
    arc_pattern = sorted({(a.parent, a.child, str(a.weight), a.arcrole) for a in filing.arcs
                          if a.parent == filing.target or a.child == filing.target})
    groups = {"instance_source": instance,
              "company": group_hash(entities) if entities else instance,
              "company_period": group_hash([entities, filing.start, filing.end]) if entities else instance,
              "concept_axis_calcpattern": group_hash([filing.target, axes, arc_pattern])}
    return {"id": case_id, "query_sha256": query_sha, "instance_sha256": instance,
            "company_entity_frames": entities, "target": filing.target_lexical,
            "period_start_or_instant": filing.start, "period_end": filing.end,
            "target_axes": axes, "calculation_pattern_sha256": group_hash(arc_pattern),
            "target_calculation_arc_count": len(arc_pattern), "groups": groups,
            "five_fold_assignments": {name: int(value[:12], 16) % 5 for name, value in groups.items()},
            "metadata_source": "bundled query only; no gold or DQC label"}


def infer(input_path: Path, output: Path) -> dict:
    # Imports happen only inside this gold-independent phase.
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(OFFICIAL)]
    from task3.engine import Prediction, predict as decimal_predict
    from task3.round3_engine import METHODS as ROUND3_METHODS, solve
    from task3.round3_priority import predict as d_predict
    from task3.round4_dimensional import predict as round4_dimension_predict
    from task3.round4_statement import predict as round4_statement_predict, predict_combined
    from task3.round4_engine import predict as round4_engine_predict, predict_competitive
    from task3.round4_axis_fragment import apply_fragment_axis, apply_missing_extraction_calculation
    from task3.precision_duplicates import consolidate
    from task3.dqc_statement_sum import apply_statement_sum
    from task3.xml_core import parse_xml
    from task3.xml_engine import analyze, guarded_fallback
    from task3.dqc_nonnegative import selective_nonnegative
    from task3_round3_trials import audit
    from task3_round3_priority_trial import audit_reported_frontier
    from baselines.rule_baseline import predict as official_predict
    from task3_core.validation import validate_submission_file

    if (output / "inference_manifest.json").exists():
        raise ValueError(f"Refusing to overwrite frozen inference: {output}")
    before = sources()
    output.mkdir(parents=True, exist_ok=True)
    counts = {m: Counter() for m in METHODS}
    errors = []
    ids = set()
    group_counts = {name: Counter() for name in ("instance_source", "company", "company_period", "concept_axis_calcpattern")}
    started = time.perf_counter()
    with ExitStack() as stack:
        predictions = {m: stack.enter_context((output / f"{m}.predictions.jsonl").open("w", encoding="utf-8", newline="\n")) for m in METHODS}
        traces = {m: stack.enter_context((output / f"{m}.audit.jsonl").open("w", encoding="utf-8", newline="\n")) for m in METHODS}
        metadata_output = stack.enter_context((output / "grouped_split_metadata.jsonl").open("w", encoding="utf-8", newline="\n"))
        for index, record in enumerate(rows(input_path), 1):
            if any(key in record for key in ("answer", "gold", "expected", "extracted_value", "calculated_value")):
                raise ValueError("Inference refuses input records containing answer/gold fields")
            case_id, query = record["id"], record["query"]
            if not isinstance(query, str) or not isinstance(case_id, str) or case_id in ids:
                raise ValueError("Input IDs and queries must be strings; IDs must be unique")
            ids.add(case_id)
            # dqc_id may be present in organizer practice inputs; it is ignored.
            results = {"official_dummy": Prediction("0", "0", "constant-zero")}
            for mode in ("full", "extract", "negate"):
                results["official_rule_" + mode] = official_predict(query, mode=mode)
            results["Decimal"] = decimal_predict(query, mode="conservative")
            abc = solve(query, statement_adapter=apply_statement_sum, anomaly_selection=True)
            results.update({m: abc[key] for m, key in zip(("A", "B", "C"), ROUND3_METHODS)})
            results["D"] = d_predict(query)
            results["R4_0117"] = round4_dimension_predict(query)
            results["R4_0126"] = round4_statement_predict(query)
            results["R4_0117_0126"] = predict_combined(query)
            results["R4_engine"] = round4_engine_predict(query)
            results["R4_engine_source_first"] = round4_engine_predict(query, sign_priority=False)
            results["R4_engine_uri"] = round4_engine_predict(query, allow_inferred_statement=True)
            results["R4_engine_uri_axis"] = predict_competitive(query)
            filing = parse_xml(query)
            role = analyze(filing, mode="role_aware_conservative")
            unique = (analyze(filing, mode="role_aware_conservative", allow_unique_dimension=True)
                      if role.mechanism in {"xml-unresolved-parent-fact", "xml-unresolved-context"} else role)
            results["round2_dimension_zero"] = guarded_fallback(unique, policy="zero")
            results["round2_dimension_dqc"] = selective_nonnegative(unique)
            query_sha = hashlib.sha256(query.encode()).hexdigest()
            metadata = group_metadata(case_id, query_sha, filing)
            metadata_output.write(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) + "\n")
            for name, group in metadata["groups"].items():
                group_counts[name][group] += 1
            for method, result in results.items():
                row = {"id": case_id, "extracted_value": result.extracted_value, "calculated_value": result.calculated_value}
                evidence = getattr(result, "evidence", {})
                checks = {"gold_correctness_verified": False}
                if method in {"A", "B", "C", "D"}:
                    try:
                        checks = audit_reported_frontier(result, query) if method == "D" else audit(result, query)
                    except (AssertionError, KeyError, TypeError, ValueError) as exc:
                        checks = {"source_audit_pass": False, "error": repr(exc), "gold_correctness_verified": False}
                        errors.append({"id": case_id, "method": method, "error": repr(exc)})
                counts[method][result.mechanism] += 1
                predictions[method].write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                traces[method].write(json.dumps({**row, "mechanism": result.mechanism, "evidence": evidence,
                                                "source_checks": checks, "query_sha256": query_sha}, ensure_ascii=False, separators=(",", ":")) + "\n")
            if index % 25 == 0:
                print(json.dumps({"stage": "infer", "rows_completed": index}), flush=True)
    after = sources()
    if before != after:
        raise RuntimeError("Inference source changed during replay; regenerate in a fresh directory")
    validation = {}
    for method in METHODS:
        report = validate_submission_file(output / f"{method}.predictions.jsonl", input_path, reference_kind="inputs")
        save(output / f"{method}.validation.json", report.to_dict())
        if not report.ok:
            raise ValueError(report.render())
        validation[method] = True
    manifest = {"stage": "gold-independent inference", "rows": len(ids), "input": str(input_path.resolve()),
                "input_sha256": sha(input_path), "no_gold_read": True, "dqc_id_forwarded_to_solver": False,
                "solver_arguments": "query string only", "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "runtime_seconds": time.perf_counter() - started, "source_sha256": before, "source_start_equals_end": True,
                "mechanisms": counts, "source_audit_errors": errors, "official_format_validation": validation,
                "grouped_split_metadata_sha256": sha(output / "grouped_split_metadata.jsonl"),
                "grouped_validation_protocol": "input-only hash grouped five folds; no model trained and no held-out score claimed",
                "group_sizes": {name: {"unique_groups": len(groups), "largest_group": max(groups.values()),
                                        "duplicate_group_count": sum(n > 1 for n in groups.values())} for name, groups in group_counts.items()},
                "artifacts": {m: {"predictions_sha256": sha(output / f"{m}.predictions.jsonl"),
                                   "audit_sha256": sha(output / f"{m}.audit.jsonl")} for m in METHODS},
                "submission_status": "NOT SUBMITTED", "no_network_or_API_calls": True}
    save(output / "inference_manifest.json", manifest)
    return manifest


def finite(value: object) -> Decimal | None:
    """Independent numeric equality: exact Decimal; no tolerance or string fallback."""
    if value is None or isinstance(value, (bool, dict, list)):
        return None
    text = str(value).strip().strip("\"'`*").strip()
    text = text.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"[$€£¥%,_\s\u00a0]", "", text).rstrip(";:")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return (number.copy_negate() if negative else number) if number.is_finite() else None


def parse_gold(record: dict) -> tuple[dict, dict]:
    answer = record["answer"]
    layers = 0
    while isinstance(answer, str) and layers < 3:
        answer = json.loads(answer)
        layers += 1
    if not isinstance(answer, dict) or set(answer) != {"extracted_value", "calculated_value"}:
        raise ValueError("gold answer must have exactly the two target fields")
    pair = {key: finite(answer[key]) for key in answer}
    if any(value is None for value in pair.values()):
        raise ValueError("gold answer has a nonnumeric or nonfinite value")
    return answer, {"id": record["id"], "json_decode_layers": layers, "finite_pair": True,
                    "exact_extracted": str(pair["extracted_value"]), "exact_calculated": str(pair["calculated_value"])}


def metric(records: list[dict]) -> dict:
    n = len(records)
    extraction_n = sum(r["extraction_matches"] for r in records)
    exact_n = sum(r["pair_matches"] for r in records)
    counts = Counter(r["exact_label"] for r in records)
    return {"n": n, "exact_pair_n": exact_n, "exact_pair_accuracy": exact_n / n if n else None,
            "extraction_correct_n": extraction_n, "extraction_accuracy": extraction_n / n if n else None,
            "conditional_calculation_denominator": extraction_n,
            "conditional_calculation_accuracy": exact_n / extraction_n if extraction_n else None,
            "marginal_calculation_accuracy": sum(r["calculation_matches"] for r in records) / n if n else None,
            "label_counts": {k: counts[k] for k in ("A", "S", "E", "C")}}


def score(gold_path: Path, output: Path, official_score: bool) -> dict:
    # No task3 solver is imported or invoked here.
    inference = json.loads((output / "inference_manifest.json").read_text(encoding="utf-8"))
    gold = {}
    parses = []
    for record in rows(gold_path):
        answer, audit = parse_gold(record)
        if record["id"] in gold:
            raise ValueError("Duplicate public gold ID")
        gold[record["id"]] = (record, answer)
        parses.append(audit)
    save(output / "gold_parse_audit.json", {"path": str(gold_path.resolve()), "sha256": sha(gold_path),
                                            "parsed_rows": len(parses), "parse_failures": 0, "rows": parses})
    if len(gold) != inference["rows"]:
        raise ValueError("Gold/inference count mismatch")
    all_cases = []
    summaries = {}
    decimal = {r["id"]: r for r in rows(output / "Decimal.predictions.jsonl")}
    metadata_path = output / "grouped_split_metadata.jsonl"
    assert sha(metadata_path) == inference["grouped_split_metadata_sha256"]
    metadata = {r["id"]: r for r in rows(metadata_path)}
    for method in METHODS:
        predictions_path = output / f"{method}.predictions.jsonl"
        audit_path = output / f"{method}.audit.jsonl"
        assert sha(predictions_path) == inference["artifacts"][method]["predictions_sha256"], "Frozen predictions changed"
        assert sha(audit_path) == inference["artifacts"][method]["audit_sha256"], "Frozen audit changed"
        predictions = {r["id"]: r for r in rows(predictions_path)}
        audits = {r["id"]: r for r in rows(audit_path)}
        if set(predictions) != set(gold) or set(audits) != set(gold):
            raise ValueError("Gold/prediction/audit ID sets disagree")
        cases = []
        for case_id, (record, answer) in gold.items():
            pred, trace = predictions[case_id], audits[case_id]
            e = trace.get("evidence", {})
            numbers = {key: finite(pred.get(key)) for key in ("extracted_value", "calculated_value")}
            structure = all(v is not None for v in numbers.values())
            extraction = structure and numbers["extracted_value"] == finite(answer["extracted_value"])
            calculation = structure and numbers["calculated_value"] == finite(answer["calculated_value"])
            complete = e.get("actual_prediction_complete_calculation_evidence")
            if complete is None:
                complete = bool(e.get("selected_equation")) or (method == "Decimal" and trace["mechanism"] == "summation" and e.get("missing_children") == 0)
            row = {"method": method, "id": case_id, "dqc_id": record.get("dqc_id", "UNKNOWN"),
                   "expected_extracted": answer["extracted_value"], "predicted_extracted": pred["extracted_value"],
                   "expected_calculated": answer["calculated_value"], "predicted_calculated": pred["calculated_value"],
                   "exact_label": "S" if not structure else "E" if not extraction else "C" if not calculation else "A",
                   "extraction_matches": extraction, "calculation_matches": calculation, "pair_matches": extraction and calculation,
                   "conditional_calculation_eligible": extraction, "mechanism": trace["mechanism"],
                   "calculation_evidence_kind": e.get("actual_calculation_evidence_kind", "legacy:" + trace["mechanism"]),
                   "complete_source_calculation": bool(complete), "source_audit_error": trace["source_checks"].get("error", ""),
                   "pair_changed_vs_Decimal": tuple(numbers.values()) != tuple(finite(decimal[case_id][k]) for k in numbers),
                   "target": e.get("target_lexical", e.get("target", "")),
                   "instance_source_group": metadata[case_id]["groups"]["instance_source"],
                   "company_group": metadata[case_id]["groups"]["company"],
                   "company_period_group": metadata[case_id]["groups"]["company_period"],
                   "concept_axis_calcpattern_group": metadata[case_id]["groups"]["concept_axis_calcpattern"],
                   "company_fold": metadata[case_id]["five_fold_assignments"]["company"],
                   "source_fold": metadata[case_id]["five_fold_assignments"]["instance_source"],
                   "concept_axis_calcpattern_fold": metadata[case_id]["five_fold_assignments"]["concept_axis_calcpattern"],
                   "audit_artifact": str(audit_path.relative_to(ROOT) if audit_path.is_relative_to(ROOT) else audit_path.resolve())}
            cases.append(row)
        all_cases.extend(cases)
        groups = {"per_dqc": defaultdict(list), "per_route": defaultdict(list), "per_evidence_kind": defaultdict(list),
                  "per_company_fold": defaultdict(list), "per_source_fold": defaultdict(list),
                  "per_concept_axis_calcpattern_fold": defaultdict(list)}
        for row in cases:
            groups["per_dqc"][row["dqc_id"]].append(row)
            groups["per_route"][row["mechanism"]].append(row)
            groups["per_evidence_kind"][row["calculation_evidence_kind"]].append(row)
            groups["per_company_fold"][row["company_fold"]].append(row)
            groups["per_source_fold"][row["source_fold"]].append(row)
            groups["per_concept_axis_calcpattern_fold"][row["concept_axis_calcpattern_fold"]].append(row)
        summary = {**metric(cases), **{key: {name: metric(group) for name, group in values.items()} for key, values in groups.items()},
                   "complete_source_calculation_n": sum(row["complete_source_calculation"] for row in cases),
                   "source_audit_errors_n": sum(bool(row["source_audit_error"]) for row in cases),
                   "pair_changed_vs_Decimal_n": sum(row["pair_changed_vs_Decimal"] for row in cases)}
        if official_score:
            directory = output / "official_deterministic" / method
            command = [sys.executable, str(OFFICIAL / "scripts/score_submission.py"), "--predictions", str(predictions_path),
                       "--gold", str(gold_path), "--judge", "deterministic", "--no-cache", "--output-dir", str(directory), "--quiet"]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "command.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            summary["organizer_deterministic_nonofficial"] = json.loads((directory / "evaluation_summary.json").read_text(encoding="utf-8"))
        summaries[method] = summary
    with (output / "per_case.csv").open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(all_cases[0]))
        writer.writeheader()
        writer.writerows(all_cases)
    scoreboard = [{"method": method, **{key: value for key, value in summary.items() if not isinstance(value, dict)}} for method, summary in summaries.items()]
    with (output / "scoreboard.csv").open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(scoreboard[0]))
        writer.writeheader()
        writer.writerows(scoreboard)
    output_summary = {"split": f"{len(gold)} supplied public Practice cases; local evaluation only", "gold_sha256": sha(gold_path),
                      "input_sha256": inference["input_sha256"], "scoring": "independent finite Decimal numeric meaning, zero tolerance",
                      "conditional_calculation_definition": "both correct divided by extracted correct",
                      "inference_completed_before_gold_read": True, "gold_parse_failures": 0, "methods": summaries}
    save(output / "summary.json", output_summary)
    report = ["# Round4 public Practice replay", "", "All predictions were generated from input query only, frozen and SHA256 checked before public gold was opened in a separate scoring process. No production solver or official submission was modified. Local Practice accuracy is not Development accuracy or an official LLM judge score.", "", "|Method|Exact pair|Extraction|Calculation given extraction correct|A/S/E/C|", "|---|---:|---:|---:|---|"]
    for method, summary in summaries.items():
        counts = summary["label_counts"]
        conditional = summary["conditional_calculation_accuracy"]
        conditional_text = f"{conditional:.2%}" if conditional is not None else "N/A (zero correct extractions)"
        report.append(f"|{method}|{summary['exact_pair_n']}/{summary['n']} ({summary['exact_pair_accuracy']:.2%})|{summary['extraction_correct_n']}/{summary['n']}|{conditional_text}|{'/'.join(str(counts[k]) for k in ('A','S','E','C'))}|")
    report += ["", "Per DQC, route, evidence category, source audits and gold parse details are in summary.json, gold_parse_audit.json, and per_case.csv. The organizer deterministic scorer is reproduced separately under official_deterministic/ and is explicitly nonofficial.", "", "The official rule baseline has no model, API key or GPU requirement. Model/API/HF/vLLM templates require configured model runtimes or paid APIs and were not run."]
    (output / "README.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return {method: {key: summary[key] for key in ("n", "exact_pair_n", "extraction_correct_n", "conditional_calculation_accuracy", "label_counts")} for method, summary in summaries.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="stage", required=True)
    run = commands.add_parser("infer")
    run.add_argument("--input", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    compare = commands.add_parser("score")
    compare.add_argument("--gold", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)
    compare.add_argument("--official-deterministic", action="store_true")
    args = parser.parse_args()
    result = infer(args.input, args.output) if args.stage == "infer" else score(args.gold, args.output, args.official_deterministic)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
