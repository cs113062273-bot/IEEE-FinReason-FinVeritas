"""Question-bound standard financial identities; no IDs or stored answers.

Independent extension of the incumbent routes. Amount/checkpoint contracts
are checked, intermediates use 130-digit Decimal arithmetic, and checkpoints
are rounded independently. Source spans are retained for every operand.
"""
import re
from decimal import Decimal,localcontext,ROUND_HALF_UP

N=r'([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)'
ROUTES={
 'growth':r'FY\d+ sales were {n} and FY\d+ sales were {n}',
 'q4':r'Full-year sales equal {n}; standalone Q1, Q2, Q3 equal {n}, {n}, {n}',
 'cagr':r'Sales changed from {n} in FY(\d{{4}}) to {n} in FY(\d{{4}})',
 'gross_margin':r'Revenue {n}, cost of goods sold {n}',
 'operating_profit':r'Revenue {n}, COGS {n}, selling/general/admin {n}, R&D {n}',
 'ebitda_margin':r'Sales {n}, operating income {n}, depreciation and amortization {n}',
 'diluted_eps':r'Net income {n}, preferred dividends {n}, basic shares {n} million, incremental dilution {n} million',
 'basic_eps':r'Net income {n}; initial common shares {n} million; {n} million extra shares outstanding for the last {n} months',
 'after_tax_income':r'EBIT {n}, interest expense {n}, tax rate {n}%',
 'normalized_fcf':r'Operating cash flow {n}, cash CAPEX {n}, separate financing cash outflow {n}, nonrecurring operating receipt {n}',
 'net_debt_ev':r'Market capitalization {n}, interest-bearing debt {n}, unrestricted cash {n}',
 'enterprise_claims':r'Equity market value {n}, gross debt {n}, minority interest {n}, preferred equity {n}, cash {n}',
 'ev_multiple':r'Equity value {n}, debt {n}, cash {n}, trailing EBITDA {n}',
 'pe_price':r'Net income {n} million USD, diluted shares {n} million, target P/E ratio {n}',
 'capm':r'Risk-free rate {n}%, beta {n}, equity market risk premium {n}%',
 'wacc':r'Equity market value {n}, debt market value {n}, cost of equity {n}%, pretax debt cost {n}%, tax rate {n}%',
 'gordon':r'End-of-year free cash flow {n}, perpetual growth {n}%, required return {n}%',
 'dcf':r'FCF years 1-3 are {n}, {n}, {n}\. At year 3, next-year FCF \(year 4\) is {n}, discount rate {n}%, perpetual growth {n}%',
 'npv':r'Project initial cost at time 0 is {n}, cash receipts at ends of years 1,2,3: {n}, {n}, {n}; discount rate {n}%',
 'breakeven':r'Price per unit {n} USD, variable cost per unit {n} USD, fixed costs {n} USD',
 'dio':r'Average inventory {n}, annual COGS {n}; use {n} days',
 'ccc':r'Average receivables {n}, annual sales {n}, average inventory {n}, annual COGS {n}, average accounts payable {n}\. Using {n} days',
 'debt_equity':r'Current interest-bearing debt {n}, long-term interest-bearing debt {n}, shareholders equity {n}',
 'quick_ratio':r'Current assets {n}, inventory {n}, prepaid expenses {n}, current liabilities {n}',
 'dupont':r'Net income {n}, revenue {n}, average total assets {n}, average equity {n}',
 'roic':r'EBIT {n}, cash tax rate {n}%, interest-bearing debt {n}, equity {n}, excess cash {n}',
 'fx_cross':r'Convert {n} million EUR to USD million\. EUR/GBP is {n} GBP per 1 EUR; USD/GBP is {n} GBP per 1 USD',
 'bond_return':r'A one-year bond has face amount {n}, annual coupon {n}%, purchase price {n}, sale price at year end {n}',
 'split_dividend':r'Pre-split share price {n} USD; {n}-for-1 forward stock split, then ex-dividend adjustment of {n} USD per NEW share',
 'weighted_price':r'Two segments sell {n} and {n} units at prices {n} and {n} USD per unit',
}


