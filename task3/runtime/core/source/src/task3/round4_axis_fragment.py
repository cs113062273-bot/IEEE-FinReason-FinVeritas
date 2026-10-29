"""Optional source-only axis-fragment and missing-extraction ablations.

This does not certify DQC0117 cube/form applicability. It tests a reported
target's same-frame facts on one public supported axis when the supplied
definition fragment does not establish the full partition. A missing target
keeps extraction's required failure sentinel 0; it is never invented as an
actual reported zero. No case ID, gold, rule label or external source enters.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext
import re

from .engine import Prediction
from .dimensional_sum import AXES
from .parser import format_number
from .round4_dimensional import FATAL, _graph, _reachable, statement_role_eligibility
from .xml_engine import select_parent


def fragment_axis_candidates(query, filing, parent):
    context, unit = filing.contexts[parent.context], filing.units[parent.unit]
    groups, blockers = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    graph, reverse, descriptions, bad_roles, witnesses = _graph(query,filing)
    for fact in filing.facts:
        fc = filing.contexts.get(fact.context)
        if (fact.concept != filing.target or fc is None or fc.qualifiers or
                (fc.scheme,fc.entity,fc.start,fc.end,fc.instant) !=
                (context.scheme,context.entity,context.start,context.end,context.instant)):
            continue
        for axis, member in fc.dimensions:
            uri, _, local = axis.lstrip("{").partition("}")
            if local not in AXES or not re.fullmatch(r"http://fasb\.org/(?:us-gaap|srt)/20\d\d(?:-\d\d-\d\d)?", uri):
                continue
            if len(fc.dimensions) != 1 or not isinstance(member,str):
                blockers[axis].append("multiple or typed dimensions require subtotal proof")
                continue
            child_unit = filing.units.get(fact.unit)
            if child_unit is None or child_unit.signature != unit.signature:
                blockers[axis].append("undeclared or incompatible target-axis unit")
                continue
            groups[axis][member].append(fact)
    candidates = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for axis, members in sorted(groups.items()):
            hierarchy_roles = []
            for (role,relation,node),domains in list(graph.items()):
                if relation=="dimension-domain" and node==axis and role not in bad_roles and len(domains)==1:
                    domain=next(iter(domains))
                    if set(members).issubset(_reachable(graph,role,domain)):
                        hierarchy_roles.append((role,domain))
            suppressed_by_role = []
            for role,domain in hierarchy_roles:
                suppressed_by_role.append({member for member in members if
                    (_reachable(reverse,role,member)-{member,domain}).intersection(members)})
            suppressed = suppressed_by_role[0] if suppressed_by_role else set()
            if len(members)>1 and not hierarchy_roles:
                blockers[axis].append("multiple reported members lack supplied ancestor/subtotal proof")
            if any(s!=suppressed for s in suppressed_by_role):
                blockers[axis].append("supplied hierarchy roles disagree on ancestor suppression")
            statement_hierarchy = [role for role,domain in hierarchy_roles
                                   if statement_role_eligibility(role,descriptions.get(role,''))[0]]
            notes_hierarchy = [role for role,domain in hierarchy_roles
                               if '- Disclosure -' in descriptions.get(role,'') or
                               re.search(r'(?:^|[/_-])(?:notes?|disclosure)(?:$|[/_-])',role.lower())]
            if notes_hierarchy and not statement_hierarchy:
                # A note-domain hierarchy can place an aggregate alongside its
                # breakdown as siblings. Numeric independence is not proved by
                # that layout, and DQC0117 statement scope is not established.
                blockers[axis].append("axis hierarchy belongs to notes/disclosure with no certified statement hierarchy")
            leaves = []
            for member, facts in sorted(members.items()):
                if len({f.value for f in facts}) != 1:
                    blockers[axis].append("inconsistent duplicate member values")
                if member not in suppressed:
                    leaves.append(min(facts,key=lambda f:f.index))
            total = sum((f.value for f in leaves), Decimal(0))
            candidates.append({"axis":axis,"value":format_number(total),"leaves":[f.evidence(filing) for f in leaves],
                "members":len(leaves),"eligible":not blockers[axis],"blockers":sorted(set(blockers[axis])),
                "same_entity_period_unit":True,"cube_domain_applicability_proven":False,
                "ancestor_subtotal_suppression_proven":bool(hierarchy_roles),"suppressed_members":sorted(suppressed),
                "hierarchy_roles":[{"role":r,"domain":d,"description":descriptions.get(r,''),
                                    "public_statement_eligible":statement_role_eligibility(r,descriptions.get(r,''))[0]}
                                   for r,d in hierarchy_roles],
                "statement_hierarchy_roles":statement_hierarchy,"notes_hierarchy_roles":notes_hierarchy,
                "frontier_policy":"supplied hierarchy suppresses descendants of reported ancestors" if hierarchy_roles else "single reported member; no hierarchy invented",
                "complete_rule_implementation":False})
    return candidates


def apply_fragment_axis(query, filing, prior):
    evidence = dict(prior.evidence)
    evidence.update(fragment_axis_promoted=False, fragment_axis_candidates=[], fragment_axis_accuracy_verified=False)
    parent, context, meta = select_parent(filing,allow_unique_dimension=True)
    if (parent is None or context is None or not context.consolidated or meta["parent_ambiguous"] or
            parent.unit not in filing.units or Decimal(prior.extracted_value) != parent.value or
            not context.entity or not context.scheme or any(d.get("kind") in FATAL for d in filing.diagnostics)):
        evidence["fragment_axis_gate"] = "requires a unique declared reported consolidated target"
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    unit = filing.units[parent.unit]
    if unit.denominator or len(unit.numerator)!=1 or not unit.numerator[0].startswith("{http://www.xbrl.org/2003/iso4217}"):
        evidence["fragment_axis_gate"] = "requires a declared monetary unit"
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    if evidence.get("round4_dimensional_promoted"):
        evidence["fragment_axis_gate"] = "retain a cube/domain supported candidate"
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    equation=evidence.get("selected_equation")
    complete_forward=bool(equation and equation.get("complete") and equation.get("kind")=="target-summation" and
                          Decimal(equation["value"])==Decimal(prior.calculated_value))
    if complete_forward or evidence.get("actual_prediction_complete_calculation_evidence"):
        evidence["fragment_axis_gate"]="retain complete source calculation; unproven fragment scope cannot override it"
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    candidates = fragment_axis_candidates(query,filing,parent)
    evidence["fragment_axis_candidates"] = candidates
    eligible = [c for c in candidates if c["eligible"] and Decimal(c["value"]) != parent.value]
    if len({c["value"] for c in eligible}) != 1:
        evidence["fragment_axis_gate"] = "no unique mismatching supported-axis reported sum"
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    from .round4_rules import eligibility
    constraint = eligibility(filing,parent,context)
    selected = eligible[0]
    if constraint["eligible"] and Decimal(selected["value"]) != parent.value.copy_negate():
        evidence["fragment_axis_gate"] = "conflicts with public nonnegative constraint"
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    if Decimal(selected["value"]) == Decimal(prior.calculated_value):
        evidence["fragment_axis_gate"] = "reported axis sum already equals prior calculation"
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    evidence.update(fragment_axis_promoted=True,fragment_axis_selected=selected,
        fragment_axis_prior_calculated=prior.calculated_value,
        fragment_axis_gate="unique same-frame reported sum; full cube/domain applicability unavailable",
        actual_calculation_evidence_kind="fragment_axis_scope_hypothesis",
        actual_prediction_complete_calculation_evidence=False,complete_evidence_gate=False,
        actual_prediction_calculated=selected["value"],actual_prediction_extracted=prior.extracted_value)
    if evidence.get("selected_equation"):
        evidence["fragment_axis_counter_equation"] = evidence["selected_equation"]
        evidence["selected_equation"] = None
    return Prediction(prior.extracted_value,selected["value"],"round4-fragment-axis-hypothesis",evidence)


def apply_missing_extraction_calculation(query, filing, prior):
    """Calculate complete forward sums even if extraction remains unresolved."""
    evidence = dict(prior.evidence)
    evidence.update(missing_target_calculation_promoted=False,missing_target_candidates=[])
    asked = [c for c in filing.contexts.values() if c.consolidated and c.scheme and c.entity and
             ((c.start,c.end)==(filing.start,filing.end) if filing.end else c.instant==filing.start)]
    target_facts = [f for f in filing.facts if f.concept==filing.target and f.context in filing.contexts and
                    ((filing.contexts[f.context].start,filing.contexts[f.context].end)==(filing.start,filing.end)
                     if filing.end else filing.contexts[f.context].instant==filing.start)]
    if target_facts or Decimal(prior.extracted_value)!=0 or not asked or any(d.get("kind") in FATAL for d in filing.diagnostics):
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    graph, candidates = defaultdict(list), []
    for arc in filing.arcs:
        if arc.parent==filing.target:
            graph[arc.role].append(arc)
    for context in asked:
        for role, arcs in graph.items():
            if any(d.get("role")==role and d.get("kind") in {"conflicting-arc-weights","unresolved-arc","unresolved-locator","invalid-arc-priority"}
                   for d in filing.diagnostics):
                continue
            units = {filing.units[f.unit].signature for f in filing.facts if f.context in filing.contexts and
                     filing.contexts[f.context].signature==context.signature and f.unit in filing.units and
                     f.concept in {a.child for a in arcs}}
            for unit in units:
                if len(unit[0])!=1 or unit[1] or not unit[0][0].startswith("{http://www.xbrl.org/2003/iso4217}"):
                    continue
                terms, missing, total = [], [], Decimal(0)
                with localcontext() as arithmetic:
                    arithmetic.prec=80
                    for arc in arcs:
                        facts = [f for f in filing.facts if f.concept==arc.child and f.context in filing.contexts and
                                 filing.contexts[f.context].signature==context.signature and f.unit in filing.units and
                                 filing.units[f.unit].signature==unit]
                        if not facts or len({f.value for f in facts})!=1:
                            missing.append(arc.child)
                            continue
                        fact=min(facts,key=lambda f:f.index)
                        total+=arc.weight*fact.value
                        terms.append({"arc":arc.evidence(),"fact":fact.evidence(filing),"weighted_value":format_number(arc.weight*fact.value)})
                if missing or not terms:
                    continue
                candidates.append({"role":role,"context":context.evidence(),"unit_signature":unit,
                    "terms":terms,"value":format_number(total),"complete_direct_children":True,
                    "reported_extraction_remains_unresolved":True})
    evidence["missing_target_candidates"]=candidates
    frames={(c["context"]["entity_scheme"],c["context"]["entity"],jsonable(c["unit_signature"])) for c in candidates}
    if len(frames)!=1 or len({c["value"] for c in candidates})!=1:
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    selected=candidates[0]
    if Decimal(selected["value"])==Decimal(prior.calculated_value):
        return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,evidence)
    evidence.update(missing_target_calculation_promoted=True,missing_target_selected=selected,
        extraction_zero_is_failure_sentinel_not_reported_fact=True,
        actual_calculation_evidence_kind="missing_extraction_complete_forward_subset",
        actual_prediction_complete_calculation_evidence=True,complete_evidence_gate=True,
        actual_prediction_calculated=selected["value"])
    return Prediction("0",selected["value"],"round4-missing-extraction-forward",evidence)


def jsonable(value):
    return tuple(tuple(v) for v in value)


def predict(query):
    from .round4_engine import predict as engine_predict
    from .xml_core import parse_xml
    filing=parse_xml(query,allow_complete_prefix=True)
    return apply_fragment_axis(query,filing,apply_missing_extraction_calculation(query,filing,engine_predict(query)))
