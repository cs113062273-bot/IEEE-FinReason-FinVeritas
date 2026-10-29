"""Independent concept/transaction binding, separate from arithmetic ranking.

The Q1source hypothesis is explicit andnotgoldcertified. Q2sign policy follows
original0015conditionalabsolute correction, not an independent amount proof.
"""
from decimal import Decimal
import json,re
from common import raw,previous,parent
from focus_inventory import member_labels
local=lambda name:name.split('}')[-1]
def clean(f):return f['context'] and f['unit_signature'] and not f['sign'] and not f['scale'] and not f['context']['opaque_qualifiers']
def locators(p,link):
    result={}
    for node in link.findall('{'+raw.LINK+'}loc'):
        fragment=node.get('{'+raw.XLINK+'}href','').split('#')[-1];prefix,sep,name=fragment.partition('_')
        if sep and prefix in p['namespaces']:result[node.get('{'+raw.XLINK+'}label')]='{'+p['namespaces'][prefix]+'}'+name
    return result
def semantic_options_exercise(p,base,programs,exc):
    if local(p['target'])!='StockIssuedDuringPeriodSharesStockOptionsExercised':return None,{'status':'outside options-exercise concept domain'}
    taxonomy=p['parts'].get('US GAAP Taxonomy','')
    documentation=taxonomy.split('Documentation:',1)[-1].split('Provenance:',1)[0].lower()
    if not all(word in documentation for word in ['share','exercised','current period']):return None,{'status':'missing original options-exercise documentation'}
    labels=member_labels(p);tree=raw.xml(p['parts']['Presentation linkbase document']);roles=[]
    # Original sibling line item separates restricted LTIP exchange from the
    # asked standard options exercise concept. No role title alone bindsfocus.
    for link in tree.findall('.//{'+raw.LINK+'}presentationLink'):
        loc=locators(p,link);arcs=[]
        for a in link.findall('{'+raw.LINK+'}presentationArc'):
            if a.get('use','optional')=='prohibited':continue
            arcs.append((loc.get(a.get('{'+raw.XLINK+'}from')),loc.get(a.get('{'+raw.XLINK+'}to')),a))
        for group,target,a in arcs:
            if target!=p['target']:continue
            others=[]
            for g,other,arc in arcs:
                if g!=group or other==target or not other:continue
                docs=[l for l in labels.get(other,[]) if l['role'].endswith('/documentation') and all(w in l['text'].lower() for w in ['exchanged','restricted common shares'])]
                if docs:others.append({'concept':other,'documentation_labels':docs,'original_arc':raw.etree.tostring(arc,encoding='unicode')})
            if others:roles.append({'role':link.get('{'+raw.XLINK+'}role'),'shared_line_items':group,'target_arc':raw.etree.tostring(a,encoding='unicode'),'restricted_exchange_sibling':others})
    if not roles:return None,{'status':'no source-documented distinction between exercise and restricted-exchange lineitems'}
    negative=previous.negative_facts(p,exc);common=[];restricted=[]
    for f in negative:
        for axis,kind,member,location in f['context']['dimensions']:
            if kind!='explicit' or local(axis)!='TransactionTypeAxis':continue
            texts=[l for l in labels.get(member,[]) if l['text'].lower().removesuffix(' [member]')=='exchanged for common stock']
            if texts:common.append({'focus':f,'axis':axis,'member':member,'linked_member_labels':texts})
            texts=[l for l in labels.get(member,[]) if l['text'].lower().removesuffix(' [member]')=='exchanged for restricted common shares']
            if texts:restricted.append({'focus':f,'axis':axis,'member':member,'linked_member_labels':texts})
    if not common or not restricted:return None,{'status':'no two source-documented competing transaction scopes'}
    ws=[];graph=previous.dimensional.definition_graph(p)
    external_graph=None
    if p.get('external_definition_parts'):
        external_graph=previous.dimensional.definition_graph({**p,'parts':p['external_definition_parts']})
    for c in common:
        # Require an exact outerAward/etc scope twin from the othertransaction.
        twins=[r for r in restricted if r['axis']==c['axis'] and previous.ownership.n.aspects(r['focus'],c['axis'])==previous.ownership.n.aspects(c['focus'],c['axis'])]
        if not twins:continue
        f=c['focus'];unit=f['unit_signature']
        if unit!=[['{http://www.xbrl.org/2003/instance}shares'],[]] and unit!=(('{http://www.xbrl.org/2003/instance}shares',),()):continue
        # The entire source query may be a reduced presentation slice. Both
        # Transaction member paths must exist in issuer-matched supplied/public
        # DRS. A path in another role proves membership, not question focus.
        pp=[]
        for witness in [c,*twins]:
            paths=[(role,previous.dimensional.member_path(graph,role,witness['axis'],witness['member'])) for role,node in list(graph) if node==witness['axis']]
            paths=[(r,path) for r,path in paths if path]
            origin='supplied source DRS'
            if not paths and external_graph is not None:
                paths=[(role,previous.dimensional.member_path(external_graph,role,witness['axis'],witness['member'])) for role,node in list(external_graph) if node==witness['axis']]
                paths=[(r,path) for r,path in paths if path];origin='exact issuer/namespace original SEC filing DRS'
            if not paths:break
            pp.append({'role':paths[0][0],'path':paths[0][1],'member':witness['member'],'origin':origin})
        if len(pp)!=1+len(twins):continue
        value=Decimal(f['value']);ws.append({**c,'competing_restricted_scopes':twins,'original_line_item_semantic_contrast':roles,'original_taxonomy_documentation':documentation,'member_paths':pp,'external_metadata_provenance':p.get('external_metadata_provenance'),'reported':str(value),'calculated':str(value.copy_negate()),'new_information':'asked standardexercise line item has source-documented siblingrestrictedexchange; prefer ordinary common-stock transaction scope rather than treating every negativeexercise value as interchangeable','Q1_selection_hypothesis_not_unique_question_binding':True,'Q2_conditional_DQC0015_absolute_repair_not_independent_amount_proof':True,'no_arithmetic_fit_feature':True})
    return parent.unique_proposal(base,ws,'E15_standard_options_exercise_transaction')

