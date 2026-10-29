"""Exact finite Decimal operations; no ambient precision or issuer rules.

The coefficient/exponent representation is closed under finite addition and
multiplication. Rounding belongs to the assertion's separate tolerance rule.
"""
from decimal import Decimal

def _parts(value):
    if not isinstance(value,Decimal) or not value.is_finite():
        raise ValueError('exact arithmetic requires a finite Decimal')
    sign,digits,exponent=value.as_tuple();coefficient=0
    for digit in digits:coefficient=10*coefficient+digit
    return (-coefficient if sign else coefficient),exponent

def _value(coefficient,exponent):
    # Decimal(int) and Decimal(tuple) are exact irrespective of context.prec.
    return Decimal((int(coefficient<0),Decimal(abs(coefficient)).as_tuple().digits,exponent))

def product(left,right):
    a,ae=_parts(left);b,be=_parts(right)
    return _value(a*b,ae+be)

def add(left,right):
    a,ae=_parts(left);b,be=_parts(right);exponent=min(ae,be)
    return _value(a*10**(ae-exponent)+b*10**(be-exponent),exponent)


def sum_values(values):
    total=Decimal(0)
    for value in values:
        total=add(total,value)
    return total
