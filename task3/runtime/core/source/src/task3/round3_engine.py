"""Round 3: keep calibrated Decimal calculations and repair source selection.

This module leaves every historical engine and ZIP intact. Generic DQC rule
definitions are licensed under resources/task3_dqc0015/License.md; no private
labels, filing findings, network calls or answer caches enter inference.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from .engine import Prediction, predict as decimal_predict
from .dqc_nonnegative import public_constraints
from .dimensional_sum import apply_dimensional_sum
from .parser import format_number
from .xml_core import XmlContext, XmlFact, XmlFiling, number, parse_xml
from .xml_engine import analyze, select_parent

ROOT = Path(__file__).resolve().parents[2]
METHODS = ("decimal_unique", "decimal_unique_sign", "decimal_unique_semantic")


def _local(name: str) -> str:
    return name.partition("}")[2] if name.startswith("{") else name.split(":")[-1]


@lru_cache(maxsize=1)
def member_exclusions() -> dict:
    """Read the pinned generic exclusion workbook with preserved cell columns."""
    workbook = ROOT / "resources/task3_dqc0015/DQC_0015_MemberExclusions.xlsx"
    expected = "5c666f28fcd6c90032fe661347c5efbfcf2447e3e1902e0fa5752b329d1318bd"
    if hashlib.sha256(workbook.read_bytes()).hexdigest() != expected:
        raise ValueError("Pinned DQC0015 member exclusions SHA mismatch")
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    result = {"strings": set(), "members": set(), "axes": set(), "axis_members": set(), "source_sha256": expected}
    with zipfile.ZipFile(workbook) as archive:
        strings = ["".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        for name in archive.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            for row in ET.fromstring(archive.read(name)).findall(".//m:row", ns):
                cells = {}
                for cell in row:
                    letters = re.match(r"[A-Z]+", cell.get("r", ""))
                    if not letters:
                        continue
                    index = 0
                    for letter in letters[0]:
                        index = index * 26 + ord(letter) - ord("A") + 1
                    value = cell.find("m:v", ns)
                    if value is not None:
                        cells[index - 1] = strings[int(value.text)] if cell.get("t") == "s" else value.text
                kind, test = cells.get(3, ""), cells.get(4, "")
                first, second = cells.get(7, ""), cells.get(11, "")
                if kind == "Member" and "contains" in test:
                    result["strings"].add(first.lower())
                elif kind == "Member" and test == "Member equals":
                    result["members"].add(first)
                elif kind == "Axis" and test == "Axis equals":
                    if "AND member equals" in cells.get(8, ""):
                        result["axis_members"].add((first, second))
                    else:
                        result["axes"].add(first)
    # Extra conservative exclusions explicitly present in approved-v29 generic
    # constant-us-gaap.xule. These only reduce applicability, never add concepts.
    constants = ROOT / "resources/task3_dqc0015/round3_constant-us-gaap.xule"
    constant_sha = "6c8377948ba8cadb3d6f749b5e9c72b4f769c2322fac1b839507309a7f8c09c3"
    if hashlib.sha256(constants.read_bytes()).hexdigest() != constant_sha:
        raise ValueError("Pinned DQC0015 constant source SHA mismatch")
    result["constant_sha256"] = constant_sha
    result["strings"].update({"basisswap", "unfunded"})
    result["axes"].update({"StatementBusinessSegmentsAxis", "InvestmentIdentifierAxis", "IncomeTaxEffectChangeInLawAxis"})
    return result


def nonnegative_eligibility(filing: XmlFiling, fact: XmlFact, context: XmlContext) -> dict:
    registry, source = public_constraints()
    match = re.fullmatch(r"\{http://fasb\.org/us-gaap/(202[3-6])\}(.+)", fact.concept)
    result = {"eligible": False, "rule": None, "exclusion": None, "definition_commit": source["commit"],
              "constraint_proves_original_magnitude": False}
    if match is None or match[2] not in registry[int(match[1])] or fact.value >= 0:
        result["exclusion"] = "not a negative listed concept in the exact supported namespace"
        return result
    if (context.qualifiers or not context.entity or not context.scheme or fact.unit not in filing.units
            or not filing.units[fact.unit].numerator):
        result["exclusion"] = "unknown entity/unit or opaque context qualifier"
        return result
    exclusions = member_exclusions()
    for axis, member in context.dimensions:
        if not isinstance(member, str):
            result["exclusion"] = "typed dimension: applicability not certified"
            return result
        axis_name, member_name = _local(axis), _local(member)
        # A conservative local-name exemption match also protects custom
        # aliases of adjustment/elimination dimensions, rather than guessing.
        if axis_name in exclusions["axes"]:
            result["exclusion"] = "public excluded axis: " + axis_name
            return result
        if member_name in exclusions["members"] or any(token and token in member_name.lower() for token in exclusions["strings"]):
            result["exclusion"] = "public excluded member: " + member_name
            return result
        if (axis_name, member_name) in exclusions["axis_members"]:
            result["exclusion"] = "public excluded axis/member pair"
            return result
    result.update({"eligible": True, "rule": "DQC.US.0015." + registry[int(match[1])][match[2]],
                   "member_exclusions_sha256": exclusions["source_sha256"], "namespace_year": match[1],
                   "constant_source_sha256": exclusions["constant_sha256"],
                   "scope": "concept/member subset; applicable-form metadata unavailable"})
    return result


def _matching_period(context: XmlContext, filing: XmlFiling) -> bool:
    return (context.start, context.end) == (filing.start, filing.end) if filing.end else context.instant == filing.start


def constraint_anomaly_parent(filing: XmlFiling) -> tuple[XmlFact | None, dict]:
    """An optional, source-rule-based selector for otherwise ambiguous targets."""
    groups = defaultdict(list)
    for fact in filing.facts:
        context = filing.contexts.get(fact.context)
        if fact.concept == filing.target and context and _matching_period(context, filing) and fact.unit in filing.units:
            groups[(context.signature, filing.units[fact.unit].signature)].append(fact)
    # Other entities or incompatible units cannot be resolved by a rule anomaly.
    frames = {(filing.contexts[fs[0].context].scheme, filing.contexts[fs[0].context].entity,
               filing.units[fs[0].unit].signature) for fs in groups.values()}
    monetary = all(filing.units[fs[0].unit].numerator
                   and len(filing.units[fs[0].unit].numerator) == 1
                   and not filing.units[fs[0].unit].denominator
                   and filing.units[fs[0].unit].numerator[0].startswith("{http://www.xbrl.org/2003/iso4217}")
                   for fs in groups.values())
    violations, evidence = [], []
    for facts in groups.values():
        values = {f.value for f in facts}
        fact = min(facts, key=lambda f: f.index)
        constraint = nonnegative_eligibility(filing, fact, filing.contexts[fact.context])
        info = {"fact": fact.evidence(filing), "duplicate_values": sorted(format_number(v) for v in values), "constraint": constraint}
        evidence.append(info)
        if len(values) == 1 and constraint["eligible"]:
            violations.append(fact)
    integrity = any(d.get("kind") in {"xml-parse-failed", "forbidden-dtd-or-entity", "duplicate-context-id-conflict",
                                      "duplicate-unit-id-conflict", "invalid-scale"} for d in filing.diagnostics)
    unique = len(violations) == 1 and len(groups) > 1 and len(frames) == 1 and monetary and not integrity
    return (violations[0] if unique else None), {"anomaly_groups": evidence,
            "source_constraint_violation_groups": len(violations), "selection_unique": unique,
            "entity_unit_frames": len(frames), "monetary_unit_certified": monetary,
            "inferred_rule_not_hidden_label": True, "gold_correctness": None}


def _alternative_axes(filing: XmlFiling, parent: dict, selected_axis: str) -> list[str]:
    context = filing.contexts[parent["context_ref"]]
    unit = filing.units.get(parent["unit_ref"])
    axes = set()
    for fact in filing.facts:
        fc = filing.contexts.get(fact.context)
        if (fact.concept != filing.target or fc is None or fact.unit not in filing.units or unit is None
                or (fc.scheme, fc.entity, fc.start, fc.end, fc.instant) != (context.scheme, context.entity, context.start, context.end, context.instant)
                or filing.units[fact.unit].signature != unit.signature):
            continue
        axes.update(axis for axis, _ in fc.dimensions if axis != selected_axis)
    return sorted(axes)


def solve(query: str, *, statement_adapter=None, anomaly_selection: bool = False) -> dict[str, Prediction]:
    """Three bounded candidates, starting with the calibrated Decimal route."""
    old = decimal_predict(query, mode="conservative")
    filing = parse_xml(query)
    xml = analyze(filing, mode="strict_complete", allow_unique_dimension=True)
    fact, context, selection = select_parent(filing, allow_unique_dimension=True)
    evidence = dict(xml.evidence)
    evidence.update({"round3_base": "historical Decimal; observed provisional Development ACC66.32",
                     "provisional_score_is_not_official_final": True, "old_decimal_extracted": old.extracted_value,
                     "old_decimal_calculated": old.calculated_value, "old_decimal_mechanism": old.mechanism,
                     "old_decimal_evidence": old.evidence, "calculation_correctness": None,
                     "no_external_case_answers": True, "extraction_changed": False,
                     "new_constraints_applied": False})
    extracted, calculated = old.extracted_value, old.calculated_value
    if (fact and context and selection["unique_dimensional_target_selected"] and not selection["parent_ambiguous"]
            and fact.unit in filing.units and filing.units[fact.unit].numerator and context.entity and context.scheme
            and not any(d.get("kind") in {"xml-parse-failed", "forbidden-dtd-or-entity", "duplicate-context-id-conflict",
                                          "duplicate-unit-id-conflict", "invalid-scale"} for d in filing.diagnostics)):
        extracted = format_number(fact.value)
        # A previously missing target's old answer had no valid dimensional
        # dependency. Recompute only a complete direct/recursive forward sum
        # in the selected exact context; do not introduce an inverse equation.
        calculated = xml.calculated_value if xml.evidence.get("selected_equation") else "0"
        evidence["extraction_changed"] = number(extracted) != number(old.extracted_value)
        evidence["extraction_policy"] = "unique numeric semantic group in the asked period"
        if xml.evidence.get("selected_equation") is None:
            alternative = analyze(filing, mode="role_aware_conservative", allow_unique_dimension=True).evidence.get("selected_equation")
            if alternative and alternative["kind"] == "inverse-target-summation":
                evidence["alternative_complete_inverse_equation"] = alternative
                evidence["candidate_equations"] = [*evidence.get("candidate_equations", []), alternative]
                evidence["inverse_policy"] = "counter-evidence only; inverse not introduced into calibrated Decimal route"
    eq = xml.evidence.get("selected_equation")
    if eq is None or number(eq["value"]) != number(calculated):
        evidence["selected_equation"] = None
    else:
        evidence["incumbent_calculation_has_independent_source_equation"] = True
    first = Prediction(extracted, calculated, "decimal-unique:" + old.mechanism, evidence)
    second_evidence = dict(evidence)
    if fact and context:
        constraint = nonnegative_eligibility(filing, fact, context)
        second_evidence["public_nonnegative_constraint"] = constraint
        # The measured incumbent's existing calculated answers stay intact.
        # This narrow repair applies to newly extracted dimensional targets
        # without an independently supported forward calculation.
        if (constraint["eligible"] and evidence["extraction_changed"]
                and evidence.get("selected_equation") is None and number(calculated) == 0):
            second_evidence.update({"new_constraints_applied": True, "constraint_repair_unverified": True,
                                    "independent_calculation_evidence": False,
                                    "repair_reason": "listed nonnegative concept and no applicable member exemption"})
            calculated = format_number(fact.value.copy_negate())
            inverse = evidence.get("alternative_complete_inverse_equation")
            second_evidence["public_sign_vs_complete_inverse_conflict"] = bool(inverse and number(inverse["value"]) != number(calculated))
    second = Prediction(extracted, calculated,
                        "decimal-unique:public-nonnegative-repair" if second_evidence["new_constraints_applied"] else first.mechanism,
                        second_evidence)
    third = second
    if anomaly_selection and fact is None:
        anomaly, anomaly_evidence = constraint_anomaly_parent(filing)
        if anomaly:
            context = filing.contexts[anomaly.context]
            selected = anomaly.evidence(filing)
            ae = dict(second_evidence)
            ae.update({"parent": selected, "anomaly_parent_selection": anomaly_evidence,
                       "context_anomaly_extraction_hypothesis": True, "extraction_changed": True,
                       "new_constraints_applied": True})
            third = Prediction(format_number(anomaly.value), format_number(anomaly.value.copy_negate()), "unique-public-constraint-anomaly", ae)
    dimension = apply_dimensional_sum(query, filing, third)
    if dimension.evidence.get("dimensional_sum_promoted"):
        candidate = dimension.evidence["selected_dimensional_equation"]
        alternative = _alternative_axes(filing, dimension.evidence["parent"], candidate["axis"])
        if alternative:
            e = dict(third.evidence)
            e.update({"blocked_dimensional_candidate": candidate,
                      "dimensional_policy_block": "same target/period/entity/unit has another dimensional axis",
                      "alternative_axes": alternative})
            third = Prediction(third.extracted_value, third.calculated_value, third.mechanism, e)
        else:
            e = dict(dimension.evidence)
            e["round3_dimensional_policy"] = "complete statement frontier; no competing target axes"
            third = Prediction(dimension.extracted_value, dimension.calculated_value, dimension.mechanism, e)
    if statement_adapter:
        proposed = statement_adapter(query, filing, third, allow_missing_direct=True)
        if proposed.evidence.get("statement_sum_promoted"):
            source_parent = proposed.evidence.get("parent")
            selected_fact = next((f for f in filing.facts if source_parent and f.context == source_parent["context_ref"]
                                 and f.concept == filing.target and f.unit == source_parent["unit_ref"]
                                 and number(proposed.extracted_value) == f.value), None)
            constraint = (nonnegative_eligibility(filing, selected_fact, filing.contexts[selected_fact.context])
                          if selected_fact else {"eligible": False})
            conflict = constraint["eligible"] and number(proposed.calculated_value) < 0
            dimension_priority = third.evidence.get("dimensional_sum_promoted", False)
            if conflict or dimension_priority:
                e = dict(third.evidence)
                e.update({"blocked_statement_candidate": proposed.evidence["selected_statement_equation"],
                          "statement_priority_block": "public nonnegative concept constraint" if conflict else "complete dimensional frontier takes priority",
                          "statement_constraint_conflict": conflict, "statement_after_dimension_overlap": dimension_priority})
                third = Prediction(third.extracted_value, third.calculated_value, third.mechanism, e)
            else:
                third = proposed
    results = {}
    for method, result in zip(METHODS, (first, second, third)):
        e = dict(result.evidence)
        e["original_xml_complete_gate"] = e.pop("complete_evidence_gate", False)
        equation = e.get("selected_equation")
        if equation and number(equation["value"]) != number(result.calculated_value):
            e["prior_selected_equation"] = equation
            e["selected_equation"] = None
        dimensional = e.get("selected_dimensional_equation")
        statement = e.get("selected_statement_equation")
        if e.get("selected_equation"):
            kind, complete = "complete_linkbase_subset", True
        elif e.get("dimensional_sum_promoted") and dimensional and number(dimensional["value"]) == number(result.calculated_value):
            kind, complete = "complete_dimension_frontier_subset", True
        elif e.get("statement_sum_promoted") and statement and number(statement["value"]) == number(result.calculated_value):
            complete = statement.get("all_direct_children_present", False)
            kind = "complete_direct_statement_subset" if complete else "observed_partial_statement"
        elif e.get("new_constraints_applied"):
            kind, complete = "public_sign_hypothesis", False
        else:
            kind, complete = "retained_legacy_or_unresolved", False
        e["actual_calculation_evidence_kind"] = kind
        e["actual_prediction_complete_calculation_evidence"] = complete
        e["complete_evidence_gate"] = complete
        e["actual_prediction_method"] = method
        e["actual_prediction_calculated"] = result.calculated_value
        e["actual_prediction_extracted"] = result.extracted_value
        results[method] = Prediction(result.extracted_value, result.calculated_value, result.mechanism, e)
    return results
