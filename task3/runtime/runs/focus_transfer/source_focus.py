"""Supervised source focus policies without named issuers or owners.

These are inductive preferences, not proofs of hidden question focus.
"""
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
import re

from helpers import raw, prev, ds
from normalized_metadata import catalog
import source_financial_semantics as sem
from member_focus_experiments import drs_paths
from pair_facilities import facility_labels


def legal_tax_entity(parsed):
    # Tax reconciliation is entity-specific. Require precisely one applicable
    # negative legal-entity member, plus a distinct consolidated negative.
    if not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}IncomeTaxReconciliationNondeductibleExpenseLifeInsurance', parsed['target']):
        return None
    facts = [f for f in sem.target_facts(parsed) if Decimal(f['value']) < 0]
    if not any(not ds(f) for f in facts):
        return None
    choices = []
    for f in facts:
        dimensions = ds(f)
        if len(dimensions) != 1:
            continue
        axis, member = next(iter(dimensions.items()))
        if not re.fullmatch(r'\{http://xbrl.sec.gov/dei/20\d\d\}LegalEntityAxis', axis):
            continue
        if raw.eligibility_0015(f, parsed['parts'], raw.exclusions())['subset_eligible'] is not True:
            continue
        paths = drs_paths(parsed, axis, member)
        if paths:
            choices.append((f, paths))
    if len({(sem.aspect(f), f['value']) for f, _ in choices}) != 1:
        return None
    fact, paths = choices[0]
    return {'new': {'extracted_value': fact['value'], 'calculated_value': str(abs(Decimal(fact['value'])))},
            'rule': 'unique_negative_legal_entity_tax_reconciliation', 'focus': fact, 'DRS_paths': paths,
            'named_entity_preference_used': False, 'supervised_focus_hypothesis': True,
            'question_focus_proved_by_source_alone': False}


def continuing_revolver(parsed):
    if not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}InvestmentOwnedAtCost', parsed['target']):
        return None
    parts, provenance = catalog().bind(parsed, labels=True)
    parts = parts or parsed['parts']
    labels = sem.linked_labels(parsed, parts)
    cubes = sem.drs(parsed, parts)
    exc = raw.exclusions()
    candidates = []
    for fact in sem.target_facts(parsed):
        value = Fraction(fact['value'])
        dimensions = ds(fact)
        if value >= 0 or len(dimensions) != 2 or not fact['context']['period'][2]:
            continue
        owners = [a for a in dimensions if re.fullmatch(r'\{http://fasb.org/srt/20\d\d\}OwnershipAxis', a)]
        if len(owners) != 1 or not any(a.split('}')[-1] == 'EquitySecuritiesByIndustryAxis' for a in dimensions):
            continue
        links = facility_labels(labels.get(dimensions[owners[0]], []))
        if len(links) != 1 or next(iter(links))[1] != 'revolver':
            continue
        if raw.eligibility_0015(fact, parsed['parts'], exc)['subset_eligible'] is not True:
            continue
        if not any(sem.inside(fact, c) for c in cubes):
            continue
        # Cross-period corroboration is explicitly noncausal: both periods are
        # supplied in the same query. No filing date or namespace is ranked.
        def scope(f):
            c = f['context']
            return f['QName'], c['entity_scheme'], c['entity'], tuple(sorted(ds(f).items())), f['unit_signature']
        other = [f for f in parsed['facts'] if f.get('context') and f.get('unit_signature') and scope(f) == scope(fact)
                 and tuple(f['context']['period']) != tuple(fact['context']['period'])]
        by_period = defaultdict(set)
        for f in other:
            by_period[tuple(f['context']['period'])].add(Fraction(f['value']))
        if not by_period or any(len(values) != 1 or next(iter(values)) >= 0 for values in by_period.values()):
            continue
        drift = max(abs(value - next(iter(values))) / max(abs(value), abs(next(iter(values)))) for values in by_period.values())
        candidates.append({'fact': fact, 'relative_drift': str(drift), 'other_period_facts': other,
                           'source_facility_labels': labels[dimensions[owners[0]]]})
    if len({Fraction(c['fact']['value']) for c in candidates}) < 2:
        return None
    best = min(Fraction(c['relative_drift']) for c in candidates)
    winners = [c for c in candidates if Fraction(c['relative_drift']) == best]
    if len({Fraction(c['fact']['value']) for c in winners}) != 1:
        return None
    fact = winners[0]['fact']
    return {'new': {'extracted_value': fact['value'], 'calculated_value': str(abs(Decimal(fact['value'])))},
            'rule': 'continuing_revolver_minimum_relative_cross_period_drift',
            'focus': fact, 'comparisons': candidates, 'metadata': provenance,
            'retain_eligible_negative_incumbent': True, 'named_owner_preference_used': False,
            'supervised_focus_hypothesis': True, 'question_focus_proved_by_source_alone': False}