def values(route,v):
    d=lambda **x:x
    if route=='growth':
        new,old=v;delta=new-old;return d(sales_delta=delta,yoy_growth_pct=delta/old*100)
    if route=='q4':
        annual,a,b,c=v;return d(nine_month_sales=a+b+c,q4_sales=annual-a-b-c)
    if route=='cagr':
        old,y0,new,y1=v;years=y1-y0
        if years<=0 or old<=0 or new<=0:raise ValueError('invalid CAGR chronology/base')
        ratio=new/old;growth=ratio.sqrt() if years==2 else ratio**(Decimal(1)/years)
        return d(sales_ratio=ratio,two_year_growth_factor=growth,cagr_pct=(growth-1)*100)
    if route=='gross_margin':
        revenue,cost=v;gross=revenue-cost;return d(gross_profit=gross,gross_margin_pct=gross/revenue*100)
    if route=='operating_profit':
        revenue,cost,sga,rd=v;return d(gross_profit=revenue-cost,total_opex=sga+rd,operating_profit=revenue-cost-sga-rd)
    if route=='ebitda_margin':
        revenue,op,da=v;return d(ebitda=op+da,ebitda_margin_pct=(op+da)/revenue*100)
    if route=='diluted_eps':
        income,pref,basic,incr=v;common=income-pref;shares=basic+incr if common>0 else basic
        return d(income_available_to_common=common,diluted_shares=shares*1000000,diluted_eps=common/shares)
    if route=='basic_eps':
        income,basic,extra,months=v;shares=basic+extra*months/12
        if not 0<=months<=12:raise ValueError('invalid within-year duration')
        return d(weighted_avg_shares=shares*1000000,basic_eps=income/shares)
    if route=='after_tax_income':
        ebit,interest,tax=v;pretax=ebit-interest;expense=pretax*tax/100
        return d(pretax_income=pretax,tax_expense=expense,net_income=pretax-expense)
    if route=='normalized_fcf':
        cfo,capex,financing,receipt=v;return d(reported_fcf=cfo-capex,normalized_fcf=cfo-capex-receipt)
    if route=='net_debt_ev':
        equity,debt,cash=v;return d(net_debt=debt-cash,enterprise_value=equity+debt-cash)
    if route=='enterprise_claims':
        equity,debt,minority,pref,cash=v;claims=equity+debt+minority+pref;return d(gross_enterprise_claims=claims,enterprise_value=claims-cash)
    if route=='ev_multiple':
        equity,debt,cash,ebitda=v;ev=equity+debt-cash;return d(enterprise_value=ev,ev_to_ebitda=ev/ebitda)
    if route=='pe_price':
        income,shares,pe=v;return d(eps=income/shares,implied_share_price=income/shares*pe)
    if route=='capm':
        rf,beta,premium=v;return d(beta_times_erp_pct=beta*premium,cost_of_equity_pct=rf+beta*premium)
    if route=='wacc':
        equity,debt,ke,kd,tax=v;we=equity/(equity+debt);wd=1-we;after=kd/100*(1-tax/100)
        return d(equity_weight=we,debt_weight=wd,after_tax_cost_debt=after,wacc_pct=(we*ke/100+wd*after)*100)
    if route=='gordon':
        fcf,growth,discount=v;following=fcf*(1+growth/100);return d(next_fcf=following,terminal_value=following/((discount-growth)/100))
    if route=='dcf':
        a,b,c,next_fcf,rate,growth=v;factor=1+rate/100;terminal=next_fcf/((rate-growth)/100)
        pv1=a/factor;pv2=b/factor**2;pv3=(c+terminal)/factor**3
        return d(terminal_value_y3=terminal,pv_y1=pv1,pv_y2=pv2,pv_y3_plus_tv=pv3,dcf=pv1+pv2+pv3)
    if route=='npv':
        initial,a,b,c,rate=v;factor=1+rate/100;pv=a/factor+b/factor**2+c/factor**3
        return d(pv_future_cf=pv,npv=pv-initial)
    if route=='breakeven':
        price,cost,fixed=v;return d(unit_contribution=price-cost,break_even_units_exact=fixed/(price-cost))
    if route=='dio':
        inventory,cost,days=v;return d(inventory_to_cogs_ratio=inventory/cost,dio_days=inventory/cost*days)
    if route=='ccc':
        receivables,revenue,inventory,cost,payables,days=v;dso=receivables/revenue*days;dio=inventory/cost*days;dpo=payables/cost*days
        return d(dso=dso,dio=dio,dpo=dpo,cash_conversion_cycle=dso+dio-dpo)
    if route=='debt_equity':
        current,longterm,equity=v;return d(total_debt=current+longterm,debt_equity_ratio=(current+longterm)/equity)
    if route=='quick_ratio':
        assets,inventory,prepaid,liability=v;quick=assets-inventory-prepaid
        return d(current_ratio=assets/liability,quick_assets=quick,quick_ratio=quick/liability)
    if route=='dupont':
        income,revenue,assets,equity=v;return d(profit_margin=income/revenue,asset_turnover=revenue/assets,equity_multiplier=assets/equity,roe_pct=income/equity*100)
    if route=='roic':
        ebit,tax,debt,equity,cash=v;nopat=ebit*(1-tax/100);capital=debt+equity-cash
        return d(nopat=nopat,invested_capital=capital,roic_pct=nopat/capital*100)
    if route=='fx_cross':
        euro,eur_gbp,usd_gbp=v;gbp=euro*eur_gbp;return d(amount_gbp=gbp,amount_usd=gbp/usd_gbp)
    if route=='bond_return':
        face,coupon,price,sale=v;receipt=face*coupon/100;gain=sale-price
        return d(coupon_received=receipt,capital_gain=gain,total_return_pct=(receipt+gain)/price*100)
    if route=='split_dividend':
        price,split,dividend=v;return d(post_split_price=price/split,ex_dividend_price=price/split-dividend)
    if route=='weighted_price':
        a,b,pa,pb=v;sales=a*pa+b*pb;quantity=a+b;return d(total_sales=sales,total_units=quantity,weighted_price=sales/quantity)
    raise ValueError('unsupported financial identity')


