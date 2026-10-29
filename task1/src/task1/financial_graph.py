"""Compositional financial quantities with source spans and dimensional checks.

This is a bounded English grammar and an explicit financial-relation library,
not a universal language model. Facts bind by quantity name, never numeric
position, case identity or a question signature. Missing inputs stay missing.
Multiple supported derivations must agree exactly. Only unanswered questions
reach this path in Solver; original submitted artifacts are not regenerated.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping

from src.common.arithmetic import execute, format_value
from src.common.fraction_budget import checked, binary
from src.task1.equation_fallback import MONEY, COUNT, TIME, DIMLESS, _dimension, _unit, _segments
from src.task1.hidden_program import execute as second_execute


@dataclass(frozen=True)
class Quantity:
    name: str
    aliases: str
    kind: str = "money"


QUANTITIES = (
    Quantity("prior_income", r"(?:prior|previous)(?:[- ]year)?\s+net\s+income"),
    Quantity("revenue", r"(?:(?:total|net|annual)\s+)?(?:revenue|sales)"),
    Quantity("cogs", r"cost\s+of\s+goods\s+sold|COGS"),
    Quantity("sga", r"selling/general/admin|SG&A|selling,?\s+general\s+and\s+administrative\s+(?:costs|expenses)"),
    Quantity("rd", r"R&D|research\s+and\s+development\s+(?:costs|expenses)"),
    Quantity("opex", r"(?:total\s+)?operating\s+expenses"),
    Quantity("gross_profit", r"gross\s+profit(?!\s+margin)"),
    Quantity("operating_income", r"operating\s+(?:income|profit)"),
    Quantity("ebit", r"EBIT"),
    Quantity("da", r"depreciation\s+and\s+amortization|D&A"),
    Quantity("ebitda", r"(?:trailing\s+)?EBITDA(?!\s+margin)"),
    Quantity("interest", r"interest\s+expense"),
    Quantity("pretax_income", r"(?:pretax|pre[- ]tax)\s+(?:income|profit)"),
    Quantity("taxes", r"tax\s+expense|income\s+taxes|taxes"),
    Quantity("net_income", r"net\s+income|after[- ]tax\s+(?:income|profit)"),
    Quantity("tax_rate", r"(?:income\s+)?tax\s+rate", "rate"),
    Quantity("cash_tax_rate", r"cash\s+tax\s+rate", "rate"),
    Quantity("riskfree", r"risk[- ]free\s+rate", "rate"),
    Quantity("beta", r"(?:equity\s+)?beta", "ratio"),
    Quantity("premium", r"(?:equity\s+)?market\s+risk\s+premium|equity\s+risk\s+premium", "rate"),
    Quantity("equity_cost", r"cost\s+of\s+equity|equity\s+cost(?:\s+of\s+capital)?", "rate"),
    Quantity("debt_cost", r"(?:pretax|pre[- ]tax)\s+(?:debt\s+cost|cost\s+of\s+debt)", "rate"),
    Quantity("equity_market", r"equity\s+market\s+value|market\s+value\s+of\s+equity|market\s+capitalization|equity\s+value"),
    Quantity("debt_market", r"debt\s+market\s+value|market\s+value\s+of\s+debt"),
    Quantity("debt_current", r"current\s+(?:interest[- ]bearing\s+)?debt"),
    Quantity("debt_long", r"long[- ]term\s+(?:interest[- ]bearing\s+)?debt"),
    Quantity("debt", r"(?:(?:total|gross|interest[- ]bearing)\s+)?debt"),
    Quantity("equity", r"(?:total\s+)?(?:shareholders['’]?\s+)?equity"),
    Quantity("assets", r"(?:total\s+)?assets"),
    Quantity("liabilities", r"(?:total\s+)?liabilities"),
    Quantity("current_assets", r"current\s+assets"),
    Quantity("current_liabilities", r"current\s+liabilities"),
    Quantity("inventory", r"inventor(?:y|ies)"),
    Quantity("prepaid", r"prepaid\s+(?:expenses|assets)"),
    Quantity("average_inventory", r"average\s+inventory"),
    Quantity("average_receivables", r"average\s+(?:accounts\s+)?receivables"),
    Quantity("average_payables", r"average\s+(?:accounts\s+)?payables?"),
    Quantity("annual_cogs", r"annual\s+(?:COGS|cost\s+of\s+goods\s+sold)"),
    Quantity("average_assets", r"average\s+(?:total\s+)?assets"),
    Quantity("opening_assets", r"(?:opening|beginning)\s+(?:total\s+)?assets"),
    Quantity("closing_assets", r"(?:closing|ending)\s+(?:total\s+)?assets"),
    Quantity("average_equity", r"average\s+(?:total\s+)?equity"),
    Quantity("day_basis", r"(?:use|using)\s+", "days"),
    Quantity("cash", r"(?:unrestricted\s+)?cash"),
    Quantity("excess_cash", r"excess\s+cash"),
    Quantity("preferred_equity", r"preferred\s+equity"),
    Quantity("minority", r"minority\s+interest"),
    Quantity("ev", r"enterprise\s+value|EV"),
    Quantity("unit_price", r"(?:selling\s+)?price\s+per\s+unit", "price"),
    Quantity("unit_cost", r"variable\s+cost\s+per\s+unit", "price"),
    Quantity("fixed_cost", r"fixed\s+costs"),
    Quantity("gross_margin", r"gross\s+(?:profit\s+)?margin", "rate"),
    Quantity("net_margin", r"net\s+(?:profit\s+)?margin|profit\s+margin", "rate"),
    Quantity("ebitda_margin", r"EBITDA\s+margin", "rate"),
    Quantity("margin_gap", r"gross[- ]to[- ]net\s+margin\s+gap", "rate"),
    Quantity("quick_assets", r"quick\s+assets"),
    Quantity("quick_ratio", r"quick\s+ratio|acid[- ]test\s+ratio", "ratio"),
    Quantity("current_ratio", r"current\s+ratio", "ratio"),
    Quantity("debt_equity", r"debt[- /]to[- /]equity\s+ratio|debt[- /]equity\s+ratio", "ratio"),
    Quantity("net_debt", r"net\s+debt"),
    Quantity("ev_multiple", r"EV\s*/\s*EBITDA(?:\s+multiple)?|enterprise\s+value\s+to\s+EBITDA", "ratio"),
    Quantity("wacc", r"WACC|weighted[- ]average\s+cost\s+of\s+capital", "rate"),
    Quantity("equity_weight", r"equity\s+weight", "ratio"),
    Quantity("debt_weight", r"debt\s+weight", "ratio"),
    Quantity("asset_turnover", r"asset\s+turnover", "ratio"),
    Quantity("equity_multiplier", r"equity\s+multiplier", "ratio"),
    Quantity("roe", r"return\s+on\s+equity|ROE", "rate"),
    Quantity("nopat", r"NOPAT|net\s+operating\s+profit\s+after\s+tax", "money"),
    Quantity("invested_capital", r"invested\s+capital"),
    Quantity("roic", r"return\s+on\s+invested\s+capital|ROIC", "rate"),
    Quantity("contribution", r"(?:unit\s+)?contribution\s+margin(?:\s+per\s+unit)?", "price"),
    Quantity("break_even", r"(?:exact\s+)?break[- ]even\s+(?:quantity|units)", "count"),
    Quantity("dso", r"days\s+sales\s+outstanding|DSO", "days"),
    Quantity("dio", r"(?:days\s+inventory\s+outstanding|DIO)(?:\s*\(DIO\))?", "days"),
    Quantity("dpo", r"days\s+payables\s+outstanding|DPO", "days"),
    Quantity("ccc", r"cash\s+conversion\s+cycle|CCC", "days"),
    Quantity("preferred_dividends", r"preferred\s+dividends"),
    Quantity("basic_shares", r"basic\s+shares", "count"),
    Quantity("incremental_shares", r"incremental\s+dilution|incremental\s+shares", "count"),
    Quantity("diluted_shares", r"diluted\s+shares", "count"),
    Quantity("eps", r"diluted\s+EPS|EPS|earnings\s+per\s+share", "price"),
    Quantity("pe", r"(?:target\s+)?P/E\s+ratio|price[- /]to[- /]earnings\s+ratio", "ratio"),
    Quantity("implied_price", r"implied\s+share\s+price", "price"),
    Quantity("current_fcf", r"end[- ]of[- ]year\s+free\s+cash\s+flow|current\s+FCF"),
    Quantity("growth", r"perpetual\s+growth(?:\s+rate)?", "rate"),
    Quantity("required_return", r"required\s+return", "rate"),
    Quantity("next_fcf", r"next[- ]year\s+FCF"),
    Quantity("terminal_value", r"(?:Gordon[- ]growth\s+)?terminal\s+value(?:\s+at\s+year[- ]end)?"),
    Quantity("face_amount", r"face\s+amount"),
    Quantity("coupon_rate", r"annual\s+coupon(?:\s+rate)?", "rate"),
    Quantity("purchase_price", r"purchase\s+price"),
    Quantity("sale_price", r"sale\s+price(?:\s+at\s+year\s+end)?"),
    Quantity("holding_return", r"holding[- ]period\s+total\s+return", "rate"),
)
BY_NAME = {q.name: q for q in QUANTITIES}
DIMS = {"money": MONEY, "price": (1, -1, 0), "count": COUNT, "days": TIME,
        "rate": DIMLESS, "ratio": DIMLESS}
RULES = {
    "gross_profit": ("revenue-cogs",), "gross_margin": ("gross_profit/revenue",),
    "net_margin": ("net_income/revenue",), "margin_gap": ("gross_margin-net_margin",),
    "opex": ("sga+rd",), "operating_income": ("gross_profit-opex",),
    "ebitda": ("operating_income+da", "ebit+da"), "ebitda_margin": ("ebitda/revenue",),
    "pretax_income": ("ebit-interest", "operating_income-interest"),
    "taxes": ("pretax_income*tax_rate",), "net_income": ("pretax_income-taxes",),
    "equity_cost": ("riskfree+beta*premium",), "debt": ("debt_current+debt_long",),
    "equity": ("assets-liabilities",), "quick_assets": ("current_assets-inventory-prepaid",),
    "quick_ratio": ("quick_assets/current_liabilities",), "current_ratio": ("current_assets/current_liabilities",),
    "debt_equity": ("debt/equity",), "net_debt": ("debt-cash",),
    # All claims are mandatory here: absence never becomes an invented zero.
    "ev": ("equity_market+net_debt+minority+preferred_equity",), "ev_multiple": ("ev/ebitda",),
    "equity_weight": ("equity_market/(equity_market+debt_market)",),
    "debt_weight": ("debt_market/(equity_market+debt_market)",),
    "wacc": ("equity_weight*equity_cost+debt_weight*debt_cost*(1-tax_rate)",),
    "average_assets": ("(opening_assets+closing_assets)/2",),
    "asset_turnover": ("revenue/average_assets",), "equity_multiplier": ("average_assets/average_equity",),
    "roe": ("net_margin*asset_turnover*equity_multiplier",),
    "nopat": ("ebit*(1-cash_tax_rate)",), "invested_capital": ("debt+equity-excess_cash",),
    "roic": ("nopat/invested_capital",), "contribution": ("unit_price-unit_cost",),
    "break_even": ("fixed_cost/contribution",),
    "dso": ("average_receivables/revenue*day_basis",),
    "dio": ("average_inventory/annual_cogs*day_basis",),
    "dpo": ("average_payables/annual_cogs*day_basis",), "ccc": ("dso+dio-dpo",),
    "diluted_shares": ("basic_shares+incremental_shares",),
    "eps": ("(net_income-preferred_dividends)/diluted_shares",),
    "implied_price": ("eps*pe",),
    "next_fcf": ("current_fcf*(1+growth)",),
    "terminal_value": ("next_fcf/(required_return-growth)",),
    "holding_return": ("(sale_price-purchase_price+face_amount*coupon_rate)/purchase_price",),
}
NUMBER = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:/\d+)?"
CONNECTOR = r"\s*(?:(?:is|are|was|were|equals?|equal\s+to|amounts?\s+to|of|at)\s+|[:=]\s*)?"
SCALE = {"thousand": Fraction(1000), "million": Fraction(10**6), "billion": Fraction(10**9)}


def _unit_scale(unit):
    return (DIMLESS, Fraction(1)) if unit == "multiple" else _unit(unit)


def _facts(body, default_money_scale):
    found = []
    for q in QUANTITIES:
        pattern = r"(?<![\w])(?:" + q.aliases + r")" + CONNECTOR + r"(?P<prefix>USD\s+|\$\s*)?(?P<value>" + NUMBER + r")(?![\d.]\d)"
        for m in re.finditer(pattern, body, re.I):
            found.append((q, m))
    # Longer explicit quantity names consume a shared source amount first:
    # current assets cannot also bind total assets; cash tax != income tax.
    selected, occupied = [], set()
    for q, m in sorted(found, key=lambda pair: (-(pair[1].end()-pair[1].start()), pair[1].start())):
        key = m.span('value')
        if key in occupied:
            continue
        occupied.add(key); selected.append((q, m))
    facts, invalid = {}, set()
    for q, m in selected:
        try:
            prefix = body[max(0, m.start()-40):m.start()]
            if re.search(r"\b(?:prior|previous|next|forecast|budgeted|segment|last[- ]year|current|long[- ]term|average|preferred|excess|not|hypothetical|example|ignore|FY\d{4}|(?:19|20)\d{2})\s+$|\b(?:not|never)\s+(?:use|include|consider|treat)\s+$|\b(?:prior|previous|last|next)(?:[- ]year)?['’]s\s+$", prefix, re.I):
                raise ValueError("unconsumed quantity qualifier")
            value = checked(Fraction(m['value'].replace(',', '')))
            suffix = body[m.end('value'):]
            scale = Fraction(1); consumed = 0
            if q.kind not in {'money','price'} and m['prefix']:
                raise ValueError('currency prefix on nonmonetary quantity')
            if q.kind in {'money', 'price'}:
                unit = re.match(r"\s*(?:(USD)(?:\s+(thousand|million|billion))?|(thousand|million|billion)\s+(USD))\b", suffix, re.I)
                magnitude = re.match(r"\s*(thousand|million|billion)\b", suffix, re.I) if m['prefix'] else None
                if unit:
                    scale = SCALE.get((unit[2] or unit[3] or '').lower(), Fraction(1)); consumed = unit.end()
                elif m['prefix']:
                    if magnitude: scale = SCALE[magnitude[1].lower()]; consumed = magnitude.end()
                elif default_money_scale is not None:
                    scale = default_money_scale
                else: raise ValueError("money unit missing")
                remaining = suffix[consumed:]
                if re.match(r"\s*(?:%|(?:USD|EUR|JPY|GBP|CAD|AUD|CNY|CHF|trillion|percent|bps?|basis|ratio|days|shares|units)\b)", remaining, re.I):
                    raise ValueError("unsupported currency or magnitude")
                per = re.match(r"\s*(?:per\s+|/\s*)([A-Za-z]+)", remaining, re.I)
                if per and (q.kind != 'price' or per[1].lower() not in {'unit', 'share', 'count'}):
                    raise ValueError("monetary denominator contradicts role")
                modifier = re.match(r'\s+([A-Za-z]+)', remaining)
                if modifier and modifier[1].lower() not in {'per','and','then','at','is','are','was','were','in','for','with','before','after','of','but','including','excluding','respectively'}:
                    raise ValueError('unrecognized monetary modifier')
            elif q.kind == 'rate':
                unit = re.match(r"\s*(%|percent\b|basis\s+points?\b|bps?\b|(?:decimal\s+)?ratio\b)", suffix, re.I)
                if not unit: raise ValueError("rate unit missing")
                text = unit[1].lower(); consumed = unit.end()
                scale = Fraction(1,10000) if re.fullmatch(r'basis\s+points?|bps?', text) else Fraction(1) if 'ratio' in text else Fraction(1,100)
            elif q.kind == 'days':
                unit = re.match(r"\s*days\b", suffix, re.I)
                if not unit: raise ValueError("day unit missing")
                consumed = unit.end()
            elif q.kind == 'count':
                unit = re.match(r'\s*(?:(thousand|million|billion)\b\s*)?(?:units|shares|count)?\b',suffix,re.I)
                if unit and unit[1]:scale=SCALE[unit[1].lower()];consumed=unit.end()
                elif unit:consumed=unit.end()
            else:
                unit = re.match(r'\s*(?:ratio|multiple|times)\b',suffix,re.I)
                if unit:consumed=unit.end()
            if q.kind not in {'money','price'} and re.match(r"\s*(?:%|(?:USD|EUR|JPY|GBP|percent|days|bps?|basis|ratio|multiple|times|thousand|million|billion|trillion)\b)", suffix[consumed:], re.I):
                raise ValueError('conflicting or repeated quantity denomination')
            value = binary(value, scale, '*')
            if q.name in facts: raise ValueError("duplicate source quantity")
            facts[q.name] = {'value':value, 'evidence':{'quantity':q.name, 'source':body[m.start():m.end('value')+consumed],
                             'start':m.start(), 'end':m.end('value')+consumed, 'canonical_value':str(value), 'scale':str(scale)}}
        except (ValueError, ZeroDivisionError):
            invalid.add(q.name)
    for name in invalid: facts.pop(name, None)
    return facts, sorted(invalid)


TARGET = re.compile('|'.join(r'(?P<q'+str(i)+r'>(?<![\w])(?:'+q.aliases+r')(?![\w]))' for i,q in sorted(enumerate(QUANTITIES),key=lambda x:-len(x[1].aliases))), re.I)


def _target_expression(text):
    text = text.strip().rstrip('.?').strip()
    text = re.sub(r'\bthe\s+exact\s+\(not\s+rounded-up\)\s+', 'exact ', text, flags=re.I)
    text = re.sub(r'\s+\(not\s+debt/assets\)$', '', text, flags=re.I)
    text = re.sub(r'\s+\(tax\s+expense\s*=\s*pretax\s+income\s+times\s+the\s+signed\s+stated\s+rate,\s*even\s+for\s+a\s+loss\)$', '', text, flags=re.I)
    text = re.sub(r',\s*percent$', '', text, flags=re.I)
    text = re.sub(r'\s*\(USD\s*/\s*share\)$', '', text, flags=re.I)
    # Export wording only; numerical unit compatibility is checked separately.
    text = re.sub(r"\s*\((?:in\s+)?%\)|\s*\(%\)", '', text, flags=re.I)
    text = re.sub(r"\s+(?:as\s+(?:a\s+)?percentage|in\s+(?:percent(?:age\s+points)?|USD)|percentage\s+in\s+percent\s+points)\s*$", '', text, flags=re.I)
    if '=' in text:
        if text.count('=')!=1:raise ValueError('ambiguous target equality')
        left,right=text.split('=')
        name,formula=_target_expression(left),_target_expression(right)
        if name not in RULES or not _same_identity(name,formula):
            raise ValueError('disclosed target formula differs from supported relation')
        return name
    hints = {
        'ebitda_margin': r'\s+including\s+D&A\s+exactly\s+once',
        'quick_ratio': r'\s+after\s+excluding\s+(?:both\s+)?inventory\s+and\s+prepaid\s+(?:assets|expenses)',
        'roe': r'\s+using\s+DuPont\s+profit\s+margin\s*[×*]\s*asset\s+turnover\s*[×*]\s*equity\s+multiplier',
        'ev': r'\s+including\s+minority\s+and\s+preferred',
    }
    for name, tail in hints.items():
        if re.fullmatch('(?:'+BY_NAME[name].aliases+')'+tail, text, re.I):return name
    # Lists ask for the last result; requested trace slots are resolved below.
    pieces = re.split(r'\s+then\s+(?!subtract\b)|,\s*(?:and\s+)?|\s+and\s+', text, flags=re.I)
    expressions=[]
    for text in pieces:
        text = re.sub(r'^the\s+', '', text.strip(), flags=re.I)
        text = re.sub(r'\s+then\s+subtract\s+', ' - ', text, flags=re.I)
        for phrase, op in [('divided by','/'),('multiplied by','*'),('times','*'),('minus','-'),('less','-'),('plus','+')]:
            text = re.sub(r'\b'+phrase+r'\b', ' '+op+' ', text, flags=re.I)
        parts, position, names = [], 0, []
        for m in TARGET.finditer(text):
            gap = text[position:m.start()]
            if not re.fullmatch(r'[\s()+*/\-]*', gap): raise ValueError("unparsed target modifier")
            name = QUANTITIES[int(m.lastgroup[1:])].name
            parts.extend((gap, name)); names.append(name); position = m.end()
        tail = text[position:]
        if not names or not re.fullmatch(r'[\s()+*/\-]*', tail):raise ValueError("unparsed target instruction")
        expression = ''.join(parts)+tail
        ast.parse(expression, mode='eval');expressions.append(expression)
    return expressions[-1]


def _same_identity(name,formula):
    """Permit named intermediate expansion, never arbitrary formula changes."""
    target=ast.parse(formula,mode='eval');atoms={n.id for n in ast.walk(target) if isinstance(n,ast.Name)}
    def additive_terms(node,sign=1,result=None):
        # Exact additive regrouping only; products/divisions remain opaque
        # AST terms. This preserves subtractive cash and other signed claims.
        if result is None:result={}
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub)):
            additive_terms(node.left,sign,result);additive_terms(node.right,-sign if isinstance(node.op,ast.Sub) else sign,result)
        else:
            key=ast.dump(node);result[key]=result.get(key,0)+sign
        return {k:v for k,v in result.items() if v}
    class Expand(ast.NodeTransformer):
        def __init__(self):self.active=set();self.expansions=0
        def visit_Name(self,node):
            if node.id in atoms or node.id not in RULES or len(RULES[node.id])!=1:return node
            if node.id in self.active or self.expansions>=32:raise ValueError('identity expansion bound')
            self.expansions+=1;self.active.add(node.id)
            result=self.visit(ast.parse(RULES[node.id][0],mode='eval').body);self.active.remove(node.id)
            return result
    for rule in RULES[name]:
        tree=ast.parse(rule,mode='eval');tree=Expand().visit(tree)
        if sum(1 for _ in ast.walk(tree))>256:raise ValueError('expanded identity bound')
        if ast.dump(tree)==ast.dump(target) or additive_terms(tree.body)==additive_terms(target.body):return True
    return False


class Missing(ValueError):
    pass


def _requested_source(body):
    """Keep the actual request separate from proven non-target annotations.

    Unknown follow-up instructions cannot be silently discarded. Every suffix
    accepted here is either a non-target disclosure explicitly excluded in the
    question, or a convention already implemented by the exact graph.
    """
    requests=list(re.finditer(r'\b(?:calculate|compute|find|determine|what\s+is)\s+|(?:^|(?<=[.;]))\s*return\s+',body,re.I))
    if requests:tail=body[requests[-1].end():]
    else:
        # A single explicitly displayed supported identity can itself be the
        # request. Its full RHS must match a known relation below.
        identities=[s[0].strip(' .;') for s in _segments(body) if '=' in s[0]]
        if len(identities)!=1:raise ValueError('no unique financial request')
        _target_expression(identities[0]);return identities[0]
    sentence=next(iter(_segments(tail)),None)
    if sentence is None:raise ValueError('empty request')
    source=sentence[0].strip(' .;')
    suffix=tail[sentence.end():].strip(' .;\t\r\n')
    allowed=[r'negative\s+equity\s+remains\s+signed',
             r'do\s+not\s+mistake\s+cash\s+for\s+a\s+debt\s+addition',
             r'a\s+separate\s+non-target\s+FY\d{4}\s+disclosure\s+states\s+'+NUMBER+r';\s*do\s+not\s+use\s+it']
    while suffix:
        match=next((m for p in allowed if (m:=re.match(p+r'(?=[.;\s]|$)',suffix,re.I))),None)
        if match is None:raise ValueError('unparsed follow-up instruction')
        suffix=suffix[match.end():].strip(' .;\t\r\n')
    return source


def solve_financial_graph(question: Mapping[str, Any], *, default_money_scale: Fraction | None = None, allow_unstated_claims: bool = False):
    body = question['question'].split('\n\nAnswer format:')[0]
    if len(body)>16000 or question['answer_spec']['type']!='decimal': return None
    try:
        shared = re.search(r'\ball\s+(?:monetary\s+)?amounts\s+(?:are\s+)?in\s+USD(?:\s+(thousands?|millions?|billions?))?\b',body,re.I)
        if shared: default_money_scale = SCALE.get((shared[1] or '').lower().rstrip('s'),Fraction(1))
        from src.task1.financial_instructions import parse_instructions
        fact_body,controls=parse_instructions(body,_target_expression,lambda name:DIMS[BY_NAME[name].kind])
        target_source = _requested_source(fact_body)
        expression = _target_expression(target_source)
        facts, invalid = _facts(fact_body, default_money_scale)
        rules=RULES.copy();assumptions=[]
        if allow_unstated_claims:
            # This is an explicitly audited estimate, not an invented source
            # literal or a certified full-claims identity. Stated claims still
            # participate and malformed/ambiguous claims never become zero.
            omitted=[name for name in ['minority','preferred_equity'] if name not in facts]
            if omitted and not any(name in invalid for name in omitted):
                rules['ev']=('equity_market+net_debt'+''.join('+'+n for n in ['minority','preferred_equity'] if n in facts),)
                assumptions.append({'quantity':'ev','unstated_claims_assumed_absent':omitted})
            if 'preferred_dividends' not in facts and 'preferred_dividends' not in invalid:
                rules['eps']=('net_income/diluted_shares',)
                assumptions.append({'quantity':'eps','unstated_preferred_dividends_assumed_absent':True})
        values, dimensions, proofs, active, base_values = {}, {}, {}, set(), {}
        def resolve(name):
            if name in values:return values[name]
            if name not in BY_NAME or name in active:raise Missing(name)
            if name in invalid:raise ValueError('ambiguous or invalid source for '+name)
            active.add(name); candidates=[]
            if name in facts:candidates.append((facts[name]['value'], {'kind':'source',**facts[name]['evidence']}))
            for rule in rules.get(name,()):
                dependencies = sorted({n.id for n in ast.walk(ast.parse(rule,mode='eval')) if isinstance(n,ast.Name)})
                try:
                    for dependency in dependencies:resolve(dependency)
                except Missing:continue
                if name=='terminal_value' and (values['required_return']<=values['growth'] or values['required_return']<=-1):
                    raise ValueError('nonconvergent growing perpetuity')
                if name=='holding_return' and (not re.search(r'\bone[- ]year\s+bond\b',body,re.I) or not re.search(r'coupon\s+received\s+separately',body,re.I) or values['purchase_price']<=0):
                    raise ValueError('coupon timing or purchase basis unsupported')
                dim = _dimension(rule,dimensions,values)
                if dim!=DIMS[BY_NAME[name].kind]:raise ValueError('rule dimensional error')
                value = execute(rule,values)
                if value!=second_execute(rule,values):raise ValueError('independent interpreter disagreement')
                candidates.append((value,{'kind':'relation','expression':rule,'dependencies':dependencies,'value':str(value)}))
            active.remove(name)
            if not candidates:raise Missing(name)
            if len({value for value,_ in candidates})!=1:raise ValueError('conflicting financial derivations: '+name)
            value=candidates[0][0];base_values[name]=value
            for control in (c for c in controls if c['target']==name):
                previous=value;applies=True;env={'base':value,'amount':control['amount']};op=control['kind']
                if op=='conditional_set':
                    predicate=value if control['predicate']==name else resolve(control['predicate'])
                    applies={'negative':predicate<0,'positive':predicate>0,'zero':predicate==0}[control['comparison']]
                    code='amount' if applies else 'base'
                elif op=='cap':code='min(base,amount)'
                elif op=='floor':code='max(base,amount)'
                elif op=='scale':code='base*amount'
                elif op=='increase':code='base*(1+amount)' if control['relative'] else 'base+amount'
                elif op=='reduce':code='base*(1-amount)' if control['relative'] else 'base-amount'
                else:raise ValueError('unsupported adjustment')
                value=execute(code,env)
                if value!=second_execute(code,env):raise ValueError('independent adjustment disagreement')
                candidates.append((value,{**{k:str(v) if isinstance(v,Fraction) else v for k,v in control.items()},'kind':'instruction','operation':op,'expression':code,'before':str(previous),'value':str(value),'applied':applies}))
            values[name]=value;dimensions[name]=DIMS[BY_NAME[name].kind]
            proofs[name]=[proof for _,proof in candidates]
            return values[name]
        def evaluate(source,spec,*,before_adjustments=False):
            for node in ast.walk(ast.parse(source,mode='eval')):
                if isinstance(node,ast.Name):resolve(node.id)
            dim = _dimension(source,dimensions,values); outdim,scale = _unit_scale(spec.get('unit','dimensionless'))
            if spec['type']!='decimal' or dim!=outdim:raise ValueError('output unit mismatch')
            env=values
            if before_adjustments:
                if not isinstance(ast.parse(source,mode='eval').body,ast.Name):raise ValueError('unadjusted checkpoint requires one named quantity')
                env={**values,source:base_values[source]}
            value = execute(source,env)
            if value!=second_execute(source,env):raise ValueError('independent final mismatch')
            return format_value(binary(value,scale,'/'),spec)
        final=evaluate(expression,question['answer_spec'])
        steps=[];seen=set()
        for slot in question['trace_spec']['slots']:
            if slot['slot_id'] in seen:raise ValueError('duplicate checkpoint')
            seen.add(slot['slot_id'])
            # Description must be an explicit supported quantity/expression;
            # neither arbitrary slot IDs nor its numeric position choose it.
            desc=re.sub(r'^(?:exact\s+value\s+of|value\s+of|compute|calculate|derive)\s+','',slot.get('description',''),flags=re.I)
            before=bool(re.search(r'\s+before\s+its\s+adjustments\.?$',desc,re.I))
            if before:desc=re.sub(r'\s+before\s+its\s+adjustments\.?$','',desc,flags=re.I)
            source=_target_expression(desc)
            steps.append({'slot_id':slot['slot_id'],'value':evaluate(source,slot['result_spec'],before_adjustments=before)})
        prediction={'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],
                    'case_id':question['case_id'],'final_answer':{'value':final},'steps':steps}
        used_assumptions=[a for a in assumptions if a['quantity'] in values]
        return prediction,{'strategy':'compositional_financial_graph','target_source':target_source,'target_expression':expression,
                           'proofs':proofs,'canonical_values':{n:str(v) for n,v in values.items()},
                           'invalid_source_quantities':invalid,'default_money_scale':str(default_money_scale),
                           'source_instruction_count':len(controls),
                           'routing_gate':'named literal sources; typed relations; agreeing derivations; fully parsed target and checkpoints',
                           'confidence_kind':'bounded structural gate, not calibrated probability',
                           **({'answer_status':'estimate','semantic_verified':False,'assumptions':used_assumptions} if used_assumptions else {})}
    except (KeyError,ValueError,TypeError,SyntaxError,ZeroDivisionError,OverflowError,RecursionError):
        return None
