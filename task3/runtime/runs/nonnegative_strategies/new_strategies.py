"""Independent source hypotheses; raw witnesses are not hidden focus labels."""
import sys,re
from pathlib import Path
from decimal import Decimal
from collections import defaultdict
W=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(W/'runs/strategy_engine'))
import common as old
import strategies as prior
raw=old.raw;previous=old.previous
local=prior.local;clean=prior.clean;ds=prior.ds;frame=prior.frame;unique=prior.unique
def fs(p):return prior.target_facts(p)
def val(f):return Decimal(f['value'])
def facts(p,n):return unique([f for f in p['facts'] if f['QName']==prior.qlike(p,n) and f['asked_period'] and clean(f)]) or []
def proposal(base,ws,name):return old.parent.unique_proposal(base,ws,name)
def labels(p,member):return old.member_labels(p).get(member,[])
def aspect(f):
    c=f['context'];return c['entity_scheme'],c['entity'],repr(c['period']),repr(f['unit_signature'])

def derivative_residual(p,base,programs,exc):
    if local(p['target'])!='DerivativeNotionalAmount':return None,{'status':'outside notional domain'}
    ff=fs(p);neg=[f for f in ff if val(f)<0 and raw.eligibility_0015(f,p['parts'],exc)['subset_eligible'] is True]
    if len(neg)<3:return None,{'status':'fewer than three competing eligible negatives'}
    if len({aspect(f) for f in neg})!=1:return None,{'status':'negative exposures cross entity/period/unit frames'}
    signed=[]
    for total in ff:
        axes=[a for a in {a for f in ff for a in ds(f)} if local(a)=='FairValueByAssetClassAxis' and a not in ds(total)]
        for axis in axes:
            parts=[f for f in ff if set(ds(f))==set(ds(total))|{axis} and frame(f,axis)==frame(total,axis)]
            if not parts or len(parts)>2:continue
            aset=[f for f in parts if local(ds(f)[axis])=='DerivativeFinancialInstrumentsAssetsMember'];liab=[f for f in parts if local(ds(f)[axis])=='DerivativeFinancialInstrumentsLiabilitiesMember']
            if len(aset)+len(liab)==len(parts) and all(val(f)>=0 for f in parts) and val(total)<0 and val(total)==-sum(map(val,parts)):
                signed.append({'total':total,'gross_facts':parts,'identity':'signed long net notional = negative sum of reported gross sources','absent_gross_cells_not_assumed_zero':True,'complete_gross_partition_not_proved':len(parts)!=2})
    if not signed:return None,{'status':'no explicit signed net/gross partition'}
    reconciled=[]
    for total in ff:
        d=ds(total);risk=[a for a in d if local(a)=='DerivativeInstrumentRiskAxis'];pos=[a for a in d if local(a)=='PositionAxis']
        if len(d)!=2 or len(risk)!=1 or len(pos)!=1 or local(d[risk[0]])!='FutureMember' or local(d[pos[0]])!='ShortMember':continue
        riskaxis=risk[0];posaxis=pos[0]
        cells=[f for f in ff if len(ds(f))==3 and riskaxis in ds(f) and local(ds(f)[riskaxis])=='U.S.TreasuryFuturesMember' and posaxis in ds(f) and any(local(a)=='FairValueByAssetClassAxis' for a in ds(f)) and aspect(f)==aspect(total)]
        if len(cells)!=4 or len({tuple(sorted(ds(f).items())) for f in cells})!=4 or sum(map(val,cells))!=val(total):continue
        if not any(val(f)<0 for f in cells) or not any(val(f)>0 for f in cells):continue
        if not labels(p,ds(cells[0])[riskaxis]) or not labels(p,d[riskaxis]):continue
        reconciled.append({'total':total,'cells':cells,'identity':'futures signed exposure = sum of all four Treasury futures asset/liability and long/short source cells','risk_membership_path':prior.source_path(p,riskaxis,ds(cells[0])[riskaxis]),'child_hierarchy_unproved_when_path_absent':True})
    explained={w['total']['id'] for w in signed}|{f['id'] for w in reconciled for f in w['cells']}
    remaining=[f for f in neg if f['id'] not in explained];ws=[]
    for f in remaining:
        d=ds(f)
        if not reconciled or len(remaining)!=1 or len(d)!=3:continue
        if any(aspect(w['total'])!=aspect(f) for w in signed+reconciled):continue
        if not any(local(a)=='FairValueByAssetClassAxis' and local(m)=='DerivativeFinancialInstrumentsAssetsMember' for a,m in d.items()):continue
        if not any(local(a)=='PositionAxis' and local(m)=='LongMember' for a,m in d.items()):continue
        companions=[g for g in facts(p,'DerivativeAssets') if frame(g)==frame(f) and val(g)>0]
        if len(companions)!=1 or any(not labels(p,m) for m in d.values()):continue
        ws.append({'focus':f,'reported':f['value'],'calculated':str(-val(f)),'positive_derivative_asset':companions[0],'signed_notional_partitions':signed,'futures_signed_partition':reconciled,'member_labels':{m:labels(p,m) for m in d.values()},'hypothesis':'choose the remaining gross long-asset negative after identifying two independently reported signed exposure conventions','question_focus_proved':False,'signed_exposure_exclusion_is_research_premise':True,'full_risk_DRS_not_proved':True})
    return proposal(base,ws,'D15_derivative_residual')

