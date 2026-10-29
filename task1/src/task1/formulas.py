"""Reviewed finance DAGs for formulas deeper than bounded induction grammar.

Equations are transcribed from public question definitions, never lookup
tables of gold answers. Binding indices belong to the exact matched prompt.
"""
from __future__ import annotations
from typing import Any


def reviewed_program(template_id: str) -> dict[str,Any] | None:
    family=template_id.split('.')[-3];topic=template_id.split('.')[2]
    definitions:dict[str,tuple[list[tuple[str,str]],str,dict[str,str]]]={
      'closing_cash_balance':([], 'x0+x1+x2+x3',{}),
      'partial_year_disposal':([('annual','x0/x1'),('dep','annual*(x2/12+x3)'),('carrying','x0-dep')],'x4-carrying',{'trace_1':'annual','trace_2':'dep','trace_3':'carrying'}),
      'dividend_lintner_smoothing':([('target','x0*x1/100'),('new','x2+x3/100*(target-x2)')],'new*x4',{'trace_1':'target','trace_2':'new'}),
      'dividend_lintner_three_year_avg':([('avg','(x0+x1+x2)/3'),('new','x4+x5/100*(avg*x3/100-x4)')],'new*x6',{'trace_1':'avg','trace_2':'new'}),
      'eps_pref_div_split_weighted':([('pref','x1*x2*4'),('shares','x3*x4')],'(x0-pref)/shares',{'trace_1':'pref','trace_2':'shares'}),
      'eps_pref_div_weighted':([('earnings','x0-x1'),('shares','x2+x3*x4/12')],'earnings/shares',{'trace_1':'earnings','trace_2':'shares'}),
      'eps_quarterly_pref_buyback':([('pref','x2*x3*4'),('shares','x4-x5*x6/365')],'(x1-pref)/shares',{'trace_1':'pref','trace_2':'shares'}),
      'capm_wacc':([('premium','x4-x3'),('ke','x3+x2*premium'),('wd','x1/(x0+x1)')],'(1-wd)*ke+wd*x5*(1-x6/100)',{'market_risk_premium_percent':'premium','capm_equity_cost_percent':'ke','debt_weight':'wd'}),
      'inflation_adjusted_capm_wacc':([('rm','100*((1+x4/100)/(1+x5/100)-1)'),('ke','x6+x3*(rm-x6)'),('kd','(x1*x7+x2*x8)/(x1+x2)')],'(x0*ke+(x1+x2)*kd*(1-x9/100))/(x0+x1+x2)',{'real_market_return_percent':'rm','capm_real_equity_cost_percent':'ke','weighted_real_debt_cost_percent':'kd'}),
      'preferred_capm_wacc':([('ke','x4+x3*(x5-x4)'),('wp','x1/(x0+x1+x2)'),('after','x7*(1-x8/100)')],'(x0*ke+x1*x6+x2*after)/(x0+x1+x2)',{'capm_equity_cost_percent':'ke','preferred_weight':'wp','after_tax_debt_cost_percent':'after'}),
      'standard_wacc':([('total','x0+x1'),('we','x0/total'),('after','x3*(1-x4/100)')],'we*x2+(1-we)*after',{'total_capital':'total','equity_weight':'we','after_tax_debt_cost_percent':'after'}),
      'weighted_debt_wacc':([('debt','x1+x3'),('kd','(x1*x2+x3*x4)/debt'),('wd','debt/(x0+debt)')],'(1-wd)*x5+wd*kd*(1-x6/100)',{'total_debt':'debt','weighted_debt_cost_percent':'kd','debt_weight':'wd'}),
      'global_macro_strategy':([('raw','x1+x2+x3'),('clipped','min(max(raw,x4),x5)'),('multiple','1+clipped/100')],'x0*multiple',{'raw_impact_trace':'raw','clipped_impact_trace':'clipped','price_multiple_trace':'multiple'}),
      'multi_factor_sentiment':([('tweet','x0*x3'),('news','x1*x4'),('raw','tweet+news+x2*x5')],'min(max(raw,x6),x7)',{'tweet_component_trace':'tweet','news_component_trace':'news','raw_composite_trace':'raw'}),
      'three_year_coupon_bond_price':([('coupon','x0*x1/100'),('terminal','x0+coupon'),('pvterminal','terminal/(1+x2/100)**3')],'coupon/(1+x2/100)+coupon/(1+x2/100)**2+pvterminal',{'annual_coupon_trace':'coupon','terminal_cash_flow_trace':'terminal','pv_terminal_trace':'pvterminal'}),
      'one_period_binomial_call':([('p','(1+x4/100-x3)/(x2-x3)'),('up','max(x0*x2-x1,0)'),('down','max(x0*x3-x1,0)')],'(p*up+(1-p)*down)/(1+x4/100)',{'up_probability_trace':'p','up_payoff_trace':'up','down_payoff_trace':'down'}),
      'two_lot_sale_net_profit':([('shares','x0+x2'),('avg','(x0*x1+x2*x3)/shares'),('proceeds','shares*x4')],'proceeds-shares*avg',{'total_shares_trace':'shares','average_cost_trace':'avg','sale_proceeds_trace':'proceeds'}),
      'investment_vs_sales_push':([('one','x0/(x1+x3-x4)'),('two','x0*(1+x6/100)/x1')],'two-one',{'trace_1':'one','trace_2':'two'}),
      'liquidity_minimum_quick_ratio':([('current','(x0+x1+x2+x3+x4)/x5'),('quick','(x0+x1+x2)/x5'),('required','x5*x6')],'max(required-x0-x1-x2,0)',{'trace_1':'current','trace_2':'quick','trace_3':'required'}),
      'effective_monthly_fee':([('sales','x0*x1'),('tier2','max(sales-x5,0)'),('fees','x2+x0*x3+min(sales,x5)*x4/100+tier2*x6/100')],'fees/sales*100',{'total_sales_trace':'sales','tier_two_sales_trace':'tier2','total_fees_trace':'fees'}),
      'monthly_contribution_projection':([('power','(1+x2/100)**x1'),('annuity','geom(1+x2/100,x1)'),('before','x0*annuity')],'before*(1-x3/100)',{'growth_power_trace':'power','annuity_factor_trace':'annuity','before_fee_trace':'before'}),
      'one_year_after_fee':([('factor','1+x1/100'),('before','x0*factor')],'before*(1-x2/100)',{'growth_multiple_trace':'factor','before_fee_trace':'before'}),
      'quarterly_compound_interest':([('rate','x1/100/x3'),('balance','x0*(1+rate)**(x3*x2)')],'balance-x0',{'quarterly_rate_trace':'rate','ending_balance_trace':'balance'}),
      'two_phase_semiannual_interest':([('first','(1+x2/200)**(2*x1)'),('second','(1+x4/200)**(2*x3)'),('balance','x0*first*second')],'balance-x0',{'first_growth_trace':'first','second_growth_trace':'second','ending_balance_trace':'balance'}),
      'after_tax_net_sale_cost':([('net','x2-x3'),('gain','max(net-x0,0)'),('after','net-gain*x4/100')],'(after/x0-1)*100',{'net_sale_proceeds_trace':'net','taxable_gain_trace':'gain','after_tax_proceeds_trace':'after'}),
      'after_tax_sale':([('gain','max(x2-x0,0)'),('tax','gain*x3/100'),('after','x2-tax')],'(after/x0-1)*100',{'taxable_gain_trace':'gain','gain_tax_trace':'tax','after_tax_proceeds_trace':'after'}),
      'bond_coupon_reinvestment':([('coupon','x2*x3/200'),('reinvest','coupon*(1+x4/200)'),('terminal','x2+coupon+reinvest')],'(terminal/x0-1)*100',{'semiannual_coupon_trace':'coupon','reinvested_first_coupon_trace':'reinvest','terminal_cash_trace':'terminal'}),
      'net_sale_proceeds':([('net','x2-x3'),('multiple','net/x0')],'(multiple-1)*100',{'net_sale_proceeds_trace':'net','gross_return_multiple_trace':'multiple'}),
      'six_month_after_tax_net_sale':([('net','x2-x3'),('after','net-max(net-x0,0)*x4/100'),('multiple','after/x0')],'(multiple**2-1)*100',{'net_sale_proceeds_trace':'net','after_tax_proceeds_trace':'after','six_month_gross_multiple_trace':'multiple'}),
      'four_year_annuity_salvage_npv':([('terminal','x1+x2'),('pv4','terminal/(1+x3/100)**4'),('total','x1/(1+x3/100)+x1/(1+x3/100)**2+x1/(1+x3/100)**3+pv4')],'total-x0',{'year_four_total_trace':'terminal','pv_year_four_trace':'pv4','total_pv_trace':'total'}),
      'four_year_cleanup_npv':([('gross','x1/(1+x6/100)+x2/(1+x6/100)**2+x3/(1+x6/100)**3+x4/(1+x6/100)**4'),('after','gross-x0'),('cleanup','x5/(1+x6/100)**4')],'after-cleanup',{'gross_pv_trace':'gross','after_initial_trace':'after','pv_cleanup_trace':'cleanup'}),
      'three_year_salvage_npv':([('terminal','x3+x4'),('pv3','terminal/(1+x5/100)**3'),('total','x1/(1+x5/100)+x2/(1+x5/100)**2+pv3')],'total-x0',{'terminal_cash_flow_trace':'terminal','pv_three_trace':'pv3','total_pv_trace':'total'}),
      'three_asset_capm_portfolio':([('total','x0+x2+x4'),('beta','(x0*x1+x2*x3+x4*x5)/total'),('premium','x7-x6')],'x6+beta*premium',{'total_value_trace':'total','portfolio_beta_trace':'beta','market_premium_trace':'premium'}),
      'conversion_campaign_roi':([('clicks','x0*x1/100'),('sales','clicks*x2/100'),('revenue','sales*x3')],'(revenue-x4)/x4*100',{'expected_clicks_trace':'clicks','expected_sales_trace':'sales','campaign_revenue_trace':'revenue'}),
      'mutual_fund_total_roi':([('dividends','x0*x3*x4'),('fees','x0*x1*x5/100*x4'),('profit','x0*(x2-x1)+dividends-fees')],'profit/(x0*x1)*100',{'total_dividends_trace':'dividends','total_fees_trace':'fees','net_profit_trace':'profit'}),
      'control_premium_debt_earnout_calculation':([('premium','x0*x1/100'),('total','x0+premium+x2*x3/100')],'total*(1-x4/100)',{'trace_1':'premium','trace_2':'total'}),
      'earnout_with_bonus_calculation':([('basic','min(x1*x3/x2,x1)'),('bonus','min(max(x3-x2*x6/100,0)*x4/100,x5)')],'x0+basic+bonus',{'trace_1':'basic','trace_2':'bonus'}),
      'leveraged_buyout_adjusted_shares_calculation':([('equity','x0*(1-x1/100)'),('basic','equity/x2')],'basic*(1+lt(x2,x3)*(x4-1))',{'trace_1':'equity','trace_2':'basic'}),
      'due_diligence_dcf_valuation':([('fcf5','x1*(1+x2/100)**4'),('terminal','fcf5*(1+x6/100)/((x5-x6)/100)')],'x1/(1+x5/100)*geom((1+x2/100)/(1+x5/100),5)+terminal/(1+x5/100)**5',{'trace_1':'fcf5','trace_2':'terminal'}),
      'revenue_synergy_net_gain':([('combined','x0+x1'),('synergy','combined*x2/100')],'synergy-combined*x3/100',{'trace_1':'combined','trace_2':'synergy'}),
      'synergy_complex_after_tax':([('gross','(x0+x1)*x2/100'),('net','gross-x3/x4')],'net*(1-x5/100)',{'trace_1':'gross','trace_2':'net'}),
      'dcf_3yr_gordon_to_equity':([('terminal','x4*(1+x6/100)/((x5-x6)/100)'),('enterprise','x2/(1+x5/100)+x3/(1+x5/100)**2+(x4+terminal)/(1+x5/100)**3')],'enterprise-x7+x8',{'trace_1':'terminal','trace_2':'enterprise'}),
      'dcf_three_year_terminal_to_equity':([('forecast','x2/(1+x5/100)+x3/(1+x5/100)**2+x4/(1+x5/100)**3'),('terminalpv','x4*(1+x6/100)/((x5-x6)/100)/(1+x5/100)**3')],'forecast+terminalpv-x7+x8',{'trace_1':'forecast','trace_2':'terminalpv'}),
      'diversification_risk':([('base','x0*x2+x1*x3'),('condition','ge(max(x0,x1),x5)'),('penalty','condition*x4')],'base+penalty',{'base_risk_score':'base','concentration_condition':'condition','applied_penalty_points':'penalty'}),
      'foreign_tax_relief':([('domestic','x0*x1'),('credit','min(x2,domestic*x3)')],'max(domestic-credit,0)',{'domestic_tax_before_relief_usd':'domestic','allowed_credit_usd':'credit'}),
      'comprehensive_strategy':([('price','x3*(1-x6/100)'),('credits','x0/price'),('surplus','max(credits-x9,0)')],'surplus*price*(1+x13/100)+x16-x0',{'discounted_price_trace':'price','credits_purchased_trace':'credits','surplus_credits_trace':'surplus'}),
      'credit_rebate':([('credits','x0/x3'),('eligible','credits*x6')],'eligible*gt(credits,x9)',{'credits_purchased_trace':'credits','eligible_rebate_trace':'eligible'}),
      'multi_company_synergy':([('credits','x1+x3'),('gross','credits*x6'),('discounted','gross*(1-x9/100)')],'gross*(1-gt(credits,x12)*x9/100)',{'total_credits_trace':'credits','gross_cost_trace':'gross','discounted_cost_trace':'discounted'}),
      'multi_factor_synergy':([('energy','x3*12'),('efficiency','x9*x12/100'),('total','(energy+efficiency+x6)*x15')],'total-x0',{'annual_energy_savings_trace':'energy','annual_efficiency_savings_trace':'efficiency','total_savings_trace':'total'}),
      'comprehensive_analysis':([('interest','x0*((1+x3/100)**x6-1)'),('bonus','x12/x16*x15*x6'),('reinvest','interest/x6*x19/100*geom(1+x22/100,x6)')],'interest*(1+x9/100)+bonus+reinvest',{'interest_earned_trace':'interest','total_bonus_trace':'bonus','reinvestment_contribution_trace':'reinvest'}),
      'financing_cost_reduction':([('original','x0*((1+x3/100)**x6-1)'),('rate','x3-x9'),('adjusted','x0*((1+rate/100)**x6-1)')],'original-adjusted',{'original_interest_trace':'original','adjusted_rate_trace':'rate','adjusted_interest_trace':'adjusted'}),
      'sustainability_roi_analysis':([('base','x3+x6'),('annual','base*(1+x9/100+x12/100)'),('net','annual*x15-x0')],'net/x0*100',{'base_annual_savings_trace':'base','total_annual_savings_trace':'annual','net_period_benefit_trace':'net'}),
      'acquisition_cash_flow_impact':([('synergies','x1+x2+x3+x4'),('costs','x0+x5+x6')],'synergies-costs',{'trace_1':'synergies','trace_2':'costs'}),
      'asset_impairment_reversal':([('gap','x1-x0'),('room','max(gap,0)')],'min(x2,room)',{'trace_1':'gap','trace_2':'room'}),
      'inventory_turnover_days':([('cogs','x0+x1-x2'),('avg','(x0+x2)/2'),('turnover','cogs/avg')],'365/turnover',{'trace_1':'cogs','trace_2':'avg','trace_3':'turnover'}),
      'sum_of_years_digits':([('sumyears','x1*(x1+1)/2'),('factor','(x1-x2+1)/sumyears')],'x0*factor',{'trace_1':'sumyears','trace_2':'factor'}),
      'liquidity_pool_reward':([('retained','1-x1/100'),('available','x0*retained')],'available*x2/100',{'distributable_ratio_trace':'retained','distributable_fees_trace':'available'}),
      'market_sentiment_shift':([('ratio','x1/100'),('raw','x0*(1+ratio)')],'max(raw,x2)',{'sentiment_ratio_trace':'ratio','raw_market_cap_trace':'raw'}),
      'multi_factor_regulatory_risk':([('total','x1+x2+x3'),('gross','x0*total/100'),('credited','gross-x4')],'max(credited,0)',{'total_factor_trace':'total','gross_cost_trace':'gross','credited_cost_trace':'credited'}),
      'multi_factor_tokenomics':([('burned','x0*(1-x2/100)'),('supply','burned*(1+x3/100)'),('price','x1*(1+x4/100)')],'supply*price',{'post_burn_supply_trace':'burned','adjusted_supply_trace':'supply','adjusted_price_trace':'price'}),
      'staking_reward_effect':([('supply','x0*(1-x2/100)'),('price','x1*(1+x3/100)')],'supply*price',{'effective_supply_trace':'supply','adjusted_price_trace':'price'}),
      'token_price_calculation':([],'x0/x1',{}),
      'bulk_transaction_fees':([('one','x0*(1-x3/100)'),('two','x1*(1-x4/100)'),('three','x2*(1-x5/100)')],'one+two+three',{'net_one_trace':'one','net_two_trace':'two','net_three_trace':'three'}),
      'multi_factor_transaction':([('one','x0*x1/100*(1-x5/100)'),('afterfixed','x0*(1-x1/100)-x7'),('two','afterfixed*(1+x8/100)')],'one+two',{'network_one_net_trace':'one','network_two_after_fixed_trace':'afterfixed','network_two_net_trace':'two'}),
      'dirty_price_with_simple_accrual':([('annual','x1*x2/100'),('coupon','annual/x3'),('accrued','coupon*x4/x5')],'x0+accrued',{'annual_coupon_trace':'annual','coupon_per_period_trace':'coupon','accrued_interest_trace':'accrued'}),
      'eur_to_gbp_cross_conversion':([('cross','x1/x2')],'x0*cross',{'cross_rate_trace':'cross'}),
      'long_call_roi':([('payoff','max(x2-x1,0)'),('net','payoff-x0')],'net/x0*100',{'call_payoff_trace':'payoff','net_profit_loss_trace':'net'}),
      'asset_turnover_compare_periods':([('prior','x0/x1'),('current','x0/(x1+x2)')],'prior-current',{'trace_1':'prior','trace_2':'current'}),
      'debt_vs_equity_scenarios':([('debt','(x0+x2)/x1'),('equity','x0/(x1+x3)')],'debt-equity',{'trace_1':'debt','trace_2':'equity'}),
      'quick_ratio_target':([('quick','x0-x1-x2'),('required','x3*x4')],'max(required-quick,0)',{'trace_1':'quick','trace_2':'required'}),
      'batch_effective_fee':([('fixed','x1*x2'),('variable','x0*x3/100'),('total','fixed+variable')],'total/x0*100',{'fixed_fee_total_trace':'fixed','variable_fee_total_trace':'variable','total_fees_trace':'total'}),
      'cross_border_net':([('platform','x1*(1-x2/100)'),('before','x0*platform')],'before-x3',{'platform_multiple_trace':'platform','before_fee_trace':'before'}),
      'tax_loss_savings':([('loss','max(x1-x2,0)'),('eligible','x0*loss'),('ratio','x3/100')],'eligible*ratio',{'loss_per_share_trace':'loss','eligible_loss_trace':'eligible','tax_ratio_trace':'ratio'}),
      'additional_saving':([('available','x1+x2*x3'),('shortfall','max(x0-available,0)')],'shortfall/x3',{'projected_available_usd':'available','shortfall_usd':'shortfall'}),
      'itemized_deduction':([('deduction','max(x1,x2)'),('income','max(x0-deduction,0)')],'income*x3',{'chosen_deduction_usd':'deduction','taxable_income_usd':'income'}),
      'monthly_deposit_future_value':([('rate','x2/100'),('power','(1+rate)**x1'),('annuity','geom(1+rate,x1)')],'x0*annuity',{'monthly_rate_trace':'rate','growth_power_trace':'power','annuity_factor_trace':'annuity'}),
      'long_position_profit_loss':([('change','x2-x1'),('pips','change/x3'),('pipvalue','x0*x3')],'x0*change',{'quote_change_trace':'change','pip_difference_trace':'pips','pip_value_trace':'pipvalue'}),
      'supply_chain_npv_net_benefit':([('annual','(x0+x1)*x2/100'),('discount','1/(1+x4/100)'),('pv','annual*discount*geom(discount,x3)')],'pv-x5',{'trace_1':'annual','trace_2':'pv'}),
    }
    if topic=='defi' and family=='multi_factor_portfolio':
        definitions[family]=([('staking','x0*x1/100*x2/100'),('fee','x0*x3/100')],'staking+fee',{'staking_impact_trace':'staking','fee_impact_trace':'fee'})
    if family=='financing_cost_reduction' and topic!='green_bonds':return None
    definition=definitions.get(family)
    if definition is None:return None
    dag,final,slots=definition
    return {'dag':dag,'final':final,'slots':slots,'enum':None,'slot_enums':{},'reviewed_formula':True}
