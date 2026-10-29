"""Exact-context extraction and role-specific Decimal calculation reasoning.

No labels, answer cache, network, or rule identifier enter prediction. Role
alternatives are evaluated independently; identical arcs are never double-counted.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, localcontext

from .parser import Context, Fact, Filing, format_number, parse
from .exact_arithmetic import add as exact_add, product as exact_product


@dataclass(frozen=True)
class Prediction:
    extracted_value: str
    calculated_value: str
    mechanism: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Candidate:
    value: Decimal
    role: str
    used: int
    missing: int
    derived: int
    mechanism: str
    evidence: tuple


def matching_facts(filing: Filing, concept: str, context: Context, unit: str | None = None) -> list[Fact]:
    return [fact for fact in filing.facts if fact.concept == concept
            and fact.context in filing.contexts
            and filing.contexts[fact.context].signature == context.signature
            and (unit is None or fact.unit == unit or (fact.unit in filing.units and unit in filing.units
                 and filing.units[fact.unit] == filing.units[unit]))]


def choose_fact(facts: list[Fact]) -> Fact | None:
    # Duplicate consistent facts preserve their numeric meaning. For inconsistent
    # duplicates choose the most precise declared fact, then stable source order.
    def precision(fact: Fact) -> int:
        if fact.decimals == "INF":
            return 10**6
        try:
            return int(fact.decimals or "-999")
        except ValueError:
            return -999
    return max(facts, key=lambda fact: (precision(fact), -fact.position)) if facts else None


def reported_fact(filing: Filing) -> tuple[Fact | None, Context | None]:
    if filing.target is None:
        return None, None
    contexts = [c for c in filing.contexts.values() if c.matches(filing.target)]
    consolidated = [c for c in contexts if not c.dimensions]
    candidates = [fact for fact in filing.facts if fact.concept == filing.target.concept
                  and fact.context in {c.id for c in consolidated}]
    fact = choose_fact(candidates)
    if fact:
        return fact, filing.contexts[fact.context]
    # A question without dimensional qualification asks for a consolidated fact.
    # A dimensional-only disclosure is not silently substituted for that figure.
    return None, consolidated[0] if consolidated else None


def calculation_candidates(filing: Filing, context: Context, unit: str | None,
                           *, allow_inverse: bool = True) -> list[Candidate]:
    if filing.target is None:
        return []
    target = filing.target.concept
    graph = defaultdict(list)
    for arc in filing.arcs:
        graph[(arc.role, arc.parent)].append(arc)

    def read_value(concept: str, role: str, active: frozenset[str]) -> tuple[Decimal | None, int]:
        fact = choose_fact(matching_facts(filing, concept, context, unit))
        if fact is not None:
            return fact.value, 0
        if concept in active:
            return None, 0
        children = graph.get((role, concept), [])
        if not children:
            return None, 0
        total, descendants = Decimal(0), 1
        for arc in children:
            value, derived = read_value(arc.child, role, active | {concept})
            if value is None:
                return None, 0
            total = exact_add(total, exact_product(arc.weight, value))
            descendants += derived
        return total, descendants

    result = []
    for (role, parent), children in graph.items():
        if parent != target:
            continue
        total, used, missing, derived, evidence = Decimal(0), 0, 0, 0, []
        for arc in children:
            value, derived_count = read_value(arc.child, role, frozenset({target}))
            if value is None:
                missing += 1
                continue
            total = exact_add(total, exact_product(arc.weight, value))
            used += 1
            derived += derived_count
            evidence.append((arc.child, format_number(arc.weight), format_number(value)))
        if used:
            result.append(Candidate(total, role, used, missing, derived, "summation", tuple(evidence)))
    if allow_inverse:
        for (role, parent), children in graph.items():
            target_arcs = [arc for arc in children if arc.child == target]
            if len(target_arcs) != 1 or target_arcs[0].weight == 0 or parent == target:
                continue
            parent_value, parent_derived = read_value(parent, role, frozenset({target}))
            if parent_value is None:
                continue
            total, used, missing, derived, evidence = Decimal(0), 1, 0, parent_derived, []
            for arc in children:
                if arc.child == target:
                    continue
                value, derived_count = read_value(arc.child, role, frozenset({target, parent}))
                if value is None:
                    missing += 1
                    continue
                total = exact_add(total, exact_product(arc.weight, value))
                used += 1
                derived += derived_count
                evidence.append((arc.child, format_number(arc.weight), format_number(value)))
            # An inverse solve needs every other member of the parent equation.
            if not missing:
                calculated = exact_add(parent_value, total.copy_negate()) / target_arcs[0].weight
                result.append(Candidate(calculated, role, used, missing, derived, "inverse-summation",
                                        ((parent, "parent", format_number(parent_value)), *evidence)))
    return result


def predict(query: str, *, mode: str = "conservative") -> Prediction:
    with localcontext() as precision:
        precision.prec = 60
        filing = parse(query)
        if filing.target is None:
            return Prediction("0", "0", "unresolved-question")
        fact, context = reported_fact(filing)
        reported = fact.value if fact else Decimal(0)
        evidence = {"target": filing.target.concept, "context": context.id if context else None,
                    "target_present": fact is not None, "matching_facts": 0,
                    "decimal_arithmetic": True, "source": "bundled query only"}
        if context is None:
            return Prediction(format_number(reported), "0", "unresolved-context", evidence)
        evidence["matching_facts"] = len(matching_facts(filing, filing.target.concept, context))
        candidates = calculation_candidates(filing, context, fact.unit if fact else None,
                                            allow_inverse=mode == "experimental")
        if mode == "conservative":
            # An absent child has unknown value. Only fully evidenced equations
            # are promoted from candidate arithmetic to a calculated answer.
            candidates = [candidate for candidate in candidates if candidate.missing == 0]
        if candidates:
            # Complete role sums take priority. Do not merge sums from roles.
            candidates.sort(key=lambda c: (c.missing == 0, c.mechanism == "summation",
                                            c.used / (c.used + c.missing), c.used, -c.derived), reverse=True)
            winner = candidates[0]
            evidence.update({"role": winner.role, "used_children": winner.used,
                             "missing_children": winner.missing, "derived_children": winner.derived,
                             "equation": winner.evidence, "candidate_count": len(candidates)})
            return Prediction(format_number(reported), format_number(winner.value), winner.mechanism, evidence)
        # XBRL balance describes debit/credit convention, not nonnegativity.
        # Listed DQC nonnegative concepts are handled by round3/round4;
        # a signed loss or cash flow must retain its sign absent an equation.
        return Prediction(format_number(reported), format_number(reported), "agree" if fact else "unresolved-fact", evidence)
