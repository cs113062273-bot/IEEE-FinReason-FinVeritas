"""Auditable role-separated XBRL sums, with no gold or sign shortcut.

The strict mode accepts a complete target equation only when complete role
alternatives agree. Role-aware mode additionally uses a unique statement-role
    preference, recording the ambiguity, and complete inverse equations when no
    complete target-parent equation exists. Neither mode infers a sign from a debit/
credit balance. A calculation that is not supported is output as 0 as required
by the competition contract, rather than asserted equal to the reported fact.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext

from .engine import Prediction
from .parser import format_number
from .xml_core import XmlContext, XmlFact, XmlFiling, parse_xml


def _precision(fact: XmlFact) -> int:
    if fact.decimals.upper() == "INF":
        return 10**6
    try:
        return int(fact.decimals)
    except ValueError:
        return -10**6


def _fact_choice(facts: list[XmlFact]) -> tuple[XmlFact | None, dict]:
    if not facts:
        return None, {"count": 0, "conflict": False}
    values = {f.value for f in facts}
    winner = max(facts, key=lambda f: (_precision(f), -f.index))
    return winner, {"count": len(facts), "conflict": len(values) > 1,
                    "values": sorted(format_number(v) for v in values),
                    "selection": "highest declared decimals, then document order",
                    "selected_fact_index": winner.index}


def _same_unit(filing: XmlFiling, first: str, second: str) -> bool:
    # A declared unit with an unresolved measure QName is also unusable.
    # Two empty signatures must never certify compatible monetary quantities.
    return (first in filing.units and second in filing.units
            and bool(filing.units[first].numerator) and bool(filing.units[second].numerator)
            and filing.units[first].signature == filing.units[second].signature)


def select_parent(filing: XmlFiling, *, allow_unique_dimension: bool = False) -> tuple[XmlFact | None, XmlContext | None, dict]:
    matching_contexts = [c for c in filing.contexts.values() if c.consolidated and
                         (((c.start, c.end) == (filing.start, filing.end)) if filing.end else c.instant == filing.start)]
    ids = {c.id for c in matching_contexts}
    facts = [f for f in filing.facts if f.concept == filing.target and f.context in ids]
    selection = "consolidated asked-period fact"
    dimension_facts, dimension_groups = [], set()
    if not facts and allow_unique_dimension:
        period_contexts = [c for c in filing.contexts.values() if
                           (((c.start, c.end) == (filing.start, filing.end)) if filing.end else c.instant == filing.start)]
        dimension_ids = {c.id for c in period_contexts if c.dimensions and not c.qualifiers}
        dimension_facts = [f for f in filing.facts if f.concept == filing.target and f.context in dimension_ids]
        dimension_groups = {(filing.contexts[f.context].signature,
                             filing.units[f.unit].signature if f.unit in filing.units else ("undeclared-unit", f.unit))
                            for f in dimension_facts}
        if len(dimension_groups) == 1:
            # The question specifies concept and period, not consolidation. A
            # unique supplied dimensional fact can answer it; choosing the
            # first of multiple dimensional groups cannot.
            facts = dimension_facts
            selection = "unique dimensional asked-period fact"
    fact, duplicate = _fact_choice(facts)
    signatures = {(filing.contexts[f.context].signature,
                   filing.units[f.unit].signature if f.unit in filing.units else ("undeclared-unit", f.unit)) for f in facts}
    meta = {"matching_consolidated_contexts": [c.id for c in matching_contexts],
            "matching_target_fact_count": len(facts), "parent_duplicate": duplicate,
            "parent_semantic_groups": len(signatures), "parent_ambiguous": len(signatures) > 1 or duplicate["conflict"],
            "parent_alternatives": [f.evidence(filing) for f in facts]}
    meta.update({"parent_selection": selection, "unique_dimension_enabled": allow_unique_dimension,
                 "dimension_target_groups": len(dimension_groups),
                 "dimension_target_fact_count": len(dimension_facts),
                 "dimension_target_alternatives": [f.evidence(filing) for f in dimension_facts],
                 "unique_dimensional_target_selected": selection == "unique dimensional asked-period fact"})
    context = filing.contexts[fact.context] if fact else (matching_contexts[0] if matching_contexts else None)
    return fact, context, meta


def _role_score(role: str, definition: str, duration: bool) -> tuple[int, int]:
    text = (role + " " + definition).lower()
    statement = int("statement" in text and "disclosure" not in text and "detail" not in text)
    relevant = (any(t in text for t in ("income", "operation", "cashflow", "cash flow")) if duration
                else any(t in text for t in ("balance", "financialposition", "financial position")))
    return statement, int(relevant)


def analyze(filing: XmlFiling, *, mode: str = "strict_complete", allow_unique_dimension: bool = False) -> Prediction:
    if mode not in {"strict_complete", "role_aware_conservative"}:
        raise ValueError("unknown namespace solver mode")
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        fact, context, parent_meta = select_parent(filing, allow_unique_dimension=allow_unique_dimension)
        reported = fact.value if fact else Decimal(0)
        evidence = {"target": filing.target, "target_lexical": filing.target_lexical,
                    "period": {"start": filing.start, "end": filing.end},
                    "parent": fact.evidence(filing) if fact else None,
                    **parent_meta, "diagnostics": filing.diagnostics,
                    "document_sha256": filing.document_sha256, "source": "bundled query only",
                    "namespace_aware": True, "decimal_precision": 80, "mode": mode,
                    "balance_metadata": filing.balances.get(filing.target),
                    "balance_never_changes_fact_sign": True, "accuracy": None,
                    "candidate_equations": [], "selected_equation": None,
                    "complete_evidence_gate": False}
        if filing.target is None:
            return Prediction("0", "0", "xml-unresolved-question", evidence)
        if context is None:
            return Prediction(format_number(reported), "0", "xml-unresolved-context", evidence)
        graph, index = defaultdict(list), defaultdict(list)
        for arc in filing.arcs:
            graph[(arc.role, arc.parent)].append(arc)
        for item in filing.facts:
            index[item.concept].append(item)

        def read(concept: str, role: str, active: frozenset[str], depth: int = 0) -> tuple[Decimal | None, dict]:
            if depth > 100 or concept in active:
                return None, {"kind": "unresolved", "concept": concept, "reason": "calculation-cycle-or-depth"}
            all_facts = index.get(concept, [])
            contextual = [f for f in all_facts if f.context in filing.contexts and
                          filing.contexts[f.context].signature == context.signature]
            unit_compatible = [f for f in contextual if fact and _same_unit(filing, fact.unit, f.unit)]
            selected, duplicate = _fact_choice(unit_compatible)
            if duplicate["conflict"]:
                return None, {"kind": "unresolved", "concept": concept, "reason": "inconsistent-duplicate-facts",
                              "duplicate": duplicate, "alternatives": [f.evidence(filing) for f in unit_compatible]}
            if selected is not None:
                node = selected.evidence(filing)
                node["duplicate"] = duplicate
                return selected.value, node
            children = graph.get((role, concept), [])
            if not children:
                reason = "unit-mismatch-or-undeclared-unit" if contextual else "context-mismatch" if all_facts else "missing-fact-and-equation"
                return None, {"kind": "unresolved", "concept": concept, "reason": reason,
                              "available_facts": [f.evidence(filing) for f in all_facts]}
            total, complete, terms = Decimal(0), True, []
            for arc in sorted(children, key=lambda a: (a.order, a.child)):
                value, node = read(arc.child, role, active | {concept}, depth + 1)
                terms.append({"arc": arc.evidence(), "node": node,
                              "weighted_value": format_number(arc.weight * value) if value is not None else None})
                if value is None:
                    complete = False
                else:
                    total += arc.weight * value
            return (total if complete else None), {"kind": "derived", "concept": concept, "role": role,
                                                   "complete": complete, "value": format_number(total) if complete else None,
                                                   "terms": terms}

        candidates = []
        for (role, parent), children in graph.items():
            if parent != filing.target:
                continue
            terms, total, missing = [], Decimal(0), 0
            for arc in sorted(children, key=lambda a: (a.order, a.child)):
                value, node = read(arc.child, role, frozenset({filing.target}))
                if value is None:
                    missing += 1
                else:
                    total += arc.weight * value
                terms.append({"arc": arc.evidence(), "node": node,
                              "weighted_value": format_number(arc.weight * value) if value is not None else None})
            role_conflict = any(d["kind"] in {"conflicting-arc-weights", "unresolved-arc", "unresolved-locator", "invalid-arc-priority"}
                                and d.get("role") == role for d in filing.diagnostics)
            complete = missing == 0 and bool(terms) and not role_conflict
            candidate = {"role": role, "role_definition": filing.role_definitions.get(role, ""),
                         "kind": "target-summation", "concept": filing.target, "complete": complete,
                         "missing_direct_children": missing, "direct_children": len(terms),
                         "arc_conflict": role_conflict, "value": format_number(total) if complete else None,
                         "observed_partial_sum": format_number(total), "terms": terms,
                         "role_preference": _role_score(role, filing.role_definitions.get(role, ""), bool(filing.end))}
            candidates.append(candidate)
        # A target can be a summation child. Solve that *complete* same-role
        # equation backwards without using the suspicious target fact as a
        # leaf. Parent and every sibling must have independent compatible
        # evidence; partial equations and cycles never imply missing zeroes.
        if mode == "role_aware_conservative":
            for (role, parent), children in graph.items():
                target_arcs = [a for a in children if a.child == filing.target]
                if parent == filing.target or len(target_arcs) != 1 or target_arcs[0].weight == 0:
                    continue
                target_arc = target_arcs[0]
                parent_value, parent_node = read(parent, role, frozenset({filing.target}))
                coefficient = Decimal(1) / target_arc.weight
                terms = [{"arc": target_arc.evidence(), "coefficient": format_number(coefficient),
                          "coefficient_origin": "1 / target arc weight; parent value",
                          "node": parent_node,
                          "weighted_value": format_number(coefficient * parent_value) if parent_value is not None else None}]
                total = coefficient * parent_value if parent_value is not None else Decimal(0)
                missing = int(parent_value is None)
                for arc in sorted(children, key=lambda a: (a.order, a.child)):
                    if arc.child == filing.target:
                        continue
                    value, node = read(arc.child, role, frozenset({filing.target, parent}))
                    coefficient = -arc.weight / target_arc.weight
                    terms.append({"arc": arc.evidence(), "coefficient": format_number(coefficient),
                                  "coefficient_origin": "negative sibling weight / target arc weight",
                                  "node": node,
                                  "weighted_value": format_number(coefficient * value) if value is not None else None})
                    if value is None:
                        missing += 1
                    else:
                        total += coefficient * value
                role_conflict = any(d["kind"] in {"conflicting-arc-weights", "unresolved-arc", "unresolved-locator", "invalid-arc-priority"}
                                    and d.get("role") == role for d in filing.diagnostics)
                complete = missing == 0 and not role_conflict
                candidates.append({"role": role, "role_definition": filing.role_definitions.get(role, ""),
                                   "kind": "inverse-target-summation", "concept": filing.target, "parent_equation": parent,
                                   "target_arc_weight": format_number(target_arc.weight), "complete": complete,
                                   "missing_direct_children": missing, "direct_children": len(terms),
                                   "arc_conflict": role_conflict, "value": format_number(total) if complete else None,
                                   "observed_partial_sum": format_number(total), "terms": terms,
                                   "role_preference": _role_score(role, filing.role_definitions.get(role, ""), bool(filing.end))})
        evidence["candidate_equations"] = candidates
        complete = [c for c in candidates if c["complete"]]
        evidence["complete_equation_count"] = len(complete)
        evidence["incomplete_equation_count"] = len(candidates) - len(complete)
        # Prefer forward equations when available. An inverse equation is an
        # additional hypothesis, not a reason to overturn complete forward data.
        forward = [c for c in complete if c["kind"] == "target-summation"]
        if forward:
            complete = forward
        values = {c["value"] for c in complete}
        evidence["role_value_disagreement"] = len(values) > 1
        winner = None
        if complete and len(values) == 1:
            winner = sorted(complete, key=lambda c: (c["role_preference"], c["role"]), reverse=True)[0]
            evidence["role_selection"] = "all complete target equations agree"
        elif complete and mode == "role_aware_conservative":
            best_score = max(c["role_preference"] for c in complete)
            best = [c for c in complete if c["role_preference"] == best_score]
            if best_score[0] and len({c["value"] for c in best}) == 1:
                winner = sorted(best, key=lambda c: c["role"])[0]
                evidence["role_selection"] = "unique value among preferred statement roles (not gold validated)"
        fatal = any(d["kind"] in {"xml-parse-failed", "forbidden-dtd-or-entity", "duplicate-context-id-conflict",
                                   "duplicate-unit-id-conflict", "invalid-scale"} for d in filing.diagnostics)
        if parent_meta["parent_ambiguous"]:
            return Prediction(format_number(reported), "0", "xml-ambiguous-parent", evidence)
        if fact is None:
            return Prediction("0", "0", "xml-unresolved-parent-fact", evidence)
        if fact.unit not in filing.units or not filing.units[fact.unit].numerator:
            return Prediction(format_number(reported), "0", "xml-unresolved-parent-unit", evidence)
        if fatal:
            return Prediction(format_number(reported), "0", "xml-document-integrity-failure", evidence)
        if winner is None:
            reason = "xml-role-disagreement" if len(values) > 1 else "xml-incomplete-equation" if candidates else "xml-no-target-equation"
            return Prediction(format_number(reported), "0", reason, evidence)
        evidence["selected_equation"] = winner
        evidence["complete_evidence_gate"] = (not evidence["role_value_disagreement"] and
                                              not any(d["kind"] in {"same-case-fragment-wrapper", "unqualified-xbrl-structure"}
                                                      for d in filing.diagnostics))
        mechanism = "xml-complete-inverse-summation" if winner["kind"] == "inverse-target-summation" else "xml-complete-summation"
        return Prediction(format_number(reported), winner["value"], mechanism, evidence)


def predict(query: str, *, mode: str = "strict_complete", allow_unique_dimension: bool = False) -> Prediction:
    return analyze(parse_xml(query), mode=mode, allow_unique_dimension=allow_unique_dimension)


def gated_hybrid(old: Prediction, strict: Prediction) -> Prediction:
    """Structural gate, not an assertion that unscored cases are more accurate.

    Synthetic fixtures validate this gate's mechanics. Actual practice/dev gold
    is unavailable, so no statistical dominance claim is made. Outside a fully
    supported unambiguous equation, the frozen old Decimal answer is retained.
    """
    if strict.evidence.get("complete_evidence_gate"):
        evidence = dict(strict.evidence)
        evidence["hybrid_gate"] = "complete unambiguous namespace/context/unit/source equation"
        evidence["quality_dominance_validated"] = False
        evidence["historical_decimal_values"] = [old.extracted_value, old.calculated_value]
        return Prediction(strict.extracted_value, strict.calculated_value, "hybrid-structural-gate", evidence)
    evidence = dict(strict.evidence)
    evidence["hybrid_gate"] = "not passed; historical Decimal retained"
    evidence["quality_dominance_validated"] = False
    evidence["legacy_unverified"] = True
    evidence["legacy_sign_or_agree_shortcut"] = old.mechanism in {"taxonomy-sign", "agree"}
    evidence["historical_decimal_mechanism"] = old.mechanism
    return Prediction(old.extracted_value, old.calculated_value, "hybrid-historical-retained", evidence)


def guarded_fallback(result: Prediction, *, policy: str = "agree", legacy: Prediction | None = None) -> Prediction:
    """A scoreable fallback ablation, not independent calculation evidence.

    ``agree`` tests retaining a proven selected reported value when a complete
    equation is absent. ``legacy_non_sign`` permits only the old engine's agree
    branch on the same unambiguous reported fact. Its unconditional balance-based
    absolute-value branch is explicitly rejected. Neither hypothesis is promoted
    as better before gold or an official Development score supports it.
    """
    if policy not in {"zero", "agree", "legacy_non_sign"}:
        raise ValueError("unknown fallback policy")
    evidence = dict(result.evidence)
    evidence.update({"fallback_policy": policy, "fallback_applied": False,
                     "fallback_accuracy_verified": False})
    if policy == "zero" or evidence.get("selected_equation") is not None:
        return Prediction(result.extracted_value, result.calculated_value, result.mechanism, evidence)
    parent = evidence.get("parent")
    blockers = {"xml-parse-failed", "forbidden-dtd-or-entity", "duplicate-context-id-conflict",
                "duplicate-unit-id-conflict", "invalid-scale", "conflicting-arc-weights",
                "unresolved-arc", "unresolved-locator", "invalid-arc-priority",
                "same-case-fragment-wrapper", "unqualified-xbrl-structure",
                "unresolved-unit-measure", "unresolved-target-namespace"}
    context = parent.get("context") if parent else None
    unit = parent.get("unit") if parent else None
    valid = (result.mechanism in {"xml-no-target-equation", "xml-incomplete-equation"}
             and parent is not None and context is not None and unit is not None
             and bool(context.get("entity")) and bool(context.get("entity_scheme"))
             and bool(unit.get("numerator")) and not context.get("dimensions") and not context.get("qualifiers")
             and not evidence.get("parent_ambiguous") and not evidence.get("parent_duplicate", {}).get("conflict")
             and not evidence.get("role_value_disagreement")
             and not any(d.get("kind") in blockers for d in evidence.get("diagnostics", []))
             and not any(c.get("arc_conflict") for c in evidence.get("candidate_equations", [])))
    if not valid:
        evidence["fallback_gate"] = "blocked: no unambiguous declared-unit target or document/role integrity uncertain"
        return Prediction(result.extracted_value, result.calculated_value, result.mechanism, evidence)
    if policy == "legacy_non_sign":
        if legacy is None or legacy.mechanism != "agree" or Decimal(legacy.extracted_value) != Decimal(parent["value"]):
            evidence["fallback_gate"] = "blocked: legacy agree not supported on the same selected target; no balance-to-abs fallback"
            evidence["legacy_sign_fallback_blocked"] = bool(legacy and legacy.mechanism == "taxonomy-sign")
            return Prediction(result.extracted_value, result.calculated_value, result.mechanism, evidence)
    evidence.update({"fallback_applied": True, "fallback_gate": "unambiguous selected target/context/declared unit",
                     "fallback_calculation_unverified": True, "independent_calculation_evidence": False,
                     "fallback_reason": "Development ablation hypothesis: retain reported value when equation is incomplete or absent",
                     "legacy_unverified": policy == "legacy_non_sign"})
    return Prediction(result.extracted_value, parent["value"], "guarded-reported-fallback", evidence)
