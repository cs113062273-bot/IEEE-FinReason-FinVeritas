"""Inventory source focus information once, no repeatednative/SATsolve."""
import json,re
from collections import Counter,defaultdict
from common import *
def member_labels(p):
    result={};tree=raw.xml(p['parts']['Label linkbase document'])
    for link in tree.findall('.//{'+raw.LINK+'}labelLink'):
        loc={};labels={}
        for node in link:
            if node.tag=='{'+raw.LINK+'}loc':
                frag=node.get('{'+raw.XLINK+'}href','').split('#')[-1];prefix,sep,name=frag.partition('_')
                if sep and prefix in p['namespaces']:loc[node.get('{'+raw.XLINK+'}label')]='{'+p['namespaces'][prefix]+'}'+name
            elif node.tag=='{'+raw.LINK+'}label':labels[node.get('{'+raw.XLINK+'}label')]={'role':node.get('{'+raw.XLINK+'}role'),'text':''.join(node.itertext()).strip(),'raw_xml':raw.etree.tostring(node,encoding='unicode')}
        for node in link.findall('{'+raw.LINK+'}labelArc'):
            concept=loc.get(node.get('{'+raw.XLINK+'}from'));label=labels.get(node.get('{'+raw.XLINK+'}to'))
            if concept and label:result.setdefault(concept,[]).append({**label,'arc_xml':raw.etree.tostring(node,encoding='unicode')})
    return result
def main():
    states={r['id']:r for r in rows(MODEL/'source_contract.case_status.jsonl')};base={r['id']:r for r in rows(BEST/'development.predictions.jsonl')};exc=raw.exclusions()
    audits={r['id']:r for r in rows(ROOT/'reports/round6_iterations/official_semantics_candidate_v34/development/audit.jsonl')};result=[]
    for row in rows(ROOT/'data/raw/task3/development_inputs.jsonl'):
        if states[row['id']]['R15_plan_state']=='necessarily_correct' and row['id'] not in {'DEV3_000036','DEV3_000193','DEV3_000039','DEV3_000050','DEV3_000058','DEV3_000110','DEV3_000145','DEV3_000148','DEV3_000152','DEV3_000215','DEV3_000666'}:continue
        p=parsed(row);labels=member_labels(p);asked=[f for f in p['facts'] if f['QName']==p['target'] and f['asked_period']]
        q=raw.sections(row['query'])['Instance document'];periods={(f['context']['entity_scheme'],f['context']['entity'],repr(f['context']['period']),repr(f['unit_signature'])) for f in asked if f['context']}
        question=p['question'];extra=re.findall(r'(?:context(?:Ref)?\s*[:=]|member\s+|axis\s+|entity\s+|CIK\s*[:=]|unit\s*[:=])[^\n]*',question,re.I)
        negative=previous.negative_facts(p,exc)
        result.append({'id':row['id'],'state':states[row['id']]['R15_plan_state'],'rule':states[row['id']]['rule'],'target':p['target'],'question':question,'explicit_additional_focus_locators':extra,'asked_entity_period_unit_scope_count':len(periods),'eligible_negative_values':sorted({f['value'] for f in negative}),'eligible_negative_contexts':[{'value':f['value'],'context':f['context_ref'],'dimensions':[{'axis':a,'member':m,'member_labels':labels.get(m,[]) if kind=='explicit' else [],'kind':kind} for a,kind,m,location in f['context']['dimensions']]} for f in negative],'original_eligible_violating_pairs':[[r['reported'],r['value']] for r in audits[row['id']]['proposals'] if r.get('eligible') and r.get('violation')],'baseline':base[row['id']],'query_sha256':sha_text(row['query'])})
    save(OUT/'focus_inventory.jsonl',result)
    groups=defaultdict(list)
    for r in result:
        if r['state']=='necessarily_correct':continue
        if r['id']=='DEV3_000214':key='0117_known_wrong_unbound_focus'
        elif r['rule']=='0015':key='0015_'+('no_eligible_negative' if not r['eligible_negative_values'] else 'single_numeric_source_still_uncertain' if len(r['eligible_negative_values'])==1 else 'competing_negative_values')
        else:key='0117_'+('no_original_eligible_violating_pair' if not r['original_eligible_violating_pairs'] else 'single_original_pair_still_uncertain' if len(set(map(tuple,r['original_eligible_violating_pairs'])))==1 else 'multiple_original_pairs')
        groups[key].append(r['id'])
    (OUT/'root_cause_groups.json').write_text(json.dumps({k:{'count':len(v),'ids':v} for k,v in groups.items()},indent=2)+'\n',encoding='utf-8')
    summary={'rows':len(result),'candidate_rows':sum(r['state']!='necessarily_correct' for r in result),'additional_question_locator_cases':[r['id'] for r in result if r['explicit_additional_focus_locators']],'candidate_rule_counts':dict(Counter(r['rule'] for r in result if r['state']!='necessarily_correct')),'unique_eligible_negative_Q1_still_uncertain':[r['id'] for r in result if r['state']!='necessarily_correct' and r['rule']=='0015' and len(r['eligible_negative_values'])==1],'new_numeric_answers':0,'scope':'question+assertion conditions+source memberlabels; no inferred gold'}
    (OUT/'focus_inventory_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary))
def sha_text(s):return hashlib.sha256(s.encode()).hexdigest()
if __name__=='__main__':main()
