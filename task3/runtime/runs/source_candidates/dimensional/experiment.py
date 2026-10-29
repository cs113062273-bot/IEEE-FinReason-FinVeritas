"""H117: research-only self-consistent dimensional frame selection.

Unlike production unique_pair, a nonviolating source program can propose Q1.
It must preserve C8's Q2, satisfy original statement eligibility, and have a
fresh raw member-sum witness. Never declares hidden-gold correctness.
"""
from pathlib import Path
from decimal import Decimal
from collections import Counter, defaultdict
import hashlib, json, sys, importlib.util

WORK=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
ROOT=WORK/'core/source'
V34=ROOT/'reports/round6_iterations/official_semantics_candidate_v34'
spec=importlib.util.spec_from_file_location('independent_raw',WORK/'runs/source_repairs/nonfallback/audit_nonfallback.py')
raw=importlib.util.module_from_spec(spec);spec.loader.exec_module(raw)

def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf8').splitlines() if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,rs):p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs),encoding='utf8')

def definition_graph(parsed):
    ns=parsed['namespaces'];schema=raw.xml(parsed['parts']['Schema document'])
    ids={e.get('id'):'{'+schema.get('targetNamespace')+'}'+e.get('name') for e in schema.iter('{'+raw.XS+'}element') if e.get('id') and e.get('name')}
    tree=raw.xml(parsed['parts']['Definition linkbase document']);graph=defaultdict(list)
    for link in tree.findall('.//{'+raw.LINK+'}definitionLink'):
        role=link.get('{'+raw.XLINK+'}role');loc={}
        for n in link.findall('{'+raw.LINK+'}loc'):
            fragment=n.get('{'+raw.XLINK+'}href','').partition('#')[2];target=ids.get(fragment)
            if not target and '_' in fragment:
                pre,local=fragment.split('_',1)
                if pre in ns:target='{'+ns[pre]+'}'+local
            loc[n.get('{'+raw.XLINK+'}label')]=target
        for n in link.findall('{'+raw.LINK+'}definitionArc'):
            if n.get('use')=='prohibited':continue
            kind=n.get('{'+raw.XLINK+'}arcrole','').rsplit('/',1)[-1]
            parent=loc.get(n.get('{'+raw.XLINK+'}from'));child=loc.get(n.get('{'+raw.XLINK+'}to'))
            drs='http://xbrl.org/2005/xbrldt'
            graph[(role,parent)].append({'kind':kind,'child':child,'next_role':n.get('{'+drs+'}targetRole',role),'usable':n.get('{'+drs+'}usable','true')!='false','raw_xml':raw.etree.tostring(n,encoding='unicode'),'line':n.sourceline})
    return graph

def member_path(graph,role,axis,member):
    todo=[(role,axis,[])];seen=set()
    while todo:
        r,node,path=todo.pop()
        if (r,node) in seen:continue
        seen.add((r,node))
        for arc in graph[(r,node)]:
            if arc['kind'] not in {'dimension-domain','domain-member'}:continue
            extended=path+[{'role':r,'parent':node,**arc}]
            if arc['child']==member and arc['usable']:return extended
            todo.append((arc['next_role'],arc['child'],extended))
    return None

def verify(parsed,p):
    proof=p['proof'];axis=proof.get('axis');role=proof.get('role')
    parent=[f for f in parsed['facts'] if f['QName']==parsed['target'] and f['asked_period'] and f['context_ref']==p['parent']['context_ref'] and f['unit_ref']==p['parent']['unit_ref'] and Decimal(f['value'])==Decimal(p['reported'])]
    if len(parent)!=1:return None,'nonunique raw parent'
    parent=parent[0];context=parent['context'];fixed={d[0]:d[2] for d in context['dimensions'] if d[1]=='explicit'}
    if len(fixed)!=len(context['dimensions']) or axis in fixed:return None,'unsupported parent dimensions'
    leaves=proof.get('reported_members',[])
    if not leaves:return None,'missing member anchors'
    graph=definition_graph(parsed);witness=[];seen=set()
    for leaf in leaves:
        fs=[f for f in parsed['facts'] if f['QName']==parsed['target'] and f['asked_period'] and f['context_ref']==leaf['context_ref'] and f['unit_ref']==leaf['unit_ref'] and Decimal(f['value'])==Decimal(leaf['value'])]
        if len(fs)!=1:return None,'nonunique raw member'
        f=fs[0];c=f['context'];dims={d[0]:d[2] for d in c['dimensions'] if d[1]=='explicit'}
        if len(dims)!=len(c['dimensions']) or set(dims)!=set(fixed)|{axis} or any(dims[a]!=m for a,m in fixed.items()):return None,'leaf differs outside aggregation axis'
        if any(c[k]!=context[k] for k in ['entity','entity_scheme','period']) or f['unit_signature']!=parent['unit_signature']:return None,'entity period unit mismatch'
        if dims[axis] in seen:return None,'duplicate member'
        seen.add(dims[axis]);path=member_path(graph,role,axis,dims[axis])
        if not path:return None,'member missing raw DRS path'
        witness.append({'fact':f,'raw_member_path':path})
    total=sum((Decimal(w['fact']['value']) for w in witness),Decimal(0))
    if total!=Decimal(p['value']) or total!=Decimal(p['reported']):return None,'raw sum is not selfconsistent'
    return {'parent':parent,'members':witness,'sum':str(total),'role':role,'axis':axis,'fixed_dimensions':fixed,'original_program_eligibility':p['eligible'],'original_rule':p['rule'],'original_rule_sha256':proof.get('source_rule_sha256'),'provided_DTS_subset_only':True},None

