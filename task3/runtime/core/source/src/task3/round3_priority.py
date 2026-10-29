"""Additional public-rule trial; never rewrites frozen A/B/C packages.

DQC0117 aggregates reported nonnil members, suppressing reported descendants
of a reported ancestor. Unreported definition leaves alone are not a refusal
condition in that part of the public rule. All other source/integrity gates
remain; this is still a bounded fragment subset, not a full DTS/XULE engine.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, localcontext

from .engine import Prediction
from .dimensional_sum import apply_dimensional_sum, DIM, XBRLDT
from .dqc_statement_sum import _document, _locators, apply_statement_sum
from .parser import format_number
from .round3_engine import _alternative_axes, nonnegative_eligibility, solve
from .xml_core import LINK, XLINK, attr, number, parse_xml, tag_parts


def _partition_scope_blocks(query, filing, candidate, parent):
    root = _document(query, filing, "Definition linkbase document")
    if root is None:
        return ["missing definition source"]
    graph, role_text, bad = defaultdict(set), {}, set()
    for link in root.iter():
        if tag_parts(link) != (LINK, "definitionLink"):
            continue
        role = attr(link, "role", XLINK)
        role_text[role] = (role + " " + attr(link, "title", XLINK) + " " + filing.role_definitions.get(role, "")).lower()
        locators = _locators(link, filing)
        for arc in link:
            if tag_parts(arc) != (LINK, "definitionArc"):
                continue
            arcrole = attr(arc, "arcrole", XLINK)
            frm, to = locators.get(attr(arc, "from", XLINK)), locators.get(attr(arc, "to", XLINK))
            if (attr(arc, "targetRole", XBRLDT) or attr(arc, "use") == "prohibited"
                    or attr(arc, "priority") not in {"", "0"}):
                bad.add(role)
            if frm and to and arcrole.startswith(DIM):
                graph[(role, arcrole[len(DIM):], frm)].add(to)
    role, axis, cube = candidate["role"], candidate["axis"], candidate["cube"]
    blocks = []
    if role in bad:
        blocks.append("unsupported effective arcs or role transitions")
    if len(graph[(role, "hypercube-dimension", cube)]) != 1:
        blocks.append("multi-axis cube requires additional subtotal/DTS proof")
    if any(token in cube.partition("}")[2].lower() for token in ("disclosure", "schedule")):
        blocks.append("disclosure/schedule cube despite statement-like role")
    if _alternative_axes(filing, parent, axis):
        blocks.append("competing same-target axes")
    def reachable(current_role, primary):
        visited, remaining = set(), [primary]
        while remaining:
            current = remaining.pop()
            if current in visited:
                continue
            visited.add(current)
            remaining.extend(graph[(current_role, "domain-member", current)] - visited)
        return visited
    for (other_role, relation, primary), cubes in tuple(graph.items()):
        if relation != "all" or not any(t in role_text.get(other_role, "") for t in ("notes", "disclosure", "detail", "parenthetical")):
            continue
        if filing.target not in reachable(other_role, primary):
            continue
        if any(axis in graph[(other_role, "hypercube-dimension", c)] for c in cubes):
            blocks.append("target-axis monetary witnesses also belong to a notes/parenthetical cube")
    return sorted(set(blocks))


def apply_reported_partition(query, filing, prior):
    probe = apply_dimensional_sum(query, filing, prior)
    parent = probe.evidence.get("parent")
    candidates, blocked = [], []
    if not parent:
        return prior
    for candidate in probe.evidence.get("dimensional_candidates", []):
        if (candidate["complete"] or not candidate["missing_members"] or candidate["blockers"]
                or not candidate["leaves"] or any(m.startswith("cycle:") for m in candidate["missing_members"])):
            if candidate["blockers"] or any(m.startswith("cycle:") for m in candidate["missing_members"]):
                blocked.append({"axis": candidate["axis"], "cube": candidate["cube"],
                                "blocks": [*candidate["blockers"], *(m for m in candidate["missing_members"] if m.startswith("cycle:"))]})
            continue
        blocks = _partition_scope_blocks(query, filing, candidate, parent)
        if blocks:
            blocked.append({"axis": candidate["axis"], "cube": candidate["cube"], "blocks": blocks})
            continue
        with localcontext() as precision:
            precision.prec = 80
            total = sum((number(f["value"]) for f in candidate["leaves"]), Decimal(0))
        record = dict(candidate)
        record.update(value=format_number(total), complete=False,
                      reported_frontier_resolved=True, unreported_definition_leaves_omitted=True,
                      source_rule_policy="public 9574 nonnil reported members, ancestor suppression retained")
        candidates.append(record)
    evidence = dict(prior.evidence)
    evidence.update(reported_partition_candidates=candidates, reported_partition_blocked=blocked)
    if len({c["value"] for c in candidates}) != 1:
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    selected = candidates[0]
    if number(selected["value"]) == number(prior.calculated_value):
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    evidence.update(selected_reported_partition=selected, reported_partition_promoted=True,
                    actual_calculation_evidence_kind="reported_dimension_frontier_subset",
                    actual_prediction_complete_calculation_evidence=False, accuracy_verified=False)
    return Prediction(prior.extracted_value, selected["value"], "dqc0117-reported-frontier-subset", evidence)


def priority_parent_guard(filing, evidence, fact):
    """Do not repair a sign when the source does not select a unique target."""
    if fact is None or fact.context not in filing.contexts or fact.unit not in filing.units:
        return False, "selected target/context/unit missing"
    fatal = {"xml-parse-failed", "forbidden-dtd-or-entity", "duplicate-context-id-conflict",
             "duplicate-unit-id-conflict", "invalid-scale"}
    if any(d.get("kind") in fatal for d in filing.diagnostics):
        return False, "document integrity blocker"
    anomaly_unique = bool(evidence.get("anomaly_parent_selection", {}).get("selection_unique"))
    if evidence.get("parent_ambiguous") and not anomaly_unique:
        return False, "unresolved parent ambiguity"
    if evidence.get("parent_duplicate", {}).get("conflict") and not anomaly_unique:
        return False, "conflicting parent duplicates"
    context, unit = filing.contexts[fact.context], filing.units[fact.unit]
    duplicates = [f for f in filing.facts if f.concept == fact.concept and f.context in filing.contexts
                  and filing.contexts[f.context].signature == context.signature and f.unit in filing.units
                  and filing.units[f.unit].signature == unit.signature]
    if len({f.value for f in duplicates}) != 1:
        return False, "chosen semantic target group has conflicting values"
    return True, "unique selected semantic group" if not anomaly_unique else "explicitly unique source-constraint anomaly group"


def predict(query):
    prior = solve(query, statement_adapter=apply_statement_sum, anomaly_selection=True)["decimal_unique_semantic"]
    filing = parse_xml(query)
    result = apply_reported_partition(query, filing, prior)
    evidence = dict(result.evidence)
    evidence.update(round3_C_extracted=prior.extracted_value, round3_C_calculated=prior.calculated_value,
                    round3_C_mechanism=prior.mechanism)
    parent = evidence.get("parent")
    fact = next((f for f in filing.facts if parent and f.concept == filing.target
                 and f.context == parent["context_ref"] and f.unit == parent["unit_ref"]
                 and f.value == number(result.extracted_value)), None)
    constraint = nonnegative_eligibility(filing, fact, filing.contexts[fact.context]) if fact else {"eligible": False}
    safe_parent, guard = priority_parent_guard(filing, evidence, fact)
    evidence["public_constraint_priority_gate"] = guard
    if safe_parent and constraint["eligible"] and number(result.calculated_value) != fact.value.copy_negate():
        evidence.update(public_constraint_priority=constraint, priority_sign_promoted=True,
                        counter_calculated_value=result.calculated_value,
                        new_constraints_applied=True,
                        actual_calculation_evidence_kind="public_constraint_priority_sign_hypothesis",
                        actual_prediction_complete_calculation_evidence=False,
                        original_magnitude_correctness_verified=False)
        result = Prediction(result.extracted_value, format_number(fact.value.copy_negate()), "public-nonnegative-priority-hypothesis", evidence)
    for key, promoted in (("selected_equation", "selected_equation"), ("selected_dimensional_equation", "dimensional_sum_promoted"),
                          ("selected_statement_equation", "statement_sum_promoted"),
                          ("selected_reported_partition", "reported_partition_promoted")):
        node = evidence.get(key)
        if node and number(node["value"]) != number(result.calculated_value):
            evidence["counter_" + key] = node
            if promoted == key:
                evidence[key] = None
            else:
                evidence[promoted] = False
    evidence["complete_evidence_gate"] = evidence["actual_prediction_complete_calculation_evidence"]
    evidence.update(actual_prediction_method="decimal_public_priority", actual_prediction_extracted=result.extracted_value,
                    actual_prediction_calculated=result.calculated_value)
    return Prediction(result.extracted_value, result.calculated_value, result.mechanism, evidence)
