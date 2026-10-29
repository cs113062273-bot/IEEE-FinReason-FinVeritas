"""Incremental frozen source hypotheses against H15, not hidden gold.

H117_terminal_violation: isolate terminal node of verified nested *violating*
same-QName aggregations, rather than H117's nonviolating alternate frame.
H15_two_axis_diamond: require three eligible equal-valued raw facts linked by
two distinct exact one-axis projections; no source-order/min-dimension rank.
H15_precision_projection: test interval-compatible Ownership projections.
"""
import hashlib,importlib.util,json,sys
from collections import defaultdict,Counter
from decimal import Decimal,localcontext
from datetime import date
from pathlib import Path

WORK=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
ROOT=WORK/'core/source'
sys.path.insert(0,str(WORK/'runs/source_candidates/nonnegative'))
import ownership_scope_candidate as ownership
sys.path.insert(0,str(WORK/'runs/source_candidates/dimensional'))
import experiment as dimensional
sys.path.insert(0,str(ROOT/'upstream/ieee-bigdata-cup/finreason_task3'))
from task3_core.validation import validate_submission_file
raw=ownership.n.audit
def rows(p):return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def same(a,b):return all(Decimal(a[k])==Decimal(b[k]) for k in ['extracted_value','calculated_value'])
def save(p,rs):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs),encoding='utf-8')

def verified_program(parsed,p):
    proof=p['proof'];axis=proof.get('axis');role=proof.get('role')
    parents=[f for f in parsed['facts'] if f['QName']==parsed['target'] and f['asked_period'] and f['context_ref']==p['parent']['context_ref'] and f['unit_ref']==p['parent']['unit_ref'] and Decimal(f['value'])==Decimal(p['reported'])]
    if len(parents)!=1 or not axis or not role:return None
    parent=parents[0];context=parent['context'];fixed={d[0]:d[2] for d in context['dimensions'] if d[1]=='explicit'}
    if len(fixed)!=len(context['dimensions']) or axis in fixed:return None
    graph=dimensional.definition_graph(parsed);members=[];seen=set()
    for leaf in proof.get('reported_members',[]):
        anchors=[f for f in parsed['facts'] if f['QName']==parsed['target'] and f['asked_period'] and f['context_ref']==leaf['context_ref'] and f['unit_ref']==leaf['unit_ref'] and Decimal(f['value'])==Decimal(leaf['value'])]
        if len(anchors)!=1:return None
        fact=anchors[0];c=fact['context'];dims={d[0]:d[2] for d in c['dimensions'] if d[1]=='explicit'}
        if len(dims)!=len(c['dimensions']) or set(dims)!=set(fixed)|{axis} or any(dims[a]!=m for a,m in fixed.items()):return None
        if any(c[k]!=context[k] for k in ['entity','entity_scheme','period']) or fact['unit_signature']!=parent['unit_signature']:return None
        if dims[axis] in seen:return None
        seen.add(dims[axis]);path=dimensional.member_path(graph,role,axis,dims[axis])
        if not path:return None
        members.append({'fact':fact,'raw_DRS_path':path})
    if not members:return None
    total=sum((Decimal(m['fact']['value']) for m in members),Decimal(0))
    if total!=Decimal(p['value']) or total==Decimal(parent['value']):return None
    return {'parent':parent,'members':members,'member_sum':str(total),'original_rule':p['rule'],'original_role':role,'aggregation_axis':axis,'original_statement_eligible':True,'original_rule_sha256':proof.get('source_rule_sha256'),'subset_DTS_only':True,'question_focus_unique':False}

