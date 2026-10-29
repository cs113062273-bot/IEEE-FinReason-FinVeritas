"""Isolated, unscored DQC0117 reported-member and subtotal candidates.

Only bundled documents enter inference. This implements a bounded subset of
9574/10093, with the pinned public statement-role exclusions. It is not a full
DTS/Xule processor. Copyright/license for the public definitions is preserved
under resources/task3_dqc0117 and resources/task3_round4_dqc.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path
import re

from lxml import etree

from .engine import Prediction
from .dimensional_sum import AXES, DIM, XBRLDT
from .dqc_statement_sum import _document, _locators
from .parser import format_number, split_sections
from .xml_core import LINK, XLINK, XmlFiling, attr, parse_xml, tag_parts
from .xml_engine import select_parent

ROOT = Path(__file__).resolve().parents[2]
CONSTANT_SHA = "9be6a5ad4d7130fde06465c9b460d5ece9adca7f50f253e0b55501e83aa8e75d"
RULE_SHA = "8df705ed472e44679449df8d8dae7aff48b6d89a0c653c5d95894d8e57a176b7"
ROLE_EXCLUSIONS = ("parenthetical", "equity", "deficit", "stockholders", "capital", "investment",
                   "changes", "shareholder", "convertible", "preferred", "temporaryequity",
                   "redeemable", "netproceedsfromallsources", "membersinterest")
CUBE_EXCLUSIONS = {"ScheduleOfInvestmentsTable", "SummaryOfInvestmentHoldingsTable",
                   "InvestmentsSoldNotYetPurchasedTable", "OpenOptionContractsWrittenTable",
                   "OpenFuturesContractTable", "OpenForwardForeignCurrencyContractTable", "OpenSwapContractTable"}
FATAL = {"xml-parse-failed", "forbidden-dtd-or-entity", "duplicate-context-id-conflict",
         "duplicate-unit-id-conflict", "invalid-scale"}


def statement_role_eligibility(role: str, description: str, cube: str = "", *, allow_inferred_uri: bool = False) -> tuple[bool, str]:
    """Apply the literal filters in pinned constant.xule:177-194."""
    inferred = (not description and allow_inferred_uri and
                bool(re.match(r"statement(?:-|_|[A-Z])", role.rstrip("/").rsplit("/", 1)[-1])))
    if "- Statement -" not in description and not inferred:
        return False, "role description lacks public statement marker"
    if any(token in role.lower() for token in ROLE_EXCLUSIONS):
        return False, "public statement URI exclusion"
    if any(token in description.lower() for token in ("schedule iii", "schedule iv")):
        return False, "public schedule III/IV exclusion"
    if cube.partition("}")[2] in CUBE_EXCLUSIONS:
        return False, "public investment cube exclusion"
    return True, "statement URI inference with omitted role description (ablation)" if inferred else "pinned public statement-role subset"


def _graph(query: str, filing: XmlFiling):
    root = _document(query, filing, "Definition linkbase document")
    graph, reverse, descriptions, bad, witness = defaultdict(set), defaultdict(set), {}, set(), {}
    if root is None:
        return graph, reverse, descriptions, {"*"}, witness
    digest = hashlib.sha256(split_sections(query).get("Definition linkbase document", "").encode()).hexdigest()
    for link in root.iter():
        if tag_parts(link) != (LINK, "definitionLink"):
            continue
        role = attr(link, "role", XLINK)
        descriptions[role] = filing.role_definitions.get(role) or attr(link, "title", XLINK)
        locs = _locators(link, filing)
        for arc in link:
            if tag_parts(arc) != (LINK, "definitionArc"):
                continue
            relation = attr(arc, "arcrole", XLINK)
            if not relation.startswith(DIM):
                continue
            parent, child = locs.get(attr(arc, "from", XLINK)), locs.get(attr(arc, "to", XLINK))
            if (not parent or not child or attr(arc, "targetRole", XBRLDT)
                    or attr(arc, "use") == "prohibited" or attr(arc, "priority") not in {"", "0"}):
                bad.add(role)
                continue
            kind = relation[len(DIM):]
            graph[(role, kind, parent)].add(child)
            reverse[(role, kind, child)].add(parent)
            witness[(role, kind, parent, child)] = {
                "role": role, "arcrole": relation, "parent": parent, "child": child,
                "line": arc.sourceline, "definition_sha256": digest,
                "xml": etree.tostring(arc, encoding="unicode", with_tail=False)}
    return graph, reverse, descriptions, bad, witness


def _reachable(graph, role, node, *, relation="domain-member") -> set:
    seen, pending = set(), [node]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(graph[(role, relation, current)] - seen)
    return seen


def _compatible(filing, parent, fact):
    pc, fc = filing.contexts[parent.context], filing.contexts.get(fact.context)
    if fc is None or fact.unit not in filing.units or fc.qualifiers:
        return False
    return ((fc.scheme, fc.entity, fc.start, fc.end, fc.instant) ==
            (pc.scheme, pc.entity, pc.start, pc.end, pc.instant)
            and filing.units[fact.unit].signature == filing.units[parent.unit].signature)


def _same_frame(filing, parent, fact):
    pc, fc = filing.contexts[parent.context], filing.contexts.get(fact.context)
    return bool(fc and not fc.qualifiers and (fc.scheme, fc.entity, fc.start, fc.end, fc.instant) ==
                (pc.scheme, pc.entity, pc.start, pc.end, pc.instant))


def dimensional_candidates(query: str, filing: XmlFiling, parent, *, allow_inferred_statement: bool = False) -> list[dict]:
    """Generate per-role, per-axis candidates without choosing a hidden rule.

    Every leaf is a reported target fact. Defined-but-absent and nil members
    are omitted by the rule's nonils reported-member query. An all-empty
    frontier abstains. Exact duplicate conflicts remain blockers in this
    bounded implementation; a rounded-duplicate extension is separate work.
    """
    graph, reverse, descriptions, bad, witness = _graph(query, filing)
    if "*" in bad:
        return []
    context, base = filing.contexts[parent.context], dict(filing.contexts[parent.context].dimensions)
    relevant = [f for f in filing.facts if f.concept == filing.target and _compatible(filing, parent, f)]
    incompatible = [f for f in filing.facts if f.concept == filing.target and _same_frame(filing, parent, f)
                    and not _compatible(filing, parent, f)]
    candidates = []
    for (role, relation, primary), cubes in list(graph.items()):
        if relation != "all" or filing.target not in _reachable(graph, role, primary):
            continue
        for cube in sorted(cubes):
            axes = graph[(role, "hypercube-dimension", cube)]
            role_eligible, role_reason = statement_role_eligibility(role, descriptions.get(role, ""), cube,
                                                                   allow_inferred_uri=allow_inferred_statement)
            if not role_eligible:
                continue
            excluded = any(r == role and rel == "notAll" and cube in cs and
                           filing.target in _reachable(graph, role, pi)
                           for (r, rel, pi), cs in list(graph.items()))
            if excluded:
                continue
            for axis in sorted(axes):
                uri, _, local = axis.lstrip("{").partition("}")
                if local not in AXES or not re.fullmatch(r"http://fasb\.org/(?:us-gaap|srt)/20\d\d(?:-\d{2}-\d{2})?", uri):
                    continue
                # 9574 uses a default total; 10093 uses a one-axis subtotal
                # and sums its second-axis facts. Both use same semantic frame.
                if axis in base or len(base) > 1:
                    continue
                fixed = tuple(sorted(base.items()))
                kind = "DQC.US.0117.10093" if fixed else "DQC.US.0117.9574"
                if fixed and (next(iter(base)) not in axes or
                              next(iter(base)).partition("}")[2] not in AXES or
                              local == "LegalEntityAxis"):
                    continue
                domains = graph[(role, "dimension-domain", axis)]
                if len(domains) != 1:
                    continue
                domain = next(iter(domains))
                defined = _reachable(graph, role, domain) - {domain}
                facts, multidimensional, blockers, outside_cube = defaultdict(list), [], [], []
                if role in bad:
                    blockers.append("unsupported effective arcs or targetRole transitions")
                # Public 606 exception requires a broader primary-item and
                # calculation-network analysis. Keep these candidates blocked.
                if local == "ProductOrServiceAxis" and filing.target.partition("}")[2] in {
                    "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax"}:
                    blockers.append("606 revenue/bank applicability requires full exception analysis")
                for fact in relevant:
                    dims = dict(filing.contexts[fact.context].dimensions)
                    if axis not in dims or any(dims.get(a) != m for a, m in fixed):
                        continue
                    if set(dims) - (set(base) | {axis}):
                        multidimensional.append(fact)
                        continue
                    member = dims[axis]
                    if not isinstance(member, str):
                        blockers.append("typed dimension is outside bounded member-query support")
                        continue
                    if member not in defined:
                        # @cube restricts queries to the cube's member domain;
                        # an unrelated disclosed member is not part of this
                        # statement partition and must not veto its sum.
                        outside_cube.append(fact.evidence(filing))
                        continue
                    facts[member].append(fact)
                for fact in incompatible:
                    dims = dict(filing.contexts[fact.context].dimensions)
                    if axis in dims and all(dims.get(a) == m for a, m in fixed):
                        blockers.append("reported target-axis witness has incompatible or undeclared unit")
                for member, fs in facts.items():
                    if len({f.value for f in fs}) > 1:
                        blockers.append("conflicting duplicate member:" + member)
                # 9574 multi-axis breakdowns require their one-axis subtotals.
                # For 10093, the same condition applies to third-axis detail.
                for fact in multidimensional:
                    member = dict(filing.contexts[fact.context].dimensions).get(axis)
                    if member not in facts:
                        blockers.append("multi-axis detail lacks reported member subtotal:" + str(member))
                selected, suppressed = [], []
                for member, fs in sorted(facts.items()):
                    ancestors = _reachable(reverse, role, member) - {member, domain}
                    if ancestors.intersection(facts):
                        suppressed.append(member)
                    else:
                        selected.append(min(fs, key=lambda f: f.index))
                if not selected:
                    blockers.append("no nonnil reported frontier members")
                # 9574/10093 permit notes overlap when a compatible notes fact
                # exceeds the default. Parenthetical overlap always blocks in
                # 9574. The bounded query still uses this target's exact frame.
                notes_max, parenthetical_overlap = None, False
                for (other_role, rel, other_primary), other_cubes in list(graph.items()):
                    if rel != "all" or filing.target not in _reachable(graph, other_role, other_primary):
                        continue
                    desc = descriptions.get(other_role, "")
                    if any(axis in graph[(other_role, "hypercube-dimension", oc)] for oc in other_cubes) and (facts or multidimensional):
                        if "- Statement -" in desc and "parenthetical" in other_role.lower():
                            parenthetical_overlap = True
                        elif "- Disclosure -" in desc:
                            notes_values = [f.value for f in relevant if axis in dict(filing.contexts[f.context].dimensions)
                                            and all(dict(filing.contexts[f.context].dimensions).get(a) == m for a,m in fixed)]
                            if notes_values:
                                maximum = max(notes_values)
                                notes_max = max(notes_max, maximum) if notes_max is not None else maximum
                if parenthetical_overlap and kind.endswith("9574"):
                    blockers.append("target-axis witnesses also aligned to parenthetical cube")
                if notes_max is not None and notes_max <= parent.value:
                    blockers.append("overlapping notes values do not exceed default target")
                with localcontext() as arithmetic:
                    arithmetic.prec = 80
                    total = sum((f.value for f in selected), Decimal(0))
                arcs = [w for (r, rel, p, c), w in witness.items() if r == role and
                        ((rel == "all" and p == primary and c == cube) or
                         (rel == "hypercube-dimension" and p == cube and c == axis) or
                         (rel == "dimension-domain" and p == axis and c == domain) or
                         (rel == "domain-member" and p in _reachable(graph, role, domain) and c in _reachable(graph, role, domain)))]
                candidates.append({"rule_subset": kind, "role": role, "role_definition": descriptions[role],
                    "statement_role_gate": role_reason, "cube": cube, "primary": primary, "axis": axis,
                    "domain": domain, "fixed_dimensions": fixed, "value": format_number(total),
                    "eligible": not blockers, "blockers": sorted(set(blockers)), "leaves": [f.evidence(filing) for f in selected],
                    "reported_member_count": len(selected), "suppressed_descendants": suppressed,
                    "multiaxis_detail_count": len(multidimensional), "defined_absent_members": sorted(defined - set(facts)),
                    "outside_cube_member_facts_ignored": outside_cube,
                    "notes_max_value": format_number(notes_max) if notes_max is not None else None,
                    "notes_greater_than_default_exception": notes_max is not None and notes_max > parent.value,
                    "missing_members_policy": "nonnil reported members only, without implicit-zero facts",
                    "source_rule_sha256": RULE_SHA, "source_constant_sha256": CONSTANT_SHA,
                    "definition_arcs": arcs, "source_scope": "bounded cube/domain and period/unit alignment",
                    "full_DTS_Xule_implementation": False})
    return candidates


def apply_dimensional_rule(query: str, filing: XmlFiling, prior: Prediction, *, allow_inferred_statement: bool = False) -> Prediction:
    if hashlib.sha256((ROOT / "resources/task3_round4_dqc/constant.xule").read_bytes()).hexdigest() != CONSTANT_SHA:
        raise ValueError("Pinned DQC statement constants changed")
    evidence = dict(prior.evidence)
    evidence.update(round4_dimensional_candidates=[], round4_dimensional_promoted=False,
                    round4_accuracy_verified=False, round4_full_rule_implementation=False)
    parent, context, selection = select_parent(filing, allow_unique_dimension=True)
    if (parent is None or context is None or selection["parent_ambiguous"] or parent.unit not in filing.units
            or Decimal(prior.extracted_value) != parent.value or not context.entity or not context.scheme
            or context.qualifiers or any(d.get("kind") in FATAL for d in filing.diagnostics)):
        evidence["round4_dimensional_gate"] = "uncertified selected target/context/unit/source"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    unit = filing.units[parent.unit]
    if unit.denominator or len(unit.numerator) != 1 or not unit.numerator[0].startswith("{http://www.xbrl.org/2003/iso4217}"):
        evidence["round4_dimensional_gate"] = "requires a certified monetary unit"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    candidates = dimensional_candidates(query, filing, parent, allow_inferred_statement=allow_inferred_statement)
    evidence["round4_dimensional_candidates"] = candidates
    mismatches = [c for c in candidates if c["eligible"] and Decimal(c["value"]) != parent.value]
    values = {c["value"] for c in mismatches}
    if len(values) != 1:
        evidence["round4_dimensional_gate"] = "no unique eligible mismatching dimensional value"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    selected = mismatches[0]
    if Decimal(selected["value"]) == Decimal(prior.calculated_value):
        evidence["round4_dimensional_gate"] = "reported frontier reproduces prior calculation"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    # A simultaneously applicable public nonnegative constraint can describe
    # another failure. It cannot select between disagreeing answer shapes.
    from .round3_engine import nonnegative_eligibility
    constraint = nonnegative_eligibility(filing, parent, context)
    if constraint["eligible"] and Decimal(selected["value"]) != parent.value.copy_negate():
        evidence["round4_dimensional_gate"] = "dimensional value conflicts with public nonnegative constraint"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    evidence.update(round4_dimensional_promoted=True, round4_selected_dimensional=selected,
                    round4_dimensional_gate="unique mismatching reported-member subtotal candidate",
                    round4_prior_calculated=prior.calculated_value,
                    actual_calculation_evidence_kind="round4_reported_member_subtotal_subset",
                    actual_prediction_complete_calculation_evidence=False, complete_evidence_gate=False,
                    actual_prediction_method="round4_dimensional", actual_prediction_calculated=selected["value"],
                    actual_prediction_extracted=prior.extracted_value)
    for key, flag in (("selected_equation", "selected_equation"),
                      ("selected_dimensional_equation", "dimensional_sum_promoted"),
                      ("selected_statement_equation", "statement_sum_promoted"),
                      ("selected_reported_partition", "reported_partition_promoted")):
        node = evidence.get(key)
        if node and Decimal(node["value"]) != Decimal(selected["value"]):
            evidence["round4_counter_" + key] = node
            if flag == key:
                evidence[key] = None
            else:
                evidence[flag] = False
    return Prediction(prior.extracted_value, selected["value"], "round4-dqc0117-reported-subtotal", evidence)


def predict(query: str) -> Prediction:
    from .round3_priority import predict as prior_predict
    return apply_dimensional_rule(query, parse_xml(query), prior_predict(query))


def predict_uri_ablation(query: str) -> Prediction:
    from .round3_priority import predict as prior_predict
    return apply_dimensional_rule(query, parse_xml(query), prior_predict(query), allow_inferred_statement=True)
