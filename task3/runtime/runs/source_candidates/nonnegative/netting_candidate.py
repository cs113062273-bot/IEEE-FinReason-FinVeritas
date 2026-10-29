"""Research-only dimensional cancellation focus. No gold, training or network.

Unlike M071, the subtotal is itself negative and no corrected aggregate is
invented. A reported negative leaf competing with C8 is selected when the
observed explicit member values exactly reproduce the negative subtotal,
with one negative leaf and at least one positive sibling. DRS membership is
independently read; missing declared members are recorded, never set to zero.
This is an intentionally unproven source-selection hypothesis, not promotion.
"""
from __future__ import annotations
import csv, hashlib, importlib.util, json, sys
from collections import defaultdict, Counter
from decimal import Decimal
from pathlib import Path
from lxml import etree

OUT=Path(__file__).resolve().parent
WORK=OUT.parents[2]
ROOT=WORK/'core/source'
spec=importlib.util.spec_from_file_location('independent_nn_source',WORK/'runs/source_repairs/nonfallback/audit_nonfallback.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
XI=audit.XI;XL=audit.XLINK;LINK=audit.LINK;XD='http://xbrl.org/2005/xbrldt'

def rows(path):return [json.loads(l) for l in Path(path).read_text(encoding='utf8').splitlines() if l.strip()]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,records):Path(path).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf8')

def definition_edges(parsed):
    root=audit.xml(parsed['parts']['Definition linkbase document']);out=[]
    for link in root.findall('.//{'+LINK+'}definitionLink'):
        role=link.get('{'+XL+'}role');loc={}
        for node in link.findall('{'+LINK+'}loc'):
            frag=node.get('{'+XL+'}href','').split('#')[-1]
            prefix,sep,name=frag.partition('_')
            loc[node.get('{'+XL+'}label')]='{'+parsed['namespaces'][prefix]+'}'+name if sep and prefix in parsed['namespaces'] else None
        grouped=defaultdict(list)
        for node in link.findall('{'+LINK+'}definitionArc'):
            parent=loc.get(node.get('{'+XL+'}from'));child=loc.get(node.get('{'+XL+'}to'))
            kind=node.get('{'+XL+'}arcrole','').split('/')[-1]
            if parent and child:
                edge={'role':role,'parent':parent,'child':child,'kind':kind,'priority':int(node.get('priority','0')),'use':node.get('use','optional'),'target_role':node.get('{'+XD+'}targetRole'),'usable':node.get('{'+XD+'}usable','true'),'line':node.sourceline,'raw_xml':etree.tostring(node,encoding='unicode')}
                grouped[(parent,child,kind,edge['target_role'],edge['usable'])].append(edge)
        for group in grouped.values():
            pr=max(e['priority'] for e in group);effective=[e for e in group if e['priority']==pr]
            if not any(e['use']=='prohibited' for e in effective):out.append(effective[0])
    return out

def dims(f):return {d[0]:d[2] for d in f['context']['dimensions'] if d[1]=='explicit'}
def aspects(f,axis):
    c=f['context']
    return (c['entity_scheme'],c['entity'],tuple(c['period']),json.dumps(f['unit_signature']),tuple(d for d in c['dimensions'] if d[0]!=axis))

def witnesses(parsed,exc):
    target=parsed['target'];fs=[f for f in parsed['facts'] if f['QName']==target and f['asked_period'] and f['context'] and f['unit_signature'] and not f['context']['opaque_qualifiers'] and not f['sign'] and not f['scale']]
    edges=definition_edges(parsed);groups=defaultdict(list)
    for e in edges:
        if e['kind']=='domain-member' and not e['target_role']:groups[(e['role'],e['parent'])].append(e)
    results=[]
    for subtotal in fs:
        if Decimal(subtotal['value'])>=0:continue
        for axis,kind,member,loc in subtotal['context']['dimensions']:
            if kind!='explicit':continue
            # The reported subtotal's member must itself be parent of members
            # in supplied domain-member relationships. No dimensional-count rank.
            for (role,parent),relations in groups.items():
                if parent!=member:continue
                axes=[e for e in edges if e['role']==role and e['kind']=='dimension-domain' and e['parent']==axis]
                if not axes:continue
                # Member must be reachable from that exact axis's domain.
                frontier=[e['child'] for e in axes];visited=set()
                while frontier:
                    n=frontier.pop()
                    if n in visited:continue
                    visited.add(n);frontier.extend(e['child'] for e in edges if e['role']==role and e['kind']=='domain-member' and e['parent']==n and not e['target_role'])
                if member not in visited:continue
                expected={e['child'] for e in relations if e['usable']!='false'};terms=[];missing=[];conflict=False
                for m in sorted(expected):
                    bound=[f for f in fs if dims(f).get(axis)==m and aspects(f,axis)==aspects(subtotal,axis)]
                    values={Decimal(f['value']) for f in bound}
                    if not bound:missing.append(m)
                    elif len(values)!=1:conflict=True
                    else:terms.append(sorted(bound,key=lambda f:json.dumps(f,sort_keys=True))[0])
                negatives=[f for f in terms if Decimal(f['value'])<0]
                if conflict or len(terms)<2 or len(negatives)!=1 or not any(Decimal(f['value'])>0 for f in terms):continue
                total=sum((Decimal(f['value']) for f in terms),Decimal(0))
                if total!=Decimal(subtotal['value']):continue
                leaf=negatives[0];eligible=audit.eligibility_0015(leaf,parsed['parts'],exc)
                if eligible['subset_eligible'] is not True:continue
                results.append({'axis':axis,'role':role,'subtotal':subtotal,'negative_leaf':leaf,'positive_siblings':[f for f in terms if Decimal(f['value'])>=0],'raw_reported_terms_sum':str(total),'raw_sum_equals_reported_subtotal':True,'missing_declared_members':missing,'complete_declared_children':not missing,'definition_relations':relations,'negative_leaf_eligibility':eligible,'claim':'source-supported focus hypothesis, not unique hidden gold','missing_members_set_to_zero':False,'subtotal_sign_repair_not_derived':True,'independent_of_C8_selector':True})
    return results