def original_assertion_focus(p,base,programs,exc):
    # Candidateproof must be originalapplicable and violating, not merely sumfit.
    ps=[a for a in programs if a['rule'].startswith('DQC.US.0117.') and a.get('eligible') and a.get('violation') and a.get('relation_verified')]
    pairs={(a['reported'],a['value']) for a in ps}
    if len(pairs)!=1:return None,{'status':'assertionfocus absent or ambiguous','eligible_pairs':sorted(pairs),'selfconsistent_alternatives_not_used':True}
    x,y=next(iter(pairs));new={**base,'extracted_value':x,'calculated_value':y}
    return new,{'status':'unique_original_applicable_assertion_focus','programs':ps,'native_rule_focus_not_question_gold':True}

def explicit_question_bind(p,base,programs,exc):
    q=p['question'];context=re.search(r'\bcontext(?:Ref)?\s*[:=]\s*["\']?([\w.-]+)',q,re.I)
    if not context:return None,{'status':'no explicit source-context locator in question'}
    fs=[f for f in p['facts'] if f['QName']==p['target'] and f['asked_period'] and clean(f) and f['context_ref']==context[1]]
    if not fs or len({Decimal(f['value']) for f in fs})!=1:return None,{'status':'explicit context missing or inconsistent'}
    value=Decimal(fs[0]['value']);eligible=raw.eligibility_0015(fs[0],p['parts'],exc)
    if eligible['subset_eligible'] is not True:return None,{'status':'explicit Q1binding not enough for a lawful numeric correction'}
    return {**base,'extracted_value':str(value),'calculated_value':str(-value)},{'status':'explicit_source_context_and_original0015','facts':fs,'conditional_Q2_sign_repair':True}

STRATEGIES={'E15_exercise_semantics':semantic_options_exercise,'A117_unique_assertion':original_assertion_focus,'Q1_explicit_context':explicit_question_bind}
