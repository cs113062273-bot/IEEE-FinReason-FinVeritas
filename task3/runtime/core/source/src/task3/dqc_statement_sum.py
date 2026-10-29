"""Bounded direct-child statement sums motivated by public DQC US.0126.

This is a Development hypothesis, not a complete XULE rule implementation.
The supplied fragments generally omit DocumentPeriodEndDate, applicable-form
metadata, and a full DTS. We use the explicitly asked period, do not expand
unreported children recursively, and never combine roles or dimensions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, localcontext
import hashlib

from .engine import Prediction
from .exact_arithmetic import add as exact_add, product as exact_product
from .parser import format_number, split_sections
from .xml_core import LINK, XLINK, XmlFiling, _safe_xml, attr, expanded, tag_parts
from .xml_engine import select_parent

RULE_SHA = "088565835eac4ffb6eb61ea12c1c93d6149e22dcbee5286d446c1cc9c5f5e0d4"
XBRLDT = "http://xbrl.org/2005/xbrldt"
DIMENSION_ARCROLE = "http://xbrl.org/int/dim/arcrole/all"


def _document(query: str, filing: XmlFiling, section: str):
    return _safe_xml(split_sections(query).get(section, ""), section, filing.namespaces, [])


def _locators(link, filing: XmlFiling) -> dict:
    result = {}
    for node in link:
        if tag_parts(node) != (LINK, "loc"):
            continue
        fragment = attr(node, "href", XLINK).partition("#")[2]
        prefix, separator, local = fragment.partition("_")
        concept = expanded(prefix + ":" + local, filing.namespaces) if separator else None
        if concept:
            result[attr(node, "label", XLINK)] = concept
    return result


def apply_statement_sum(query: str, filing: XmlFiling, prior: Prediction, *,
                        allow_missing_direct: bool = False) -> Prediction:
    """Use a witnessed non-table statement relationship, retaining all blockers.

    Missing/nil direct addends may be omitted only in the explicitly experimental
    policy. Missing compatible values because of unit mismatch or duplicate
    conflicts are always blockers. The original reported value is never changed.
    """
    evidence = dict(prior.evidence)
    evidence.update(statement_sum_promoted=False, statement_sum_candidates=[],
                    statement_rule="DQC.US.0126.9590 bounded direct-child hypothesis",
                    statement_rule_complete_implementation=False, statement_rule_source_sha256=RULE_SHA,
                    statement_rule_period_policy="explicitly asked period; DEI/form scope may be omitted",
                    statement_sum_missing_policy="omit absent direct addends (experimental)" if allow_missing_direct else "require every direct addend")
    def retain(reason: str) -> Prediction:
        evidence["statement_sum_gate"] = reason
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)

    parent, context, meta = select_parent(filing, allow_unique_dimension=True)
    if (not parent or not context or not context.consolidated or meta["parent_ambiguous"]
            or parent.unit not in filing.units or not filing.units[parent.unit].numerator
            or parent.value != Decimal(prior.extracted_value)):
        return retain("requires an unambiguous consolidated target with the same extracted value")
    if any(d.get("kind") in {"xml-parse-failed", "forbidden-dtd-or-entity", "duplicate-context-id-conflict",
                             "duplicate-unit-id-conflict", "invalid-scale"} for d in filing.diagnostics):
        return retain("document integrity blocker")
    if any(f.concept.partition("}")[2] == "LiabilitiesSubjectToCompromise" for f in filing.facts):
        return retain("bankruptcy exception conservatively excluded without complete form/text metadata")
    presentation = _document(query, filing, "Presentation linkbase document")
    definition = _document(query, filing, "Definition linkbase document")
    if presentation is None or definition is None:
        return retain("both presentation and definition documents required")
    cube_roles, invalid_roles = set(), set()
    for link in definition.iter():
        if tag_parts(link) != (LINK, "definitionLink"):
            continue
        role = attr(link, "role", XLINK)
        for arc in link:
            if tag_parts(arc) != (LINK, "definitionArc"):
                continue
            if attr(arc, "arcrole", XLINK) == DIMENSION_ARCROLE:
                cube_roles.add(role)
            if attr(arc, "targetRole", XBRLDT) or attr(arc, "priority") not in {"", "0"}:
                invalid_roles.add(role)
    witnessed_roles = {}
    for link in presentation.iter():
        if tag_parts(link) != (LINK, "presentationLink"):
            continue
        role = attr(link, "role", XLINK)
        description = filing.role_definitions.get(role, "") + " " + attr(link, "title", XLINK)
        text = (role + " " + description).lower()
        if "statement" not in text or any(token in text for token in ("disclosure", "detail", "parenthetical", "equity")):
            continue
        if role in cube_roles or role in invalid_roles:
            continue
        locators = _locators(link, filing)
        involved = set()
        bad = False
        for arc in link:
            if tag_parts(arc) != (LINK, "presentationArc"):
                continue
            if attr(arc, "use") == "prohibited" or attr(arc, "priority") not in {"", "0"}:
                bad = True
            involved.update(filter(None, (locators.get(attr(arc, "from", XLINK)), locators.get(attr(arc, "to", XLINK)))))
        if filing.target in involved and not bad:
            witnessed_roles[role] = description
    graph = defaultdict(list)
    for arc in filing.arcs:
        if arc.parent == filing.target and arc.role in witnessed_roles:
            graph[arc.role].append(arc)
    candidates = []
    for role, arcs in graph.items():
        if any(d.get("role") == role and d.get("kind") in {"conflicting-arc-weights", "unresolved-arc", "unresolved-locator", "invalid-arc-priority"}
               for d in filing.diagnostics):
            continue
        precision_counts = Counter(f.decimals for f in filing.facts if f.context in filing.contexts
                                   and filing.contexts[f.context].signature == context.signature
                                   and f.unit in filing.units and filing.units[f.unit].signature == filing.units[parent.unit].signature)
        modal = max(precision_counts, key=lambda p: (precision_counts[p], p)) if precision_counts else None
        total, terms, missing, blockers = Decimal(0), [], [], []
        with localcontext() as arithmetic:
            arithmetic.prec = 80
            for arc in arcs:
                contextual = [f for f in filing.facts if f.concept == arc.child and f.context in filing.contexts
                              and filing.contexts[f.context].signature == context.signature]
                compatible = [f for f in contextual if f.unit in filing.units and filing.units[f.unit].numerator and
                              filing.units[f.unit].signature == filing.units[parent.unit].signature]
                if contextual and not compatible:
                    blockers.append("incompatible-or-undeclared-child-unit:" + arc.child)
                if len({f.value for f in compatible}) > 1:
                    blockers.append("conflicting-duplicate-child:" + arc.child)
                    continue
                if not compatible:
                    missing.append(arc.child)
                    terms.append({"arc": arc.evidence(), "fact": None, "direct_addend_absent": True,
                                  "recursion_used": False})
                    continue
                chosen = min(compatible, key=lambda f: (f.decimals != modal, f.index))
                total = exact_add(total, exact_product(arc.weight, chosen.value))
                terms.append({"arc": arc.evidence(), "fact": chosen.evidence(filing),
                              "weighted_value": format_number(exact_product(arc.weight, chosen.value)), "recursion_used": False})
        if missing and not allow_missing_direct:
            blockers.append("missing-direct-child")
        observed = len(terms) - len(missing)
        if not observed:
            blockers.append("no-observed-addends")
        candidates.append({"role": role, "role_definition": witnessed_roles[role], "value": format_number(total),
                           "parent": parent.evidence(filing), "terms": terms, "missing": missing,
                           "blockers": blockers, "observed_direct_children": observed,
                           "modal_decimals": modal, "eligible": not blockers,
                           "complete": not blockers and not missing,
                           "all_direct_children_present": not missing, "no_cube_role": True,
                           "presentation_sha256": hashlib.sha256(split_sections(query).get("Presentation linkbase document", "").encode()).hexdigest(),
                           "definition_sha256": hashlib.sha256(split_sections(query).get("Definition linkbase document", "").encode()).hexdigest()})
    evidence["statement_sum_candidates"] = candidates
    eligible = [c for c in candidates if c["eligible"]]
    if not eligible:
        return retain("no eligible direct statement equation")
    if len({c["value"] for c in eligible}) != 1:
        return retain("eligible statement roles disagree")
    selected = eligible[0]
    evidence["selected_statement_equation"] = selected
    if Decimal(selected["value"]) == Decimal(prior.calculated_value):
        return retain("direct statement result already agrees with prior")
    evidence.update(statement_sum_promoted=True, statement_sum_gate="witnessed non-cube statement direct sum; Development calibration required",
                    accuracy_verified=False)
    return Prediction(prior.extracted_value, selected["value"], "dqc0126-direct-statement-hypothesis", evidence)
