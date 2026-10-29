"""Independent financial bridge hypotheses against frozen665 incumbent.

R15: exact reserve roll-forward supports a fully settled negative-payment
component. No recent-plan rank, negative onset or hidden answer filtering.
A117: cost-of-sales OCI expense bridge with pretax = net + tax anchors;
Disclosure applicability is NOT certified; research source binding only.
T15: additive monetary-flow same-aspect disjoint-period decomposition.
"""
import hashlib,json,sys
from collections import Counter,defaultdict
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path

WORK=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
ROOT=WORK/'core/source'
BEST=WORK/'DELIVERY/task3_N117_best_provisional_97_79_20261015'
sys.path.insert(0,str(WORK/'runs/source_strategies'));import source_experiments as previous
raw=previous.raw
def rows(p):return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def same(a,b):return all(Decimal(a[k])==Decimal(b[k]) for k in ['extracted_value','calculated_value'])
def save(p,records):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
def expanded_like(target,local):return target.rsplit('}',1)[0]+'}'+local
def aspect(f):
    c=f['context'];return c['entity_scheme'],c['entity'],tuple(c['dimensions']),f['unit_signature']
def bind(facts,qname,reference,period):
    choices=[f for f in facts if f['QName']==qname and f['context'] and aspect(f)==aspect(reference) and f['context']['period']==period and not f['sign'] and not f['scale'] and not f['context']['opaque_qualifiers']]
    if not choices or len({Decimal(f['value']) for f in choices})!=1:return None
    return choices[0]
def unique_proposal(prior,witnesses,key):
    pairs={(w['reported'],w['calculated']) for w in witnesses}
    if len(pairs)!=1:return None,{'status':'no unique source-supported financial bridge','witnesses':witnesses}
    x,y=next(iter(pairs));return {**prior,'extracted_value':x,'calculated_value':y},{'status':key,'witnesses':witnesses,'question_to_scope_unique':False,'hidden_gold_correctness_proven':False}

def reserve_equations(parsed,exc):
    from task3.exact_arithmetic import add as exact_add
    target=parsed['target']
    if target.split('}')[-1]!='PaymentsForRestructuring':return []
    facts=parsed['facts'];result=[]
    for focus in previous.negative_facts(parsed,exc):
        start,end,instant=focus['context']['period']
        if not start or not end or instant:continue
        opening_date=(date.fromisoformat(start)-timedelta(days=1)).isoformat()
        opening=bind(facts,expanded_like(target,'RestructuringReserve'),focus,[None,None,opening_date])
        ending=bind(facts,expanded_like(target,'RestructuringReserve'),focus,[None,None,end])
        charges=bind(facts,expanded_like(target,'RestructuringCharges'),focus,[start,end,None])
        noncash=bind(facts,expanded_like(target,'RestructuringReserveSettledWithoutCash2'),focus,[start,end,None])
        if not all([opening,ending,charges,noncash]):continue
        # Restrict to zero otherflows to avoid inventing a noncash sign rule.
        if Decimal(charges['value'])!=0 or Decimal(noncash['value'])!=0:continue
        cash=exact_add(Decimal(opening['value']),Decimal(ending['value']).copy_negate())
        if cash<=0 or Decimal(focus['value']).copy_negate()!=cash:continue
        result.append({'focus':focus,'opening':opening,'ending':ending,'charges':charges,'noncash':noncash,'reported':focus['value'],'calculated':str(cash),'identity':'positive cash outflow = opening reserve - ending reserve, with original charges=0 and noncash=0','independent_numeric_inputs_do_not_use_abs_focus':True,'source_calculation_arc_available':False,'financial_identity_is_explicit_research_premise':True})
    return result

def reserve_component(parsed,prior,programs,exc):
    candidates=[w for w in reserve_equations(parsed,exc) if Decimal(w['ending']['value'])==0 and Decimal(w['opening']['value'])>0]
    for w in candidates:w['focus_hypothesis']='Select the component whose reserve is completely settled by reported cash, rather than another still-open restructuring balance.'
    return unique_proposal(prior,candidates,'R15_completely_settled_component')