def terminal_violation(parsed,prior,programs,exc):
    eligible=[p for p in programs if p['rule'].startswith('DQC.US.0117.') and p.get('eligible') and p.get('relation_verified') and p.get('violation')]
    if len(eligible)<2:return None,{'status':'fewer than2 original applicable violating programs'}
    verified=[]
    for p in eligible:
        witness=verified_program(parsed,p)
        if witness:verified.append(witness)
    if len(verified)!=len(eligible):return None,{'status':'cannot independently verify all original competing programs'}
    edges=[]
    for i,p in enumerate(verified):
        for j,q in enumerate(verified):
            if i==j:continue
            parent=q['parent']
            if any(m['fact']['id']==parent['id'] and m['fact']['context_ref']==parent['context_ref'] and m['fact']['unit_signature']==parent['unit_signature'] and m['fact']['context']==parent['context'] for m in p['members']):edges.append((i,j))
    if not edges:return None,{'status':'competing violations not nested'}
    participating=set(v for e in edges for v in e)
    if participating!=set(range(len(verified))):return None,{'status':'unconnected competing violation'}
    targets=set(j for _,j in edges);roots=set(i for i,_ in edges)-targets
    # Every original program must be reachable, and no dependency cycles.
    reached=set();pending=list(roots)
    while pending:
        i=pending.pop()
        if i in reached:continue
        reached.add(i);pending.extend(j for a,j in edges if a==i)
    terminals=targets-set(i for i,_ in edges)
    if reached!=participating or len(terminals)!=1:return None,{'status':'no unique reachable terminal violation'}
    leaf=verified[next(iter(terminals))]
    new={**prior,'extracted_value':leaf['parent']['value'],'calculated_value':leaf['member_sum']}
    return new,{'status':'research_terminal_violation_hypothesis','hypothesis':'A reported member that itself violates an original applicable aggregation is the corruption focus rather than a propagated outer mismatch. No hidden focus binding is proved.','nested_edges':[{'outer_parent_context':verified[i]['parent']['context_ref'],'inner_parent_context':verified[j]['parent']['context_ref']} for i,j in edges],'program_witnesses':verified,'selected_terminal':leaf,'source_order_feature':False,'H117_nonviolating_frame_reused':False}

def negative_facts(parsed,exc):
    return [f for f in parsed['facts'] if f['QName']==parsed['target'] and f['asked_period'] and f['context'] and f['unit_signature'] and Decimal(f['value'])<0 and not f['sign'] and not f['scale'] and not f['context']['opaque_qualifiers'] and raw.eligibility_0015(f,parsed['parts'],exc)['subset_eligible']]
def projection_edges(parsed,exc,precision=False):
    facts=negative_facts(parsed,exc);edges=[]
    for subtotal in facts:
        base=ownership.n.dims(subtotal)
        for detail in facts:
            dims=ownership.n.dims(detail);extra=set(dims)-set(base)
            if len(extra)!=1 or not set(base)<=set(dims) or any(dims[a]!=m for a,m in base.items()):continue
            axis=next(iter(extra))
            if ownership.n.aspects(detail,axis)!=ownership.n.aspects(subtotal,axis):continue
            a,b=Decimal(detail['value']),Decimal(subtotal['value'])
            compatible=a==b
            if precision:
                def interval(f):
                    if f['decimals'] is None or f['decimals']=='INF':return Decimal(f['value']),Decimal(f['value'])
                    radius=Decimal(10)**(-int(f['decimals']))/2
                    return Decimal(f['value'])-radius,Decimal(f['value'])+radius
                aa,bb=interval(detail),interval(subtotal);compatible=max(aa[0],bb[0])<=min(aa[1],bb[1])
            if compatible:edges.append({'detail':detail,'subtotal':subtotal,'axis':axis,'literal_values_equal':a==b,'precision_overlap':compatible})
    return edges

def diamond(parsed,prior,programs,exc):
    if Decimal(prior['extracted_value'])>=0:return None,{'status':'preserve existing positive focus; no new hypothesis'}
    edges=projection_edges(parsed,exc);witnesses=[]
    for i,a in enumerate(edges):
        for b in edges[i+1:]:
            if a['subtotal']['id']!=b['subtotal']['id'] or a['axis']==b['axis'] or a['detail']['id']==b['detail']['id']:continue
            # Original supplied DRS membership must support both deleted axes.
            graph=dimensional.definition_graph(parsed);paths=[]
            for e in [a,b]:
                member=ownership.n.dims(e['detail'])[e['axis']]
                candidates=[(role,dimensional.member_path(graph,role,e['axis'],member)) for role,node in list(graph) if node==e['axis']]
                candidates=[(r,p) for r,p in candidates if p]
                if not candidates:break
                paths.append({'axis':e['axis'],'role':candidates[0][0],'path':candidates[0][1]})
            if len(paths)==2:witnesses.append({'subtotal':a['subtotal'],'details':[a['detail'],b['detail']],'independent_dimension_paths':paths,'three_distinct_raw_source_nodes':True})
    pairs={(w['subtotal']['value'],str(abs(Decimal(w['subtotal']['value'])))) for w in witnesses}
    if len(pairs)!=1:return None,{'status':'no unique two-axis corroborated magnitude','witnesses':witnesses}
    x,y=next(iter(pairs));return {**prior,'extracted_value':x,'calculated_value':y},{'status':'research_two_axis_projection_hypothesis','witnesses':witnesses,'question_scope_unique':False,'positive_correction_magnitude_proved':False}

