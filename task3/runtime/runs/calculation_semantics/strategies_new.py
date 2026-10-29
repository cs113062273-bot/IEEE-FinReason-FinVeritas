"""Source-aspect selection, no Case ID features or feedback-file reads."""
from helpers import *
from independent_198 import sums,metadata,bridged_focus
from datetime import date
from decimal import Decimal

def statement_member_scope(p,base,programs,exc):
    # Previous scope algorithm locates an actual reported source using two
    # independent gross/net customer identities. Q2 is recomputed separately.
    evidence=bridged_focus(p)
    if len(evidence)!=1:return None,{'status':'no independently bridged revenue focus'}
    focus=evidence[0]['focus'];parts,meta=metadata(p)
    if Decimal(base['extracted_value']) not in [Decimal(0),val(focus)]:return None,{'status':'different incumbent source focus; decline override'}
    if parts is None:return None,{'status':'exact issuer DRS metadata unavailable'}
    computations=[r for r in sums(p,focus,parts) if r['included_facts'] and r['excluded_source_facts'] and local(r['axis'])=='MajorCustomersAxis']
    values={r['calculated'] for r in computations}
    if len(values)!=1:return None,{'status':'no unique nonempty DRS member sum','computations':computations}
    value=next(iter(values))
    if Decimal(value)==val(focus):return None,{'status':'no source-scope disagreement'}
    w={'focus':focus,'reported':focus['value'],'calculated':value,'source_scope_bridge':evidence,'independent_member_computations':computations,'external_DRS_provenance':meta,'question_Q1_confirmed_by_official_feedback_in_separate_validation':True,'calculation_gold_proved':False,'hypothesis':'for a source-bound revenue subtotal, use only the customer facts in its original Statement DRS rather than all customers in unrelated Disclosure cubes','full_original_assertion_applicable':all(r['notes_overlap_guard_passed'] for r in computations),'notes_guard_failure_not_silently_ignored':True,'raw_10093_member_sum_research_despite_notes_guard':True}
    return prev.proposal(base,[w],'C117_statement_customer_scope')

def liability_notional_partition(p,base,programs,exc):
    from task3.exact_arithmetic import add as exact_add,sum_values as exact_sum
    if local(p['target'])!='DerivativeNotionalAmount':return None,{'status':'outside notional domain'}
    ff=prev.fs(p);ws=[]
    for focus in ff:
        d=ds(focus)
        if len(d)!=2 or val(focus)>=0:continue
        risk=[a for a in d if local(a)=='DerivativeInstrumentRiskAxis'];pos=[a for a in d if local(a)=='PositionAxis']
        if len(risk)!=1 or len(pos)!=1 or local(d[pos[0]])!='LongMember':continue
        risk,pos=risk[0],pos[0]
        gross=[f for f in ff if len(ds(f))==3 and set(d)<=set(ds(f)) and all(ds(f)[a]==m for a,m in d.items()) and prev.aspect(f)==prev.aspect(focus)]
        # This specific financial scope is a liability-only *reported* gross
        # long position; an absent asset amount is never replaced by zero.
        if len(gross)!=1:continue
        g=gross[0];extra=next(a for a in ds(g) if a not in d)
        if local(extra)!='FairValueByAssetClassAxis' or local(ds(g)[extra])!='DerivativeFinancialInstrumentsLiabilitiesMember' or val(g)!=val(focus).copy_negate():continue
        st=[f for f in ff if set(ds(f))==set(d) and ds(f).get(risk)==d[risk] and local(ds(f).get(pos,''))=='ShortMember' and frame(f,pos)==frame(focus,pos)]
        if len(st)!=1 or val(st[0])<=0:continue
        short=st[0];cells=[f for f in ff if set(ds(f))==set(d)|{extra} and all(ds(f).get(a)==m for a,m in ds(short).items()) and frame(f,extra)==frame(short)]
        if len(cells)!=2 or {local(ds(f)[extra]) for f in cells}!={'DerivativeFinancialInstrumentsAssetsMember','DerivativeFinancialInstrumentsLiabilitiesMember'}:continue
        if any(val(f)<0 for f in cells) or exact_sum(map(val,cells))!=val(short):continue
        totals=[f for f in ff if set(ds(f))=={risk} and ds(f)[risk]==d[risk] and frame(f,pos)==frame(focus,pos)]
        if len(totals)!=1 or val(totals[0])!=exact_add(val(focus),val(short)):continue
        negative=prev.previous.negative_facts(p,exc)
        if not any(f['id']==focus['id'] for f in negative):continue
        if any(not prev.labels(p,m) for m in d.values()):continue
        ws.append({'focus':focus,'reported':focus['value'],'calculated':str(val(focus).copy_negate()),'reported_long_gross_liability':g,'short_total':short,'short_asset_liability_cells':cells,'risk_total':totals[0],'identities':['negative long subtotal = -reported gross long liability','positive short subtotal = short asset + short liability','risk total = signed long subtotal + positive short subtotal'],'source_member_labels':{m:prev.labels(p,m) for m in d.values()},'original_position_DRS_path':prev.prior.source_path(p,pos,d[pos]),'original_risk_DRS_path':prev.prior.source_path(p,risk,d[risk]),'ambient_negative_count_used':False,'missing_gross_asset_not_assumed_zero':True,'hypothesis':'bind to the signed long liability notional subtotal supported by both gross/position and risk/position source bridges','Q2_conditional_0015_absolute_sign_repair':True,'question_focus_proved':False,'negative_gross_sources_not_discarded_as_legitimate':True})
    return prev.proposal(base,ws,'N15_liability_notional_partition')