def reserve_closed_plan(parsed,prior,programs,exc):
    from task3.exact_arithmetic import sum_values as exact_sum
    # Separate scope hypothesis, selected by numerical reserve closure rather
    # than the year/name of a restructuring plan (oldC9).
    equations=reserve_equations(parsed,exc);witnesses=[]
    closed=[w for w in equations if Decimal(w['ending']['value'])==0]
    for total in equations:
        totaldims=previous.ownership.n.dims(total['focus'])
        for axis in {d[0] for w in equations for d in w['focus']['context']['dimensions'] if d[1]=='explicit'}-set(totaldims):
            children=[w for w in equations if axis in previous.ownership.n.dims(w['focus']) and previous.ownership.n.aspects(w['focus'],axis)==previous.ownership.n.aspects(total['focus'],axis)]
            if len(children)<2 or not any(w in closed for w in children):continue
            if len({previous.ownership.n.dims(w['focus'])[axis] for w in children})!=len(children):continue
            if exact_sum(Decimal(w['reported']) for w in children)!=Decimal(total['reported']):continue
            graph=previous.dimensional.definition_graph(parsed);paths=[]
            for w in children:
                member=previous.ownership.n.dims(w['focus'])[axis]
                matched=[(role,previous.dimensional.member_path(graph,role,axis,member)) for role,node in list(graph) if node==axis]
                matched=[(r,p) for r,p in matched if p]
                if not matched:break
                paths.append({'member':member,'role':matched[0][0],'DRS_path':matched[0][1]})
            if len(paths)!=len(children):continue
            witnesses.append({**total,'children_rollforwards':children,'original_child_member_paths':paths,'focus_hypothesis':'Select the fully reconciled plan total containing a cash-settled component, rather than the component itself. Not recent-plan-year ranking.'})
    return unique_proposal(prior,witnesses,'R15_reconciled_plan_with_closed_component')

def income_tax_bridge(parsed,prior,programs,exc):
    target=parsed['target'];local=target.split('}')[-1]
    if local not in {'CostOfGoodsAndServicesSold','InterestExpenseNonoperating'}:return None,{'status':'not a supported expense bridge concept'}
    facts=parsed['facts'];witnesses=[]
    for focus in facts:
        if focus['QName']!=target or not focus['asked_period'] or not focus['context'] or Decimal(focus['value'])<=0:continue
        if focus['sign'] or focus['scale'] or focus['context']['opaque_qualifiers']:continue
        dims=focus['context']['dimensions']
        if not any(a.split('}')[-1]=='ReclassificationOutOfAccumulatedOtherComprehensiveIncomeAxis' and k=='explicit' for a,k,m,l in dims):continue
        product=[a for a,k,m,l in dims if k=='explicit' and a.split('}')[-1]=='ProductOrServiceAxis']
        if len(product)!=1:continue
        reference={**focus,'context':{**focus['context'],'dimensions':[d for d in dims if d[0]!=product[0]]}}
        period=focus['context']['period']
        before=bind(facts,expanded_like(target,'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'),reference,period)
        net=bind(facts,expanded_like(target,'NetIncomeLoss'),reference,period)
        tax=bind(facts,expanded_like(target,'IncomeTaxExpenseBenefit'),reference,period)
        if not all([before,net,tax]):continue
        predicted=-(Decimal(net['value'])+Decimal(tax['value']))
        if Decimal(before['value'])!=Decimal(net['value'])+Decimal(tax['value']) or predicted!=Decimal(focus['value']):continue
        if Decimal(before['value'])>=0:continue
        # Reject any observed other nonzero expense in this projected frame.
        expense_names={'CostOfGoodsAndServicesSold','InterestExpenseNonoperating','SellingGeneralAndAdministrativeExpense','OtherCostAndExpenseOperating','OperatingExpenses','IncomeTaxExpenseBenefit'}
        rivals=[f for f in facts if f['context'] and f['asked_period'] and f['QName']!=target and f['QName'].split('}')[-1] in expense_names-{'IncomeTaxExpenseBenefit'} and (aspect(f)==aspect(reference) or aspect(f)==aspect(focus)) and Decimal(f['value'])!=0]
        if rivals:continue
        # Source membership of the erased Product/Service axis is checked;
        # this does not authorize broadening original DQC Statement scope.
        graph=previous.dimensional.definition_graph(parsed);member=previous.ownership.n.dims(focus)[product[0]]
        paths=[(role,previous.dimensional.member_path(graph,role,product[0],member)) for role,node in list(graph) if node==product[0]]
        paths=[(r,p) for r,p in paths if p]
        if not paths:continue
        witnesses.append({'focus':focus,'pretax':before,'net':net,'tax':tax,'projection_axis':product[0],'original_member_DRS_path':paths[0][1],'role':paths[0][0],'reported':focus['value'],'calculated':str(predicted),'identity':'pretax = net income + tax; expense-only OCI channel hypothesizes expense = -pretax','independent_numeric_Q2_anchors':[net,tax],'other_reported_expenses':rivals,'missing_expenses_assumed_zero':False,'complete_expense_channel_certified':False,'original_DQC0117_Statement_applicability_proved':False,'focus_hypothesis':'OCI expense channel independently agrees with pretax/net/tax bridge; question scope remains uncertain.'})
    return unique_proposal(prior,witnesses,'A117_OCI_expense_income_tax_bridge')

