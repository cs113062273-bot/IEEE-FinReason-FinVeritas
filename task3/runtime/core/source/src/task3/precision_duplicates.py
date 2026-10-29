"""Experimental SEC-style numeric duplicate consolidation with exact intervals.

Same declared decimals require identical values. Different decimals may be
compatible if their closed rounding intervals have a common intersection.
This is not full XBRL/OIM or Calculations 1.1 conformance. It is a separate trial;
existing prediction engines and sealed submission archives remain unchanged.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

from .xml_core import XmlFiling, XmlFact

SOURCE = "https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-05-15.pdf"


def interval(value: Decimal, decimals: str) -> tuple[Fraction, Fraction]:
    if not value.is_finite():
        raise ValueError("Nonfinite value")
    v = Fraction(value)
    if decimals.upper() == "INF":
        return v, v
    d = int(decimals)
    if abs(d) > 4096:
        raise ValueError("Decimals outside bounded arithmetic policy")
    radius = Fraction(10 ** (-d), 2) if d <= 0 else Fraction(1, 2 * 10 ** d)
    return v - radius, v + radius


def consistent_choice(facts: list[XmlFact]) -> tuple[XmlFact | None, dict]:
    values_by_precision = defaultdict(set)
    intervals = []
    for fact in facts:
        try:
            d = fact.decimals.upper()
            rank = 10**9 if d == "INF" else int(d)
            low, high = interval(fact.value, d)
        except (ValueError, OverflowError):
            return None, {"consistent": False, "reason": "unknown or unsupported decimals"}
        values_by_precision[rank].add(fact.value)
        intervals.append((low, high))
    if not facts:
        return None, {"consistent": False, "reason": "no facts"}
    if any(len(v) != 1 for v in values_by_precision.values()):
        return None, {"consistent": False, "reason": "different values at the same declared precision"}
    low, high = max(i[0] for i in intervals), min(i[1] for i in intervals)
    if low > high:
        return None, {"consistent": False, "reason": "disjoint declared rounding intervals"}
    winner = max(facts, key=lambda f: (10**9 if f.decimals.upper() == "INF" else int(f.decimals), -f.index))
    return winner, {"consistent": True, "reason": "shared closed rounding interval and equal values at each precision",
                    "intersection_low": str(low), "intersection_high": str(high),
                    "selected_index": winner.index, "selected_value": str(winner.value),
                    "selected_decimals": winner.decimals, "source": SOURCE, "full_xbrl_conformance": False}


def consolidate(filing: XmlFiling) -> tuple[XmlFiling, list[dict]]:
    groups, untouched = defaultdict(list), []
    for fact in filing.facts:
        context, unit = filing.contexts.get(fact.context), filing.units.get(fact.unit)
        if context is None or unit is None or not unit.numerator:
            untouched.append(fact)
        else:
            groups[(fact.concept, context.signature, unit.signature)].append(fact)
    evidence, selected = [], list(untouched)
    for fs in groups.values():
        if len({f.value for f in fs}) <= 1:
            selected.extend(fs)
            continue
        winner, proof = consistent_choice(fs)
        if winner is None:
            selected.extend(fs)  # conflicting/unknown duplicates remain blockers
        else:
            selected.append(winner)
        evidence.append({"concept": fs[0].concept, "proof": proof,
                         "original_facts": [f.evidence(filing) for f in fs],
                         "consolidated": winner is not None})
    return replace(filing, facts=sorted(selected, key=lambda f: f.index)), evidence
