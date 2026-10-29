"""Bounded AST interpreter for exact arithmetic and scenario decision programs."""
from __future__ import annotations
import ast
import math
from fractions import Fraction
from typing import Any, Mapping
from src.common.fraction_budget import checked, binary, power, geometric


def execute(source: str, values: Mapping[str, Any]) -> Any:
    if len(source) > 4096:
        raise ValueError('Program source exceeds resource budget')
    tree = ast.parse(source, mode="eval")
    if len(list(ast.walk(tree))) > 300:
        raise ValueError("Program too complex")

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if type(node.value) in (bool, str):
                return node.value
            if type(node.value) in (float, int):
                return checked(Fraction(ast.get_source_segment(source, node) or str(node.value)))
        if isinstance(node, ast.Name) and node.id in values:
            value = values[node.id]
            return checked(value) if isinstance(value, Fraction) else value
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.Not):
                return not value
        if isinstance(node, ast.IfExp):
            return visit(node.body if visit(node.test) else node.orelse)
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(visit(item) for item in node.values)
            if isinstance(node.op, ast.Or):
                return any(visit(item) for item in node.values)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = visit(node.left), visit(node.comparators[0])
            operator = node.ops[0]
            if isinstance(operator, ast.Lt): return left < right
            if isinstance(operator, ast.LtE): return left <= right
            if isinstance(operator, ast.Gt): return left > right
            if isinstance(operator, ast.GtE): return left >= right
            if isinstance(operator, ast.Eq): return left == right
            if isinstance(operator, ast.NotEq): return left != right
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return binary(left, right, '+')
            if isinstance(node.op, ast.Sub): return binary(left, right, '-')
            if isinstance(node.op, ast.Mult): return binary(left, right, '*')
            if isinstance(node.op, ast.Div): return binary(left, right, '/')
            if isinstance(node.op, ast.Pow) and isinstance(right, Fraction) and right.denominator == 1 and abs(right) <= 128:
                return power(left, right, max_exponent=128)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords and 1 <= len(node.args) <= 4:
            args = [visit(item) for item in node.args]
            if node.func.id == "min": return min(args)
            if node.func.id == "max": return max(args)
            if node.func.id == "abs" and len(args) == 1: return abs(args[0])
            if node.func.id == "floor" and len(args) == 1: return Fraction(args[0].numerator // args[0].denominator)
            if node.func.id == "ceil" and len(args) == 1: return Fraction(-(-args[0].numerator // args[0].denominator))
            if node.func.id == "gt" and len(args) == 2: return Fraction(int(args[0] > args[1]))
            if node.func.id == "ge" and len(args) == 2: return Fraction(int(args[0] >= args[1]))
            if node.func.id == "lt" and len(args) == 2: return Fraction(int(args[0] < args[1]))
            if node.func.id == "geom" and len(args) == 2 and args[1].denominator == 1 and 0 <= args[1] <= 128:
                return geometric(args[0], args[1], max_count=128)
            if node.func.id == "sqrt_exact" and len(args) == 1:
                value = args[0]
                numerator, denominator = math.isqrt(value.numerator), math.isqrt(value.denominator)
                if numerator ** 2 != value.numerator or denominator ** 2 != value.denominator:
                    raise ValueError("Nonrational square root")
                return Fraction(numerator, denominator)
        raise ValueError("Unapproved program node")

    result = visit(tree.body)
    if isinstance(result, Fraction) and max(result.numerator.bit_length(), result.denominator.bit_length()) > 20000:
        raise ValueError("Result budget exceeded")
    return result
