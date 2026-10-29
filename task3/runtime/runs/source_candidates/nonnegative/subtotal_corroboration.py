"""Unproven research focus: negative same-QName detail/subtotal agreement.

Reported, numerically matching detail and subtotal corroborate extraction,
not the question's intended frame or correctness of absolute-value repair.
No hidden labels or source ordering participate in selection.
"""
import copy, hashlib, json
from collections import Counter,defaultdict
from decimal import Decimal
from pathlib import Path
import netting_candidate as n
from lxml import etree

OUT=n.OUT/'subtotal_corroboration';OUT.mkdir(exist_ok=True)
STRICT_XML=n.audit.xml
def closed_xml(body):
    try:return STRICT_XML(body)
    except etree.XMLSyntaxError:
        parser=etree.XMLPullParser(events=('start','end'),resolve_entities=False,no_network=True,recover=False,huge_tree=True)
        root=None;children=[]
        data=body.strip().encode()
        for index in range(0,len(data),4096):
            error=False
            try:parser.feed(data[index:index+4096])
            except etree.XMLSyntaxError:error=True
            for kind,node in parser.read_events():
                if root is None and kind=='start':root=node
                if kind=='end' and node.getparent() is root:children.append(copy.deepcopy(node))
            if error:break
        if root is None:raise
        clone=etree.Element(root.tag,attrib=dict(root.attrib),nsmap=root.nsmap)
        clone.extend(children)
        if not children:raise ValueError('No complete top-level supplied nodes')
        return clone

def witnesses(parsed,exc):
    fs=[f for f in parsed['facts'] if f['QName']==parsed['target'] and f['asked_period'] and f['context'] and f['unit_signature'] and not f['context']['opaque_qualifiers'] and not f['sign'] and not f['scale']]
    out=[]
    for subtotal in fs:
        if Decimal(subtotal['value'])>=0:continue
        axes={d[0] for f in fs for d in f['context']['dimensions'] if d[1]=='explicit'}-set(n.dims(subtotal))
        for axis in axes:
            children=[f for f in fs if axis in n.dims(f) and n.aspects(f,axis)==n.aspects(subtotal,axis)]
            grouped=defaultdict(list)
            for child in children:grouped[n.dims(child)[axis]].append(child)
            if not grouped:continue
            terms=[];conflict=False
            for member,group in grouped.items():
                if len({Decimal(f['value']) for f in group})!=1:conflict=True;break
                terms.append(sorted(group,key=lambda f:json.dumps(f,sort_keys=True))[0])
            if conflict:continue
            negative=[f for f in terms if Decimal(f['value'])<0]
            if len(negative)!=1 or any(Decimal(f['value'])!=0 for f in terms if f is not negative[0]):continue
            leaf=negative[0]
            if Decimal(leaf['value'])!=Decimal(subtotal['value']):continue
            leafproof=n.audit.eligibility_0015(leaf,parsed['parts'],exc);totalproof=n.audit.eligibility_0015(subtotal,parsed['parts'],exc)
            if leafproof['subset_eligible'] is not True or totalproof['subset_eligible'] is not True:continue
            out.append({'axis_removed':axis,'negative_detail':leaf,'reported_negative_subtotal':subtotal,'observed_siblings':terms,'same_QName_entity_period_unit_other_dimensions':True,'raw_numeric_equality':True,'distinct_raw_source_nodes':leaf['id']!=subtotal['id'],'leaf_eligibility':leafproof,'subtotal_eligibility':totalproof,'DRS_aggregation_applicability_proved':False,'unreported_members_set_to_zero':False,'question_scope_uniquely_proved':False,'absolute_value_magnitude_proved':False,'source_supported_hypothesis':'prefer a violating raw value independently repeated in detail and subtotal over an unrelated competing value'})
    return out

def select(parsed,base,exc):
    ws=witnesses(parsed,exc);pairs={(str(Decimal(w['negative_detail']['value'])),str(abs(Decimal(w['negative_detail']['value'])))) for w in ws};new=dict(base)
    if len(pairs)==1:new['extracted_value'],new['calculated_value']=next(iter(pairs))
    return new,ws

