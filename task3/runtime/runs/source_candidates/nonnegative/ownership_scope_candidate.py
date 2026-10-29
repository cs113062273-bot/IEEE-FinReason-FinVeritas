"""New isolated ownership-labelled scope arm, retaining bare-arm failures."""
import hashlib,json,re
from decimal import Decimal
from lxml import etree
import netting_candidate as n
import subtotal_corroboration as s

OUT=n.OUT/'ownership_scope';OUT.mkdir(exist_ok=True)
def ownership_axis_proof(parsed,axis):
    """Bind the public dimension declaration, independently of label language.

    This qualifies the axis's meaning only. It neither proves aggregation
    completeness nor gives an ownership focus priority over another focus.
    """
    return public_ownership_axis(axis)


from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=32)
def public_ownership_axis(axis):
    if not re.fullmatch(r'\{http://fasb.org/srt/20\d\d(?:-01-31)?\}OwnershipAxis',axis):
        return None
    workspace=Path(__file__).resolve().parents[3]
    cache=workspace/'runs/native_runtime/runtime/cache'
    declarations=[]
    for path in cache.rglob('srt-*.xsd'):
        root=etree.fromstring(path.read_bytes(),etree.XMLParser(resolve_entities=False,no_network=True))
        if '{'+root.get('targetNamespace','')+'}OwnershipAxis'!=axis:continue
        for node in root.findall('{http://www.w3.org/2001/XMLSchema}element'):
            if node.get('name')!='OwnershipAxis':continue
            prefix,separator,name=node.get('substitutionGroup','').partition(':')
            uri=node.nsmap.get(prefix if separator else None)
            if (uri,name if separator else prefix)!=('http://xbrl.org/2005/xbrldt','dimensionItem'):continue
            if node.get('abstract') not in {'true','1'}:continue
            declarations.append({'schema_SHA256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'schema':str(path),'declaration_xml':etree.tostring(node,encoding='unicode')})
    if not declarations:return None
    return {'exact_QName':axis,'public_dimension_declarations':declarations,
            'label_text_or_language_used_as_gate':False,
            'taxonomy_identity_proves_axis_semantics_only':True,
            'aggregation_completeness_or_question_focus_proved':False}


# Compatibility for other experimental projection callers; identity, not text.
ownership_label_proof=ownership_axis_proof


def select(parsed,base,exc):
    candidates=s.witnesses(parsed,exc);retained=[]
    for w in candidates:
        proof=ownership_label_proof(parsed,w['axis_removed'])
        if proof:retained.append({**w,'public_ownership_axis_identity':proof})
    pairs={(str(Decimal(w['negative_detail']['value'])),str(abs(Decimal(w['negative_detail']['value'])))) for w in retained};new=dict(base)
    if len(pairs)==1:new['extracted_value'],new['calculated_value']=next(iter(pairs))
    return new,retained,candidates

def main():
    freeze={'strategy':'original_ownership_label_scoped_negative_subtotal_corroboration_v1','code_sha256':n.sha(__file__),'base_strategy_sha256':n.sha(s.__file__),'parser_sha256':n.sha(n.audit.__file__),'frozen_before_own_gold_evaluation':True,'training_used':False,'post_counterexample_research_revision':True,'counterexample_was_previously_known_not_blind':True,'prior_practice_gold_already_scored_for_bare_arm':True,'new_blind_generalization_claim':False,'original_bare_failure_retained':'../subtotal_corroboration/development.changes.jsonl#DEV3_000110','selection_is_research_hypothesis':True,'qualification':'exact supplied SRT OwnershipAxis QName and original linked Ownership [Axis] label; never Case ID','known_gold_context_guard':False,'promotion_enabled':False}
    (OUT/'STRATEGY_FREEZE.json').write_text(json.dumps(freeze,indent=2)+'\n',encoding='utf8')
    cohort={r['id'] for r in n.csv.DictReader((n.WORK/'runs/source_repairs/all196_audit.csv').open(encoding='utf-8-sig')) if r['DQC']=='0015' and 'necessarily_correct' not in r['source_contract_state']};exc=n.audit.exclusions();n.audit.xml=s.closed_xml;summary={}
    for split in ['development','practice']:
        inp=n.ROOT/'data/raw/task3'/('finmr/public_dev_inputs.jsonl' if split=='practice' else 'development_inputs.jsonl');sources={r['id']:r for r in n.rows(inp)}
        baseline=n.rows(n.WORK/'DELIVERY/task3_C8_v34_provisional_97_50_R_6b5e45c5/development.predictions.jsonl') if split=='development' else n.rows(n.ROOT/'reports/round6_iterations/official_semantics_candidate_v34/practice/unanimity.predictions.jsonl')
        preds=[];changes=[];diagnostics=[]
        for base in baseline:
            cid=base['id'];new=dict(base)
            if split=='practice' or cid in cohort or cid in {'DEV3_000058','DEV3_000110','DEV3_000215','DEV3_000666'}:
                parsed=n.audit.source_parse(sources[cid]['query']);new,retained,bare=select(parsed,base,exc);changed=any(Decimal(new[k])!=Decimal(base[k]) for k in ['extracted_value','calculated_value']);counterexample=split=='development' and cid not in cohort
                record={'id':cid,'old':base,'new':new,'source_witnesses':retained,'bare_witnesses_rejected_by_original_axis_scope':[w for w in bare if not ownership_label_proof(parsed,w['axis_removed'])],'numeric_change':changed,'known_correct_counterexample':counterexample,'query_sha256':hashlib.sha256(sources[cid]['query'].encode()).hexdigest(),'correct_answer_proven':False,'source_scope_makes_hidden_gold_unique':False}
                diagnostics.append(record)
                if changed:changes.append(record)
                if counterexample:new=dict(base)
            preds.append(new)
        n.write(OUT/f'{split}.predictions.jsonl',preds);n.write(OUT/f'{split}.changes.jsonl',changes);n.write(OUT/f'{split}.source_evidence.jsonl',diagnostics)
        summary[split]={'rows':len(preds),'analyzed':len(diagnostics),'numeric_changes':sum(not r['known_correct_counterexample'] for r in changes),'ids':[r['id'] for r in changes if not r['known_correct_counterexample']],'known_correct_adverse':[r['id'] for r in changes if r['known_correct_counterexample']],'known_correct_checks':{r['id']:{'changed':r['numeric_change'],'bare_witnesses_rejected':len(r['bare_witnesses_rejected_by_original_axis_scope'])} for r in diagnostics if r['known_correct_counterexample']}}
    (OUT/'candidate_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8');print(json.dumps(summary))
if __name__=='__main__':main()
