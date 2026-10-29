"""Bounded, source-bound financial series and time-weighted measures.

Periods and vector lengths come from the question. No case IDs, gold values,
numeric position retrieval, external rates, or model calls are used.
"""
import ast
import re
from fractions import Fraction

from src.common.arithmetic import execute,format_value
from src.task1.hidden_program import execute as second_execute
from src.task1.financial_graph import NUMBER,SCALE
from src.task1.program_reexecution import parse_number,source_number_witnesses
from src.task1.interval_program import solve as solve_interval


def solve_series(question):
    raw=question['question'].split('\n\nAnswer format:')[0]
    if len(raw)>16000 or question['answer_spec']['type']!='decimal':return None
    try:
        body=raw.strip();offset=len(raw)-len(raw.lstrip());money_scale=None
        header=re.match(r'All\s+monetary\s+amounts\s+are\s+in\s+USD(?:\s+(thousand|million|billion))?(?:\s+unless\s+an\s+explicit\s+different\s+currency\s+or\s+unit\s+is\s+stated)?\.\s*',body,re.I)
        if header:money_scale=SCALE.get((header[1] or '').lower(),Fraction(1));offset+=header.end();body=body[header.end():]
        note=re.search(r'\s*A\s+separate\s+non-target\s+FY\d{4}\s+disclosure\s+states\s+'+NUMBER+r';\s*do\s+not\s+use\s+it\.\s*$',body,re.I)
        if note:body=body[:note.start()]
        values={};proofs=[];dimensions={};evidence=[];target=None;kind=None
        def source(match,group,name,dimension='ratio',scale=Fraction(1)):
            value=parse_number(match[group].replace(',',''))*scale
            values[name]=value;dimensions[name]=dimension
            evidence.append({'name':name,'source':match[group],'start':offset+match.start(group),'end':offset+match.end(group),'scale':str(scale),'value':str(value)})
            return value
        def node(name,expression,dimension='ratio'):
            value=execute(expression,values)
            if value!=second_execute(expression,values):raise ValueError('independent series disagreement')
            values[name]=value;dimensions[name]=dimension;proofs.append({'name':name,'expression':expression,'value':str(value)})
        def match(pattern):return re.fullmatch(pattern,body.strip(),re.I)
        # Time weighting is held months / disclosed fiscal-year months; the
        # additional shares never replace the original outstanding balance.
        m=match(r'Net\s+income\s+(?P<income>'+NUMBER+r');\s*initial\s+common\s+shares\s+(?P<initial>'+NUMBER+r')\s+million;\s*(?P<extra>'+NUMBER+r')\s+million\s+extra\s+shares\s+outstanding\s+for\s+the\s+last\s+(?P<held>'+NUMBER+r')\s+months\s+of\s+a\s+(?P<year>'+NUMBER+r')-month\s+year\.\s*Compute\s+weighted\s+average\s+shares\s+then\s+basic\s+EPS\.')
        if m:
            if money_scale is None:return None
            source(m,'income','net income','money',money_scale);initial=source(m,'initial','initial shares','count',10**6);extra=source(m,'extra','additional shares','count',10**6)
            held=source(m,'held','held months');year=source(m,'year','year months')
            if initial<0 or extra<0 or not 0<=held<=year or year<=0:return None
            # AST names are separate from human-facing quantity descriptions.
            values.update(income=values['net income'],initial=initial,extra=extra,held=held,year=year)
            node('period_weight','held/year');node('weighted_shares','initial+extra*period_weight','count');node('basic_eps','income/weighted_shares','price');target='basic_eps';kind='time_weighted_shares'
        if target is None:
            m=match(r'FY(?P<current_year>\d{4})\s+sales\s+were\s+(?P<current>'+NUMBER+r')\s+and\s+FY(?P<prior_year>\d{4})\s+sales\s+were\s+(?P<prior>'+NUMBER+r')\.\s*Determine\s+the\s+absolute\s+change\s+and\s+year-over-year\s+percentage\s+change\s+in\s+sales;\s*final\s+answer\s+percentage\s+in\s+percent\s+points\.')
            if m:
                if int(m['current_year'])-int(m['prior_year'])!=1:return None
                source(m,'current','current',scale=money_scale or Fraction(1));source(m,'prior','prior',scale=money_scale or Fraction(1))
                node('absolute_change','current-prior','money' if money_scale else 'ratio');node('yoy_change','(current-prior)/prior','ratio');target='yoy_change';kind='signed_prior_period_change'
        if target is None:
            m=match(r'Sales\s+changed\s+from\s+(?P<prior>'+NUMBER+r')\s+in\s+FY(?P<prior_year>\d{4})\s+to\s+(?P<current>'+NUMBER+r')\s+in\s+FY(?P<current_year>\d{4})\.\s*Compute\s+the\s+(?P<duration>two|\d+)-year\s+CAGR,\s*percent\.\s*Do\s+not\s+divide\s+a\s+simple\s+percentage\s+by\s+(?P<divisor>\d+)\.')
            if m:
                duration=int(m['current_year'])-int(m['prior_year']);stated=2 if m['duration'].lower()=='two' else int(m['duration'])
                if duration!=stated or int(m['divisor'])!=duration or not 1<=duration<=100:return None
                old=source(m,'prior','prior');new=source(m,'current','current');source(m,'prior_year','prior_year');source(m,'current_year','current_year')
                if old<=0 or new<0:return None
                spec=question['answer_spec']
                if spec['unit'] not in {'percent','ratio'} or question['trace_spec']['slots']:return None
                factor='100' if spec['unit']=='percent' else '1'
                expression=factor+'*((current/prior)**(1/(current_year-prior_year))-1)'
                witnesses=source_number_witnesses(raw)
                for e in evidence:witnesses.setdefault(parse_number(e['source']),[]).append(e)
                rendered,certificate=solve_interval({'variables':{n:str(v) for n,v in values.items()},'steps':{},'final_expression':expression},witnesses,spec)
                return {'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],'case_id':question['case_id'],'final_answer':{'value':rendered},'steps':[]},{'strategy':'source_bound_series','series_kind':'dated_cagr','sources':evidence,'interval_program':certificate}
        if target is None:
            m=match(r'FCF\s+years\s+1-(?P<last>\d+)\s+are\s+(?P<flows>.+?)\.\s*At\s+year\s+(?P<terminal>\d+),\s*next-year\s+FCF\s*\(year\s+(?P<next>\d+)\)\s+is\s+(?P<nextflow>'+NUMBER+r'),\s*discount\s+rate\s+(?P<discount>'+NUMBER+r')%,\s*perpetual\s+growth\s+(?P<growth>'+NUMBER+r')%\.\s*Find\s+enterprise\s+DCF\s+today:\s*(?P<formula>.+)\.')
            if m:
                n=int(m['last'])
                if money_scale is None or not 1<=n<=24 or int(m['terminal'])!=n or int(m['next'])!=n+1:return None
                flows=[parse_number(v.strip().replace(',','')) for v in re.split(r',\s+',m['flows'])]
                if len(flows)!=n:return None
                # Record the complete disclosed vector, including all signs.
                evidence.append({'name':'cash flow vector','source':m['flows'],'start':offset+m.start('flows'),'end':offset+m.end('flows')})
                for i,v in enumerate(flows,1):values['FCF'+str(i)]=v*money_scale
                source(m,'nextflow','nextflow','money',money_scale);r=source(m,'discount','r',scale=Fraction(1,100));g=source(m,'growth','g',scale=Fraction(1,100))
                if r<=g or r<=-1:return None
                tv='TV'+str(n);node(tv,'nextflow/(r-g)','money')
                terms=[('FCF'+str(i)+('+'+tv if i==n else '')) for i in range(1,n+1)]
                expected='+'.join('('+term+')/(1+r)**'+str(i) for i,term in enumerate(terms,1))
                class Identity(ast.NodeTransformer):
                    def visit_Name(self,node):
                        canonical={name.casefold():name for name in values}
                        return ast.copy_location(ast.Name(canonical.get(node.id.casefold(),node.id),ast.Load()),node)
                    def visit_BinOp(self,node):
                        node=self.generic_visit(node)
                        return node.left if isinstance(node.op,ast.Pow) and isinstance(node.right,ast.Constant) and node.right.value==1 else node
                shape=lambda s:ast.dump(Identity().visit(ast.parse(s.replace('^','**'),mode='eval')))
                if shape(m['formula'])!=shape(expected):return None
                node('present_value',expected,'money');target='present_value';kind='dated_discounted_series_with_terminal_value'
        if target is None:
            m=match(r'Project\s+initial\s+cost\s+at\s+time\s+0\s+is\s+(?P<initial>'+NUMBER+r'),\s*cash\s+receipts\s+at\s+ends\s+of\s+years\s+(?P<years>[\d,\s]+):\s*(?P<flows>.+?);\s*discount\s+rate\s+(?P<discount>'+NUMBER+r')%\.\s*Calculate\s+NPV\s+with\s+outflow\s+at\s+time\s+0\.')
            if m:
                years=[int(y.strip()) for y in m['years'].split(',')];flows=[parse_number(v.strip()) for v in re.split(r',\s+',m['flows'])]
                if money_scale is None or not 1<=len(years)<=24 or years!=list(range(1,len(years)+1)) or len(years)!=len(flows):return None
                source(m,'initial','initial','money',money_scale);r=source(m,'discount','r',scale=Fraction(1,100))
                if r<=-1:return None
                evidence.append({'name':'cash receipt vector','source':m['flows'],'start':offset+m.start('flows'),'end':offset+m.end('flows')})
                for i,v in enumerate(flows,1):values['receipt'+str(i)]=v*money_scale
                node('net_present_value','-initial+'+'+'.join('receipt'+str(i)+'/(1+r)**'+str(i) for i in years),'money');target='net_present_value';kind='dated_net_present_value'
        if target is None:
            m=match(r'(?P<count>Two|\d+)\s+segments\s+sell\s+(?P<volumes>.+?)\s+units\s+at\s+prices\s+(?P<prices>.+?)\s+USD\s+per\s+unit\.\s*Calculate\s+total\s+sales,\s*total\s+volume,\s*and\s+volume-weighted\s+average\s+selling\s+price\.\s*Do\s+not\s+average\s+prices\s+arithmetically\.')
            if m:
                n=2 if m['count'].lower()=='two' else int(m['count'])
                if not 1<=n<=24:return None
                vectors=[]
                for label in ['volumes','prices']:
                    parts=re.split(r',\s*(?:and\s+)?|\s+and\s+',m[label],flags=re.I);vector=[parse_number(x.strip()) for x in parts]
                    if len(vector)!=n:return None
                    vectors.append(vector);evidence.append({'name':label,'source':m[label],'start':offset+m.start(label),'end':offset+m.end(label)})
                if any(v<0 for v in vectors[0]):return None
                for i,(volume,price) in enumerate(zip(*vectors)):
                    values['volume'+str(i)]=volume;values['price'+str(i)]=price
                node('total_sales','+'.join('volume'+str(i)+'*price'+str(i) for i in range(n)),'money')
                node('total_volume','+'.join('volume'+str(i) for i in range(n)),'count')
                node('weighted_price','total_sales/total_volume','price');target='weighted_price';kind='volume_weighted_price'
        if target is None:return None
        def render(name,spec):
            if spec['type']!='decimal':raise ValueError('series outputs must be numeric')
            unit=spec['unit'];dim=dimensions[name];scale=Fraction(1)
            if dim=='money':
                if unit not in {'usd','usd_million'}:raise ValueError('money output mismatch')
                if unit=='usd_million':scale=Fraction(10**6)
            elif dim=='count':
                if unit!='count':raise ValueError('count output mismatch')
            elif dim=='price':
                if unit!='usd_per_count':raise ValueError('price output mismatch')
            elif unit=='percent':scale=Fraction(1,100)
            elif unit not in {'ratio','multiple','dimensionless'}:raise ValueError('ratio output mismatch')
            return format_value(values[name]/scale,spec)
        aliases={'weighted average shares':'weighted_shares','basic eps':'basic_eps','period weight':'period_weight','absolute change':'absolute_change','year-over-year percentage change':'yoy_change','present value':'present_value','net present value':'net_present_value','total sales':'total_sales','total volume':'total_volume','volume-weighted average selling price':'weighted_price'}
        steps=[]
        for slot in question['trace_spec']['slots']:
            desc=re.sub(r'^(?:exact\s+value\s+of|exact|report)\s+','',' '.join(slot['description'].lower().split())).strip(' .')
            name=aliases.get(desc,desc)
            if name not in dimensions:raise ValueError('unknown series checkpoint')
            steps.append({'slot_id':slot['slot_id'],'value':render(name,slot['result_spec'])})
        return {'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],'case_id':question['case_id'],'final_answer':{'value':render(target,question['answer_spec'])},'steps':steps},{'strategy':'source_bound_series','series_kind':kind,'sources':evidence,'program':proofs,'arithmetic_verified':True}
    except (ValueError,KeyError,TypeError,SyntaxError,ArithmeticError,RecursionError):return None