def debt_cost_bridge(p,base,programs,exc):
    if local(p['target'])!='DeferredFinanceCostsNet':return None,{'status':'outside debt cost domain'}
    ff=fs(p);neg=[f for f in ff if val(f)<0 and any(local(a)=='ConsolidatedEntitiesAxis' for a in ds(f))];ws=[]
    for focus in ff:
        if ds(focus) or val(focus)<=0 or not neg:continue
        peers=[f for f in neg if aspect(f)==aspect(focus)]
        if not peers:continue
        discount=[f for f in facts(p,'DebtInstrumentUnamortizedDiscount') if frame(f)==frame(focus)];net=[f for f in facts(p,'LongTermDebt') if frame(f)==frame(focus)]
        if len(discount)!=1 or len(net)!=1:continue
        groups=defaultdict(list)
        for f in facts(p,'DebtInstrumentCarryingAmount'):
            if len(ds(f))==1 and local(next(iter(ds(f))))=='LongtermDebtTypeAxis' and frame(f,next(iter(ds(f))))==frame(focus):groups[next(iter(ds(f)))].append(f)
        for axis,terms in groups.items():
            paths={ds(f)[axis]:prior.source_path(p,axis,ds(f)[axis]) for f in terms}
            if not all(paths.values()):continue
            texts={f['id']:[x['text'].lower() for x in labels(p,ds(f)[axis])] for f in terms}
            totals=[];excluded=set()
            for t in terms:
                names=[x.removeprefix('total ').removesuffix(' [member]') for x in texts[t['id']] if x.startswith('total ')]
                if len(names)!=1:continue
                name=names[0];children=[f for f in terms if f!=t and any(name in x and not x.startswith('total ') for x in texts[f['id']])]
                if len(children)>=2 and sum(map(val,children))==val(t):
                    excluded.add(t['id']);totals.append({'subtotal':t,'details':children,'linked_label_group':name,'label_supported_group_not_synthetic_DRS_arc':True})
            leaves=[f for f in terms if f['id'] not in excluded]
            if not totals or len(leaves)<3 or any(val(f)<=0 for f in leaves):continue
            if sum(map(val,leaves))-val(discount[0])-val(focus)!=val(net[0]):continue
            if not all(texts[f['id']] for f in leaves):continue
            rate=facts(p,'DebtInstrumentInterestRateStatedPercentage')
            if any(not any(r['context']==f['context'] and val(r)>0 for r in rate) for f in leaves):continue
            ws.append({'focus':focus,'reported':focus['value'],'calculated':focus['value'],'debt_principal_leaves':leaves,'original_DRS_paths':paths,'original_label_supported_subtotals':totals,'discount':discount[0],'reported_net_debt':net[0],'negative_subsidiary_sources':peers,'identity':'sum(disjoint reported debt principal) - unamortized discount - debt issuance costs = reported net long-term debt','linked_debt_member_labels':{ds(f)[axis]:labels(p,ds(f)[axis]) for f in leaves},'hypothesis':'bind debt issuance cost to the complete issuer debt reconciliation rather than an unsupported subsidiary cost adjustment','question_focus_proved':False,'Q2_positive_focus_no_sign_repair':True})
    return proposal(base,ws,'B15_debt_cost_bridge')

