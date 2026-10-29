"""Requested-QName/period DQC0015 violation value consensus or ranked ablation.

No gold, labels, identifiers, external filing findings or magnitude lookup.
Value consensus can determine a violating reported number without identifying
a unique dimension context. It does not prove the correct sign-repaired amount.
Document-first is deliberately marked ambiguous and needs explicit opt-in.
"""
from __future__ import annotations

from collections import defaultdict

from .round4_engine import FATAL, select_source_parent
from .round4_rules import eligibility


def choose_parent(filing, *, policy: str = "consensus"):
    """Return (fact, context, metadata), preserving R4 selection when gated out.

    consensus: all eligible negative requested-frame values must agree.
    document_first: use first eligible fact as an ambiguous research candidate.
    Every candidate must share entity/scheme/unit and explicit question period.
    """
    if policy not in {"consensus", "document_first"}:
        raise ValueError("Unknown Round5 selection policy")
    prior_fact, prior_context, prior_meta = select_source_parent(filing)
    meta = dict(prior_meta)
    meta.update(round5_selection_policy=policy, round5_selection_override=False,
                round5_sign_repair_magnitude_proven=False)
    def retained(reason):
        meta["round5_selection_gate"] = "retain R4: " + reason
        return prior_fact, prior_context, meta
    if any(d["kind"] in FATAL for d in filing.diagnostics):
        return retained("source-integrity failure")
    if prior_fact is not None and prior_context is not None and not prior_meta['parent_ambiguous']:
        # Agreement among a negative subset does not justify replacing a
        # resolved reported target (e.g. a positive consolidated number).
        # This policy repairs unresolved selection only; it never asserts that
        # the negative subset identifies the question's intended context.
        return retained('existing source target is resolved; subset consensus cannot override it')
    groups = defaultdict(list)
    for fact in filing.facts:
        context = filing.contexts.get(fact.context)
        unit = filing.units.get(fact.unit)
        asked_period = bool(context) and (((context.start, context.end) == (filing.start, filing.end))
                                         if filing.end else context.instant == filing.start)
        if fact.concept != filing.target or not asked_period:
            continue
        if (not unit or not unit.numerator or not context.entity or not context.scheme
                or context.qualifiers):
            return retained("requested target has unresolved entity/unit/context qualifier")
        groups[(context.signature, unit.signature)].append(fact)
    # All supplied target frames share entity/unit, including non-violating
    # frames. This prevents selecting one currency/entity merely by its sign.
    frames = {(filing.contexts[facts[0].context].scheme,
               filing.contexts[facts[0].context].entity,
               filing.units[facts[0].unit].signature) for facts in groups.values()}
    if len(frames) != 1:
        return retained("requested target spans multiple or no entity/unit frames")
    violations = []
    for facts in groups.values():
        if len({f.value for f in facts}) != 1:
            return retained("conflicting duplicates in requested target frame")
        fact = min(facts, key=lambda f: f.index)
        context = filing.contexts[fact.context]
        constraint = eligibility(filing, fact, context)
        if constraint["eligible"]:
            violations.append((fact, context, constraint))
    meta["round5_violation_alternatives"] = [
        {"fact": fact.evidence(filing), "constraint": constraint}
        for fact, _, constraint in violations]
    values = {fact.value for fact, _, _ in violations}
    meta.update(round5_violation_context_count=len(violations),
                round5_violation_distinct_value_count=len(values),
                round5_context_ambiguous=len(violations) > 1,
                round5_violation_value_invariant=len(values) == 1,
                round5_full_target_value_invariant=len({f.value for facts in groups.values() for f in facts}) == 1)
    if not violations:
        return retained("no eligible negative requested-frame violation")
    if policy == "consensus" and len(values) != 1:
        return retained("eligible violation values disagree")
    fact, context, constraint = min(violations, key=lambda item: item[0].index)
    context_unique = len(violations) == 1
    numeric_ambiguous = len(values) > 1
    meta.update(round5_selection_override=True, selected_public_constraint=constraint,
                parent_selection=("invariant eligible-negative value across requested-frame contexts"
                                  if policy == "consensus" else "document-first eligible-negative ambiguous ablation"),
                parent_ambiguous=numeric_ambiguous,
                round5_selection_accepted_as_ambiguous_ablation=policy == "document_first" and numeric_ambiguous,
                round5_selected_context_unique=context_unique,
                round5_selected_reported_value_unique=not numeric_ambiguous,
                round5_selection_gate="source-only requested QName/period/entity/unit eligibility gate passed",
                round5_selection_confidence_kind=("structural value invariance, not unique context"
                                                  if not numeric_ambiguous else "uncalibrated ambiguous ranking"))
    return fact, context, meta