def precision_projection(parsed,prior,programs,exc):
    if Decimal(prior['extracted_value'])>=0:return None,{'status':'preserve positive focus'}
    witnesses=[]
    for e in projection_edges(parsed,exc,True):
        if e['literal_values_equal'] or not ownership.ownership_label_proof(parsed,e['axis']):continue
        siblings=[f for f in parsed['facts'] if f['QName']==parsed['target'] and f['asked_period'] and f['context'] and e['axis'] in ownership.n.dims(f) and ownership.n.aspects(f,e['axis'])==ownership.n.aspects(e['subtotal'],e['axis'])]
        if any(Decimal(f['value'])!=0 and f['id']!=e['detail']['id'] for f in siblings):continue
        witnesses.append(e)
    pairs={(w['detail']['value'],str(abs(Decimal(w['detail']['value'])))) for w in witnesses}
    if len(pairs)!=1:return None,{'status':'no unique precision-compatible ownership projection','witnesses':witnesses}
    x,y=next(iter(pairs));return {**prior,'extracted_value':x,'calculated_value':y},{'status':'research_precision_projection_hypothesis','witnesses':witnesses,'interval_overlap_not_gold':True}

def contrastive_sign_onset(parsed,prior,programs,exc):
    """Exact-frame sign transition versus persistently negative competitors.

    Unlike M047 positive history magnitude corroboration, require every rival
    current negative value to have a same-frame negative prior comparator.
    New negative sign is a focus hypothesis, not a magnitude certificate.
    """
    current=negative_facts(parsed,exc)
    if len({Decimal(f['value']) for f in current})<2:return None,{'status':'no competing negative magnitudes'}
    target=parsed['target'];histories=[];states=defaultdict(set);witnesses=[]
    def end(period):return period[2] or period[1]
    def kind(period):return 'instant' if period[2] else 'duration'
    for f in current:
        c=f['context'];previous=[]
        for old in parsed['facts']:
            oc=old['context']
            if old['QName']!=target or not oc or old['unit_signature']!=f['unit_signature'] or old['sign'] or old['scale']:continue
            if any(c[k]!=oc[k] for k in ['entity','entity_scheme','dimensions','opaque_qualifiers']):continue
            if kind(c['period'])!=kind(oc['period']) or not end(oc['period']) or end(oc['period'])>=end(c['period']):continue
            if kind(c['period'])=='duration':
                if not oc['period'][0] or not c['period'][0]:continue
                nowlength=(date.fromisoformat(c['period'][1])-date.fromisoformat(c['period'][0])).days
                oldlength=(date.fromisoformat(oc['period'][1])-date.fromisoformat(oc['period'][0])).days
                if abs(nowlength-oldlength)>3:continue
            previous.append(old)
        if not previous:return None,{'status':'at least one negative competitor lacks exact-aspect previous source'}
        latest=max(end(o['context']['period']) for o in previous)
        chosen=[o for o in previous if end(o['context']['period'])==latest]
        values={Decimal(o['value']) for o in chosen}
        if len(values)!=1:return None,{'status':'conflicting exact-aspect previous duplicate'}
        value=Decimal(f['value']);onset=next(iter(values))>=0
        states[value].add(onset);witnesses.append({'current':f,'latest_same_aspect_previous':chosen,'newly_negative':onset})
    if any(len(v)!=1 for v in states.values()):return None,{'status':'same magnitude spans inconsistent comparative sign histories'}
    proposed=[v for v,status in states.items() if status=={True}]
    if len(proposed)!=1 or not any(v=={False} for v in states.values()):return None,{'status':'no unique sign-onset against persistent negative rivals','witnesses':witnesses}
    value=proposed[0]
    return {**prior,'extracted_value':str(value),'calculated_value':str(abs(value))},{'status':'research_contrastive_sign_onset','witnesses':witnesses,'hypothesis':'Prefer the sole newly negative exact-aspect source when all other current negative magnitudes have same-aspect negative prior-period reports. No hidden focus or absolute-value correction proved.','financial_role_changed':False,'question_scope_unique':False,'positive_magnitude_certified':False}