def main():
    manifest={'strategy':'reported_negative_detail_subtotal_corroboration_v1','frozen_before_practice_gold_scoring':True,'code_sha256':n.sha(__file__),'dependency_sha256':n.sha(n.__file__),'production_promotion_enabled':False,'selection_is_hypothesis_not_gold':True,'membership_and_aggregation_not_certified':True,'new_information_vs_M072':'requires independent raw detail and subtotal numeric equality, rather than member subset or dimensionality rank','new_information_vs_M071':'negative raw subtotal, not a proven positive corrected subtotal; only focus is proposed','closed_prefix':'only completely ended raw top-level nodes retained, never synthetic facts or contexts'}
    (OUT/'STRATEGY_FREEZE.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    cohort={r['id'] for r in n.csv.DictReader((n.WORK/'runs/source_repairs/all196_audit.csv').open(encoding='utf-8-sig')) if r['DQC']=='0015' and 'necessarily_correct' not in r['source_contract_state']};assert len(cohort)==59
    exc=n.audit.exclusions();n.audit.xml=closed_xml;summary={}
    for split in ['development','practice']:
        inp=n.ROOT/'data/raw/task3'/('finmr/public_dev_inputs.jsonl' if split=='practice' else 'development_inputs.jsonl')
        sources={r['id']:r for r in n.rows(inp)}
        baseline=n.rows(n.WORK/'DELIVERY/task3_C8_v34_provisional_97_50_R_6b5e45c5/development.predictions.jsonl') if split=='development' else n.rows(n.ROOT/'reports/round6_iterations/official_semantics_candidate_v34/practice/unanimity.predictions.jsonl')
        predictions=[];changes=[];audits=[]
        for base in baseline:
            cid=base['id'];new=dict(base)
            eligible=split=='practice' or cid in cohort or cid in {'DEV3_000058','DEV3_000110','DEV3_000215','DEV3_000666'}
            if eligible:
                error=None;ws=[];prefix=False
                try:
                    parts=n.audit.sections(sources[cid]['query'])
                    try:STRICT_XML(parts['Instance document'])
                    except etree.XMLSyntaxError:prefix=True
                    parsed=n.audit.source_parse(sources[cid]['query']);new,ws=select(parsed,base,exc)
                except (etree.XMLSyntaxError,KeyError,AssertionError,AttributeError,ValueError) as e:error=str(e)
                changed=any(Decimal(new[k])!=Decimal(base[k]) for k in ['extracted_value','calculated_value'])
                counterexample=split=='development' and cid not in cohort
                record={'id':cid,'old':base,'new':new,'witnesses':ws,'unavailable_reason':error,'used_complete_nodes_from_truncated_source':prefix,'numeric_change':changed,'known_correct_counterexample':counterexample,'query_sha256':hashlib.sha256(sources[cid]['query'].encode()).hexdigest(),'correct_answer_proven':False}
                audits.append(record)
                if changed:changes.append(record)
                if counterexample:new=dict(base)
            predictions.append(new)
        n.write(OUT/f'{split}.predictions.jsonl',predictions);n.write(OUT/f'{split}.changes.jsonl',changes);n.write(OUT/f'{split}.source_evidence.jsonl',audits)
        summary[split]={'rows':len(predictions),'analyzed':len(audits),'source_errors':sum(bool(r['unavailable_reason']) for r in audits),'complete_prefix_cases':sum(r['used_complete_nodes_from_truncated_source'] for r in audits),'numeric_changes':sum(not r['known_correct_counterexample'] for r in changes),'ids':[r['id'] for r in changes if not r['known_correct_counterexample']],'known_correct_adverse':[r['id'] for r in changes if r['known_correct_counterexample']]}
    (OUT/'candidate_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8');print(json.dumps(summary))
if __name__=='__main__':main()
