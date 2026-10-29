"""Fresh C5 native fallback, isolated restored runtime, no prediction lookups.

Original C5 used a reduced metadata dependency set and an asked-period override;
those limitations are retained and disclosed, never described as a full DTS.
"""
from pathlib import Path
import os,json,hashlib,subprocess,re,sys
from decimal import Decimal,InvalidOperation
O=Path(__file__).resolve().parent
W=O.parents[1]
R=W/'core/source'
S=O/'source_config'
PY=Path(sys.executable)
PLUGIN=S/'upstream/desktop_xule_generic/plugin/xule'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def calculated_from_message(code,message):
    """Parse a complete finite token from the pinned native message template.

    DQC0126 appends sentence punctuation; DQC0117 appends 'using'. Never
    accept only a mantissa, exponent prefix or malformed thousands grouping.
    This remains a serialization bridge, not a proof of assertion scope.
    """
    phrase=(r'dimensional breakdown of\s+(\S+)' if code.startswith('DQC.US.0117')
            else r'The sum of these child components is\s+(\S+)')
    match=re.search(phrase,message)
    if not match:return None
    token=match[1]
    if token.endswith('.'):token=token[:-1]
    if not re.fullmatch(r'[+-]?(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',token):return None
    try:value=Decimal(token.replace(',',''))
    except InvalidOperation:return None
    return value if value.is_finite() else None
def execute(command,log,timeout=120,seed=None):
    env=os.environ.copy()
    if seed is not None:env['PYTHONHASHSEED']=str(seed)
    r=subprocess.run(list(map(str,command)),capture_output=True,text=True,encoding='utf8',timeout=timeout,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    log.write_text(r.stdout+r.stderr,encoding='utf8')
    if r.returncode:raise RuntimeError(f'{log.name}: exit {r.returncode}; '+(r.stdout+r.stderr)[-600:])
def run(query,seeds=(0,),version=6):
    h=hashlib.sha256(query.encode()).hexdigest();case=O/'fresh'/h
    case.mkdir(parents=True,exist_ok=True)
    inp=case/'input.jsonl';inp.write_text(json.dumps({'id':'source','query':query})+'\n',encoding='utf8')
    bundle=case/f'bundle_v{version}'
    if not bundle.exists():
        execute([PY,S/f'scripts/task3_desktop_source_bundle_v{version}.py','--input',inp,'--case-id','source','--output',bundle],case/f'prepare_v{version}.log')
    manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf8'))
    assert manifest['input_query_sha256']==h
    for name,expected in manifest['files_sha256'].items():
        assert sha(bundle/name)==expected,('Source bundle modified after preparation',name)
    rules=['DQC_0117.xule','DQC_0126.xule','DQC_0015.xule','source_dependencies.xule']
    kh=hashlib.sha256(''.join(sha(bundle/x) for x in rules).encode()).hexdigest();comp=O/'fresh_compiled'/kh
    comp.mkdir(parents=True,exist_ok=True)
    if not (comp/'rules.zip').exists():
        execute([PY,'-m','arelle.CntlrCmdLine','--plugins',PLUGIN,'--xule-compile','|'.join(str(bundle/x) for x in rules),'--xule-rule-set',comp/'rules.zip','--internetConnectivity','offline','--logFile',comp/'compile.log'],comp/'compile_process.log')
    results=[]
    for seed in seeds:
        access=case/f'access_v{version}_seed{seed}.json'
        execute([PY,S/'scripts/task3_desktop_arelle_run.py','--access-log',access,'--plugins',PLUGIN,'--file',bundle/'instance.xml','--validate','--xule-run','--xule-rule-set',comp/'rules.zip','--internetConnectivity','offline','--cacheDirectory',O/'runtime/cache','--logFile',case/f'native_v{version}_seed{seed}.log'],case/f'process_v{version}_seed{seed}.log',seed=seed)
        results.append(json.loads(access.read_text(encoding='utf8')))
    return {'query_sha256':h,'case':case.relative_to(O).as_posix(),'metadata_reduced':True,'asked_period_override':True,'version':version,'seeds':list(seeds),'accesses':results}

def select(query,filing,native,prior):
    """Faithful frozen C5 unique-pair policy; independently bind focus to source."""
    if native.get('query_sha256')!=hashlib.sha256(query.encode()).hexdigest():return None,{'reason':'native query SHA does not match source'}
    pairs=[];witnesses=[]
    for a in native['accesses']:
        pp=set()
        for f in a['computed_DQC_findings']:
            if '{'+f['concept_namespace']+'}'+f['concept_local_name']!=filing.target or f['schema_validation_state']!=4:continue
            c=filing.contexts.get(f['context_ref']);u=filing.units.get(f['unit_ref'])
            if not c or not u or c.qualifiers:continue
            if not ((c.start,c.end)==(filing.start,filing.end) if filing.end else c.instant==filing.start):continue
            vals={x.value for x in filing.facts if x.concept==filing.target and x.context==c.id and x.unit==u.id}
            if len(vals)!=1 or next(iter(vals))!=Decimal(f['typed_value']):continue
            reported=Decimal(f['typed_value'])
            if f['code'].startswith('DQC.US.0015'):calculated=reported.copy_abs()
            else:
                calculated=calculated_from_message(f['code'],f['message'])
                if calculated is None:continue
            pp.add((reported,calculated));witnesses.append(f)
        pairs.append(pp)
    if not pairs or any(len(p)!=1 for p in pairs) or any(p!=pairs[0] for p in pairs):return None,{'reason':'native pair not unique and stable','pairs':[[(str(x),str(y)) for x,y in p] for p in pairs]}
    x,y=next(iter(pairs[0]));px=Decimal(prior['extracted_value']);py=Decimal(prior['calculated_value'])
    if x!=px and (px,py)!=(0,0):return None,{'reason':'C5 preserved resolved conflicting reported frame'}
    def fmt(x):return format(x,'f').rstrip('0').rstrip('.') if '.' in format(x,'f') else format(x,'f')
    return {**prior,'extracted_value':fmt(x),'calculated_value':fmt(y)},{'reason':'fresh native C5 unique pair, asked QName/period and raw focus bound','witnesses':witnesses,'metadata_reduced':True,'not_full_DTS':True}
