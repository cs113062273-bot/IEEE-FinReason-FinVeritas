"""Check rational size BEFORE allocating products or nested powers.

A final-value check cannot bound the work done while evaluating an AST.
These deliberately conservative limits also constrain each intermediate.
"""
from __future__ import annotations
from fractions import Fraction

MAX_BITS = 14000


def checked(value: Fraction) -> Fraction:
    if not isinstance(value, Fraction):
        value = Fraction(value)
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > MAX_BITS:
        raise ValueError('Intermediate rational exceeds arithmetic resource budget')
    return value


def binary(left: Fraction, right: Fraction, operator: str) -> Fraction:
    left, right = checked(left), checked(right)
    a, b = left.numerator.bit_length(), left.denominator.bit_length()
    c, d = right.numerator.bit_length(), right.denominator.bit_length()
    if operator in {'+', '-'}:
        projected = max(a + d, c + b, b + d) + 1
    elif operator == '*':
        projected = max(a + c, b + d)
    elif operator == '/':
        if not right: raise ZeroDivisionError('division by zero')
        projected = max(a + d, b + c)
    else:
        raise ValueError('Unsupported budgeted operation')
    if projected > MAX_BITS:
        raise ValueError('Projected rational operation exceeds resource budget')
    if operator == '+': return checked(left + right)
    if operator == '-': return checked(left - right)
    if operator == '*': return checked(left * right)
    return checked(left / right)


def power(base: Fraction, exponent: Fraction, *, max_exponent: int) -> Fraction:
    base, exponent = checked(base), checked(exponent)
    if exponent.denominator != 1 or abs(exponent) > max_exponent:
        raise ValueError('Bounded integer exponents only')
    count = int(exponent)
    if max(base.numerator.bit_length(), base.denominator.bit_length()) * abs(count) > MAX_BITS:
        raise ValueError('Projected power exceeds arithmetic resource budget')
    return checked(base ** count)


def geometric(base: Fraction, count: Fraction, *, max_count: int) -> Fraction:
    base, count = checked(base), checked(count)
    if count.denominator != 1 or not 0 <= count <= max_count:
        raise ValueError('Bounded geometric series only')
    total, term = Fraction(), Fraction(1)
    for _ in range(int(count)):
        total = binary(total, term, '+')
        term = binary(term, base, '*')
    return total
