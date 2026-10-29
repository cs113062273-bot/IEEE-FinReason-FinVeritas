"""Source-only Practice-calibrated successor; historical engines stay available.

Parse only complete supplied XML elements, bind the requested semantic frame,
then evaluate generic rule candidates. No DQC input label, case ID or gold
enters this entry point. Sign-magnitude repair remains explicitly a hypothesis.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .engine import Prediction
from .parser import format_number
from .precision_duplicates import consolidate
from .round3_priority import predict as d_predict
from .round4_dimensional import apply_dimensional_rule
from .round4_rules import eligibility
from .round4_statement import apply_statement_rule
from .xml_core import parse_xml
from .xml_engine import analyze, select_parent

FATAL = {"xml-parse-failed", "forbidden-dtd-or-entity", "duplicate-context-id-conflict",
         "duplicate-unit-id-conflict", "invalid-scale"}


def select_source_parent(filing):
    ordinary, context, metadata = select_parent(filing, allow_unique_dimension=True)
    groups = defaultdict(list)
    for fact in filing.facts:
        ctx, unit = filing.contexts.get(fact.context), filing.units.get(fact.unit)
        period = bool(ctx) and ((ctx.start, ctx.end) == (filing.start, filing.end) if filing.end else ctx.instant == filing.start)
        if fact.concept == filing.target and period and unit and unit.numerator and ctx.entity and ctx.scheme and not ctx.qualifiers:
            groups[(ctx.signature, unit.signature)].append(fact)
    violations = []
    frames = set()
    for facts in groups.values():
        ctx, unit = filing.contexts[facts[0].context], filing.units[facts[0].unit]
        frames.add((ctx.scheme, ctx.entity, unit.signature))
        if len({f.value for f in facts}) != 1:
            continue
        fact = min(facts, key=lambda f: f.index)
        constraint = eligibility(filing, fact, ctx)
        if constraint["eligible"]:
            violations.append((fact, constraint))
    metadata["public_negative_violation_candidates"] = [{"fact": f.evidence(filing), "constraint": c} for f, c in violations]
    if len(violations) == 1 and len(frames) == 1:
        fact, constraint = violations[0]
        metadata.update(parent_selection="unique public nonnegative-rule violation in supplied requested frame",
                        parent_ambiguous=False, selected_public_constraint=constraint)
        return fact, filing.contexts[fact.context], metadata
    if ordinary is not None:
        metadata["selected_public_constraint"] = eligibility(filing, ordinary, context)
    return ordinary, context, metadata


def predict(query: str, *, sign_priority: bool = True, allow_inferred_statement: bool = False) -> Prediction:
    prior = d_predict(query)
    filing, duplicate_proofs = consolidate(parse_xml(query, allow_complete_prefix=True))
    fact, context, selection = select_source_parent(filing)
    evidence = dict(prior.evidence)
    evidence.update(round4_source_only=True, round4_source_prefix_policy=True,
                    round4_duplicate_proofs=duplicate_proofs, round4_parent_selection=selection,
                    diagnostics=filing.diagnostics, document_sha256=filing.document_sha256,
                    round4_accuracy=None, round4_full_DTS=False)
    if fact is None or context is None or selection["parent_ambiguous"] or any(d["kind"] in FATAL for d in filing.diagnostics):
        evidence["round4_gate"] = "retain prior: target missing, ambiguous or source integrity failure"
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    changed_context = not evidence.get("parent") or evidence["parent"].get("context_ref") != fact.context
    reported = format_number(fact.value)
    calculated = prior.calculated_value if not changed_context and Decimal(prior.extracted_value) == fact.value else "0"
    standard, _, standard_metadata = select_parent(filing, allow_unique_dimension=True)
    xml = analyze(filing, mode="strict_complete", allow_unique_dimension=True)
    source_equation = xml.evidence.get("selected_equation")
    if standard and not standard_metadata["parent_ambiguous"] and standard.context == fact.context and source_equation:
        calculated = xml.calculated_value
    evidence.update(parent=fact.evidence(filing), target=filing.target, target_lexical=filing.target_lexical,
                    round4_prior_extracted=prior.extracted_value, round4_prior_calculated=prior.calculated_value,
                    selected_equation=source_equation if source_equation and source_equation["value"] == calculated else None,
                    actual_prediction_extracted=reported, actual_prediction_calculated=calculated,
                    actual_prediction_complete_calculation_evidence=bool(source_equation and source_equation["value"] == calculated),
                    actual_calculation_evidence_kind="round4_complete_forward" if source_equation and source_equation["value"] == calculated else "retained_or_unresolved",
                    dimensional_sum_promoted=False, reported_partition_promoted=False, statement_sum_promoted=False,
                    round4_gate="requested source target selected")
    result = Prediction(reported, calculated, "round4-source-target", evidence)
    constraint = eligibility(filing, fact, context)
    if sign_priority and constraint["eligible"]:
        sign_value = format_number(fact.value.copy_negate())
        evidence.update(round4_nonnegative_constraint=constraint, round4_sign_magnitude_hypothesis=True,
                        actual_prediction_calculated=sign_value, actual_calculation_evidence_kind="round4_public_sign_hypothesis",
                        actual_prediction_complete_calculation_evidence=False, selected_equation=None)
        return Prediction(reported, sign_value, "round4-public-nonnegative-sign", evidence)
    result = apply_statement_rule(query, filing, result, allow_inferred_statement=allow_inferred_statement)
    result = apply_dimensional_rule(query, filing, result, allow_inferred_statement=allow_inferred_statement)
    return result


def predict_competitive(query: str) -> Prediction:
    """Frozen train-selected URI/axis candidate, still awaiting official feedback."""
    from .round4_axis_fragment import apply_fragment_axis, apply_missing_extraction_calculation
    filing, _ = consolidate(parse_xml(query, allow_complete_prefix=True))
    result = predict(query, allow_inferred_statement=True)
    return apply_fragment_axis(query, filing, apply_missing_extraction_calculation(query, filing, result))
