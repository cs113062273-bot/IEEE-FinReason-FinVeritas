"""Replace named borrower preference with linked facility-type relationships.

This provides a borrower-independent source corroboration hypothesis. It is
not proof of the question's hidden focus and does not settle other borrowers.
"""
from collections import defaultdict
from decimal import Decimal
import re
from normalized_metadata import catalog
import source_financial_semantics as semantics
from helpers import raw,prev,ds,local

def facility_labels(texts):
    results=set()
    for label in texts:
        text=label['text'].strip()
        m=re.fullmatch(r'(.*?)\s*\(\s*(delayed\s+draw|revolver)\s*\)\s*(?:\[member\])?',text,re.I)
        if not m:continue
        borrower=' '.join(re.sub(r'[^\w ]',' ',m[1].casefold()).split())
        kind=' '.join(m[2].casefold().split())
        if borrower:results.add((borrower,kind))
    return results

def frame(f,owner_axis):
    c=f['context']
    return (f['QName'],c['entity_scheme'],c['entity'],tuple(c['period']),
            tuple(tuple(u) for u in f['unit_signature']),
            tuple(sorted(tuple(d) for d in c['dimensions'] if d[0]!=owner_axis)))

def select(p):
    if not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}InvestmentOwnedAtCost',p['target']):
        return None
    parts,metadata=catalog().bind(p,labels=True)
    if parts is None:
        parts=p['parts']
        metadata={**(metadata or {}),'supplied_metadata_only':True,'external_instance_read':False}
    try:
        linked=semantics.linked_labels(p,parts)
        cubes=semantics.drs(p,parts)
    except (semantics.E.XMLSyntaxError,KeyError):
        return None
    grouped=defaultdict(list)
    exc=raw.exclusions()
    for f in prev.fs(p):
        if Decimal(f['value'])>=0 or not f['context']['period'][2]:continue
        if f['unit_signature']!=(('{http://www.xbrl.org/2003/iso4217}USD',),()):continue
        dimensions=ds(f)
        owners=[a for a in dimensions if re.fullmatch(r'\{http://fasb.org/srt/20\d\d\}OwnershipAxis',a)]
        if len(owners)!=1 or not any(local(a)=='EquitySecuritiesByIndustryAxis' for a in dimensions):continue
        axis=owners[0];member=dimensions[axis]
        pairs=facility_labels(linked.get(member,[]))
        if len(pairs)!=1:continue
        if raw.eligibility_0015(f,p['parts'],exc)['subset_eligible'] is not True:continue
        applicable=[cube for cube in cubes if semantics.inside(f,cube)]
        if not applicable:continue
        borrower,kind=next(iter(pairs))
        grouped[(frame(f,axis),borrower,Decimal(f['value']))].append({
            'fact':f,'owner_axis':axis,'member':member,'kind':kind,
            'linked_labels':linked[member],
            'original_cubes':[{'role':c['role'],'cube':c['cube'],'description':c['description']} for c in applicable]})
    witnesses=[]
    for key,rows in grouped.items():
        bykind={kind:[r for r in rows if r['kind']==kind] for kind in ['delayed draw','revolver']}
        if any(len(v)!=1 for v in bykind.values()):continue
        a,b=bykind['delayed draw'][0],bykind['revolver'][0]
        if a['member']==b['member'] or a['fact']['context_ref']==b['fact']['context_ref']:continue
        # Compare values numerically, never the issuer, period, QName local
        # names, source order or spelling of the borrower.
        witnesses.append({'delayed_draw':a,'revolver':b,'reported':a['fact']['value'],
                          'calculated':str(abs(Decimal(a['fact']['value'])))})
    values={(Decimal(w['reported']),Decimal(w['calculated'])) for w in witnesses}
    if len(values)!=1:return None
    x,y=next(iter(values))
    return {'new':{'extracted_value':str(x),'calculated_value':str(y)},
            'rule':'paired_facility_equal_cost_source_corroboration',
            'source_witnesses':witnesses,'original_metadata':metadata,
            'question_focus_proved_by_source_alone':False,
            'named_issuer_member_or_quarter_rank_used':False,
            'hypothesis':'Corroborate one negative cost through distinct delayed-draw and revolving facilities of a source-linked same borrower and same remaining aspects.',
            'normalization_status':'identifier dependency removed; focus precedence remains an inductive hypothesis'}
