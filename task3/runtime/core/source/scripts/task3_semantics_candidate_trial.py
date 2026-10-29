"""Isolated exact-QName / axis-unanimity / native-duration trials; no upload."""
from collections import Counter
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'upstream/ieee-bigdata-cup/finreason_task3')]
from task3.xml_core import parse_xml
from task3.round6_candidates import inventory,target_groups,unique_pair
from task3.round6_source_interval import normalize,compatible_choice
from task3.round6_dqc0117_consensus import candidates as dimensions
from task3.round6_dqc0126 import candidates as calculations
from task3.round6_dqc0015_exact import eligibility
from task3.round6_engine_v2 import candidates as old_candidates
from task3_core.validation import validate_submission_file
OUT=ROOT/'reports/round6_iterations/official_semantics_candidate_v34'

def rows(p):return [json.loads(s) for s in p.read_text(encoding='utf8').splitlines() if s.strip()]
def write(p,rs):p.write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs).encode())
def sig(p):return (p['rule'].split('.')[2],p['parent']['concept'],p['parent']['context_ref'],p['parent']['unit_ref'],Decimal(p['reported']),Decimal(p['value']))
def make(query,filing,native_duration):
    def dim(q,f,parent,*,allow_inferred_statement):
        return dimensions(q,f,parent,duplicate_policy='raw_include_dups',allow_inferred_statement=False,native_duration=native_duration)
    def calc(q,f,parent,*,allow_inferred_statement):
        return calculations(q,f,parent,duplicate_policy='raw_include_dups',allow_inferred_statement=False)
    ps,summary=inventory(query,filing,adapters={'0117':dim,'0126':calc},infer_statement_uri=False)
    ps=[p for p in ps if not p['rule'].startswith('DQC.US.0015')]
    for fs in target_groups(filing).values():
        parent,binding=compatible_choice(filing,fs)
        if parent is None:continue
        proof=eligibility(filing,parent,filing.contexts[parent.context],query=query)
        if proof['eligible']:
            ps.append({'rule':proof['rule'],'reported':str(parent.value),'value':str(parent.value.copy_abs()),'parent':parent.evidence(filing),
                'eligible':True,'violation':True,'relation_verified':False,'magnitude_repair_hypothesis':True,'proof':{**proof,'duplicate_binding':binding}})
    for p in ps:
        if p['proof'].get('rule_family')=='0117':p['violation']=bool(p['proof']['eligible'] and p['proof']['violates']);p['tolerance']=p['proof']['tolerance']
    return ps,summary

def infer():
    OUT.mkdir(parents=True,exist_ok=False)
    def guard(event,args):
        if event=='socket.connect':raise PermissionError('Offline source inference')
        if event=='open' and isinstance(args[0],(str,bytes,Path)):
            p=Path(args[0].decode() if isinstance(args[0],bytes) else args[0])
            if 'gold' in p.name.lower() or p.name=='public_dev.jsonl' or '1500' in str(p):raise PermissionError('No gold or blind data')
    sys.addaudithook(guard);tick=time.perf_counter();summary={}
    for split in ['practice','development','test']:
        inp=ROOT/'data/raw/task3'/('finmr/public_dev_inputs.jsonl' if split=='practice' else split+'_inputs.jsonl')
        old={r['id']:r for r in rows(ROOT/f'outputs/task3_desktop_candidate_v4_C6_extraction/{split}.predictions.jsonl')}
        audits=[];preds={a:[] for a in ['new_only','unanimity','native_duration']};counts=Counter();changes={a:[] for a in preds};errors=[]
        for r in rows(inp):
            prior=old[r['id']];query=r['query']
            try:
                raw=parse_xml(query,allow_complete_prefix=True);filing,dups=normalize(raw)
                baseline,_,_=old_candidates(query,filing=raw)
                existing={sig(p) for p in baseline if p['eligible'] and p['violation']}
                ps,s=make(query,filing,False);native_ps,native_summary=make(query,filing,True)
                selected=unique_pair(ps,s);new_ps=[p for p in ps if sig(p) not in existing]
                # A new proof may not hide conflicting old eligible proofs.
                # Require invariance across the entire applicable inventory.
                new_selected=selected if selected and sig(selected) not in existing else None
                native_selected=unique_pair(native_ps,native_summary)
                picks={'new_only':new_selected,'unanimity':selected,'native_duration':native_selected}
                evidence={'id':r['id'],'query_sha256':hashlib.sha256(query.encode()).hexdigest(),'C6':prior,'duplicates':dups,'summary':s,'proposals':ps,'native_duration_proposals':native_ps,'new_proposals':new_ps,'selections':picks}
                counts['proposals']+=len(ps);counts['eligible']+=sum(p['eligible'] for p in ps);counts['new_eligible']+=sum(p['eligible'] for p in new_ps)
            except Exception as e:
                errors.append({'id':r['id'],'error':repr(e)});picks={a:None for a in preds};evidence={'id':r['id'],'error':repr(e)}
            audits.append(evidence)
            for arm,p in picks.items():
                prediction=dict(prior)
                if p:prediction.update(extracted_value=p['reported'],calculated_value=p['value'])
                preds[arm].append(prediction)
                if any(Decimal(prediction[k])!=Decimal(prior[k]) for k in ['extracted_value','calculated_value']):changes[arm].append({'id':r['id'],'C6':prior,'new':prediction,'source_proposal':p})
        folder=OUT/split;folder.mkdir();write(folder/'audit.jsonl',audits)
        for arm,rs in preds.items():
            path=folder/f'{arm}.predictions.jsonl';write(path,rs);write(folder/f'{arm}.changes.jsonl',changes[arm]);valid=validate_submission_file(path,inp,reference_kind='inputs');assert valid.ok,valid.render()
        summary[split]={'count':len(audits),'errors':errors,'counts':dict(counts),'changes':{a:len(cs) for a,cs in changes.items()},'format_valid_all_arms':True,'input_sha256':hashlib.sha256(inp.read_bytes()).hexdigest()}
        print(json.dumps({split:summary[split]}),flush=True)
    summary.update(no_gold_read=True,uploaded=False,runtime_seconds=time.perf_counter()-tick)
    (OUT/'manifest.json').write_bytes((json.dumps(summary,indent=2)+'\n').encode())

def score():
    from collections import Counter
    public={r['id']:r for r in rows(ROOT/'data/raw/task3/finmr/public_dev.jsonl')}
    # Public Practice labels only, separate process after completed inference.
    print(next(iter(public.values())).keys())

if __name__=='__main__':infer()