def select(parsed,baseline,exc,complete_only=False):
    ws=witnesses(parsed,exc)
    if complete_only:ws=[w for w in ws if w['complete_declared_children']]
    pairs={(str(Decimal(w['negative_leaf']['value'])),str(abs(Decimal(w['negative_leaf']['value'])))) for w in ws}
    new=dict(baseline)
    if len(pairs)==1:new['extracted_value'],new['calculated_value']=next(iter(pairs))
    return new,ws

def main():
    freeze={'strategy':'negative_reported_subtotal_exact_observed_member_netting_focus_v1','strategies':['observed_member_netting','complete_declared_member_netting'],'source_code_sha256':sha(__file__),'independent_parser_sha256':sha(audit.__file__),'frozen_before_practice_gold_scoring':True,'promotion_enabled':False,'scope_selection_is_hypothesis':True,'absolute_value_is_unproved_magnitude_repair_hypothesis':True,'forbidden_features':['Case ID','document order','dimension count','recent plan','gold'],'prior_method_difference':'M071 requires a nonnegative aggregate and independent corrected leaf equation; here aggregate remains negative and no aggregate correction is derived; focus follows reported cancellation supported by member hierarchy'}
    (OUT/'STRATEGY_FREEZE.json').write_text(json.dumps(freeze,indent=2)+'\n',encoding='utf8')
    cohort={r['id'] for r in csv.DictReader((WORK/'runs/source_repairs/all196_audit.csv').open(encoding='utf-8-sig')) if r['DQC']=='0015' and 'necessarily_correct' not in r['source_contract_state']};assert len(cohort)==59
    exc=audit.exclusions();v34=ROOT/'reports/round6_iterations/official_semantics_candidate_v34';summary={}
    for split in ['development','practice']:
        inp=ROOT/'data/raw/task3'/('finmr/public_dev_inputs.jsonl' if split=='practice' else 'development_inputs.jsonl')
        sources={r['id']:r for r in rows(inp)}
        baseline=rows(WORK/'DELIVERY/task3_C8_v34_provisional_97_50_R_6b5e45c5/development.predictions.jsonl') if split=='development' else rows(v34/'practice/unanimity.predictions.jsonl')
        variants={name:[] for name in freeze['strategies']};changes={name:[] for name in variants};details=[]
        for base in baseline:
            cid=base['id'];eligible=split=='practice' or cid in cohort or cid in {'DEV3_000058','DEV3_000110','DEV3_000215','DEV3_000666'}
            parsed=None;err=None
            if eligible:
                try:parsed=audit.source_parse(sources[cid]['query'])
                except (etree.XMLSyntaxError,KeyError,AssertionError,AttributeError) as e:err=str(e)
            ws=[]
            for name in variants:
                new=dict(base)
                if parsed:
                    try:new,ws=select(parsed,base,exc,name=='complete_declared_member_netting')
                    except (etree.XMLSyntaxError,KeyError,AssertionError,AttributeError) as e:err=str(e)
                # Known-correct cases get the identical strategy evaluated, but
                # output is confined to the authorized research cohort.
                counterexample=split=='development' and cid not in cohort
                changed=any(Decimal(new[k])!=Decimal(base[k]) for k in ['extracted_value','calculated_value'])
                record={'id':cid,'old':base,'new':new,'strategy':name,'source_witnesses':ws,'numeric_changed':changed,'counterexample':counterexample,'query_sha256':hashlib.sha256(sources[cid]['query'].encode()).hexdigest(),'correct_answer_proven':False}
                if changed:changes[name].append(record)
                variants[name].append(dict(base) if counterexample else new)
            if eligible:details.append({'id':cid,'parsed':parsed is not None,'reason_if_unavailable':err,'target':parsed['target'] if parsed else None,'witnesses':ws,'cohort':cid in cohort,'known_correct_counterexample':split=='development' and cid not in cohort})
        for name,preds in variants.items():
            dest=OUT/name;dest.mkdir(exist_ok=True);write(dest/f'{split}.predictions.jsonl',preds);write(dest/f'{split}.changes.jsonl',changes[name])
            summary[name+'_'+split]={'rows':len(preds),'numeric_changes':sum(not r['counterexample'] for r in changes[name]),'ids':[r['id'] for r in changes[name] if not r['counterexample']],'known_correct_adverse':[r['id'] for r in changes[name] if r['counterexample']]}
        write(OUT/f'{split}.source_witnesses.jsonl',details)
        summary[split+'_parsing']={'analyzed':len(details),'strict_supplied_source_available':sum(r['parsed'] and not r['reason_if_unavailable'] for r in details),'unavailable':sum(bool(r['reason_if_unavailable']) for r in details),'complete_prefix_not_fabricated':True}
    (OUT/'candidate_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8');print(json.dumps(summary))

if __name__=='__main__':main()
