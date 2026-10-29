"""Query-only extraction candidates; ambiguous ranking is explicit opt-in."""
from __future__ import annotations
from decimal import Decimal
from .engine import Prediction
from .parser import format_number
from .precision_duplicates import consolidate
from .round4_engine import predict_competitive
from .round5_selection import choose_parent
from .xml_core import parse_xml

def predict(query: str, *, policy: str = 'consensus', prior=None, filing=None):
    prior = prior if prior is not None else predict_competitive(query)
    filing = filing if filing is not None else consolidate(parse_xml(query, allow_complete_prefix=True))[0]
    fact, context, selection = choose_parent(filing, policy=policy)
    evidence = dict(prior.evidence)
    evidence.update(round5_selection=selection, round5_promoted=False)
    if not selection.get('round5_selection_override') or fact is None or context is None:
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    if selection['parent_ambiguous'] and policy != 'document_first':
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    extracted, calculated = format_number(fact.value), format_number(fact.value.copy_negate())
    if (Decimal(extracted), Decimal(calculated)) == (Decimal(prior.extracted_value), Decimal(prior.calculated_value)):
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism, evidence)
    evidence.update(round5_promoted=True, parent=fact.evidence(filing),
        round5_prior_extracted=prior.extracted_value, round5_prior_calculated=prior.calculated_value,
        round5_context_unique=selection['round5_selected_context_unique'],
        round5_value_unique=selection['round5_selected_reported_value_unique'],
        round5_ambiguous_ranking=selection.get('round5_selection_accepted_as_ambiguous_ablation', False),
        actual_prediction_extracted=extracted, actual_prediction_calculated=calculated,
        actual_calculation_evidence_kind='round5_public_sign_hypothesis',
        actual_prediction_complete_calculation_evidence=False, selected_equation=None,
        complete_evidence_gate=False, round5_sign_magnitude_is_hypothesis=True)
    return Prediction(extracted, calculated, 'round5-negative-value-'+policy, evidence)