STRATEGIES={'H117_terminal_violation':terminal_violation,'H15_two_axis_diamond':diamond,'H15_precision_projection':precision_projection,'H15_contrastive_sign_onset':contrastive_sign_onset}
def main():
    frozen={'source_sha256':sha(Path(__file__)),'strategy_names':list(STRATEGIES),'baseline':'H15 scored664/680','frozen_before_new_Practice_scoring':True,'training':False,'no_hidden_gold':True,'promotion':False}
    (OUT/'experiment_freeze.json').write_text(json.dumps(frozen,indent=2)+'\n',encoding='utf-8')
    def guard(event,args):
        if event=='socket.connect':raise PermissionError('offline inference')
        if event=='open' and isinstance(args[0],(str,Path)) and ('gold' in Path(args[0]).name.lower() or Path(args[0]).name=='public_dev.jsonl'):raise PermissionError('no gold in inference')
    sys.addaudithook(guard)
    raw.xml=ownership.s.closed_xml;exc=raw.exclusions()
    cohort=set(read(OUT/'source_contract.summary.json')['remaining16_error_universe'])
    counters={'DEV3_000058','DEV3_000110','DEV3_000215','DEV3_000666'}
    summary={n:{} for n in STRATEGIES}
    for split in ['development','practice']:
        inputpath=ROOT/'data/raw/task3'/('development_inputs.jsonl' if split=='development' else 'finmr/public_dev_inputs.jsonl')
        baselinepath=WORK/'DELIVERY/task3_H15_best_provisional_97_65_20261015/development.predictions.jsonl' if split=='development' else ROOT/'reports/round6_iterations/official_semantics_candidate_v34/practice/unanimity.predictions.jsonl'
        baseline=rows(baselinepath);sources={r['id']:r for r in rows(inputpath)}
        audits={r['id']:r for r in rows(ROOT/f'reports/round6_iterations/official_semantics_candidate_v34/{split}/audit.jsonl')}
        outputs={n:[] for n in STRATEGIES};decisions={n:[] for n in STRATEGIES};changes={n:[] for n in STRATEGIES}
        for prior in baseline:
            cid=prior['id'];active=split=='practice' or cid in cohort|counters
            if active:parsed=raw.source_parse(sources[cid]['query'])
            for n,select in STRATEGIES.items():
                new=None;proof={'status':'reuse H15 outside112cohort'}
                if active:
                    new,proof=select(parsed,prior,audits[cid]['proposals'],exc)
                    record={'id':cid,'old':prior,'new':new or prior,'evidence':proof,'query_sha256':hashlib.sha256(sources[cid]['query'].encode()).hexdigest(),'known_correct_counterexample':cid in counters,'correct_answer_proven':False}
                    decisions[n].append(record)
                    if new and not same(prior,new):changes[n].append(record)
                outputs[n].append(new or prior)
        for n in STRATEGIES:
            target=OUT/n;save(target/f'{split}.predictions.jsonl',outputs[n]);save(target/f'{split}.decisions.jsonl',decisions[n]);save(target/f'{split}.changes.jsonl',changes[n])
            valid=validate_submission_file(target/f'{split}.predictions.jsonl',inputpath,reference_kind='inputs');assert valid.ok
            (target/f'{split}.validation.json').write_text(json.dumps(valid.to_dict(),indent=2)+'\n',encoding='utf-8')
            summary[n][split]={'rows':len(outputs[n]),'changes':len(changes[n]),'changed_ids':[r['id'] for r in changes[n]],'counterexample_changes':[r['id'] for r in changes[n] if r['known_correct_counterexample']],'status_counts':dict(Counter(r['evidence']['status'] for r in decisions[n]))}
    assert sha(Path(__file__))==frozen['source_sha256']
    (OUT/'experiment_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
