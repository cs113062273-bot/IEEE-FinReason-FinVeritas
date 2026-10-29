"""Bounded DQC0117-style, complete single-axis statement breakdown sums.

This conservative subset requires a supplied statement cube, the target as a
primary item, a supported axis and a completely evidenced member frontier.
Multi-axis facts, missing/nil leaves, conflicting duplicates/roles and foreign
targetRole transitions abstain. It is not a full XULE/DTS implementation.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext
import hashlib
import re

from lxml import etree

from .engine import Prediction
from .parser import format_number, split_sections
from .xml_core import LINK, XLINK, XSI, XmlFiling, _safe_xml, attr, expanded, tag_parts

XBRLDT = "http://xbrl.org/2005/xbrldt"
DIM = "http://xbrl.org/int/dim/arcrole/"
AXES = {"StatementClassOfStockAxis", "ProductOrServiceAxis", "PropertyPlantAndEquipmentByTypeAxis",
        "LongtermDebtTypeAxis", "RelatedPartyTransactionsByRelatedPartyAxis", "StatementBusinessSegmentsAxis",
        "FinancialInstrumentAxis", "LimitedPartnersCapitalAccountByClassAxis", "PartnerTypeOfPartnersCapitalAccountAxis",
        "FiniteLivedIntangibleAssetsByMajorClassAxis", "InformationByCategoryOfDebtSecurityAxis"}


def apply_dimensional_sum(query: str, filing: XmlFiling, prior: Prediction) -> Prediction:
    evidence = dict(prior.evidence)
    evidence["dimensional_candidates"] = []
    evidence["dimensional_sum_promoted"] = False
    parent = evidence.get("parent")
    if (not parent or evidence.get("parent_ambiguous") or parent["context"]["dimensions"]
            or parent["context"]["qualifiers"] or not parent.get("unit")):
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    if (parent["unit"]["denominator"] or len(parent["unit"]["numerator"]) != 1
            or not parent["unit"]["numerator"][0].startswith("{http://www.xbrl.org/2003/iso4217}")):
        evidence["dimensional_abstention"] = "nonmonetary or compound unit"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    context = filing.contexts[parent["context_ref"]]
    target = filing.target
    sections = split_sections(query)
    diagnostics = []
    definition_text = sections.get("Definition linkbase document", "")
    root = _safe_xml(definition_text, "Definition linkbase document", filing.namespaces, diagnostics)
    if root is None or diagnostics:
        evidence["dimensional_parse_diagnostics"] = diagnostics
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    definition_sha = hashlib.sha256(definition_text.encode("utf-8")).hexdigest()
    graph = defaultdict(list)
    role_info, bad_roles = {}, set()
    for link in root.iter("{" + LINK + "}definitionLink"):
        role = attr(link, "role", XLINK)
        text = (role + " " + attr(link, "title", XLINK) + " " + filing.role_definitions.get(role, "")).lower()
        statement = "statement" in text or "balancesheet" in text or "financialposition" in text
        if not statement or any(t in text for t in ("disclosure", "parenthetical", "note -", "detail", "stockholdersequity", "shareholdersequity", "changesinequity", "changes in equity", "statementofequity")):
            continue
        role_info[role] = {"role": role, "title": attr(link, "title", XLINK), "definition": filing.role_definitions.get(role, "")}
        locs = {}
        for node in link:
            if tag_parts(node) == (LINK, "loc"):
                fragment = attr(node, "href", XLINK).partition("#")[2]
                prefix, separator, local = fragment.partition("_")
                concept = expanded(prefix + ":" + local, filing.namespaces) if separator else None
                if concept:
                    locs[attr(node, "label", XLINK)] = concept
        seen = set()
        for node in link:
            if tag_parts(node) != (LINK, "definitionArc"):
                continue
            arcrole = attr(node, "arcrole", XLINK)
            if not arcrole.startswith(DIM):
                continue
            parent_concept, child = locs.get(attr(node, "from", XLINK)), locs.get(attr(node, "to", XLINK))
            transition = attr(node, "targetRole", XBRLDT)
            if (not parent_concept or not child or (transition and transition != role)
                    or attr(node, "use") == "prohibited" or attr(node, "priority") not in {"", "0"}):
                bad_roles.add(role)
                continue
            key = (arcrole, parent_concept, child)
            if key in seen:
                continue
            seen.add(key)
            graph[(role, arcrole[len(DIM):], parent_concept)].append((child, {
                "role": role, "arcrole": arcrole, "parent": parent_concept, "child": child,
                "line": node.sourceline, "definition_sha256": definition_sha,
                "xml": etree.tostring(node, encoding="unicode", with_tail=False)}))

    def descendants(role: str, node: str, active=frozenset()) -> set[str]:
        if node in active:
            return set()
        return {node} | set().union(*(descendants(role, child, active | {node})
                                    for child, _ in graph.get((role, "domain-member", node), [])))

    candidates = []
    with localcontext() as precision:
        precision.prec = 80
        for (role, relation, primary), cube_edges in list(graph.items()):
            if relation != "all" or role in bad_roles or target not in descendants(role, primary):
                continue
            for cube, cube_arc in cube_edges:
                if any(relation2 == "notAll" and role2 == role and target in descendants(role, primary2)
                       and any(excluded_cube == cube for excluded_cube, _ in excluded_edges)
                       for (role2, relation2, primary2), excluded_edges in graph.items()):
                    continue
                for axis, axis_arc in graph.get((role, "hypercube-dimension", cube), []):
                    namespace, _, local = axis.lstrip("{").partition("}")
                    if local not in AXES or not re.fullmatch(r"http://fasb\.org/(?:us-gaap|srt)/20\d\d", namespace):
                        continue
                    if local == "ProductOrServiceAxis" and target.partition("}")[2] in {
                            "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax"}:
                        # The public rule has special FASB 606 banking/revenue
                        # exceptions. This bounded trial excludes that entire
                        # combination instead of pretending to implement them.
                        continue
                    domain_edges = graph.get((role, "dimension-domain", axis), [])
                    if len(domain_edges) != 1:
                        continue
                    domain, domain_arc = domain_edges[0]
                    defined = descendants(role, domain) - {domain}
                    facts, blockers = defaultdict(list), []
                    for fact in filing.facts:
                        if fact.concept != target or fact.context not in filing.contexts or fact.unit not in filing.units:
                            continue
                        fc = filing.contexts[fact.context]
                        if ((fc.scheme, fc.entity, fc.start, fc.end, fc.instant) !=
                                (context.scheme, context.entity, context.start, context.end, context.instant)
                                or fc.qualifiers or filing.units[fact.unit].signature != filing.units[parent["unit_ref"]].signature):
                            continue
                        dimensions = dict(fc.dimensions)
                        if axis not in dimensions:
                            continue
                        if len(dimensions) != 1 or not isinstance(dimensions[axis], str):
                            blockers.append("multiple-or-typed-dimensions")
                            continue
                        member = dimensions[axis]
                        if member not in defined:
                            blockers.append("reported-member-outside-defined-statement-frontier")
                            continue
                        facts[member].append(fact)
                    for member, fs in facts.items():
                        if len({f.value for f in fs}) > 1:
                            blockers.append("inconsistent-member-duplicates")
                    # Any matching nil target in the axis is a missing member,
                    # not an implicit zero. Parse it directly from supplied XML.
                    instance = _safe_xml(sections.get("Instance document", ""), "Instance document", filing.namespaces, [])
                    if instance is not None:
                        for node in instance.iter():
                            if node.tag != target or attr(node, "nil", XSI).lower() not in {"true", "1"}:
                                continue
                            nc = filing.contexts.get(attr(node, "contextRef"))
                            if nc and (nc.scheme, nc.entity, nc.start, nc.end, nc.instant) == (context.scheme, context.entity, context.start, context.end, context.instant) and axis in dict(nc.dimensions):
                                blockers.append("nil-member-fact")
                    selected, missing, selected_arcs = [], [], []
                    def frontier(node: str, active=frozenset()) -> None:
                        if node in active:
                            missing.append("cycle:" + node)
                            return
                        if node in facts:
                            selected.append(min(facts[node], key=lambda f: f.index))
                            return  # reported ancestor excludes descendants
                        children = graph.get((role, "domain-member", node), [])
                        if not children:
                            missing.append(node)
                            return
                        for child, arc in children:
                            selected_arcs.append(arc)
                            frontier(child, active | {node})
                    frontier(domain)
                    value = sum((f.value for f in selected), Decimal(0))
                    complete = bool(selected) and not missing and not blockers
                    candidate = {"kind": "complete-single-axis-dimensional-sum", **role_info[role], "axis": axis,
                                 "domain": domain, "cube": cube, "primary_item": primary,
                                 "complete": complete, "value": format_number(value) if complete else None,
                                 "missing_members": missing, "blockers": sorted(set(blockers)),
                                 "member_count": len(selected), "leaves": [f.evidence(filing) for f in selected],
                                 "definition_arcs": [cube_arc, axis_arc, domain_arc, *selected_arcs],
                                 "definition_sha256": definition_sha, "same_entity_period_unit": True,
                                 "full_rule_implementation": False,
                                 "source_rule_sha256": "8df705ed472e44679449df8d8dae7aff48b6d89a0c653c5d95894d8e57a176b7"}
                    candidates.append(candidate)
    evidence["dimensional_candidates"] = candidates
    complete = [c for c in candidates if c["complete"]]
    values = {c["value"] for c in complete}
    if len(values) == 1:
        candidate = complete[0]
        evidence["selected_dimensional_equation"] = candidate
        # A satisfied dimension check is not evidence to overrule a different
        # calculation failure. Promote only a real default/breakdown mismatch.
        if Decimal(candidate["value"]) != Decimal(prior.extracted_value):
            evidence.update({"dimensional_sum_promoted": True, "dimensional_rule": "DQC.US.0117.9574 subset",
                             "independent_calculation_evidence": True, "accuracy_verified": False})
            return Prediction(prior.extracted_value, candidate["value"], "dqc0117-complete-dimensional-sum", evidence)
    elif len(values) > 1:
        evidence["dimensional_axis_or_role_disagreement"] = True
    return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
