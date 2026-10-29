"""Interpret fictional policies stated in the question; no external law data."""
from __future__ import annotations
import re
from fractions import Fraction
from typing import Any
from src.task1.templates import bind
from src.common.arithmetic import format_value


def solve_policy(q: dict[str,Any]) -> dict[str,Any] | None:
    text=q['question'].split('\n\n')[0]
    if not text.startswith('Apply only this fictional scenario-local') or q['answer_spec']['type']!='enum':return None
    x=[b.value for b in bind(text)[1]];slot_ids={s['slot_id'] for s in q['trace_spec']['slots']};v:dict[str,Any]={};answer:Any=None
    flag=lambda phrase: (match.group(1).lower()=='true') if (match:=re.search(r'\b'+re.escape(phrase)+r' is (true|false)\b',text,re.I)) else False
    if 'total_ownership_percent' in slot_ids:
        v['total_ownership_percent']=x[0]+x[1];v['ownership_threshold_met']=v['total_ownership_percent']>=x[2];answer=v['ownership_threshold_met'] or flag('scenario control flag')
    elif 'aggregate_ownership_percent' in slot_ids:
        v['aggregate_ownership_percent']=sum(x[:3]);v['largest_entity_percent']=max(x[:3]);answer=v['aggregate_ownership_percent']>=x[3] or v['largest_entity_percent']>=x[4]
    elif 'review_trigger' in slot_ids:
        t=flag('Transaction flag');i=flag('Identity flag');v['high_trigger']=x[0]>=x[2] or (t and i);v['review_trigger']=x[0]>=x[1] or t or i;answer='file_sar' if v['high_trigger'] else 'manual_review' if v['review_trigger'] else 'no_action'
    elif 'count_trigger_met' in slot_ids:
        v['count_trigger_met']=x[0]>=x[2];v['amount_below_ceiling']=x[1]<x[3];answer=v['count_trigger_met'] and v['amount_below_ceiling']
    elif 'amount_excess' in slot_ids:
        v['amount_excess']=x[0]-x[1];answer=v['amount_excess']>=0
    elif 'leverage_percent' in slot_ids:
        v['leverage_percent']=x[1]/x[2]*100;answer=v['leverage_percent']>=x[3]
    elif 'leverage_met' in slot_ids:
        v['leverage_met']=x[1]/x[2]*100>=x[7];v['capital_met']=x[3]/x[4]*100>=x[8];v['liquidity_met']=x[5]/x[6]*100>=x[9];answer=all(v.values())
    elif 'new_rwa_usd_million' in slot_ids:
        v['new_rwa_usd_million']=x[1]+x[2];v['new_capital_percent']=x[0]/v['new_rwa_usd_million']*100;answer=v['new_capital_percent']>=x[3]
    elif 'residual_risk_score' in slot_ids:
        v['residual_risk_score']=x[0]*(1-x[1]);v['composite_risk_score']=v['residual_risk_score']+x[2];v['high_trigger']=v['composite_risk_score']>=x[3] or flag('High-risk override');answer='high_risk' if v['high_trigger'] else 'medium_risk' if v['composite_risk_score']>=x[4] else 'low_risk'
    elif 'numeric_risk_band' in slot_ids:
        c=x[0]*x[1];v['composite_risk_score']=c;v['numeric_risk_band']='high_risk' if c>=x[2] else 'medium_risk' if c>=x[3] else 'standard_risk';answer='high_risk' if c>=x[2] or flag('scenario high-risk override') else 'medium_risk' if c>=x[3] or flag('sector EDD flag') else 'standard_risk'
    elif 'volume_risk_points' in slot_ids:
        account=re.search(r'The account type is (\w+)\.',text).group(1);volume=x[1]
        v['volume_risk_points']=Fraction(1 if volume<=x[6] else 2 if volume<=x[9] else 3 if volume<=x[12] else 4)
        v['escalation_bonus']=Fraction(int(account=='offshore' and volume>x[15]));v['total_risk_points']=x[0]+{'savings':x[2],'business':x[3],'offshore':x[4]}[account]+v['volume_risk_points']+v['escalation_bonus'];t=v['total_risk_points'];answer='low_risk' if t<=x[16] else 'medium_risk' if t<=x[18] else 'high_risk'
    elif 'legal_form_family' in slot_ids:
        account=re.search(r'The account nature is (\w+)\.',text).group(1)
        mapping={'personal_savings':('natural_person','individual_customer'),'joint':('natural_person','individual_customer'),'minor_account':('natural_person','individual_customer'),'trust':('legal_arrangement','trust_account'),'nonprofit_organization':('nonprofit_entity','ngo_noncorporate_entity'),'partnership':('partnership_entity','partnership_customer'),'business':('legal_person','corporate_customer'),'offshore_company':('legal_person','corporate_customer')}
        v['legal_form_family'],answer=mapping[account];v['holder_configuration']='single_holder' if x[0]==1 else 'multiple_holders'
    elif 'document_category' in slot_ids:
        document=re.search(r'The submitted document is (\w+)\.',text).group(1);purpose=re.search(r'The requested use is (\w+)\.',text).group(1)
        matrix={}
        for names,category_name in re.findall(r'The identifiers? (.*?) (?:are|is) (identity_only|address_only|dual_purpose|unsupported)\.',text):
            for name in re.findall(r'[a-z_]+',names):
                if name!='and':matrix[name]=category_name
        category=matrix[document]
        v['document_category']=category;answer=category=='dual_purpose' or (purpose=='identity_verification' and category=='identity_only') or (purpose=='address_verification' and category=='address_only')
    elif 'amount_traceability_route' in slot_ids:
        v['total_risk_score']=x[0]+x[1];route=x[2]>=x[3] and bool(re.search(r'evidence traceability is low\b',text));v['amount_traceability_route']='high_value_low_traceability_route' if route else 'standard_amount_route';answer='high_risk' if v['total_risk_score']>=x[4] or route else 'medium_risk' if v['total_risk_score']>=x[5] else 'low_risk'
    elif 'ownership_margin_percent' in slot_ids:
        v['ownership_margin_percent']=x[0]-x[1];answer=x[0]>=x[1]
    elif 'disclosure_delay_days' in slot_ids:
        v['disclosure_delay_days']=x[1]-x[0];v['late_condition']=v['disclosure_delay_days']>x[2];answer='immediate_escalation' if flag('Leak flag') else 'late_disclosure' if v['late_condition'] else 'timely_disclosure'
    elif 'ownership_trigger' in slot_ids:
        v['ownership_trigger']=x[0]>=x[2];v['value_trigger']=x[1]>=x[3];answer=v['ownership_trigger'] or v['value_trigger']
    elif 'financial_base_usd' in slot_ids:
        v['financial_base_usd']=max(x[0],x[1]);v['investment_limit_usd']=v['financial_base_usd']*x[3]/100;answer=x[2]<=v['investment_limit_usd']
    elif 'effective_penalty_usd' in slot_ids:
        v['effective_penalty_usd']=Fraction() if flag('Penalty-waived flag') else x[0]*x[2];v['payoff_due_usd']=x[0]+x[1]+v['effective_penalty_usd'];v['cash_surplus_usd']=x[3]-v['payoff_due_usd'];answer=v['cash_surplus_usd']>=0
    elif 'funding_gap_usd' in slot_ids:
        v['net_annual_need']=max(x[1]-x[3],Fraction());v['required_capital_usd']=v['net_annual_need']*x[2]*(1+x[4]);v['funding_gap_usd']=v['required_capital_usd']-x[0];answer=v['funding_gap_usd']<=0
    else:return None
    render=lambda value,spec:('true' if value else 'false') if isinstance(value,bool) else value if isinstance(value,str) else format_value(value,spec)
    return {'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':q['dataset_version'],'case_id':q['case_id'],'final_answer':{'value':render(answer,q['answer_spec'])},'steps':[{'slot_id':s['slot_id'],'value':render(v[s['slot_id']],s['result_spec'])} for s in q['trace_spec']['slots']]}
