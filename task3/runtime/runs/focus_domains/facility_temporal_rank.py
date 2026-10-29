"""Experimental facility comparison with a cross-period incumbent safeguard.

Borrower labels are used only to link two facilities in the same filing;
no particular borrower identity is favored. Ranking uses dimensionless ratios.
"""
from collections import defaultdict
from decimal import Decimal
from normalized_metadata import catalog
import source_financial_semantics as sem
from pair_facilities import facility_labels,frame
from helpers import raw

def same_scope(f):
    c=f['context']
    return (f['QName'],c['entity_scheme'],c['entity'],
            tuple(sorted(sem.dims(f).items())),tuple(tuple(u) for u in f['unit_signature']))

def select(parsed,incumbent,programs):
    if parsed['target'].split('}')[-1]!='InvestmentOwnedAtCost':return None
    eligible={(Decimal(p['reported']),Decimal(p['value'])) for p in programs
              if p.get('eligible') and p['rule'].startswith('DQC.US.0015.') and Decimal(p['reported'])<0}
    old=(Decimal(incumbent['extracted_value']),Decimal(incumbent['calculated_value']))
    if old not in eligible or len(eligible)<2:return None
    facts=sem.target_facts(parsed)
    incumbent_facts=[f for f in facts if Decimal(f['value'])==old[0]]
    # Retain a negative incumbent when another reported period independently
    # corroborates the sign in the exact same financial scope and currency.
    historical=[]
    for f in incumbent_facts:
        for h in parsed['facts']:
            if not h.get('context') or not h.get('unit_signature') or h['QName']!=parsed['target']:continue
            if tuple(h['context']['period'])==tuple(f['context']['period']):continue
            if same_scope(h)==same_scope(f) and Decimal(h['value'])<0:historical.append(h)
    if historical:return None
    parts,provenance=catalog().bind(parsed,labels=True)
    parts=parts or parsed['parts'];labels=sem.linked_labels(parsed,parts);cubes=sem.drs(parsed,parts)
    groups=defaultdict(lambda:defaultdict(dict));exc=raw.exclusions()
    for f in facts:
        numeric=(Decimal(f['value']),abs(Decimal(f['value'])))
        if numeric not in eligible:continue
        dims=sem.dims(f)
        owners=[a for a in dims if a.startswith('{http://fasb.org/srt/') and a.split('}')[-1]=='OwnershipAxis']
        if len(owners)!=1 or not any(a.split('}')[-1]=='EquitySecuritiesByIndustryAxis' for a in dims):continue
        owner=owners[0];member=dims[owner]
        links=facility_labels(labels.get(member,[]))
        if len(links)!=1:continue
        if raw.eligibility_0015(f,parsed['parts'],exc)['subset_eligible'] is not True:continue
        valid=[c for c in cubes if sem.inside(f,c)]
        if not valid:continue
        borrower,kind=next(iter(links))
        groups[(frame(f,owner),borrower)][kind][numeric]={
            'fact':f,'kind':kind,'labels':labels.get(member,[]),
            'roles':[{'role':c['role'],'cube':c['cube'],'description':c['description']} for c in valid]}
    compared=[]
    for bykind in groups.values():
        if set(bykind)!={'delayed draw','revolver'} or any(len(x)!=1 for x in bykind.values()):continue
        a=next(iter(bykind['delayed draw']));b=next(iter(bykind['revolver']))
        av,bv=abs(a[0]),abs(b[0]);ratio=min(av,bv)/max(av,bv)
        winner=max([a,b],key=lambda p:abs(p[0]))
        compared.append({'relative_agreement':ratio,'pair':winner,'delayed_draw':bykind['delayed draw'][a],'revolver':bykind['revolver'][b]})
    if not compared:return None
    best=max(w['relative_agreement'] for w in compared)
    best_rows=[w for w in compared if w['relative_agreement']==best]
    if len(best_rows)!=1:return None
    pair=best_rows[0]['pair']
    if pair==old:return None
    return {'new':{'extracted_value':str(pair[0]),'calculated_value':str(pair[1])},
            'rule':'paired_facility_relative_cost_with_temporal_incumbent_safeguard',
            'experimental_ranking_not_unique_focus_proof':True,
            'incumbent_negative_history':historical,
            'source_facility_comparisons':compared,'structural_metadata':provenance}
