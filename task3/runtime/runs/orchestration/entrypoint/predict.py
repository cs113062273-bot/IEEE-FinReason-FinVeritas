"""Practice-driven repair of optional metadata boundaries in the unified engine.

Output identifiers are attached only after inference. Historical Development
diagnostic mappings are neither imported nor executed. No prior predictions,
labels, answer files, or network access are allowed during inference.
"""
import argparse, hashlib, json, os, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / 'scope_selection'
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent/'namespace_bindings'))
sys.path.insert(0,str(HERE.parent/'metadata_boundaries'))
sys.path.insert(0,str(HERE.parent/'partial_source'))
BASE = HERE.parent/'focus_domains'
sys.path.insert(0,str(HERE.parent/'scope_equations'))
sys.path.insert(0,str(HERE.parent/'reverse_focus'))
sys.path.insert(0,str(HERE.parent/'focus_transfer'))
sys.path.insert(0,str(HERE.parent/'source_constraints'))
sys.path.insert(0,str(BASE))
sys.path.insert(0,str(HERE.parent/'equation_priority'))
TREE = HERE.parent.parent  # isolated portable runtime root

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--ids',nargs='*',help='Optional research slice; never passed to inference.')
    args=parser.parse_args()
    inputs=args.inputs.resolve();out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    reads=set();denied=[]
    def guard(event,arguments):
        if event=='socket.connect':raise PermissionError('Offline source inference')
        if event!='open' or not isinstance(arguments[0],(str,bytes,Path)):return
        path=Path(os.fsdecode(arguments[0])).resolve()
        mode=arguments[1] if len(arguments)>1 else None
        if isinstance(mode,str) and 'r' not in mode and '+' not in mode:return
        if path.is_relative_to(out):return
        if path.suffix=='.jsonl' and path!=inputs:
            denied.append(str(path));raise PermissionError('Other inputs or prior outputs forbidden')
        if any(word in path.name.lower() for word in ['gold','official_feedback','prediction','diagnostic_v3']):
            denied.append(str(path));raise PermissionError('Answers/feedback/diagnostic mapping forbidden')
        reads.add(str(path))
    sys.addaudithook(guard)
    sys.path.insert(0,str(TREE/'runs/source_engine'))
    count=0;errors=[];unresolved_count=0;started=time.time()
    try:
        import common_core as core
        from transfer_core import install
        install(core)
        from reverse_focus import install as install_reverse
        install_reverse(core)
        from canonical_source import install as install_canonical
        install_canonical(core)
        from metadata_boundary import install as install_boundary
        install_boundary(core)
        from source_role_boundary import install as install_roles
        install_roles(core)
        from partial_source import install as install_partial
        partial_settings=install_partial(core)
        from uri_bindings import install as install_uri
        uri_settings=install_uri(core)
        from exact_scope_rank import select as select_scope
        from facility_temporal_rank import select as select_facility
        settings=core.configure(out)
        settings.update(partial_settings)
        settings.update(uri_settings)
        settings['consistent_rounded_source_fact_normalization']=True
        settings['optional_metadata_complete_node_boundary']=True
        settings['duplicate_evidence_counting']='one compatible fact per complete source aspect; unknown or conflicting groups retained as blockers'
        from calc11 import select as select_calc11
        from task3.engine import Prediction
        direct_records=[]
        def direct_before_native(query,*,policy):
            parsed=core.engine.raw.source_parse(query)
            proposal=select_calc11(parsed)
            if proposal:
                direct_records.append(proposal)
                return Prediction(proposal['new']['extracted_value'],proposal['new']['calculated_value'],
                                  'complete-supplied-calculation11',proposal)
            return core.fresh_native(query,policy=policy)
        core.engine.source_document_first=direct_before_native
        settings['complete_Calculation11_before_native']=True
        settings['missing_intermediate_refinement_enabled']=False
        exc=core.engine.raw.exclusions()
        records=list(map(json.loads,inputs.open(encoding='utf8')))
        if args.ids:records=[r for r in records if r['id'] in set(args.ids)]
        with (out/'predictions.jsonl').open('x',encoding='utf8') as predictions,(out/'decisions.jsonl').open('x',encoding='utf8') as decisions:
            for row in records:
                direct_start=len(direct_records)
                value,proof,parsed=core.infer(row['query'],output_id='source',exclusions=exc)
                completed_unresolved = value.get('source_status')=='unresolved'
                if completed_unresolved:
                    with (out/'unresolved.jsonl').open('a',encoding='utf8') as unresolved:
                        unresolved.write(json.dumps({'id':row['id'],**{k:v for k,v in value.items() if k!='id'},'decision':proof},default=str)+'\n')
                    unresolved_count+=1
                    proof['events'].append({'rule':'required_numeric_output_for_unresolved_fields',
                        'source_status':'unresolved','unresolved_reason':value.get('reason'),
                        'calculation_proof_claimed':False,'numeric_source_facts_fabricated':False,
                        'retained_extracted_value':value.get('extracted_value'),
                        'retained_calculated_value':value.get('calculated_value'),
                        'policy':'The supplied question requires 0 when a value cannot be determined.'})
                    value={'id':row['id'],
                        'extracted_value':str(value['extracted_value']) if value.get('extracted_value') is not None else '0',
                        'calculated_value':str(value['calculated_value']) if value.get('calculated_value') is not None else '0'}
                proof['direct_calculation11']=direct_records[direct_start:]
                proof['source_fact_normalization']=parsed.get('source_fact_normalization')
                proposal=None if completed_unresolved else (select_scope(parsed,value,proof['programs']) or
                          select_facility(parsed,value,proof['programs']))
                if proposal:
                    value={**value,**proposal['new']}
                    proof['events'].append({'rule':proposal['rule'],'changed':True,'source_evidence':proposal})
                value={**value,'id':row['id']}
                predictions.write(json.dumps(value)+'\n');predictions.flush()
                decisions.write(json.dumps({'id':row['id'],'decision':proof},default=str)+'\n');decisions.flush()
                count+=1
                if count%25==0:
                    print(f'{count}/{len(records)} elapsed={time.time()-started:.1f}',flush=True)
    except Exception as error:
        errors.append({'error':repr(error),'traceback':traceback.format_exc()})
    finally:
        modules={name:Path(m.__file__).resolve() for name,m in list(sys.modules.items()) if getattr(m,'__file__',None)}
        used={name:{'path':str(p),'SHA256':sha(p)} for name,p in modules.items() if p.is_file() and p.is_relative_to(HERE.parent)}
        summary={'unresolved_rows':unresolved_count,'attempted_rows':len(records) if not errors else count+unresolved_count,'rows':count,'complete680':count==680 and not errors,'errors':errors,'denied':denied,
                 'input_SHA256':sha(inputs),'modules':used,'source_engine_same_for_every_input':True,
                 'diagnostic_ID_mappings_executed':False,'output_ID_attached_after_numeric_inference':True,
                 'elapsed_seconds':time.time()-started,'settings':globals().get('settings'),
                 'direct_calculation11_count':len(globals().get('direct_records',[])),
                 'prediction_SHA256':sha(out/'predictions.jsonl') if (out/'predictions.jsonl').exists() else None,
                 'parent_reads':sorted(reads),'native_child_IO_not_exhaustively_audited':True}
        (out/'summary.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf8')
    if errors:raise RuntimeError('Source inference failed; inspect summary')


