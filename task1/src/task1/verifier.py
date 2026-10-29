"""Independent learned-DAG reexecution and complete finite output checks."""
from __future__ import annotations
import hashlib
import json
from fractions import Fraction
from typing import Any, Mapping
from .hidden_program import execute
from .explicit_solver import format_value


def verify_prediction(question: Mapping[str, Any], prediction: Mapping[str, Any], audit: Mapping[str, Any]) -> dict[str, Any]:
    errors = []
    expected = {slot["slot_id"]: slot for slot in question["trace_spec"]["slots"]}
    actual = {slot["slot_id"]: slot["value"] for slot in prediction["steps"]}
    if prediction["case_id"] != question["case_id"] or prediction["dataset_version"] != question["dataset_version"]:
        errors.append("Source identifier/version mismatch")
    if set(expected) != set(actual) or len(actual) != len(prediction["steps"]):
        errors.append("Missing, duplicate or additional checkpoints")
    final = prediction["final_answer"]
    if final is None:
        errors.append("Final answer abstention")
    for value, spec in [(final["value"] if final else None, question["answer_spec"])] + [(actual.get(key), slot["result_spec"]) for key, slot in expected.items()]:
        try:
            if spec["type"] == "decimal":
                Fraction(value)
            elif value not in spec["allowed_values"]:
                errors.append("Enum outside question contract")
        except (TypeError, ValueError, ZeroDivisionError):
            errors.append("Nonfinite or malformed numeric value")
    body = question["question"].split("\n\nAnswer format:")[0]
    variables = {}
    for binding in audit.get("bindings", []):
        if body[binding["start"]:binding["end"]] != binding["text"]:
            errors.append("Numeric binding provenance mismatch")
        variables[binding["name"]] = Fraction(binding["text"])
    if audit.get("question_sha256") != hashlib.sha256(json.dumps(question, sort_keys=True).encode()).hexdigest():
        errors.append("Question hash mismatch")
    independently_recomputed = 0
    program = audit.get("program")
    if program is not None and audit.get("strategy") in {"induced_symbolic", "reviewed_financial_dag"}:
        try:
            for name, expression in program.get("dag", []):
                variables[name] = execute(expression, variables)
            if program.get("final"):
                answer = format_value(execute(program["final"], variables), question["answer_spec"])
                if answer != final["value"]:
                    errors.append("Independent final DAG mismatch")
                independently_recomputed += 1
            elif program.get("enum"):
                enum = program["enum"]
                value = execute(enum["expression"], variables)
                answer = enum["labels"].get("positive" if value > 0 else "negative" if value < 0 else "zero")
                if answer != final["value"]:
                    errors.append("Independent final classification mismatch")
                independently_recomputed += 1
            for key, slot in expected.items():
                if key in program.get("slots", {}):
                    value = execute(program["slots"][key], variables)
                    answer = ("true" if value else "false") if slot["result_spec"]["type"] == "enum" else format_value(value, slot["result_spec"])
                    if answer != actual.get(key):
                        errors.append("Independent checkpoint DAG mismatch")
                    independently_recomputed += 1
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
            errors.append(f"Independent DAG execution failed: {exc}")
    return {"case_id": question["case_id"], "valid": not errors, "errors": errors, "independent_dag_values": independently_recomputed, "strategy": audit.get("strategy"), "limitation": "Question-formula, explicit and policy routes receive finite/completeness/provenance checks; their semantics are covered by independent peer review and synthetic tests, not learned-DAG reexecution."}