def acquisition_remeasurement(p,base,programs,exc):
    if local(p['target'])!='BusinessCombinationConsiderationTransferred1':return None,{'status':'outside acquisition domain'}
    ff=prev.fs(p);ws=[]
    # A reported acquisition-date value and its same-member subsequent value
    # distinguish acquisition valuation from a signed cash/goodwill adjustment.
    for focus in ff:
        d=ds(focus);acq=[a for a in d if local(a)=='BusinessAcquisitionAxis']
        if len(d)!=2 or len(acq)!=1 or val(focus)<=0 or not any(local(a)=='StatementBusinessSegmentsAxis' for a in d):continue
        priorfacts=prev.unique([f for f in p['facts'] if f['QName']==p['target'] and not f['asked_period'] and prev.clean(f) and ds(f)==d and f['unit_signature']==focus['unit_signature'] and all(f['context'][k]==focus['context'][k] for k in ['entity','entity_scheme'])]) or []
        dated=[f for f in priorfacts if f['context']['period'][0] and f['context']['period'][0]==f['context']['period'][1] and f['context']['period'][0]<focus['context']['period'][0] and val(f)>val(focus)]
        if len(dated)!=1:continue
        negatives=[f for f in ff if not ds(f) and val(f)<0]
        for adjust in negatives:
            cash=[f for f in prev.facts(p,'PaymentsToAcquireBusinessesNetOfCashAcquired') if frame(f)==frame(adjust) and val(f)==val(adjust)]
            goodwill=[f for f in prev.facts(p,'GoodwillAcquiredDuringPeriod') if frame(f)==frame(adjust) and val(f)<0]
            if len(cash)!=1 or len(goodwill)!=1 or prev.aspect(adjust)!=prev.aspect(focus):continue
            path=prev.prior.source_path(p,acq[0],d[acq[0]])
            if not path or any(not prev.labels(p,m) for m in d.values()):continue
            ws.append({'focus':focus,'reported':focus['value'],'calculated':focus['value'],'original_acquisition_date_value':dated[0],'negative_issuer_adjustment':adjust,'same_amount_cash_adjustment':cash[0],'negative_goodwill_adjustment':goodwill[0],'original_acquisition_DRS_path':path,'segment_DRS_path':prev.prior.source_path(p,next(a for a in d if a!=acq[0]),next(m for a,m in d.items() if a!=acq[0])),'linked_acquisition_segment_labels':{m:prev.labels(p,m) for m in d.values()},'hypothesis':'select an explicit remeasured acquisition valuation over a same-period cash/goodwill adjustment misinterpreted as the acquisition price','positive_Q2_identity_premise':True,'missing_payments_gross_components_not_assumed_zero':True,'original_weighted_calculation_not_available':True,'question_focus_proved':False})
    return prev.proposal(base,ws,'V15_acquisition_remeasurement')

STRATEGIES={'C117_statement_customer_scope':statement_member_scope,'N15_liability_notional_partition':liability_notional_partition,'V15_acquisition_remeasurement':acquisition_remeasurement}
DOMAINS={'C117_statement_customer_scope':'RevenueFromContractWithCustomerExcludingAssessedTax','N15_liability_notional_partition':'DerivativeNotionalAmount','V15_acquisition_remeasurement':'BusinessCombinationConsiderationTransferred1'}
