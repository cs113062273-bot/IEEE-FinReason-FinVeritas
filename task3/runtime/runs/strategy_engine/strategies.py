"""Source algorithms; question focus is a research hypothesis, never gold."""
from decimal import Decimal
from collections import defaultdict
from common import *

def clean(f):
    return f['context'] and f['unit_signature'] and not f['sign'] and not f['scale'] and not f['context']['opaque_qualifiers'] and all(d[1]=='explicit' for d in f['context']['dimensions'])
def ds(f):return {d[0]:d[2] for d in f['context']['dimensions']}
def frame(f,axis=None):
    c=f['context'];return repr((c['entity_scheme'],c['entity'],c['period'],f['unit_signature'],[d for d in c['dimensions'] if d[0]!=axis]))
def unique(fs):
    groups=defaultdict(list)
    for f in fs:groups[(f['QName'],frame(f))].append(f)
    if any(len({Decimal(f['value']) for f in g})!=1 for g in groups.values()):return None
    return [g[0] for g in groups.values()]
def target_facts(p):return unique([f for f in p['facts'] if f['QName']==p['target'] and f['asked_period'] and clean(f)]) or []
def qlike(p,name):return p['target'].split('}')[0]+'}'+name
def source_path(p,axis,member):
    try:graph=previous.dimensional.definition_graph(p)
    except (raw.etree.XMLSyntaxError, KeyError):return None
    for role,node in list(graph):
        if node!=axis:continue
        path=previous.dimensional.member_path(graph,role,axis,member)
        if path:return {'role':role,'axis':axis,'member':member,'arcs':path}
    return None
def presentation_names(p):
    tree=raw.xml(p['parts']['Presentation linkbase document']);names=set()
    for n in tree.findall('.//{'+LINK+'}loc'):
        prefix,sep,name=n.get('{'+XLINK+'}href','').split('#')[-1].partition('_')
        if sep and prefix in p['namespaces']:names.add('{'+p['namespaces'][prefix]+'}'+name)
    return names

def exception_contaminated_allowance(p,base,programs,exc):
    if local(p['target'])!='FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest':return None,{'status':'outside financing allowance domain'}
    fs=target_facts(p);ws=[]
    for total in fs:
        if Decimal(total['value'])>=0 or Decimal(total['value'])!=Decimal(base['extracted_value']):continue
        for axis in {a for f in fs for a in ds(f)}-set(ds(total)):
            if local(axis)!='FinancingReceivableRecordedInvestmentByClassOfFinancingReceivableAxis':continue
            leaves=[f for f in fs if axis in ds(f) and set(ds(f))==set(ds(total))|{axis} and frame(f,axis)==frame(total,axis)]
            if len(leaves)<3 or len({ds(f)[axis] for f in leaves})!=len(leaves):continue
            if sum(Decimal(f['value']) for f in leaves)!=Decimal(total['value']):continue
            eligible=[];exempt=[]
            for f in leaves:
                if Decimal(f['value'])>=0:continue
                qualification=raw.eligibility_0015(f,p['parts'],exc)
                if qualification['subset_eligible'] is True:eligible.append({'fact':f,'qualification':qualification})
                elif qualification['subset_eligible'] is False and qualification.get('reason')=='original exact member/substring exemption':exempt.append({'fact':f,'qualification':qualification})
            if len(eligible)!=1 or len(exempt)!=1:continue
            paths=[source_path(p,axis,ds(f)[axis]) for f in leaves]
            labels=member_labels(p)
            linked_labels={ds(f)[axis]:labels.get(ds(f)[axis],[]) for f in leaves}
            if not all(linked_labels.values()):continue
            f=eligible[0]['fact']
            ws.append({'focus':f,'reported':f['value'],'calculated':str(-Decimal(f['value'])),'aggregate':total,'class_facts':leaves,'unique_eligible_negative_class':eligible,'original_rule_exempt_negative_class':exempt,'raw_DRS_paths':paths,'linked_class_labels':linked_labels,'complete_DRS_class_membership_proved':all(paths),'hypothesis':'a signed negative class rollup containing an exempt unallocated member does not uniquely bind the nonnegative assertion; prefer its sole non-exempt negative financing class','difference_from_previous_unfunded_label_hypothesis':'requires actual full signed class rollup and original DQC member exemption; no unfunded label preference','question_focus_proved':False,'Q2_conditional_absolute_sign_repair':True})
    return parent.unique_proposal(base,ws,'X15_exception_contaminated_allowance')

