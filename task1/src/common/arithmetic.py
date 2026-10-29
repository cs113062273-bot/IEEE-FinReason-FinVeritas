"""Small bounded AST interpreter; never evaluates arbitrary Python code."""
from __future__ import annotations

import ast
from fractions import Fraction
from typing import Mapping, Any
from .fraction_budget import checked, binary, power, geometric


class UnsafeExpression(ValueError):
    pass


def execute(expression: str, variables: Mapping[str, Fraction]) -> Fraction:
    if len(expression) > 2048:
        raise UnsafeExpression("expression too long")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 256:
        raise UnsafeExpression("expression too complex")

    def visit(node: ast.AST) -> Fraction:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            return checked(Fraction(node.value))
        if isinstance(node, ast.Name) and node.id in variables:
            return checked(variables[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = visit(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return binary(left, right, '+')
            if isinstance(node.op, ast.Sub): return binary(left, right, '-')
            if isinstance(node.op, ast.Mult): return binary(left, right, '*')
            if isinstance(node.op, ast.Div): return binary(left, right, '/')
            if isinstance(node.op, ast.Pow):
                if right.denominator != 1 or abs(right) > 120: raise UnsafeExpression("bounded integer exponents only")
                return power(left, right, max_exponent=120)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            values = [visit(a) for a in node.args]
            if node.func.id == "min" and len(values) == 2: return min(values)
            if node.func.id == "max" and len(values) == 2: return max(values)
            if node.func.id == "abs" and len(values) == 1: return abs(values[0])
            if node.func.id == "floor" and len(values) == 1: return Fraction(values[0].numerator // values[0].denominator)
            if node.func.id == "ceil" and len(values) == 1: return Fraction(-(-values[0].numerator // values[0].denominator))
            if node.func.id == "gt" and len(values) == 2:return Fraction(int(values[0]>values[1]))
            if node.func.id == "ge" and len(values) == 2:return Fraction(int(values[0]>=values[1]))
            if node.func.id == "lt" and len(values) == 2:return Fraction(int(values[0]<values[1]))
            if node.func.id == "geom" and len(values) == 2:
                base, count = values
                if count.denominator != 1 or not 0 <= count <= 120: raise UnsafeExpression("bounded geometric series only")
                return geometric(base, count, max_count=120)
        raise UnsafeExpression(f"unsupported AST node {type(node).__name__}")

    value = visit(tree.body)
    if max(len(str(abs(value.numerator))), len(str(value.denominator))) > 4096:
        raise UnsafeExpression("arithmetic magnitude limit")
    return value


def exact_text(value: Fraction) -> str:
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1; denominator //= 2
    while denominator % 5 == 0:
        fives += 1; denominator //= 5
    if denominator != 1:
        return f"{value.numerator}/{value.denominator}"
    places = max(twos, fives)
    scaled = abs(value.numerator) * 2 ** (places - twos) * 5 ** (places - fives)
    whole, tail = divmod(scaled, 10 ** places)
    sign = "-" if value < 0 else ""
    return f"{sign}{whole}" if not tail else f"{sign}{whole}.{tail:0{places}d}".rstrip("0")


def format_value(value: Fraction, spec: Mapping[str, Any]) -> str:
    rounding = spec["rounding"]
    if rounding["mode"] == "exact": return exact_text(value)
    places = rounding["decimal_places"]
    scale = 10 ** places
    rounded = (2 * abs(value.numerator) * scale + value.denominator) // (2 * value.denominator)
    sign = "-" if value < 0 and rounded else ""
    whole, tail = divmod(rounded, scale)
    return f"{sign}{whole}" if not places else f"{sign}{whole}.{tail:0{places}d}"
