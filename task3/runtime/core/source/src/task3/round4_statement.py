"""Isolated DQC0126 source-network decimals and first-value tier candidate.

Public generic rules only; no labels, answer tables, model/API or network calls.
This remains a bounded fragment implementation: asked period substitutes for
omitted DEI/form metadata, ties in most_frequent abstain, and list-first order
is the stable supplied fact order rather than a full Xule alignment scheduler.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path

from .engine import Prediction
from .dqc_statement_sum import _document, _locators
from .parser import format_number
from .round4_dimensional import CONSTANT_SHA, FATAL, statement_role_eligibility
from .xml_core import LINK, XLINK, attr, parse_xml, tag_parts
from .xml_engine import select_parent

ROOT = Path(__file__).resolve().parents[2]
LIB_FUNCTION_SHA = "7017ea34482bf7b2b5369de94d6628e7840bde75157bc4faf9d39df019c43ea6"
RULE_SHA = "088565835eac4ffb6eb61ea12c1c93d6149e22dcbee5286d446c1cc9c5f5e0d4"
XBRLDT = "http://xbrl.org/2005/xbrldt"
DIMENSION_ALL = "http://xbrl.org/int/dim/arcrole/all"
PRES_EXTRA_EXCLUSIONS = ("membershipinterest", "highlights", "employee", "ebp")


def decimals_rank(value: str) -> Decimal | None:
    if value.upper() == "INF":
        return Decimal("Infinity")
    try:
        return Decimal(int(value))
    except (ValueError, TypeError):
        return None


def network_modal_decimals(filing, role: str) -> tuple[Decimal | None, dict]:
    """Covered nonnil facts for calcNetworkSource, across all semantic frames."""
    concepts = {arc.parent for arc in filing.arcs if arc.role == role}
    counts = Counter(decimals_rank(f.decimals) for f in filing.facts if f.concept in concepts)
    unknown = counts.pop(None, 0)
    winners = [d for d, count in counts.items() if count == max(counts.values())] if counts else []
    # Public lib/functions.xule builds dict(count, item), with a set as input.
    # Tied frequencies collide; no deterministic highest-decimals rule exists.
    modal = winners[0] if len(winners) == 1 and not unknown else None
    return modal, {"source_concepts": sorted(concepts), "decimals_counts": {str(d): n for d,n in counts.items()},
                   "unknown_decimals_count": unknown, "tied_modes": [str(d) for d in sorted(winners)] if len(winners)>1 else [],
                   "modal_decimals": str(modal) if modal is not None else None,
                   "covered_policy": "all nonnil supplied facts whose concept is a source in this calculation role",
                   "tie_policy": "abstain on ambiguous most_frequent dictionary collision",
                   "public_functions_sha256": LIB_FUNCTION_SHA}


def first_value_by_decimals(facts, modal: Decimal):
    """Respect exact, then >=, then < tier, with source-order first within tier."""
    tiers = [[f for f in facts if decimals_rank(f.decimals) == modal],
             [f for f in facts if decimals_rank(f.decimals) is not None and decimals_rank(f.decimals) >= modal],
             [f for f in facts if decimals_rank(f.decimals) is not None and decimals_rank(f.decimals) < modal]]
    names = ("decimals==modal", "decimals>=modal", "decimals<modal")
    for name, tier in zip(names, tiers):
        if not tier:
            continue
        chosen = min(tier, key=lambda f: f.index)
        same_precision = [f for f in tier if decimals_rank(f.decimals) == decimals_rank(chosen.decimals)]
        conflict = len({f.value for f in same_precision}) > 1
        return (None if conflict else chosen), {"tier": name, "chosen_index": chosen.index,
            "chosen_decimals": chosen.decimals, "same_precision_conflict": conflict,
            "tier_indexes": [f.index for f in sorted(tier, key=lambda f:f.index)],
            "cross_tier_values_differ": len({f.value for f in facts}) > 1,
            "within_tier_policy": "first in stable supplied fact order; full Xule scheduler not reproduced"}
    return None, {"tier": "all alternatives unbound", "same_precision_conflict": False,
                  "unknown_decimals": any(decimals_rank(f.decimals) is None for f in facts)}


def _witnessed_roles(query, filing, *, allow_inferred_statement=False):
    presentation = _document(query, filing, "Presentation linkbase document")
    definition = _document(query, filing, "Definition linkbase document")
    if presentation is None or definition is None:
        return {}, {"*"}, set()
    cube_roles, bad_roles = set(), set()
    for link in definition.iter():
        if tag_parts(link) != (LINK, "definitionLink"):
            continue
        role, locs = attr(link, "role", XLINK), _locators(link, filing)
        description = filing.role_definitions.get(role) or attr(link, "title", XLINK)
        inferred = bool(allow_inferred_statement and not description and "statement" in role.lower()
                        and any(k in role.lower() for k in ("balance", "income", "operation", "cashflow", "financialposition")))
        if inferred:
            description = "- Statement - (inferred from supplied relationship URI; missing role metadata)"
        for arc in link:
            if tag_parts(arc) != (LINK, "definitionArc"):
                continue
            if attr(arc, "arcrole", XLINK) == DIMENSION_ALL:
                cube = locs.get(attr(arc, "to", XLINK), "")
                if statement_role_eligibility(role, description, cube)[0]:
                    cube_roles.add(role)
            if attr(arc, "targetRole", XBRLDT) or attr(arc, "priority") not in {"", "0"}:
                bad_roles.add(role)
    roles = {}
    for link in presentation.iter():
        if tag_parts(link) != (LINK, "presentationLink"):
            continue
        role = attr(link, "role", XLINK)
        description = filing.role_definitions.get(role) or attr(link, "title", XLINK)
        if (allow_inferred_statement and not description and "statement" in role.lower()
                and any(k in role.lower() for k in ("balance", "income", "operation", "cashflow", "financialposition"))):
            description = "- Statement - (inferred from supplied relationship URI; missing role metadata)"
        if (not statement_role_eligibility(role, description)[0]
                or any(t in role.lower() for t in PRES_EXTRA_EXCLUSIONS) or role in cube_roles or role in bad_roles):
            continue
        locs, involved, unsupported = _locators(link, filing), set(), False
        for arc in link:
            if tag_parts(arc) != (LINK, "presentationArc"):
                continue
            priority = attr(arc, "priority")
            if attr(arc, "use") == "prohibited" or (priority and (not priority.isdigit())):
                unsupported = True
            involved.update(filter(None, [locs.get(attr(arc, "from", XLINK)), locs.get(attr(arc, "to", XLINK))]))
        if filing.target in involved and not unsupported:
            roles[role] = description
    return roles, bad_roles, cube_roles


def statement_candidates(query, filing, parent, *, allow_inferred_statement=False):
    roles, bad, cubes = _witnessed_roles(query, filing, allow_inferred_statement=allow_inferred_statement)
    if "*" in bad:
        return []
    graph, result = defaultdict(list), []
    context, parent_unit = filing.contexts[parent.context], filing.units[parent.unit]
    for arc in filing.arcs:
        if arc.parent == filing.target and arc.role in roles:
            graph[arc.role].append(arc)
    for role, arcs in graph.items():
        modal, modal_evidence = network_modal_decimals(filing, role)
        blockers = []
        if modal is None:
            blockers.append("source-network decimals mode missing, unknown or tied")
        if modal is not None and decimals_rank(parent.decimals) != modal:
            blockers.append("reported target is not at statement modal decimals")
        if any(d.get("role") == role and d.get("kind") in {"conflicting-arc-weights", "unresolved-arc", "unresolved-locator", "invalid-arc-priority"}
               for d in filing.diagnostics):
            blockers.append("unsupported or conflicting effective calculation arcs")
        terms, missing, total, observed = [], [], Decimal(0), 0
        with localcontext() as arithmetic:
            arithmetic.prec = 80
            for arc in arcs:
                contextual = [f for f in filing.facts if f.concept == arc.child and f.context in filing.contexts
                              and filing.contexts[f.context].signature == context.signature]
                compatible = [f for f in contextual if f.unit in filing.units and filing.units[f.unit].numerator
                              and filing.units[f.unit].signature == parent_unit.signature]
                if contextual and not compatible:
                    blockers.append("incompatible or undeclared child unit:" + arc.child)
                selected, choice = first_value_by_decimals(compatible, modal) if modal is not None else (None, {"tier":"unresolved modal"})
                if choice.get("same_precision_conflict") or choice.get("unknown_decimals"):
                    blockers.append("ambiguous or unknown child decimals:" + arc.child)
                if selected is None:
                    missing.append(arc.child)
                    terms.append({"arc": arc.evidence(), "fact": None, "choice": choice,
                                  "unbound_addend_omitted": True, "recursion_used": False})
                    continue
                weighted = arc.weight * selected.value
                total += weighted
                observed += 1
                terms.append({"arc": arc.evidence(), "fact": selected.evidence(filing), "choice":choice,
                              "weighted_value": format_number(weighted), "recursion_used": False,
                              "alternative_facts": [f.evidence(filing) for f in compatible if f.index != selected.index]})
        if not observed:
            blockers.append("all direct addends unbound; source sum is none")
        # Source exception requires both the addend relationship and bankruptcy
        # text fact. Missing text/form metadata leaves this conservative blocker.
        if any(a.child.partition("}")[2] == "LiabilitiesSubjectToCompromise" for a in arcs):
            blockers.append("Chapter 11 exception cannot be certified from fragments")
        result.append({"rule_subset":"DQC.US.0126.9590", "role":role, "role_definition":roles[role],
            "modal":modal_evidence, "value":format_number(total), "parent":parent.evidence(filing),
            "terms":terms, "missing":missing, "observed_direct_children":observed,
            "eligible":not blockers, "blockers":sorted(set(blockers)), "all_direct_children_present":not missing,
            "source_rule_sha256":RULE_SHA, "source_constant_sha256":CONSTANT_SHA,
            "source_functions_sha256":LIB_FUNCTION_SHA, "recursion_used":False,
            "period_policy":"explicitly asked period; DEI/current form applicability not certified",
            "full_DTS_Xule_implementation":False})
    return result


def apply_statement_rule(query, filing, prior, *, allow_inferred_statement=False):
    for name, digest in (("constant.xule", CONSTANT_SHA), ("functions-lib.xule", LIB_FUNCTION_SHA)):
        if hashlib.sha256((ROOT / "resources/task3_round4_dqc" / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Pinned generic DQC source changed")
    evidence = dict(prior.evidence)
    evidence.update(round4_statement_candidates=[], round4_statement_promoted=False, round4_accuracy_verified=False)
    parent, context, selection = select_parent(filing, allow_unique_dimension=True)
    if (parent is None or context is None or not context.consolidated or selection["parent_ambiguous"]
            or Decimal(prior.extracted_value) != parent.value or parent.unit not in filing.units
            or not filing.units[parent.unit].numerator or not context.entity or not context.scheme
            or any(d.get("kind") in FATAL for d in filing.diagnostics)):
        evidence["round4_statement_gate"] = "requires unambiguous consolidated target with source integrity"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    candidates = statement_candidates(query, filing, parent, allow_inferred_statement=allow_inferred_statement)
    evidence["round4_statement_candidates"] = candidates
    eligible = [c for c in candidates if c["eligible"]]
    if len({c["value"] for c in eligible}) != 1:
        evidence["round4_statement_gate"] = "no unique eligible direct source-mode sum"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    selected = eligible[0]
    if Decimal(selected["value"]) == Decimal(prior.calculated_value):
        evidence["round4_statement_gate"] = "corrected source tier reproduces prior calculation"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    from .round3_engine import nonnegative_eligibility
    constraint = nonnegative_eligibility(filing, parent, context)
    if constraint["eligible"] and Decimal(selected["value"]) != parent.value.copy_negate():
        evidence["round4_statement_gate"] = "direct sum conflicts with applicable public nonnegative constraint"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    if evidence.get("dimensional_sum_promoted") or evidence.get("reported_partition_promoted"):
        evidence["round4_statement_gate"] = "retain an existing reported dimensional-rule candidate"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    evidence.update(round4_statement_promoted=True, round4_selected_statement=selected,
        round4_statement_gate="unique direct same-context sum with source-network decimals and ordered first-value tiers",
        round4_statement_prior_calculated=prior.calculated_value,
        actual_calculation_evidence_kind="round4_direct_source_decimals_subset",
        actual_prediction_complete_calculation_evidence=selected["all_direct_children_present"],
        complete_evidence_gate=selected["all_direct_children_present"], actual_prediction_method="round4_statement",
        actual_prediction_extracted=prior.extracted_value, actual_prediction_calculated=selected["value"])
    for key, flag in (("selected_equation","selected_equation"), ("selected_statement_equation","statement_sum_promoted")):
        node = evidence.get(key)
        if node and Decimal(node["value"]) != Decimal(selected["value"]):
            evidence["round4_counter_" + key] = node
            if key == flag:
                evidence[key] = None
            else:
                evidence[flag] = False
    return Prediction(prior.extracted_value, selected["value"], "round4-dqc0126-source-decimals", evidence)


def predict(query):
    from .round3_priority import predict as d_predict
    return apply_statement_rule(query, parse_xml(query), d_predict(query))


def predict_combined(query):
    from .round4_dimensional import apply_dimensional_rule
    filing = parse_xml(query)
    return apply_dimensional_rule(query, filing, predict(query))