def loss_component_partition(p,base,programs,exc):
    from task3.exact_arithmetic import sum_values as exact_sum
    if local(p['target'])!='UnrealizedLossOnSecurities':return None,{'status':'outside legacy securities loss domain'}
    if 'DeprecatedDate: 2023' not in p['parts'].get('US GAAP Taxonomy',''):return None,{'status':'no supplied legacy loss concept metadata'}
    fs=target_facts(p);ws=[];names=presentation_names(p)
    siblings={qlike(p,n) for n in ['TradingSecuritiesUnrealizedHoldingLoss','DebtSecuritiesTradingUnrealizedLoss']}
    if not siblings<=names:return None,{'status':'missing original separate loss line items'}
    for total in fs:
        if ds(total) or Decimal(total['value'])>=0 or Decimal(total['value'])!=Decimal(base['extracted_value']):continue
        leaves=[f for f in fs if len(ds(f))==1 and frame(f,next(iter(ds(f))))==frame(total)]
        negative=[f for f in leaves if Decimal(f['value'])<0 and raw.eligibility_0015(f,p['parts'],exc)['subset_eligible'] is True]
        if len(negative)!=1:continue
        focus=negative[0];axis=next(iter(ds(focus)))
        if local(axis)!='InvestmentTypeAxis':continue
        typed=unique([f for f in p['facts'] if f['QName'] in siblings and f['asked_period'] and clean(f) and len(ds(f))==1 and axis in ds(f) and frame(f,axis)==frame(total)])
        if not typed or {f['QName'] for f in typed}!=siblings or any(Decimal(f['value'])<0 for f in typed):continue
        all_components=typed+leaves
        if len({ds(f)[axis] for f in all_components})!=len(all_components):continue
        # The legacy total uses a loss-magnitude convention, not signed raw sum.
        # This is explicit evidence about that total, not an assumption that
        # the partition establishes a hidden question label.
        if exact_sum(Decimal(f['value']).copy_abs() for f in all_components)!=Decimal(total['value']).copy_abs():continue
        paths=[source_path(p,axis,ds(f)[axis]) for f in all_components]
        if not all(paths):continue
        members={ds(f)[axis] for f in all_components}
        if any(any(a['child'] in members-{path['member']} for a in path['arcs']) for path in paths):continue
        gains=[f for f in p['facts'] if f['QName']==qlike(p,'UnrealizedGainOnSecurities') and f['asked_period'] and clean(f) and frame(f)==frame(focus) and Decimal(f['value'])>0]
        if len(gains)!=1:continue
        ws.append({'focus':focus,'reported':focus['value'],'calculated':str(Decimal(focus['value']).copy_negate()),'legacy_total':total,'separate_reported_loss_components':typed,'legacy_class_components':leaves,'same_context_separately_reported_gain':gains[0],'original_DRS_paths':paths,'loss_partition_identity':'abs(legacy total) = sum(abs(source loss facts)) on disjoint InvestmentType members','hypothesis':'the legacy total is an independently reconciled presentation magnitude; choose its sole eligible negative class source as the sign assertion focus','sign_magnitude_partition_premise':True,'question_focus_proved':False,'Q2_conditional_absolute_sign_repair':True})
    return parent.unique_proposal(base,ws,'L15_legacy_loss_partition')