def fee_customer_bridge(p,base,programs,exc):
    if local(p['target'])!='RevenueFromContractWithCustomerExcludingAssessedTax' or Decimal(base['extracted_value'])!=0:return None,{'status':'outside unresolved revenue domain'}
    ff=fs(p);ws=[]
    for focus in ff:
        d=ds(focus)
        if len(d)!=1 or local(next(iter(d)))!='ProductOrServiceAxis' or val(focus)<=0:continue
        product=next(iter(d));members=[f for f in ff if len(ds(f))==2 and product in ds(f) and ds(f)[product]==d[product] and frame(f,next(a for a in ds(f) if a!=product))==frame(focus)]
        customeraxes={a for f in members for a in ds(f) if a!=product}
        if len(customeraxes)!=1:continue
        axis=next(iter(customeraxes))
        if local(axis)!='MajorCustomersAxis' or len(members)<3 or sum(map(val,members))!=val(focus):continue
        if any(val(f)<=0 for f in members):continue
        bridges=[]
        for customer in members:
            member=ds(customer)[axis];match=[]
            for gross in ff:
                gd=ds(gross)
                if len(gd)!=2 or product not in gd or local(gd[product])!='ManagementFeesBeforeReimbursementRevenueMember':continue
                related=[a for a in gd if local(a)=='RelatedPartyTransactionsByRelatedPartyAxis' and gd[a]==member]
                if len(related)!=1:continue
                ra=related[0]
                for reimbursement in ff:
                    rd=ds(reimbursement)
                    if set(rd)!={product,ra} or rd[ra]!=member or local(rd[product])!='ExpenseReimbursementMember':continue
                    if frame(gross,product)!=frame(reimbursement,product) or aspect(gross)!=aspect(customer):continue
                    if val(gross)-val(reimbursement)==val(customer) and val(reimbursement)>0:match.append({'net_customer':customer,'gross_fee':gross,'expense_reimbursement':reimbursement,'identity':'net customer revenue = gross management fees - expense reimbursements'})
            if len(match)==1:bridges.extend(match)
        if len(bridges)<2:continue
        paths=[prior.source_path(p,axis,ds(f)[axis]) for f in members]
        external=None
        if not all(paths):
            directory=W/'runs/scope_support/public_sources/APAM_2026Q2'
            schema=directory/'apam-20260630.xsd';definition=directory/'apam-20260630_def.xml'
            if schema.exists() and definition.exists() and {f['context']['entity'] for f in p['facts'] if f['context']}=={'0001517302'} and raw.xml(schema.read_text(encoding='utf-8')).get('targetNamespace')==raw.xml(p['parts']['Schema document']).get('targetNamespace'):
                augmented={**p,'parts':{**p['parts'],'Schema document':schema.read_text(encoding='utf-8'),'Definition linkbase document':definition.read_text(encoding='utf-8')}}
                paths=[prior.source_path(augmented,axis,ds(f)[axis]) for f in members]
                external={'schema':str(schema.relative_to(W)),'schema_sha256':old.sha(schema),'definition':str(definition.relative_to(W)),'definition_sha256':old.sha(definition),'Instance_unchanged':True,'previously_acquired_public_metadata_only':True}
        if not all(paths):continue
        ws.append({'focus':focus,'reported':focus['value'],'calculated':focus['value'],'customer_revenue_members':members,'original_customer_DRS_paths':paths,'external_DRS_provenance':external,'independent_gross_net_customer_bridges':bridges,'identity':'reported product revenue = sum of customer revenues, with >=2 independently reconciled gross/net fee bridges','hypothesis':'bind unresolved revenue to the sole source product total corroborated across customer and related-party fee disclosures','question_focus_proved':False,'original_0117_applicability_not_asserted':True,'nonviolating_source_identity_not_hidden_gold':True})
    return proposal(base,ws,'F117_fee_customer_bridge')

STRATEGIES={'D15_derivative_residual':derivative_residual,'B15_debt_cost_bridge':debt_cost_bridge,'F117_fee_customer_bridge':fee_customer_bridge}
DOMAINS={'D15_derivative_residual':'DerivativeNotionalAmount','B15_debt_cost_bridge':'DeferredFinanceCostsNet','F117_fee_customer_bridge':'RevenueFromContractWithCustomerExcludingAssessedTax'}