def temporal_flow(parsed,prior,programs,exc):
    # Additivity is a research premise only for explicit monetary flow names.
    local=parsed['target'].split('}')[-1]
    if not local.startswith(('Payments','Costs','Expense','Revenue','RestructuringCharges')):return None,{'status':'not supported additive monetary flow'}
    witnesses=[]
    for focus in previous.negative_facts(parsed,exc):
        start,end,instant=focus['context']['period']
        if not start or not end or instant or focus['unit_signature'][1]:continue
        facts=[f for f in parsed['facts'] if f['QName']==parsed['target'] and f['context'] and aspect(f)==aspect(focus) and f['context']['period'][2] is None and not f['sign'] and not f['scale']]
        pairs=set()
        for a in facts:
            aa,ab,_=a['context']['period']
            if aa!=start or not ab or ab>=end:continue
            nextdate=(date.fromisoformat(ab)+timedelta(days=1)).isoformat()
            for b in facts:
                if b['context']['period']!=[nextdate,end,None]:continue
                total=Decimal(a['value'])+Decimal(b['value'])
                if total<=0:continue
                pairs.add((str(total),a['id'],b['id']))
                witnesses.append({'focus':focus,'first_period':a,'second_period':b,'reported':focus['value'],'calculated':str(total),'financial_flow_additivity_premise':True,'original_calculation_arc_proved':False})
    return unique_proposal(prior,witnesses,'T15_disjoint_duration_flow_bridge')

def equity_identity(parsed,prior,programs,exc):
    target=parsed['target'];local=target.split('}')[-1]
    if local not in {'StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'}:return None,{'status':'not a supported equity identity target'}
    witnesses=[]
    for focus in parsed['facts']:
        if focus['QName']!=target or not focus['asked_period'] or not focus['context']:continue
        if focus['sign'] or focus['scale'] or focus['context']['opaque_qualifiers']:continue
        period=focus['context']['period']
        assets=bind(parsed['facts'],expanded_like(target,'Assets'),focus,period)
        liabilities=bind(parsed['facts'],expanded_like(target,'Liabilities'),focus,period)
        if not assets or not liabilities:continue
        nc=[]
        if local=='StockholdersEquity':
            nc=[f for n in ['MinorityInterest','MinorityInterestInConsolidatedSubsidiaries'] if (f:=bind(parsed['facts'],expanded_like(target,n),focus,period))]
            if not nc or len({Decimal(f['value']) for f in nc})!=1:continue
        expected=Decimal(assets['value'])-Decimal(liabilities['value'])-(Decimal(nc[0]['value']) if nc else 0)
        if expected==Decimal(focus['value']):continue
        witnesses.append({'focus':focus,'assets':assets,'liabilities':liabilities,'noncontrolling_interest':nc,'reported':focus['value'],'calculated':str(expected),'identity':'equity = assets - liabilities; excluding noncontrolling interest requires an actual source NCI fact, never implicit0','missing_anchors_set_to_zero':False,'original_DQC_member_sum_not_used_for_number':True,'standard_accounting_identity_premise':True})
    return unique_proposal(prior,witnesses,'E117_complete_equity_identity')

def cash_flow_bridge(parsed,prior,programs,exc):
    target=parsed['target']
    if target.split('}')[-1]!='CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents':return None,{'status':'not supported exact cash+restricted-cash target'}
    witnesses=[];changeconcept=expanded_like(target,'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect')
    for focus in parsed['facts']:
        if focus['QName']!=target or not focus['asked_period'] or not focus['context']:continue
        end=focus['context']['period'][2]
        if not end or focus['sign'] or focus['scale'] or focus['context']['opaque_qualifiers']:continue
        changes=[f for f in parsed['facts'] if f['QName']==changeconcept and f['context'] and aspect(f)==aspect(focus) and f['context']['period'][1]==end and f['context']['period'][0] and not f['sign'] and not f['scale']]
        for change in changes:
            opening_date=(date.fromisoformat(change['context']['period'][0])-timedelta(days=1)).isoformat()
            opening=bind(parsed['facts'],target,focus,[None,None,opening_date])
            if not opening:continue
            expected=Decimal(opening['value'])+Decimal(change['value'])
            if expected==Decimal(focus['value']):continue
            witnesses.append({'focus':focus,'opening':opening,'reported_net_change_including_exchange_effect':change,'reported':focus['value'],'calculated':str(expected),'identity':'same-scope closing cash+restricted cash = opening + net change INCLUDING exchange effects','financial_concept_identity_premise':True,'missing_anchors_set_to_zero':False,'member_sum_not_used_for_number':True})
    return unique_proposal(prior,witnesses,'K117_cash_temporal_bridge')