def select(query,prior,programs):
    candidates=[p for p in programs if p['rule'].startswith('DQC.US.0117.') and p.get('eligible') and p.get('relation_verified') and not p.get('violation') and Decimal(p['reported'])==Decimal(p['value'])==Decimal(prior['calculated_value']) and Decimal(p['reported'])!=Decimal(prior['extracted_value'])]
    if not candidates:return None,{'status':'no alternative selfconsistent eligible aggregation'}
    parsed=raw.source_parse(query);verified=[];rejected=[]
    for p in candidates:
        proof,reason=verify(parsed,p)
        if proof:verified.append((p,proof))
        else:rejected.append({'context':p['parent']['context_ref'],'reason':reason})
    pairs={(Decimal(p['reported']),Decimal(p['value'])) for p,_ in verified}
    if len(pairs)!=1:return None,{'status':'ambiguous or no independently verified pair','rejected':rejected}
    p,proof=verified[0]
    return {**prior,'extracted_value':p['reported']},{'status':'research_hypothesis_not_promoted','assumption':'A selfconsistent eligible dimensional subtotal with the same Q2 as C8 is the intended Q1 frame, even when no DQC violation fires. The question itself does not specify this scope.','proof':proof,'rejected':rejected,'production_promotion_authorized':False,'hidden_gold_correctness_proved':False}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    frozen={'strategy':'H117_selfconsistent_dimensional_frame','algorithm_sha256':sha(Path(__file__)),'raw_parser_sha256':sha(Path(raw.__file__)),'scoring_not_read':True,'C8_calculation_preserved':True}
    (OUT/'freeze.json').write_text(json.dumps(frozen,indent=2)+'\n',encoding='utf8')
    # Abort any accidental label/network access during inference.
    def guard(event,args):
        if event=='socket.connect':raise PermissionError('offline experiment')
        if event=='open' and isinstance(args[0],(str,Path)) and ('gold' in Path(args[0]).name.lower() or Path(args[0]).name=='public_dev.jsonl'):raise PermissionError('No gold in source inference')
    sys.addaudithook(guard)
    inventory={r['id']:r for r in rows(WORK/'runs/task3_error_localization_20261014/source_evidence_inventory.jsonl')}
    cohort={r['id'] for r in inventory.values() if r['locally_inferred_DQC']=='0117' and r['score_constraint_all_history']['state']!='necessarily_correct'}
    counters={'DEV3_000058','DEV3_000110','DEV3_000215','DEV3_000666'}
    summary={}
    for split in ['development','practice']:
        inp=ROOT/'data/raw/task3'/('finmr/public_dev_inputs.jsonl' if split=='practice' else 'development_inputs.jsonl')
        base={r['id']:r for r in rows(V34/split/'unanimity.predictions.jsonl')};audits={r['id']:r for r in rows(V34/split/'audit.jsonl')}
        predictions=[];decisions=[];changes=[]
        for r in rows(inp):
            cid=r['id'];prior=base[cid];new=None;proof={'status':'passthrough outside expensive cohort'}
            if split=='practice' or cid in cohort|counters:
                assert hashlib.sha256(r['query'].encode()).hexdigest()==audits[cid]['query_sha256']
                new,proof=select(r['query'],prior,audits[cid]['proposals'])
                decisions.append({'id':cid,'C8':prior,'candidate':new or prior,'evidence':proof})
            predictions.append(new or prior)
            if new and any(Decimal(new[k])!=Decimal(prior[k]) for k in ['extracted_value','calculated_value']):changes.append({'id':cid,'old':prior,'new':new,'evidence':proof})
        save(OUT/f'{split}.predictions.jsonl',predictions);save(OUT/f'{split}.decisions.jsonl',decisions);save(OUT/f'{split}.changes.jsonl',changes)
        summary[split]={'rows':len(predictions),'changes':len(changes),'ids':[r['id'] for r in changes],'status_counts':dict(Counter(r['evidence']['status'] for r in decisions)),'old_sha256':sha(V34/split/'unanimity.predictions.jsonl'),'new_sha256':sha(OUT/f'{split}.predictions.jsonl')}
    assert sha(Path(__file__))==frozen['algorithm_sha256']
    summary['cohort']=len(cohort);summary['known_correct_counterexamples_changed']=[r['id'] for r in changes if r['id'] in counters]
    summary['official_ACC_claimed']=False;summary['strategy_frozen_before_Practice_gold']=True
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8');print(json.dumps(summary))

if __name__=='__main__':main()