def render(value,spec):
    if spec['type']!='decimal' or spec['rounding']['mode']!='half_up':raise ValueError('unsupported output contract')
    with localcontext() as ctx:
        ctx.prec=150
        return format(value.quantize(Decimal(1).scaleb(-spec['rounding']['decimal_places']),rounding=ROUND_HALF_UP),'f')


def solve(question):
    body=question['question'];matches=[(name,m) for name,pattern in ROUTES.items() if (m:=re.search(pattern.format(n=N),body,re.I))]
    if len(matches)!=1:return None,{'reason':'no unique financial identity'}
    name,m=matches[0]
    try:
        with localcontext() as ctx:
            ctx.prec=130
            operands=[Decimal(s) for s in m.groups()];computed=values(name,operands)
        slots=question['trace_spec']['slots']
        if {s['slot_id'] for s in slots}!=set(computed):return None,{'reason':'checkpoint semantics differ from matched identity','route':name}
        if name=='diluted_eps' and ('antidilutive' not in body.lower() or 'actual share count' not in body.lower()):return None,{'reason':'EPS share/numerator convention unspecified'}
        steps=[{'slot_id':s['slot_id'],'value':render(computed[s['slot_id']],s['result_spec'])} for s in slots]
        final=list(computed.values())[-1]
        prediction={'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],
                    'case_id':question['case_id'],'final_answer':{'value':render(final,question['answer_spec'])},'steps':steps}
        return prediction,{'strategy':'financial_identity_extension','identity':name,
            'source_operands':[{'text':m.group(i+1),'span':m.span(i+1)} for i in range(len(operands))],
            'unrounded_values':{key:str(value) for key,value in computed.items()},'gold_or_ID_feature':False}
    except (ArithmeticError,ValueError,KeyError) as exc:return None,{'reason':str(exc),'route':name}
