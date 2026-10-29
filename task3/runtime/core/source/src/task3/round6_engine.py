"""Separate fact retrieval, DQC execution, selection and bounded hybrid policy.

All numeric candidates have supplied-source provenance. DQC0015 sign repair
remains an explicit magnitude hypothesis. DQC0126 uses a pinned Xule-style
duplicate index and non-dimensional fact selection, direct children only.
DQC0117's bounded adapter is separately replaceable; full DTS/form coverage
is not claimed. No gold, IDs, network or free-form numeric model output.
"""
from dataclasses import replace
from decimal import Decimal

from .engine import Prediction
from .parser import format_number
from .round6_candidates import inventory, target_groups, unique_pair
from .round6_dqc0126 import candidates as statement_candidates, indexed_facts
from .round4_dimensional import dimensional_candidates
from .xml_core import parse_xml


def candidates(query, *, filing=None, duplicate_policy='xule_default'):
    raw = filing or parse_xml(query, allow_complete_prefix=True)
    facts, index_proof = indexed_facts(raw, duplicate_policy)
    indexed = replace(raw, facts=facts)
    def statement(q, f, p, *, allow_inferred_statement):
        return statement_candidates(q, raw, p, duplicate_policy=duplicate_policy,
                                    allow_inferred_statement=allow_inferred_statement)
    result, summary = inventory(query, indexed, adapters={'0117': dimensional_candidates, '0126': statement})
    summary['indexing'] = index_proof
    summary['calculation_policy'] = 'source DQC direct semantics; no arbitrary inverse or missing-child recursion'
    return result, summary, indexed


def _source_fallback(filing):
    groups = target_groups(filing)
    consistent = [fs for fs in groups.values() if len({f.value for f in fs}) == 1]
    defaults = [fs for fs in consistent if filing.contexts[fs[0].context].consolidated]
    eligible = defaults or consistent
    values = {f.value for fs in eligible for f in fs}
    scopes = {(filing.contexts[fs[0].context].scheme, filing.contexts[fs[0].context].entity,
               filing.units[fs[0].unit].signature) for fs in groups.values()}
    if eligible and len(values) == 1 and len(scopes) == 1 and len(consistent) == len(groups):
        return min((f for fs in eligible for f in fs), key=lambda f: f.index)
    return None


def predict(query, *, mode='A', prior=None, filing=None, prepared=None, duplicate_policy='xule_default'):
    if mode not in {'A', 'Hybrid'}:
        raise ValueError('Unknown Round6 mode')
    proposals, summary, indexed = prepared or candidates(query, filing=filing, duplicate_policy=duplicate_policy)
    chosen = unique_pair(proposals, summary)
    source_parent = _source_fallback(indexed)
    evidence = {'round6_source_only': True, 'round6_candidates': proposals, 'round6_inventory': summary,
                'round6_full_DTS_Xule': False, 'official_accuracy': None,
                'gold_or_case_ID_used': False, 'model_final_numbers_allowed': False,
                'round6_architecture': mode}
    if mode == 'Hybrid' and prior is None:
        from .round5_engine import predict as baseline
        prior = baseline(query, policy='consensus')
    if chosen is not None:
        if mode == 'Hybrid':
            # An existing resolved reported frame needs stronger cross-frame
            # evidence than merely a different arithmetic result elsewhere.
            previous_parent = prior.evidence.get('parent')
            unresolved = not previous_parent or prior.evidence.get('parent_ambiguous', False)
            if Decimal(chosen['reported']) != Decimal(prior.extracted_value) and not unresolved:
                evidence.update(round6_gate='retain resolved prior frame; conflicting DQC frame recorded',
                                round6_blocked_selection=chosen)
                return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism,
                                  {**prior.evidence, **evidence})
        evidence.update(round6_gate='single numeric pair across eligible DQC violations', round6_selected=chosen,
                        parent=chosen['parent'], actual_calculation_evidence_kind='round6_DQC_candidate',
                        actual_prediction_extracted=chosen['reported'], actual_prediction_calculated=chosen['value'],
                        actual_prediction_complete_calculation_evidence=bool(chosen['relation_verified'] and
                            chosen['proof'].get('all_direct_children_present', False)),
                        magnitude_repair_hypothesis=chosen['magnitude_repair_hypothesis'],
                        unique_context_verified=len({c['parent']['context_ref'] for c in proposals if c['violation']}) == 1)
        evidence.update(selected_equation=None, dimensional_sum_promoted=False,
                        reported_partition_promoted=False, statement_sum_promoted=False,
                        round4_dimensional_promoted=False, round4_statement_promoted=False,
                        actual_prediction_method='round6-' + mode)
        return Prediction(chosen['reported'], chosen['value'], 'round6-' + chosen['rule'],
                          {**(prior.evidence if prior else {}), **evidence})
    if mode == 'Hybrid':
        evidence['round6_gate'] = 'retain prior: no unique eligible violation pair'
        return Prediction(prior.extracted_value, prior.calculated_value, prior.mechanism,
                          {**prior.evidence, **evidence})
    reported = format_number(source_parent.value) if source_parent else '0'
    evidence.update(round6_gate='source-only fallback; calculation unresolved sentinel',
                    parent=source_parent.evidence(indexed) if source_parent else None,
                    unresolved_calculation=True, zero_is_missing_sentinel=True)
    return Prediction(reported, '0', 'round6-unresolved-DQC', evidence)