def sole_preferred_equity_component(p,base,programs,exc):
    if local(p['target'])!='PreferredStockValue' or Decimal(base['extracted_value'])!=0:return None,{'status':'outside zero preferred-stock total domain'}
    fs=target_facts(p);ws=[]
    for total in fs:
        if ds(total) or Decimal(total['value'])!=0:continue
        classes=[f for f in fs if len(ds(f))==1 and local(next(iter(ds(f))))=='StatementClassOfStockAxis' and frame(f,next(iter(ds(f))))==frame(total)]
        positives=[f for f in classes if Decimal(f['value'])>0];zeros=[f for f in classes if Decimal(f['value'])==0]
        if len(positives)!=1 or len(zeros)<2 or len(classes)!=len(positives)+len(zeros):continue
        focus=positives[0];axis=next(iter(ds(focus)));paths=[source_path(p,axis,ds(f)[axis]) for f in classes]
        if not all(paths):continue
        equity_names={qlike(p,'StockholdersEquity'),qlike(p,'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest')}
        equities=unique([f for f in p['facts'] if f['QName'] in equity_names and f['asked_period'] and clean(f)]) or []
        for equity in equities:
            if ds(equity) or frame(equity)!=frame(total):continue
            components=[f for f in equities if f['QName']==equity['QName'] and len(ds(f))==1 and frame(f,next(iter(ds(f))))==frame(equity) and local(next(iter(ds(f)))) in {'StatementEquityComponentsAxis','PartnerCapitalComponentsAxis'}]
            if len(components)<4:continue
            component_members={local(next(iter(ds(f).values()))) for f in components}
            if not {'CommonStockMember','AdditionalPaidInCapitalMember','RetainedEarningsMember'}<=component_members:continue
            if len({next(iter(ds(f).values())) for f in components})!=len(components):continue
            if sum(Decimal(f['value']) for f in components)!=Decimal(equity['value']):continue
            preferred=[f for f in components if 'Preferred' in local(next(iter(ds(f).values()))) and Decimal(f['value'])==Decimal(focus['value'])]
            if len(preferred)!=1:continue
            paired=preferred[0];preferred_axis=next(iter(ds(paired)));epath=source_path(p,preferred_axis,ds(paired)[preferred_axis])
            # Reduced definition/presentation commonly omits the independent
            # equity breakdown. Do not fabricate its relationship.
            stockmember=local(ds(focus)[axis]);equitymember=local(ds(paired)[preferred_axis])
            import re
            series=lambda name:re.sub(r'Preferred(?:Stock|Stocks|Shares|StockShares)?Member$','',name)
            if series(stockmember)!=series(equitymember):continue
            labels=member_labels(p);focus_labels=labels.get(ds(focus)[axis],[]);equity_labels=labels.get(ds(paired)[preferred_axis],[])
            if not focus_labels or not equity_labels:continue
            ws.append({'focus':focus,'reported':focus['value'],'calculated':focus['value'],'zero_aggregate':total,'reported_stock_classes':classes,'stock_class_paths':paths,'independent_equity_total':equity,'independent_equity_components':components,'matching_preferred_equity_component':paired,'preferred_equity_DRS_path':epath,'cross_axis_series_labels':{'stock':focus_labels,'equity':equity_labels},'equity_DRS_membership_proved':epath is not None,'same_series_identifier':series(stockmember),'hypothesis':'where all other reported preferred classes are literal zero and one class is independently embedded in a complete equity bridge, bind the question to that sole economically represented preferred class','zero_is_a_real_fact_not_assumed_sentinel':True,'question_focus_proved':False,'DQC00117_total_vs_class_binding_unproved':True})
    return parent.unique_proposal(base,ws,'P117_sole_preferred_equity_component')

STRATEGIES={'X15_allowance_exception':exception_contaminated_allowance,'L15_loss_partition':loss_component_partition,'P117_preferred_component':sole_preferred_equity_component}
DOMAINS={'X15_allowance_exception':'FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest','L15_loss_partition':'UnrealizedLossOnSecurities','P117_preferred_component':'PreferredStockValue'}
