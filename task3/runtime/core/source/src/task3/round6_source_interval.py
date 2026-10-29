"""Independent rounded-value binder with semantic frame isolation.

Implements rounded intervals and precision-to-decimals inference, not complete
OIM/XBRL conformance. Excess digits, unknown accuracy and conflicting facts
remain explicit blockers. No synthetic financial value is created.
"""
from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
import re

SPEC='https://www.xbrl.org/Specification/calculation-1.1/REC-2023-02-22+corrected-errata-2024-02-14/calculation-1.1-REC-2023-02-22+corrected-errata-2024-02-14.html'


def accuracy(fact):
    raw=fact.source.get('raw_xml',fact.source.get('serialized_xml',''))
    attributes=dict((m[1],m[3]) for m in re.finditer(r'\b(decimals|precision)\s*=\s*([\"\x27])(.*?)\2',raw))
    decimals=fact.decimals or attributes.get('decimals','')
    precision=attributes.get('precision','')
    if decimals and precision:raise ValueError('both decimals and precision declared')
    if decimals:
        d=None if decimals.upper()=='INF' else int(decimals)
    elif precision:
        if precision.upper()=='INF':d=None
        else:
            p=int(precision)
            if p<=0:raise ValueError('precision zero or negative is not usable accuracy')
            d=None if fact.value==0 else p-fact.value.copy_abs().adjusted()-1
    else:raise ValueError('no source accuracy declared')
    if d is not None and abs(d)>4096:raise ValueError('accuracy outside arithmetic bound')
    value=Fraction(fact.value)
    quantum=Fraction(10**(-d)) if d is not None and d<=0 else Fraction(1,10**d) if d is not None else Fraction(0)
    if quantum and (value/quantum).denominator!=1:raise ValueError('digits in excess of declared accuracy')
    radius=quantum/2
    return d,(value-radius,value+radius),{'source_decimals':decimals,'source_precision':precision,
        'inferred_decimals':'INF' if d is None else str(d),'rounding_mode':'round-to-nearest',
        'bounds':[str(value-radius),str(value+radius)],'specification':SPEC,'full_conformance':False}


def semantic_key(filing,fact):
    context=filing.contexts.get(fact.context);unit=filing.units.get(fact.unit)
    if not context or not unit or not unit.numerator:return None
    return fact.concept,context.signature,unit.signature


def compatible_choice(filing,facts):
    proof={'accepted':False,'different_contexts_never_merged_by_numeric_proximity':True}
    if not facts:return None,{**proof,'reason':'no facts'}
    keys={semantic_key(filing,f) for f in facts}
    if len(keys)!=1 or None in keys:return None,{**proof,'reason':'different or unresolved semantic aspects'}
    intervals=[];ranks=[];by_accuracy=defaultdict(set)
    for f in facts:
        try:d,bounds,detail=accuracy(f)
        except (ValueError,OverflowError) as exc:return None,{**proof,'reason':str(exc)}
        rank=10**9 if d is None else d
        intervals.append(bounds);ranks.append((rank,f,detail));by_accuracy[rank].add(f.value)
    if any(len(values)>1 for values in by_accuracy.values()):return None,{**proof,'reason':'different values at equal accuracy'}
    low,high=max(v[0] for v in intervals),min(v[1] for v in intervals)
    if low>high:return None,{**proof,'reason':'disjoint rounding intervals'}
    rank=max(r[0] for r in ranks);best=[r for r in ranks if r[0]==rank]
    if len({r[1].value for r in best})!=1:return None,{**proof,'reason':'highest-accuracy values disagree'}
    # Only numerically equivalent representatives remain. This deterministic
    # serialization choice is not a document-order numerical heuristic.
    winner=min(best,key=lambda r:(r[1].context,r[1].unit,r[1].source.get('raw_xml','')))
    normalized=replace(winner[1],decimals=winner[2]['inferred_decimals'])
    return normalized,{**proof,'accepted':True,'reason':'same semantic aspects and compatible rounded intervals',
        'intersection':[str(low),str(high)],'selected_source_value':str(normalized.value),
        'selected_accuracy':winner[2],'source_fact_count':len(facts),'original_fact_indexes':[f.index for f in facts],
        'document_order_used_to_select_numeric_value':False}


def normalize(filing):
    groups=defaultdict(list);unresolved=[]
    for f in filing.facts:
        key=semantic_key(filing,f)
        if key is None:unresolved.append(f)
        else:groups[key].append(f)
    facts=list(unresolved);proofs=[]
    for group in groups.values():
        winner,proof=compatible_choice(filing,group)
        if winner:facts.append(winner)
        else:facts.extend(group)
        if len(group)>1 or not winner or any('precision=' in f.source.get('raw_xml','') for f in group):
            proofs.append({'concept':group[0].concept,'contexts':sorted({f.context for f in group}),
                'values':sorted({str(f.value) for f in group}),'proof':proof})
    return replace(filing,facts=facts),proofs


def bind(filing,witness):
    qname='{'+witness['concept_namespace']+'}'+witness['concept_local_name']
    if qname!=filing.target or witness['schema_validation_state']!=4:return None,{'accepted':False,'reason':'QName or native validation mismatch'}
    c=filing.contexts.get(witness['context_ref']);u=filing.units.get(witness['unit_ref'])
    if not c or not u or not u.numerator or c.qualifiers:return None,{'accepted':False,'reason':'unresolved or qualified frame'}
    if not ((c.start,c.end)==(filing.start,filing.end) if filing.end else c.instant==filing.start):
        return None,{'accepted':False,'reason':'wrong explicit query period'}
    typed=Decimal(witness['typed_value'])
    exact=[f for f in filing.facts if f.concept==qname and f.context==c.id and f.unit==u.id and f.value==typed]
    if not exact:return None,{'accepted':False,'reason':'native focus is not a supplied source fact'}
    key=semantic_key(filing,exact[0])
    group=[f for f in filing.facts if semantic_key(filing,f)==key]
    winner,proof=compatible_choice(filing,group)
    if winner is None:return None,proof
    if winner.value!=typed:return None,{**proof,'accepted':False,'reason':'native focus is not most accurate compatible source value'}
    return winner,{**proof,'native_focus_context':c.id,'native_focus_unit':u.id,'exact_query_period_verified':True}
