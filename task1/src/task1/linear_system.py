"""Explicit, unit-checked affine systems without a financial-template catalog.

Grammar: literal declarations; ``Unknown name in unit``; two or more
``Equation: lhs=rhs`` statements; one final ``Solve for name`` request.
All quantities are normalized to base units, as in equation_fallback. No
unparsed prose or implicit unknown units are accepted. This is a bounded
program-language extension, not a general natural-language financial solver.
"""
from __future__ import annotations

import ast
import re
from fractions import Fraction
from typing import Any, Mapping

from src.common.arithmetic import execute, format_value
from src.common.fraction_budget import binary, checked
from src.task1.equation_fallback import (
    DIMLESS, FUNCTIONS, LITERAL, RATE_UNITS, RATIO_UNITS, _dimension,
    _rate_mode, _segments, _source_expression, _unit,
)
from src.task1.hidden_program import execute as independent_execute

NAME = r"[A-Za-z][A-Za-z0-9_]*"
UNKNOWN = re.compile(rf"Unknown\s+({NAME})\s+in\s+([A-Za-z_% ]+)", re.I)
REQUEST = re.compile(rf"(?:compute|calculate|return|find|solve for)\s+(?:the\s+)?({NAME})", re.I)


def _affine(source: str, known: Mapping[str, Fraction], names: list[str]):
    """Extract exact coefficients structurally; sampled values cannot prove linearity."""
    tree = ast.parse(source, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 256:
        raise ValueError("AST size bound")
    zero = (Fraction(0),) * len(names)
    index = {name: i for i, name in enumerate(names)}

    def scale(value, scalar):
        return binary(value[0], scalar, '*'), tuple(binary(x, scalar, '*') for x in value[1])

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return checked(Fraction(node.value)), zero
        if isinstance(node, ast.Name):
            if node.id in known:
                return known[node.id], zero
            if node.id in index:
                return Fraction(0), tuple(Fraction(i == index[node.id]) for i in range(len(names)))
            raise ValueError("undeclared name")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return scale(visit(node.operand), Fraction(-1 if isinstance(node.op, ast.USub) else 1))
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                op = '+' if isinstance(node.op, ast.Add) else '-'
                return binary(left[0], right[0], op), tuple(binary(a, b, op) for a, b in zip(left[1], right[1]))
            if isinstance(node.op, ast.Mult):
                if any(left[1]) and any(right[1]):
                    raise ValueError("nonlinear product")
                return scale(left, right[0]) if not any(right[1]) else scale(right, left[0])
            if isinstance(node.op, ast.Div):
                if any(right[1]):
                    raise ValueError("unknown denominator")
                return scale(left, binary(Fraction(1), right[0], '/'))
        # Powers/functions may only depend on declared constants. The common
        # interpreter independently enforces its AST and rational-work bounds.
        if any(isinstance(n, ast.Name) and n.id in index for n in ast.walk(node)):
            raise ValueError("nonlinear or unsupported unknown expression")
        return execute(ast.unparse(node), known), zero

    return visit(tree.body)


def _unique_solution(matrix: list[list[Fraction]], count: int):
    rows = [list(row) for row in matrix]
    pivots = []
    for column in range(count):
        pivot = next((r for r in range(len(pivots), len(rows)) if rows[r][column]), None)
        if pivot is None:
            continue
        position = len(pivots)
        rows[position], rows[pivot] = rows[pivot], rows[position]
        divisor = rows[position][column]
        rows[position] = [binary(v, divisor, '/') for v in rows[position]]
        for r in range(len(rows)):
            if r == position or not rows[r][column]:
                continue
            factor = rows[r][column]
            rows[r] = [binary(a, binary(factor, b, '*'), '-') for a, b in zip(rows[r], rows[position])]
        pivots.append(column)
    if any(not any(row[:count]) and row[count] for row in rows):
        raise ValueError("inconsistent equations")
    if len(pivots) != count:
        raise ValueError("underdetermined system")
    return [rows[i][-1] for i in range(count)], rows


def solve_linear_system(question: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    body = question["question"].split("\n\nAnswer format:")[0]
    if len(body) > 16000 or question["answer_spec"]["type"] != "decimal":
        return None
    # Most official questions do not use this language; avoid AST work on them.
    if not re.search(r"\bUnknown\s+" + NAME + r"\s+in\s+", body, re.I):
        return None
    try:
        known, dimensions, unknowns, evidence, equations, rates = {}, {}, [], [], [], {}
        target = None
        # The shared splitter can return the terminal period as an extra
        # segment. Strip sentence separators while preserving source offsets.
        segments = [m for m in _segments(body) if m[0].strip(" .")]
        for i, segment in enumerate(segments):
            text = segment[0].strip(" .")
            start = segment.start() + len(segment[0]) - len(segment[0].lstrip(" ."))
            if text == "Use exact arithmetic":
                continue
            request = REQUEST.fullmatch(text)
            if request:
                if target is not None or i != len(segments) - 1:
                    return None
                target = request[1]
                continue
            unknown = UNKNOWN.fullmatch(text)
            literal = re.fullmatch(rf"({NAME})\s*=\s*(.+)", text)
            if unknown or literal:
                name = (unknown or literal)[1]
                if name in dimensions or name in FUNCTIONS:
                    raise ValueError("duplicate/reserved name")
                if unknown:
                    dim, unit_scale = _unit(unknown[2])
                    # Percent unknown coordinates would leave raw-points vs
                    # fractional formulas ambiguous. Declare these as ratio.
                    if " ".join(unknown[2].lower().split()) in RATE_UNITS:
                        raise ValueError("unknown rate must be declared as ratio")
                    unknowns.append(name)
                    kind, unit = "unknown", unknown[2]
                else:
                    value = LITERAL.fullmatch(literal[2])
                    if not value:
                        raise ValueError("only literal known declarations")
                    dim, unit_scale = _unit(value[2])
                    known[name] = binary(checked(Fraction(value[1])), unit_scale, '*')
                    unit = " ".join(value[2].lower().split())
                    if unit in RATE_UNITS | RATIO_UNITS:
                        rates[name] = (unit, checked(Fraction(value[1])))
                    kind = "known"
                dimensions[name] = dim
                evidence.append({"name": name, "kind": kind, "unit": unit,
                                 "source": text, "start": start, "end": start + len(text)})
                continue
            equation = re.fullmatch(r"Equation\s*:\s*(.+)", text, re.I)
            if not equation or equation[1].count('=') != 1:
                return None
            left, right = equation[1].split('=')
            equations.append({"source": text, "start": start, "end": start + len(text),
                              "expression": _source_expression(f"({left})-({right})")})
        if not 1 <= len(unknowns) <= 8 or not 2 <= len(equations) <= 16 or target not in unknowns:
            return None
        expressions = {str(i): e["expression"] for i, e in enumerate(equations)}
        representations = {}
        for name, (unit, declared) in rates.items():
            mode = _rate_mode(name, unit, expressions, {k: v for k, v in known.items() if k not in rates})
            if unit == "percentage points" and _rate_mode(name, "percent", expressions, {k: v for k, v in known.items() if k not in rates}) != "raw_percentage_points":
                # Unknown coordinates are canonical fractions. Raw points
                # cannot enter their equations without explicit /100.
                raise ValueError("percentage-point equations require explicit fractional conversion")
            representations[name] = mode
            if mode != "ratio":
                known[name] = declared
        matrix = []
        # Unknowns are not numeric constants: zero placeholders are used only
        # by dimensional analysis; coefficient extraction never samples them.
        dimension_values = {**known, **dict.fromkeys(unknowns, Fraction(0))}
        for equation in equations:
            _dimension(equation["expression"], dimensions, dimension_values)
            constant, coefficients = _affine(equation["expression"], known, unknowns)
            matrix.append([*coefficients, -constant])
        solution, reduced = _unique_solution(matrix, len(unknowns))
        values = {**known, **dict(zip(unknowns, solution))}
        # Exact substitution into every ORIGINAL equation, including redundant
        # rows, through two AST interpreters. Rounding happens only at export.
        for equation in equations:
            if execute(equation["expression"], values) != 0 or independent_execute(equation["expression"], values) != 0:
                raise ValueError("original-equation residual")
        def render(name, spec):
            dim, scale = _unit(spec.get("unit", "dimensionless"))
            if name not in values or spec["type"] != "decimal" or dim != dimensions[name]:
                raise ValueError("output dimension/variable mismatch")
            # A raw percent literal checkpoint must be converted back to its
            # canonical fraction before applying the requested output scale.
            factor = Fraction(1, 100) if representations.get(name) == "raw_percentage_points" else Fraction(1, 10000) if representations.get(name) == "raw_basis_points" else Fraction(1)
            return format_value(binary(binary(values[name], factor, '*'), scale, '/'), spec)
        steps, seen = [], set()
        for slot in question["trace_spec"]["slots"]:
            sid = slot["slot_id"]
            if sid in seen:
                return None
            seen.add(sid)
            name = sid.removesuffix("_trace")
            mentioned = {n for n in dimensions if re.search(rf"\b{re.escape(n)}\b", slot.get("description", ""))}
            if name not in dimensions:
                if len(mentioned) != 1:
                    return None
                name = next(iter(mentioned))
            elif mentioned and mentioned != {name}:
                return None
            steps.append({"slot_id": sid, "value": render(name, slot["result_spec"])})
        prediction = {"schema_version": "finreason.task1.prediction/1.0.0",
                      "dataset_version": question["dataset_version"], "case_id": question["case_id"],
                      "final_answer": {"value": render(target, question["answer_spec"])}, "steps": steps}
        return prediction, {"strategy": "bounded_linear_system", "target": target,
                            "declarations": evidence, "equations": equations, "unknowns": unknowns,
                            "dimensions": {k: list(v) for k, v in dimensions.items()},
                            "rate_representations": representations,
                            "canonical_solution": {k: str(values[k]) for k in unknowns},
                            "augmented_matrix": [[str(x) for x in row] for row in matrix],
                            "reduced_matrix": [[str(x) for x in row] for row in reduced],
                            "rank": len(unknowns), "independent_zero_residuals": len(equations),
                            "routing_gate": "complete explicit program; unique full-rank affine system; compatible units; complete checkpoints",
                            "confidence_kind": "structural gate, not calibrated probability"}
    except (KeyError, ValueError, TypeError, SyntaxError, ZeroDivisionError, OverflowError, RecursionError):
        return None