STRATEGIES={'R15_component':reserve_component,'R15_plan':reserve_closed_plan,'A117_OCI_bridge':income_tax_bridge,'T15_duration_bridge':temporal_flow,'E117_equity_bridge':equity_identity,'K117_cash_bridge':cash_flow_bridge}
def main():
    frozen={'script_sha256':sha(Path(__file__)),'baseline_seals_sha256':sha(BEST/'SHA256.json'),'baseline_correct':665,'frozen_before_own_Practice_scoring':True,'historical_feedback_not_used_to_choose_numbers':True,'strategies':list(STRATEGIES),'dependency_sha256':{'previous_source_experiments':sha(Path(previous.__file__)),'independent_parser':sha(Path(raw.__file__))},'promotion':False}
    (OUT/'freeze.json').write_text(json.dumps(frozen,indent=2)+'\n',encoding='utf-8')
    def guard(event,args):
        if event=='socket.connect':raise PermissionError('offline inference')
        if event=='open' and isinstance(args[0],(str,Path)) and ('gold' in Path(args[0]).name.lower() or Path(args[0]).name=='public_dev.jsonl'):raise PermissionError('no labels during inference')
    sys.addaudithook(guard)
    assert all(sha(BEST/n)==s for n,s in read(BEST/'SHA256.json').items())
    cohort=set(read(WORK/'runs/n117_s15_feedback_20261015/source_contract.summary.json')['remaining15_error_universe'])
    counters={'DEV3_000058','DEV3_000110','DEV3_000215','DEV3_000666','DEV3_000193'}
    raw.xml=previous.ownership.s.closed_xml;exc=raw.exclusions();summary={n:{} for n in STRATEGIES}
    for split in ['development','practice']:
        sourcepath=ROOT/'data/raw/task3'/('development_inputs.jsonl' if split=='development' else 'finmr/public_dev_inputs.jsonl')
        baselinepath=BEST/'development.predictions.jsonl' if split=='development' else ROOT/'reports/round6_iterations/official_semantics_candidate_v34/practice/unanimity.predictions.jsonl'
        baseline=rows(baselinepath);sources={r['id']:r for r in rows(sourcepath)}
        predictions={n:[] for n in STRATEGIES};changes={n:[] for n in STRATEGIES};decisions={n:[] for n in STRATEGIES}
        for prior in baseline:
            cid=prior['id'];active=split=='practice' or cid in cohort|counters
            if active:parsed=raw.source_parse(sources[cid]['query'])
            for name,selector in STRATEGIES.items():
                new=None;proof={'status':'unchanged outside111cohort'}
                if active:
                    new,proof=selector(parsed,prior,[],exc)
                    record={'id':cid,'old':prior,'new':new or prior,'evidence':proof,'query_sha256':hashlib.sha256(sources[cid]['query'].encode()).hexdigest(),'historical_confirmed_correct':cid in counters,'correct_answer_proven':False}
                    decisions[name].append(record)
                    if new and not same(new,prior):changes[name].append(record)
                predictions[name].append(new or prior)
        for name in STRATEGIES:
            target=OUT/name
            for suffix,rs in [('predictions',predictions[name]),('changes',changes[name]),('decisions',decisions[name])]:save(target/f'{split}.{suffix}.jsonl',rs)
            valid=previous.validate_submission_file(target/f'{split}.predictions.jsonl',sourcepath,reference_kind='inputs');assert valid.ok
            (target/f'{split}.validation.json').write_text(json.dumps(valid.to_dict(),indent=2)+'\n',encoding='utf-8')
            summary[name][split]={'rows':len(predictions[name]),'changes':len(changes[name]),'changed_ids':[r['id'] for r in changes[name]],'known_correct_changes':[r['id'] for r in changes[name] if r['historical_confirmed_correct']],'statuses':dict(Counter(r['evidence']['status'] for r in decisions[name]))}
    assert sha(Path(__file__))==frozen['script_sha256']
    (OUT/'experiment_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
