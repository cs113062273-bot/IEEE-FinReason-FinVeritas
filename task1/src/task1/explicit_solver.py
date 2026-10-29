"""Question-only exact solver for explicitly disclosed financial expressions.

No gold, manifests, upstream execution, network, or eval. Scenario figures are
used as supplied even when surrounding generator-range prose is inconsistent.
"""
from __future__ import annotations

import ast
import re
from fractions import Fraction
from typing import Any, Mapping
from src.common.fraction_budget import checked, binary, power

NUMBER = r"-?\d+(?:\.\d+)?(?:/\d+)?"


def arithmetic(expression: str, variables: Mapping[str, Fraction]) -> Fraction:
    """Interpret a small exact arithmetic AST, rejecting every other operation."""
    source = expression.replace("^", "**")
    tree = ast.parse(source, mode="eval")
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("Expression too complex")

    def visit(node: ast.AST) -> Fraction:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return checked(Fraction(ast.get_source_segment(source, node) or str(node.value)))
        if isinstance(node, ast.Name) and node.id in variables:
            return checked(variables[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return binary(left, right, '+')
            if isinstance(node.op, ast.Sub):
                return binary(left, right, '-')
            if isinstance(node.op, ast.Mult):
                return binary(left, right, '*')
            if isinstance(node.op, ast.Div):
                return binary(left, right, '/')
            if isinstance(node.op, ast.Pow) and right.denominator == 1 and abs(right) <= 200:
                return power(left, right, max_exponent=200)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"min", "max", "abs"} and not node.keywords and 1 <= len(node.args) <= 4:
            values = [visit(value) for value in node.args]
            if node.func.id == "abs" and len(values) == 1:
                return abs(values[0])
            if node.func.id == "max":
                return max(values)
            if node.func.id == "min":
                return min(values)
        raise ValueError("Unapproved arithmetic node")

    result = visit(tree.body)
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 20000:
        raise ValueError("Result exceeds resource budget")
    return result


def format_value(value: Fraction, spec: Mapping[str, Any]) -> str:
    rounding = spec.get("rounding", {})
    if rounding.get("mode") == "half_up":
        places = rounding["decimal_places"]
        scale = 10 ** places
        count = (2 * abs(value.numerator) * scale + value.denominator) // (2 * value.denominator)
        whole, fractional = divmod(count, scale)
        sign = "-" if value < 0 and count else ""
        return f"{sign}{whole}.{fractional:0{places}d}" if places else f"{sign}{whole}"
    if rounding.get("mode") != "exact":
        raise ValueError("Unknown rounding")
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return f"{value.numerator}/{value.denominator}"
    places = max(twos, fives)
    scale = 10 ** places
    count = abs(value.numerator) * 2 ** (places - twos) * 5 ** (places - fives)
    whole, fractional = divmod(count, scale)
    sign = "-" if value < 0 else ""
    if not fractional:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{fractional:0{places}d}".rstrip("0")


def solve_explicit(question: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a complete prediction only for a recognized disclosed program."""
    body = question["question"].split("\n\nAnswer format:")[0]
    if not body.startswith("Use exact arithmetic."):
        return None
    variables = {match[1]: Fraction(match[2]) for match in re.finditer(rf"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*({NUMBER})", body)}
    traces: dict[str, Fraction] = {}

    def calculate(expression: str) -> Fraction:
        return arithmetic(expression, variables)

    def trace(key: str, expression: str) -> Fraction:
        value = calculate(expression)
        traces[key] = value
        return value

    try:
        if "penalty=max(E-T,0)" in body and "total=penalty+shortfall+gap" in body:
            penalty = trace("penalty_trace", "max(E-T,0)*(r/100)")
            shortfall = trace("shortfall_trace", "max(M-C,0)")
            gap = trace("gap_trace", "max(Q-A,0)")
            final = penalty + shortfall + gap
        elif "shortfall=max(R-C,0)" in body:
            raw = trace("raw_shortfall_trace", "R-C")
            final = max(raw, Fraction(0))
        elif "deficiency=max(M-C,0)" in body:
            raw = trace("raw_deficiency_trace", "M-C")
            final = max(raw, Fraction(0))
        elif "gap=max(Q-A,0)" in body:
            raw = trace("raw_gap_trace", "Q-A")
            final = max(raw, Fraction(0))
        elif "excess=max(E-T,0)" in body:
            trace("raw_excess_trace", "E-T")
            excess = trace("excess_trace", "max(E-T,0)")
            final = excess * calculate("r/100")
        elif "G*n" in body:
            final = calculate("G*n")
        elif "weighted volatility S=" in body:
            variables["S"] = trace("weighted_volatility_trace", "(w1*s1+w2*s2+w3*s3)/100")
            trace("weighted_ratio_trace", "S/100")
            variables["m"] = trace("confidence_multiplier_trace", "1+(100-c)/100")
            final = calculate("V*(S/100)*t*m")
        elif "combined risk R=" in body:
            variables["R"] = trace("combined_risk_trace", "(a+b+q)/3")
            variables["m"] = trace("confidence_multiplier_trace", "1+(100-c)/100")
            final = calculate("V*(R/100)*t*m")
        elif "VaR=V*(s/100)*t*z" in body:
            trace("volatility_ratio_trace", "s/100")
            trace("scaled_volatility_trace", "(s/100)*t*z")
            final = calculate("V*(s/100)*t*z")
        elif "VaR=V*(s/100)*t*m" in body:
            trace("volatility_ratio_trace", "s/100")
            variables["m"] = trace("confidence_multiplier_trace", "1+(100-c)/100")
            final = calculate("V*(s/100)*t*m")
        elif "VaR=V*(s/100)*z" in body:
            trace("volatility_ratio_trace", "s/100")
            final = calculate("V*(s/100)*z")
        elif "VaR=V*(l/100)*z" in body:
            trace("loss_ratio_trace", "l/100")
            trace("base_loss_trace", "V*(l/100)")
            final = calculate("V*(l/100)*z")
        elif "impact_i=V*(wi/100)*(ci/100)*si" in body:
            impacts = [trace(f"impact_{word}_trace", f"V*(w{i}/100)*(c{i}/100)*s{i}") for i, word in enumerate(("one", "two", "three"), 1)]
            final = sum(impacts, Fraction(0))
        elif "S=w1*s1/100+w2*s2/100+w3*s3/100" in body:
            variables["S"] = trace("weighted_sensitivity_trace", "w1*s1/100+w2*s2/100+w3*s3/100")
            trace("factor_ratio_trace", "c/100")
            final = calculate("V*(c/100)*S")
        elif "credit impact=V*(qc/100)*sc" in body:
            final = trace("credit_impact_trace", "V*(qc/100)*sc") + trace("market_impact_trace", "V*(qm/100)*sm")
        elif "si*ci/100+sm*cm/100+sc*cc/100" in body:
            for label, expression in [("interest", "si*ci/100"), ("market", "sm*cm/100"), ("credit", "sc*cc/100")]:
                trace(f"{label}_effect_trace", expression)
            final = calculate("V*(si*ci/100+sm*cm/100+sc*cc/100)")
        elif "sm*cm/100+si*ci/100+sf*cf/100" in body:
            for label, expression in [("market", "sm*cm/100"), ("interest", "si*ci/100"), ("inflation", "sf*cf/100")]:
                trace(f"{label}_effect_trace", expression)
            final = calculate("V*(sm*cm/100+si*ci/100+sf*cf/100)")
        elif "adjusted threshold=C*(a/100)*m" in body:
            variables["m"] = trace("adjustment_trace", "1+v/100")
            trace("appetite_ratio_trace", "a/100")
            final = calculate("C*(a/100)*m")
        elif "additional allocation=C*(f/100)*(p/100)" in body:
            trace("factor_ratio_trace", "f/100")
            trace("premium_ratio_trace", "p/100")
            final = calculate("C*(f/100)*(p/100)")
        elif "final revenue=R*(1-d/100)*(1+q/100)" in body:
            trace("remaining_ratio_trace", "1-d/100")
            trace("recovery_multiple_trace", "1+q/100")
            final = calculate("R*(1-d/100)*(1+q/100)")
        elif "new revenue=R*(1-d/100)" in body:
            trace("remaining_ratio_trace", "1-d/100")
            final = calculate("R*(1-d/100)")
        elif "new cost=C*(1+g/100)" in body:
            trace("growth_multiple_trace", "1+g/100")
            final = calculate("C*(1+g/100)")
        elif "absolute loss=P*(d/100)" in body:
            trace("drop_ratio_trace", "d/100")
            final = calculate("P*(d/100)")
        elif "additional cost=L*(r/100)*s" in body:
            trace("rate_ratio_trace", "r/100")
            final = calculate("L*(r/100)*s")
        elif "additional liquidity cost=V*(s/100)" in body:
            trace("spread_ratio_trace", "s/100")
            final = calculate("V*(s/100)")
        elif "threshold=B*(a/100)" in body or "allocation=C*(a/100)" in body or "maximum exposure=A*(r/100)" in body:
            if "threshold=B" in body:
                trace("appetite_ratio_trace", "a/100")
                final = calculate("B*(a/100)")
            elif "allocation=C" in body:
                trace("appetite_ratio_trace", "a/100")
                final = calculate("C*(a/100)")
            else:
                trace("appetite_ratio_trace", "r/100")
                final = calculate("A*(r/100)")
        elif "V*(c/100)*s" in body or "P*(c/100)*s" in body or "P*(q/100)*s" in body:
            if "P*(q/100)" in body:
                trace("shock_ratio_trace", "q/100")
                final = calculate("P*(q/100)*s")
            elif "P*(c/100)" in body:
                trace("market_ratio_trace", "c/100")
                final = calculate("P*(c/100)*s")
            else:
                trace("factor_ratio_trace", "c/100")
                final = calculate("V*(c/100)*s")
        else:
            return None
        if question["answer_spec"]["type"] != "decimal":
            return None
        steps = []
        for slot in question["trace_spec"]["slots"]:
            if slot["slot_id"] not in traces:
                return None
            steps.append({"slot_id": slot["slot_id"], "value": format_value(traces[slot["slot_id"]], slot["result_spec"])})
        return {"schema_version": "finreason.task1.prediction/1.0.0", "dataset_version": question["dataset_version"], "case_id": question["case_id"], "final_answer": {"value": format_value(final, question["answer_spec"])}, "steps": steps}
    except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
