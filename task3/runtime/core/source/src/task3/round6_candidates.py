"""Query-only per-frame DQC candidates; no IDs, labels or external findings.

Selection is separate from relation evaluation. Numeric disagreement alone is
not a DQC finding: precision tolerance, applicability and source scope remain
explicit. The sign candidate is the published DQC0015 repair hypothesis, not
proof that an arbitrary negative fact originally had the same magnitude.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .parser import format_number
from .round4_dimensional import dimensional_candidates, FATAL
from .round4_rules import eligibility
from .round4_statement import statement_candidates
from .exact_arithmetic import add as exact_add, product as exact_product


def target_groups(filing):
    groups = defaultdict(list)
    for fact in filing.facts:
        ctx = filing.contexts.get(fact.context)
        unit = filing.units.get(fact.unit)
        if not ctx or not unit or not unit.numerator or ctx.qualifiers or not ctx.entity or not ctx.scheme:
            continue
        asked = ((ctx.start, ctx.end) == (filing.start, filing.end)) if filing.end else ctx.instant == filing.start
        if fact.concept == filing.target and asked:
            groups[(ctx.signature, unit.signature)].append(fact)
    return groups


def _decimals(raw):
    if str(raw).upper() == 'INF':
        return None
    try:
        d = int(raw)
    except (ValueError, TypeError):
        return 'unknown'
    return d if abs(d) <= 4096 else 'unknown'


def violation_tolerance(parent, calculated, rule, proof):
    """Public functions-lib tolerance, retaining boundary-rounding uncertainty.

    Xule round behavior is not asserted equal at half-way boundaries. Such
    source cases abstain rather than acquire a fabricated violation proof.
    """
    values = [parent.value, Decimal(calculated)]
    d = _decimals(parent.decimals)
    if d == 'unknown':
        return {'outside': False, 'certified': False, 'reason': 'unknown parent decimals'}
    if rule.startswith('DQC.US.0117'):
        ds = [d]
        for fact in proof.get('leaves', []):
            fd = _decimals(fact.get('decimals'))
            if fd == 'unknown':
                return {'outside': False, 'certified': False, 'reason': 'unknown member decimals'}
            ds.append(fd)
        ds = [x for x in ds if x is not None]
        # tolerance_for_decimals_comp caps INF and decimals above five at five.
        d = min(ds) if ds else 5
        d = min(d, 5)
        factor = 2
    else:
        factor = len(proof.get('terms', [])) + 1
    if d is None:
        rounded, quantum, tolerance = values, Decimal(0), Decimal(0)
    else:
        quantum = Decimal((0,(1,),-d))
        for value in values:
            # Inspect the exact source coefficient; division/remainder under a
            # fixed context can round away the half-way digit or raise first.
            _, digits, exponent = value.as_tuple()
            fractional_places = -(exponent + d)
            if (0 < fractional_places <= len(digits)
                    and digits[-fractional_places] == 5
                    and all(x == 0 for x in digits[len(digits)-fractional_places+1:])):
                return {'outside': False, 'certified': False, 'reason': 'half-way rounding boundary'}
        with localcontext() as arithmetic:
            arithmetic.prec = max(100, *(max(len(v.as_tuple().digits),
                max(1,v.adjusted()+1)+max(0,d))+5 for v in values))
            rounded = [v.quantize(quantum, rounding=ROUND_HALF_EVEN) for v in values]
        tolerance = exact_product(quantum,Decimal(factor))
    difference = exact_add(rounded[0],rounded[1].copy_negate()).copy_abs()
    return {'outside': difference > tolerance, 'certified': True,
            'rounded_difference': format_number(difference), 'tolerance': format_number(tolerance),
            'factor': factor, 'decimals': d, 'source': 'pinned functions-lib.xule',
            'full_xule_rounding_implementation': False}


def inventory(query, filing, *, adapters=None, infer_statement_uri=True):
    """Return independently scoped candidates for every requested target frame.

    Adapter functions receive (query, filing, parent, allow_inferred_statement).
    Default bounded R4 adapters exist solely for a reproducible comparison.
    New normative adapters can replace them without changing parent retrieval.
    """
    adapters = adapters or {'0117': dimensional_candidates, '0126': statement_candidates}
    groups = target_groups(filing)
    scopes = {(signature[0], signature[1], unit) for signature, unit in groups}
    summary = {'requested_groups': len(groups), 'entity_unit_scopes': len(scopes),
               'conflicting_target_groups': 0, 'fatal_source': any(x.get('kind') in FATAL for x in filing.diagnostics),
               'source_only': True, 'current_document_form_and_period_not_fully_certified': True}
    result = []
    if summary['fatal_source']:
        return result, summary
    for key, facts in groups.items():
        if len({f.value for f in facts}) != 1:
            summary['conflicting_target_groups'] += 1
            continue
        parent = min(facts, key=lambda f: f.index)
        ctx, unit = filing.contexts[parent.context], filing.units[parent.unit]
        constraint = eligibility(filing, parent, ctx)
        if constraint['eligible']:
            result.append({'rule': constraint.get('rule', 'DQC.US.0015'), 'reported': format_number(parent.value),
                'value': format_number(parent.value.copy_negate()), 'parent': parent.evidence(filing),
                'eligible': True, 'violation': True, 'relation_verified': False,
                'magnitude_repair_hypothesis': True, 'proof': constraint})
        monetary = not unit.denominator and len(unit.numerator) == 1 and unit.numerator[0].startswith('{http://www.xbrl.org/2003/iso4217}')
        for family, adapter in adapters.items():
            if family == '0117' and not monetary:
                continue
            if family == '0126' and not ctx.consolidated:
                continue
            for proof in adapter(query, filing, parent, allow_inferred_statement=infer_statement_uri):
                rule = proof.get('rule_subset', 'DQC.US.' + family)
                tolerance = violation_tolerance(parent, proof['value'], rule, proof)
                result.append({'rule': rule, 'reported': format_number(parent.value), 'value': proof['value'],
                    'parent': parent.evidence(filing), 'eligible': bool(proof['eligible']),
                    'violation': bool(proof['eligible'] and tolerance['certified'] and tolerance['outside']),
                    'relation_verified': bool(proof['eligible']), 'magnitude_repair_hypothesis': False,
                    'tolerance': tolerance, 'proof': proof})
    return result, summary


def unique_pair(candidates, summary, *, relations_only=False):
    """Select only a single numeric pair across applicable violation candidates.

    This is evidence-driven numeric invariance, not unique-context evidence.
    Other source scopes or conflicting target duplicates prevent selection.
    """
    if summary['entity_unit_scopes'] != 1 or summary['fatal_source'] or summary['conflicting_target_groups']:
        return None
    eligible = [c for c in candidates if c['violation'] and (c['relation_verified'] or not relations_only)]
    pairs = {(Decimal(c['reported']), Decimal(c['value'])) for c in eligible}
    return eligible[0] if len(pairs) == 1 else None
