"""Validated Flourish owner focus, with issuer-safe original DRS matching.

Member preference comes from provisional feedback. Other eligible original
owners remain disclosed. No Development ID, answer, fixed CIK/date/hash selects
the focus. Original source-file IDs are used only to verify exact rebinding.
"""
import re,hashlib
from decimal import Decimal
from source_rules_v3 import apply as v3_apply
from source_rules import W,prev,ds,local,xml
from helpers import raw
from member_focus_experiments import drs_paths
from independent_198 import drs,inside

LINK='{http://www.xbrl.org/2003/linkbase}';XL='{http://www.w3.org/1999/xlink}';XI='{http://www.xbrl.org/2003/instance}'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def original_context_unit_match(original,focus):
    contexts=[n for n in original.findall(XI+'context') if n.get('id')==focus['context_ref']]
    units=[n for n in original.findall(XI+'unit') if n.get('id')==focus['unit_ref']]
    if len(contexts)!=1 or len(units)!=1:return False
    context=contexts[0];unit=units[0]
    entity=context.find('.//'+XI+'identifier');source=focus['context']
    if entity is None or (entity.get('scheme'),entity.text)!=(source['entity_scheme'],source['entity']):return False
    text=lambda name:context.findtext(XI+'period/'+XI+name)
    if (text('startDate'),text('endDate'),text('instant'))!=tuple(source['period']):return False
    def qname(n,v):
        prefix,sep,name=v.partition(':')
        return '{'+n.nsmap[prefix if sep else None]+'}'+(name if sep else prefix)
    dims=[]
    for n in context.iter('{http://xbrl.org/2006/xbrldi}explicitMember'):
        location='scenario' if any(a.tag==XI+'scenario' for a in n.iterancestors()) else 'segment'
        dims.append((qname(n,n.get('dimension')),'explicit',qname(n,n.text.strip()),location))
    if sorted(dims)!=sorted(tuple(x) for x in source['dimensions']):return False
    measures=tuple(sorted(qname(n,n.text.strip()) for n in unit.findall(XI+'measure')))
    return (measures,())==focus['unit_signature']

def entity_bound_original_metadata(p,focus):
    from normalized_metadata import metadata as exact_metadata
    return exact_metadata(p,focus)

def flourish(p):
    target=p['target']
    if not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}InvestmentOwnedAtCost',target):return None
    year=re.search(r'/([0-9]{4})}',target).group(1);extension=xml(p['parts']['Schema document']).get('targetNamespace')
    owner_axis='{http://fasb.org/srt/'+year+'}OwnershipAxis';industry_axis='{http://fasb.org/us-gaap/'+year+'}EquitySecuritiesByIndustryAxis'
    owner='{'+extension+'}FlourishResearchAcquisitionLLCRevolverMember';industry='{'+extension+'}HealthCareProvidersServicesMember'
    candidates=[f for f in prev.fs(p) if ds(f)=={owner_axis:owner,industry_axis:industry} and Decimal(f['value'])<0 and f['unit_signature']==(('{http://www.xbrl.org/2003/iso4217}USD',),()) and f['context']['period'][2] is not None]
    if len(candidates)!=1:return None
    focus=candidates[0];exc=raw.exclusions()
    eligible=raw.eligibility_0015(focus,p['parts'],exc)
    if eligible['subset_eligible'] is not True:return None
    parts,metadata=entity_bound_original_metadata(p,focus)
    if parts is None:return None
    full={**p,'parts':parts};paths={a:drs_paths(full,a,m) for a,m in ds(focus).items()}
    if not all(paths.values()):return None
    cubes=[{'role':c['role'],'description':c['description'],'cube':c['cube'],'primary_path':c['primary'][focus['QName']]} for c in drs(parts) if inside(focus,c)]
    if not cubes:return None
    others=[{'id':f['id'],'value':f['value'],'context_ref':f['context_ref'],'dimensions':ds(f)} for f in prev.fs(p) if Decimal(f['value'])<0 and f['id']!=focus['id'] and raw.eligibility_0015(f,p['parts'],exc)['subset_eligible'] is True]
    return {'new':{'extracted_value':focus['value'],'calculated_value':str(abs(Decimal(focus['value'])))},'rule':'F15_InvestmentCost_FlourishResearchAcquisitionLLCRevolver','focus':focus,'eligibility':eligible,'full_original_DRS_paths':paths,'full_cube_membership':cubes,'original_metadata':metadata,'other_eligible_negative_foci':others,'focus_preference_learned_from_provisional_feedback':True,'question_focus_proved_by_source_alone':False,'calculation_basis':'Provisional-validated DQC0015 magnitude sign repair, not an original financial calculation arc.','risk':'Original assertion has no owner ranking and the filing footnote permits natural negative cost from unamortized fees. Three other original legal owners remain. This is a learned provisional focus convention, not Xule uniqueness.'}

def apply(p):return v3_apply(p) or flourish(p)
