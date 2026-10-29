"""One audited source engine for both inputs; no predictions or ID dispatch.

Native findings are freshly executed in each isolated run. Only standard
taxonomy XML/XSD caches are copied; no past finding/output is consumed.
"""
import sys,json,hashlib,shutil,time
from pathlib import Path
from decimal import Decimal
O=Path(__file__).resolve().parent;W=O.parents[1]
sys.path[:0]=[str(W/'runs/integrated_engine'),str(W/'runs/native_runtime')]
import pipeline as engine
import native
from task3.engine import Prediction
from task3.xml_core import parse_xml
P=W/'runs/rule_programs/programs'
sys.path[:0]=[str(P/'round6'),str(P/'round5'),str(P/'round4'),str(P)]
from source_rules_v5 import apply
original=engine.source_document_first
native_records=[]
settings=None

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def configure(work):
 global settings
 assert settings is None,'One isolated process per replay'
 work=Path(work);native.O=work/'native';native.O.mkdir(parents=True)
 source=W/'runs/native_runtime/runtime/cache'
 files={}
 for p in source.rglob('*'):
  if not p.is_file():continue
  rel=p.relative_to(source)
  if len(rel.parts)<2 or rel.parts[1] not in {'www.xbrl.org','xbrl.org','xbrl.fasb.org','xbrl.sec.gov'}:raise ValueError('Non-generic taxonomy cache '+str(rel))
  if p.suffix.lower() not in {'.xsd','.xml'}:raise ValueError('Non XML/XSD generic cache '+str(rel))
  target=native.O/'runtime/cache'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target);files[rel.as_posix()]=sha(p)
 compiled={}
 # Executable rule compilation is keyed by the four regenerated Xule source
 # hashes inside native.run. No access log or finding is copied or read.
 for previous in ['test_run1','test_run2','development_run']:
  for artifact in sorted((O/previous/'native/fresh_compiled').glob('*/rules.zip')):
   key=artifact.parent.name;digest=sha(artifact)
   if key in compiled:
    compiled[key].setdefault('other_compilations_same_source_key',[]).append({'SHA256':digest,'path':str(artifact)})
    continue
   target=native.O/'fresh_compiled'/key/'rules.zip';target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(artifact,target)
   compiled[key]={'SHA256':digest,'kind':'compiled Xule rules only; selected by freshly regenerated source hashes, not findings','source':str(artifact)}
 settings={'native_workspace':str(native.O),'standard_taxonomy_cache_files':files,'source_hash_keyed_compilation_cache':compiled,'past_findings_read':False,'legacy_compatibility_enabled':False,'native_failure_policy':'raise; no old answer fallback','owner_policy':'Retain an incumbent eligible negative focus over equally ambiguous single-Flourish preference. Allow explicitly recorded dual-Spark source convention.','source_same_for_all_inputs':True}
 engine.source_document_first=fresh_native
 return settings

def fresh_native(query,*,policy):
 if settings is None:raise RuntimeError('configure must precede inference')
 started=time.time();prior=original(query,policy=policy)
 record={'query_SHA256':hashlib.sha256(query.encode()).hexdigest(),'prior_document_first':{'extracted_value':prior.extracted_value,'calculated_value':prior.calculated_value,'mechanism':prior.mechanism,'evidence':prior.evidence},'fresh_native_executed':False,'old_finding_consumed':False}
 try:
  result=native.run(query,seeds=(0,));record['fresh_native_executed']=True
  value,proof=native.select(query,parse_xml(query,allow_complete_prefix=True),result,{'extracted_value':prior.extracted_value,'calculated_value':prior.calculated_value})
  record.update(source_case=result['case'],fresh_access_files=[str(p.relative_to(native.O)) for p in (native.O/result['case']).glob('access_v6_seed*.json')],selection=proof,selected_new_pair=value is not None,elapsed_seconds=time.time()-started)
  if value:
   record['selected_value']=value
   return Prediction(value['extracted_value'],value['calculated_value'],'fresh-native-source-bound',record)
  return Prediction(prior.extracted_value,prior.calculated_value,prior.mechanism,{**prior.evidence,'fresh_native_abstention':record})
 except Exception as error:
  record.update(error=repr(error),elapsed_seconds=time.time()-started)
  raise RuntimeError('Fresh native failed; no archived finding or answer permitted: '+record['query_SHA256']) from error
 finally:native_records.append(record)

def infer(query,*,output_id,exclusions):
 from task3.period_semantics import normalize_query
 query,period_normalization=normalize_query(query)
 before=len(native_records)
 value,events,c8_value,programs=engine.infer(query,None,exclusions,output_id=output_id)
 parsed=engine.raw.source_parse(query)
 proposal=apply(parsed)
 if proposal:
  incumbent=[f for f in engine.cn.prev.fs(parsed) if Decimal(f['value'])==Decimal(value['extracted_value']) and Decimal(f['value'])<0 and engine.raw.eligibility_0015(f,parsed['parts'],exclusions)['subset_eligible'] is True]
  single_flourish=proposal.get('rule')=='F15_InvestmentCost_FlourishResearchAcquisitionLLCRevolver'
  blocked=single_flourish and incumbent and Decimal(proposal['new']['extracted_value'])!=Decimal(value['extracted_value'])
  if blocked:
   events.append({'rule':'retain_eligible_incumbent_over_ambiguous_single_owner','changed':False,'incumbent_source_facts':incumbent,'declined_proposal':proposal,'reason':'Original assertion does not rank these legal owners; a single-owner preference must not replace another eligible negative focus.'})
  else:
   updated={**value,**proposal['new']};events.append({'rule':proposal.get('rule',proposal.get('mode')),'changed':not engine.same(value,updated),'source_evidence':proposal});value=updated
 value={k:value[k] for k in ['id','extracted_value','calculated_value']}
 if value['id']!=output_id:raise ValueError('ID changed during source inference')
 return value,{'period_normalization':period_normalization,'events':events,'programs':programs,'c8_value':c8_value,'fresh_native':native_records[before:]},parsed
