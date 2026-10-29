"""Portable inference entry point; offline cached proposals by default."""
import argparse,hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'upstream/ieee-bigdata-cup')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--questions',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--registry',type=Path,default=ROOT/'data/processed/task1_registry.json')
    parser.add_argument('--local-model',action='store_true',help='Enable new requests to your local compatible server at 127.0.0.1:8771.')
    parser.add_argument('--allow-nonofficial',action='store_true',help='For ancillary report/stress question schemas only; skip the official input-format gate. Official Test keeps validation enabled.')
    parser.add_argument('--json-spacing', choices=('compact','standard'), default='compact', help='JSON whitespace only; standard reproduces the submitted Test serialization.')
    parser.add_argument('--verify',action='store_true',help='Run post-hoc completeness/provenance checks and independent learned-DAG reexecution; write an adjacent .verification.json report.')
    args=parser.parse_args()
    from src.task1.solver import Solver
    import src.task1.best_effort as be
    if not args.local_model:
        def cached_only(q):
            public={k:q[k] for k in ['question','answer_spec','trace_spec']}
            key=hashlib.sha256((be.MODEL_SHA+be.PROMPT+json.dumps(public,sort_keys=True)).encode()).hexdigest()
            path=ROOT/'data/processed/task1_best_effort_cache'/(key+'.json')
            if not path.exists():raise ValueError('Offline: no cached proposal; mandatory fallback remains available.')
            record=json.loads(path.read_text(encoding='utf8'))
            if record.get('model_sha256')!=be.MODEL_SHA:raise ValueError('Unexpected cached model identity')
            return record,'bundled_offline_cache'
        be._model=cached_only
    questions=[json.loads(s) for s in args.questions.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    solver=Solver(args.registry);pairs=[solver.predict(q) for q in questions];predictions=[p for p,a in pairs]
    if not args.allow_nonofficial:
        from finreason_task1.contracts import validate_submission
        valid=validate_submission(predictions,{q['case_id']:q for q in questions},require_complete=True).as_dict()
        if not valid['valid']:raise ValueError(valid)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    verification=None
    if args.verify:
        from src.task1.verifier import verify_prediction
        checks=[verify_prediction(q,p,a) for q,(p,a) in zip(questions,pairs)]
        failures=[check for check in checks if not check['valid']]
        verification={'records':len(checks),'valid_records':len(checks)-len(failures),
                      'independent_dag_values':sum(check['independent_dag_values'] for check in checks),
                      'errors':failures,
                      'scope':'All rows: completeness, finite values and binding provenance. Learned-DAG routes: independent expression reexecution. Other routes: no independent semantic correctness claim.'}
        args.output.with_suffix('.verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf8')
        if failures:raise ValueError('Post-hoc verification failed; inspect the .verification.json report.')
    from src.common.jsonl import write_jsonl
    if args.json_spacing == 'standard':
        payload=''.join(json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n' for row in predictions)
        args.output.write_bytes(payload.encode('utf8'))
    else:
        write_jsonl(args.output,predictions)
    write_jsonl(args.output.with_suffix('.audit.jsonl'),[a for p,a in pairs])
    summary={'records':len(predictions),'answered':sum(p['final_answer'] is not None for p in predictions),'offline':not args.local_model,'official_format_checked':not args.allow_nonofficial}
    if verification is not None:
        summary['posthoc_verified_records']=verification['valid_records']
        summary['independent_dag_values']=verification['independent_dag_values']
    print(json.dumps(summary))


if __name__=='__main__':main()
