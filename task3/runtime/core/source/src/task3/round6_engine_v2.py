"""Isolated strict-0117 integration; preserve the frozen v1 behavior."""
from dataclasses import replace

from .round6_candidates import inventory
from .round6_dqc0117 import candidates as dimensional_candidates
from .round6_dqc0126 import candidates as statement_candidates, indexed_facts
from .round6_engine import predict as predict_v1
from .xml_core import parse_xml


def candidates(query, *, filing=None, duplicate_policy='xule_default'):
    raw = filing or parse_xml(query, allow_complete_prefix=True)
    facts, indexing = indexed_facts(raw, duplicate_policy)
    indexed = replace(raw, facts=facts)

    def dimensional(q, f, parent, *, allow_inferred_statement):
        return dimensional_candidates(q, raw, parent, duplicate_policy=duplicate_policy,
                                      allow_inferred_statement=allow_inferred_statement)

    def statement(q, f, parent, *, allow_inferred_statement):
        return statement_candidates(q, raw, parent, duplicate_policy=duplicate_policy,
                                    allow_inferred_statement=allow_inferred_statement)

    proposals, summary = inventory(query, indexed, adapters={'0117': dimensional, '0126': statement})
    for proposal in proposals:
        proof = proposal['proof']
        if proof.get('rule_family') == '0117':
            # The strict adapter evaluates member precision and applicability.
            # The old generic wrapper expects `leaves`, whereas this adapter
            # supplies `reported_members`; its re-comparison loses precision.
            proposal['tolerance'] = proof['tolerance']
            proposal['violation'] = bool(proof['eligible'] and proof['violates'])
    summary.update(indexing=indexing, adapter_version='strict-0117-v2',
                   calculation_policy='pinned direct DQC semantics; strict supplied DRS membership')
    return proposals, summary, indexed


def predict(query, *, mode='A', prior=None, filing=None, prepared=None, duplicate_policy='xule_default'):
    prepared = prepared or candidates(query, filing=filing, duplicate_policy=duplicate_policy)
    result = predict_v1(query, mode=mode, prior=prior, prepared=prepared,
                        duplicate_policy=duplicate_policy)
    result.evidence['round6_adapter_version'] = 'strict-0117-v2'
    return result
