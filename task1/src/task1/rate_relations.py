"""Named rate/base/time relations, exact source extraction and checkpoints.

Bounded financial grammar; no template IDs, question signatures, stored values
or missing-input defaults. Range disclosures cannot become scenario inputs.
"""
import re
from fractions import Fraction
from src.common.arithmetic import execute,format_value
from src.common.fraction_budget import binary
from src.task1.hidden_program import execute as independent_execute
from src.task1.program_reexecution import parse_number

N=r'[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d{1,3})?(?:/\d+)?'
MONEY=r'USD(?:\s+(?:thousand|million|billion))?'
RATE=r'(?:percent|%|basis\s+points?|bps?|ratio)'
RANGE=rf'(?:,\s+(?:a\s+whole-dollar\s+amount|an?\s+exact\s+decimal)\s+from\s+{N}\s+through\s+{N}\s+inclusive(?:\s+with\s+at\s+most\s+(?:two|\d+)\s+decimal\s+places)?)?'
SCALES={'thousand':1000,'million':10**6,'billion':10**9}

def solve_rate_relations(question):
    body=question['question'].split('\n\nAnswer format:')[0]
    if len(body)>16000 or question['answer_spec']['type']!='decimal':return None
    try:
        # Conditions, fees, changes of rate, and intermediate rounding need
        # richer programs; do not erase them when using a closed-form identity.
        if re.search(r'\b(?:if|unless|otherwise|except|capped|tax|taxes|deduct|fee|fees|monthly|quarterly|variable\s+rate|round\s+(?:each|every))\b',body,re.I):return None
        values={};evidence={};derived={};yearly=set();ratios=set();multiples=set();expressions={};target=None;family=None;reduction_labels=[]
        rounding_tail=r'(?:,?\s+(?:and\s+)?(?:using\s+exact\s+arithmetic\s+and\s+)?round(?:ing)?\s+only\s+the\s+final\s+(?:annual\s+)?USD\s+amount\s+half\s+up\s+to\s+(?:two|2)\s+decimal\s+places)?'
        def request(pattern):
            requests=list(re.finditer(r'\b(?:compute|calculate|find|what\s+is)\s+',body,re.I))
            if len(requests)!=1:raise ValueError('ambiguous requested result')
            text=body[requests[0].start():].strip(' .?')
            if not re.fullmatch(pattern,text,re.I):raise ValueError('unsupported target instruction')
        def fact(name,pattern,kind='number',positive=False):
            matches=list(re.finditer(pattern,body,re.I))
            if len(matches)!=1:raise ValueError('missing or duplicate role '+name)
            m=matches[0];value=parse_number(m['value'].replace(',',''));scale=Fraction(1)
            if kind=='money':
                magnitude=(m.groupdict().get('unit') or '').lower().split()
                scale=Fraction(SCALES.get(magnitude[-1],1)) if magnitude else scale
            if kind=='rate':
                unit=m['unit'].lower();scale=Fraction(1,10000) if re.fullmatch(r'basis\s+points?|bps?',unit) else Fraction(1) if unit=='ratio' else Fraction(1,100)
            value=binary(value,scale,'*')
            if positive and value<=0:raise ValueError('nonpositive '+name)
            values[name]=value;evidence[name]={'source':m[0],'start':m.start(),'end':m.end(),'literal':m['value'],'scale':str(scale),'canonical_value':str(value)}
            return value
        def calculate(name,expression):
            value=execute(expression,values)
            if independent_execute(expression,values)!=value:raise ValueError('independent arithmetic mismatch')
            values[name]=value;derived[name]={'expression':expression,'exact_value':str(value)};return value
        def normalize(text):
            text=re.sub(r'\s+',' ',text).strip(' .?').casefold()
            for _ in range(5):
                replacement=re.sub(r'^(?:report|exact|signed|unrounded|converted)\s+','',text)
                if replacement==text:break
                text=replacement
            return text

        # Any named annual cost/reduction pair can contribute to savings.
        reductions=list(re.finditer(r'\bannual\s+(?P<label>[A-Za-z][A-Za-z -]{0,48}?)\s+cost\s+(?P<value>'+N+r')\s+(?P<unit>'+MONEY+r')'+RANGE+r',?\s+reduced\s+by\s+(?P<rate>'+N+r')\s+(?P<rateunit>'+RATE+r')',body,re.I))
        if reductions and re.search(r'\b(?:compute|calculate|find)\s+(?:combined|total)\s+annual\s+savings\b',body,re.I):
            request(r'(?:compute|calculate|find)\s+(?:combined|total)\s+annual\s+savings(?:\s+as\s+exact\s+[a-z -]+\s+savings\s+plus\s+exact\s+[a-z -]+\s+savings)?'+rounding_tail)
            if len(reductions)>16:raise ValueError('reduction count bound')
            seen=set();terms=[]
            for i,m in enumerate(reductions):
                label=re.sub(r'\s+',' ',m['label']).strip().casefold()
                if label in seen:raise ValueError('duplicate cost label')
                seen.add(label);cost='cost'+str(i);rate='rate'+str(i);name='saving'+str(i)
                values[cost]=binary(parse_number(m['value'].replace(',','')),Fraction(SCALES.get(m['unit'].lower().split()[-1],1)),'*')
                unit=m['rateunit'].lower();values[rate]=parse_number(m['rate'].replace(',',''))*(Fraction(1,10000) if re.fullmatch(r'basis\s+points?|bps?',unit) else Fraction(1) if unit=='ratio' else Fraction(1,100))
                if not 0<=values[rate]<=1:raise ValueError('reduction ratio outside supported range')
                if values[cost]<0:raise ValueError('negative annual cost')
                evidence[cost]={'source':m[0],'start':m.start(),'end':m.end(),'canonical_value':str(values[cost]),'rate_ratio':str(values[rate])}
                calculate(name,cost+'*'+rate);terms.append(name);yearly.add(name);expressions['annual '+label+' savings']=name;reduction_labels.append((label,name))
            target='total_savings';calculate(target,'+'.join(terms));yearly.add(target);family='annual_cost_reductions'

        elif re.search(r'\bwhat\s+is\s+the\s+resulting\s+price\b',body,re.I):
            request(r'what\s+is\s+the\s+resulting\s+price(?:\s+in\s+USD)?')
            if not re.search(r'convert\s+the\s+impact\s+to\s+a\s+ratio,\s+add\s+one,\s+and\s+multiply\s+by\s+the\s+initial\s+price',body,re.I):return None
            fact('initial_price',r'\binitial\s+(?:asset\s+)?price\s+(?:is\s+)?(?P<value>'+N+r')\s+(?P<unit>'+MONEY+r')','money',True)
            fact('impact_ratio',r'\bimpact\s+(?:is\s+)?(?P<value>'+N+r')\s+(?P<unit>'+RATE+r')','rate')
            calculate('price_multiplier','1+impact_ratio');target='resulting_price';calculate(target,'initial_price*price_multiplier')
            family='explicit_signed_rate_multiplier';ratios.add('impact_ratio');multiples.add('price_multiplier')
            expressions.update({'impact ratio':'impact_ratio','price multiplier':'price_multiplier'})

        elif re.search(r'\b(?:compute|calculate|what\s+is)\s+(?:the\s+)?penalty\s+amount\b',body,re.I):
            request(r'(?:compute|calculate|what\s+is)\s+(?:the\s+)?penalty\s+amount(?:\s+in\s+USD)?')
            fact('base',r'\bcovered\s+(?:transaction\s+)?volume\s+(?:is\s+)?(?P<value>'+N+r')\s+(?P<unit>'+MONEY+r')','money')
            fact('rate',r'\bpenalty\s+rate\s+(?:is\s+)?(?P<value>'+N+r')\s+(?P<unit>'+RATE+r')','rate')
            if not re.search(r'convert\s+the\s+percentage\s+to\s+a\s+ratio\s+and\s+multiply\s+it\s+by\s+the\s+volume',body,re.I):return None
            if values['base']<0 or values['rate']<0:return None
            target='penalty';calculate(target,'base*rate');family='explicit_rate_times_base';ratios.add('rate');expressions['penalty ratio']='rate'

        elif re.search(r'\bsimple\s+annual\s+yield\b',body,re.I) and re.search(r'\bcompute\s+total\s+interest\b',body,re.I):
            request(r'compute\s+total\s+interest(?:\s+as\s+principal\s+times\s+the\s+annual\s+yield\s+ratio\s+times\s+years)?'+rounding_tail)
            if not re.search(r'\bignore\s+compounding\s+and\s+principal\s+repayment\b',body,re.I):return None
            fact('principal',r'\bprincipal\s+(?P<value>'+N+r')\s+(?P<unit>'+MONEY+r')','money',True)
            fact('rate',r'\bsimple\s+annual\s+yield\s+(?:is|of)\s+(?P<value>'+N+r')\s+(?P<unit>'+RATE+r')','rate')
            fact('term',r'\bfor\s+(?P<value>'+N+r')\s+years\b',positive=True)
            calculate('annual_interest','principal*rate');yearly.add('annual_interest');target='total_interest';calculate(target,'annual_interest*term');family='simple_interest'
            expressions['annual simple-interest amount used downstream']='annual_interest';expressions['annual simple interest']='annual_interest'

        elif re.search(r'\bcompounds?\s+annually\b',body,re.I) and re.search(r'\bcompute\s+total\s+benefit\s+as\s+compound\s+interest\s+plus\s+the\s+annual\s+bonus\s+times\s+years',body,re.I):
            request(r'compute\s+total\s+benefit\s+as\s+compound\s+interest\s+plus\s+the\s+annual\s+bonus\s+times\s+years,?\s+excluding\s+principal\.\s+Use\s+exact\s+arithmetic\s+and\s+round\s+only\s+the\s+final\s+USD\s+amount\s+half\s+up\s+to\s+(?:two|2)\s+decimal\s+places')
            if not re.search(r'fractional\s+.+?savings\s+blocks\s+earn\s+a\s+proportional\s+bonus',body,re.I):return None
            fact('principal',r'\bprincipal\s+(?P<value>'+N+r')\s+(?P<unit>'+MONEY+r')','money',True)
            fact('rate',r'\bannual\s+coupon\s+yield\s+(?:of|is)\s+(?P<value>'+N+r')\s+(?P<unit>'+RATE+r')','rate')
            fact('term',r'\bcompounds?\s+annually\s+for\s+(?P<value>'+N+r')\s+years\b',positive=True)
            fact('savings',r'\bproject\s+saves\s+(?P<value>'+N+r')\s+(?P<unit>'+MONEY+r')\s+each\s+year','money')
            match=re.search(r'\bpays\s+the\s+investor\s+(?P<bonus>'+N+r')\s+(?P<bonusunit>'+MONEY+r')\s+for\s+every\s+(?P<block>'+N+r')\s+(?P<blockunit>'+MONEY+r')\s+of\s+annual\s+savings',body,re.I)
            if not match:return None
            for name in ['bonus','block']:
                values[name]=binary(parse_number(match[name].replace(',','')),Fraction(SCALES.get(match[name+'unit'].lower().split()[-1],1)),'*')
                evidence[name]={'source':match[0],'start':match.start(),'end':match.end(),'canonical_value':str(values[name])}
            if values['term'].denominator!=1 or not 0<values['term']<=100 or values['rate']<=-1 or values['block']<=0:return None
            calculate('compound_interest','principal*((1+rate)**term-1)');calculate('annual_bonus','savings*bonus/block');calculate('total_bonus','annual_bonus*term')
            target='total_benefit';calculate(target,'compound_interest+total_bonus');family='compound_interest_periodic_bonus';yearly.add('annual_bonus')
            expressions.update({'compound interest':'compound_interest','proportional annual bonus':'annual_bonus','total bonus over the term':'total_bonus'})

        elif re.search(r'\bdouble-declining-balance\s+depreciation\b',body,re.I):
            if not re.search(r'\bresidual\s+value\s+is\s+zero\b',body,re.I) or not re.search(r'no\s+switch\s+to\s+straight-line',body,re.I):return None
            fact('cost',r'\bpurchases\s+an?\s+asset\s+for\s+(?P<value>'+N+r')\s+(?P<unit>'+MONEY+r')','money',True)
            fact('life',r'\bwith\s+a\s+useful\s+life\s+of\s+(?P<value>'+N+r')\s+years','number',True)
            year=re.search(r'\bcompute\s+book\s+value\s+at\s+the\s+end\s+of\s+Year\s+(?P<value>'+N+r')',body,re.I)
            if not year:return None
            if body[year.end():].strip(' .?'):return None
            values['term']=parse_number(year['value']);evidence['term']={'source':year[0],'start':year.start(),'end':year.end(),'canonical_value':str(values['term'])}
            if values['life']<2 or values['term'].denominator!=1 or not 1<=values['term']<=100:return None
            # Scope of the supplied no-switch statement must cover the term.
            horizon=re.search(r'no\s+switch\s+to\s+straight-line\s+depreciation\s+occurs\s+during\s+the\s+first\s+(two|\d+)\s+years',body,re.I)
            if not horizon or int(values['term'])>int('2' if horizon[1].lower()=='two' else horizon[1]):return None
            calculate('ddb_rate','2/life');ratios.add('ddb_rate');calculate('year1_balance','cost*(1-ddb_rate)');calculate('year2_depreciation','year1_balance*ddb_rate')
            target='closing_balance';calculate(target,'cost*(1-ddb_rate)**term');family='double_declining_balance'
            expressions.update({'annual ddb rate as a rational value':'ddb_rate','first-year closing book value used downstream':'year1_balance','second-year depreciation used in the final subtraction':'year2_depreciation'})
        else:return None

        def rendered(name,spec):
            if spec['type']!='decimal':raise ValueError('decimal result required')
            unit=spec['unit'];value=values[name]
            if name in ratios:
                scale={'ratio':Fraction(1),'ratio_per_year':Fraction(1),'percent':Fraction(1,100),'basis_point':Fraction(1,10000)}.get(unit)
            elif name in multiples:scale=Fraction(1) if unit in {'multiple','dimensionless','ratio'} else None
            elif name in yearly:scale=Fraction(1) if unit=='usd_per_year' else None
            else:scale={'usd':Fraction(1),'usd_million':Fraction(10**6)}.get(unit)
            if scale is None:raise ValueError('result dimension mismatch')
            return format_value(binary(value,scale,'/'),spec)
        steps=[]
        for slot in question['trace_spec']['slots']:
            description=normalize(slot['description']);name=expressions.get(description)
            if name is None and family=='annual_cost_reductions':
                label=re.fullmatch(r'annual\s+(.+?)\s+savings',description)
                if label:
                    candidates=[value for phrase,value in reduction_labels if re.search(r'\b'+re.escape(label[1])+r'\b',phrase.replace('-',' '))]
                    if len(candidates)==1:name=candidates[0]
            if name is None:raise ValueError('unbound checkpoint meaning')
            steps.append({'slot_id':slot['slot_id'],'value':rendered(name,slot['result_spec'])})
        prediction={'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],'case_id':question['case_id'],
                    'final_answer':{'value':rendered(target,question['answer_spec'])},'steps':steps}
        return prediction,{'strategy':'named_rate_relations','family':family,'source_facts':evidence,'exact_derivations':derived,
                           'arithmetic_verified':True,'semantic_scope':'bounded declared rate/base/time grammar;all required checkpoint meanings matched'}
    except (ValueError,KeyError,TypeError,SyntaxError,ArithmeticError,RecursionError):return None
