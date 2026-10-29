"""Directed, source-quoted exchange routes; never assume quote orientation.

Different quoted cycles may contain arbitrage. Only the explicitly requested
route is followed; inverse quotes are used only when no direct quote exists.
This bounded grammar uses no real exchange-rate or currency database.
"""
import re
from fractions import Fraction
from src.common.arithmetic import execute,format_value
from src.common.fraction_budget import binary
from src.task1.hidden_program import execute as independent_execute
from src.task1.program_reexecution import parse_number
from src.task1.equation_fallback import _segments

NUMBER=r'[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d{1,3})?(?:/\d+)?'
CODE=r'[A-Za-z][A-Za-z0-9_]{0,15}'
ASSET=r'(?:(?:units?\s+of\s+)?currency\s+|units?\s+of\s+|unit\s+of\s+)?('+CODE+r')'
QUOTES=[re.compile(r'(?<![\w.])(?P<value>'+NUMBER+r')\s+'+ASSET+r'\s+per\s+'+ASSET+r'(?!\w)',re.I),
        re.compile(r'(?<!\w)(?P<prefix>'+CODE+r')\s+(?P<value>'+NUMBER+r')\s+per\s+'+ASSET+r'(?!\w)',re.I)]
ORDINAL={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8}


def solve_cross_quote(question,*,allow_output_currency_estimate=False):
    """Two explicit common-currency quotes, directed by their stated units.

    The optional estimate mode records conflicting output currency metadata;
    it is used only by the existing mandatory best-effort layer.
    """
    raw=question['question'].split('\n\nAnswer format:')[0]
    if len(raw)>12000 or question['answer_spec']['type']!='decimal':return None
    try:
        header=re.match(r'All\s+monetary\s+amounts\s+are\s+in\s+USD\s+million\s+unless\s+an\s+explicit\s+different\s+currency\s+or\s+unit\s+is\s+stated\.\s*',raw,re.I)
        offset=header.end() if header else 0;body=raw[offset:]
        m=re.fullmatch(r'Convert\s+(?P<amount>'+NUMBER+r')\s+million\s+(?P<origin>'+CODE+r')\s+to\s+(?P<destination>'+CODE+r')\s+million\.\s*(?P<label_a>'+CODE+r')/(?P<label_common_a>'+CODE+r')\s+is\s+(?P<a>'+NUMBER+r')\s+(?P<common_a>'+CODE+r')\s+per\s+1\s+(?P<quote_a>'+CODE+r');\s*(?P<label_b>'+CODE+r')/(?P<label_common_b>'+CODE+r')\s+is\s+(?P<b>'+NUMBER+r')\s+(?P<common_b>'+CODE+r')\s+per\s+1\s+(?P<quote_b>'+CODE+r')\.\s*Compute\s+(?P<intermediate>'+CODE+r')\s+intermediate\s+and\s+final\s+(?P<final>'+CODE+r');\s*do\s+not\s+invert\s+the\s+first\s+quote\.',body,re.I)
        if not m:return None
        word=lambda k:m[k].upper()
        if not word('origin')==word('quote_a')==word('label_a') or not word('destination')==word('quote_b')==word('label_b')==word('final'):return None
        if len({word(k) for k in ['common_a','common_b','label_common_a','label_common_b','intermediate']})!=1:return None
        if len({word('origin'),word('destination'),word('common_a')})!=3:return None
        values={k:parse_number(m[k].replace(',','')) for k in ['amount','a','b']}
        if values['a']<=0 or values['b']<=0:return None
        intermediate=execute('amount*a',values);values['intermediate']=intermediate;final=execute('intermediate/b',values)
        if intermediate!=independent_execute('amount*a',values) or final!=independent_execute('intermediate/b',values):return None
        spec=question['answer_spec'];unit=spec['unit'];mismatch=word('destination')!='USD' and unit in {'usd','usd_million'}
        if mismatch and not allow_output_currency_estimate:return None
        if unit not in {'usd','usd_million','count',word('destination').lower()+'_million'} or question['trace_spec']['slots']:return None
        if unit=='usd' and word('destination')!='USD':return None
        rendered=format_value(final if unit.endswith('_million') else binary(final,Fraction(10**6),'*'),spec)
        return {'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],'case_id':question['case_id'],'final_answer':{'value':rendered},'steps':[]},{'strategy':'directed_cross_quote','arithmetic_verified':True,'target_currency':word('destination'),'intermediate_currency':word('common_a'),'intermediate_millions':str(intermediate),'final_millions':str(final),
            'sources':[{'name':k,'source':m[k],'start':offset+m.start(k),'end':offset+m.end(k)} for k in ['amount','a','b']],
            **({'answer_status':'estimate','semantic_verified':False,'output_currency_metadata_mismatch':{'requested':word('destination')+' million','answer_spec_unit':unit,'assumption':'Question explicitly requested currency; numeric millions returned in that currency.'}} if mismatch else {})}
    except (ValueError,KeyError,TypeError,SyntaxError,ArithmeticError,RecursionError):return None

def solve_currency_graph(question):
    cross=solve_cross_quote(question)
    if cross is not None:return cross
    body=question['question'].split('\n\nAnswer format:')[0]
    if len(body)>12000 or question['answer_spec']['type']!='decimal':return None
    try:
        start=None;quotes={};route=None;target=None;evidence=[]
        for segment in _segments(body):
            text=segment[0].strip(' \t\r\n.;');position=segment.start()+len(segment[0])-len(segment[0].lstrip(' \t\r\n.;'))
            if not text:continue
            initial=re.fullmatch(r'(?:start\s+with|initial\s+balance\s+is|starting\s+amount\s+is)\s+('+CODE+r')\s+('+NUMBER+')',text,re.I)
            if initial:
                if start is not None:raise ValueError('duplicate starting balance')
                start=(initial[1].upper(),parse_number(initial[2].replace(',','')))
                evidence.append({'kind':'starting_balance','source':text,'start':position,'end':position+len(text)});continue
            quote_header=re.match(r'(?:the\s+)?(?:exact\s+)?(?:conversion|exchange)\s+rates?\s+(?:are|is)\s+',text,re.I)
            if quote_header:
                content=text[quote_header.end():];found=[]
                for index,pattern in enumerate(QUOTES):
                    for match in pattern.finditer(content):
                        if any(match.start()<end and match.end()>begin for begin,end,_,_,_ in found):continue
                        if index==0:destination,source=match[2].upper(),match[3].upper()
                        else:destination,source=match['prefix'].upper(),match[3].upper()
                        value=parse_number(match['value'].replace(',',''))
                        found.append((match.start(),match.end(),source,destination,value))
                cursor=0
                for begin,end,source,destination,value in sorted(found):
                    if not re.fullmatch(r'[\s,]*(?:and\s+)?',content[cursor:begin],re.I):raise ValueError('unparsed quote modifier')
                    if value<=0 or source==destination or (source,destination) in quotes:raise ValueError('duplicate/nonpositive conversion quote')
                    quotes[source,destination]=value
                    evidence.append({'kind':'quote','from':source,'to':destination,'rate':str(value),
                                     'source':content[begin:end],'start':position+quote_header.end()+begin,'end':position+quote_header.end()+end})
                    cursor=end
                if not found or content[cursor:].strip():raise ValueError('incomplete quote grammar')
                continue
            request=re.fullmatch(r'convert\s+(.+?)\s+(?:by\s+multiplication\s*,\s*)?then\s+(?:compute|calculate|report)\s+(.+)',text,re.I)
            if request:
                if route is not None:raise ValueError('multiple requested routes')
                legs=re.split(r',\s*(?:and\s+)?|\s+and\s+',request[1],flags=re.I);route=[]
                for leg in legs:
                    match=re.fullmatch(r'('+CODE+r')\s+(?:back\s+)?to\s+('+CODE+r')',leg.strip(),re.I)
                    if not match:raise ValueError('unparsed conversion leg')
                    route.append((match[1].upper(),match[2].upper()))
                target=request[2].strip();continue
            if re.fullmatch(r'generated\s+inputs\s+produce\s+whole\s+intermediate\s+currency\s+counts|use\s+no\s+fees\s+or\s+intermediate\s+rounding|use\s+exact\s+arithmetic|no\s+fees\s+apply',text,re.I):continue
            raise ValueError('unparsed currency instruction')
        if start is None or not route or not 1<=len(route)<=8 or len(quotes)>16:return None
        if route[0][0]!=start[0]:return None
        current,value=start;values={'starting_amount':value};proofs=[];balances=[]
        for index,(source,destination) in enumerate(route,1):
            if source!=current:raise ValueError('disconnected route')
            if (source,destination) in quotes:rate=quotes[source,destination];operator='*';orientation='direct'
            elif (destination,source) in quotes:rate=quotes[destination,source];operator='/';orientation='inverse'
            else:raise ValueError('missing quoted conversion')
            expression='amount'+operator+'rate';env={'amount':value,'rate':rate}
            result=execute(expression,env)
            if result!=independent_execute(expression,env):raise ValueError('interpreter disagreement')
            proofs.append({'trade':index,'from':source,'to':destination,'orientation':orientation,'expression':expression,'amount':str(value),'quoted_rate':str(rate),'result':str(result)})
            value=result;current=destination;balances.append((current,value))
        if current!='USD' or start[0]!='USD':return None
        final_target=re.fullmatch(r'ending\s+USD\s+minus\s+starting\s+USD|ending\s+USD|(?:the\s+)?USD\s+profit',target,re.I)
        if not final_target:return None
        difference=bool(re.search(r'minus|profit',target,re.I));final=binary(value,start[1],'-') if difference else value
        def render(amount,spec,currency):
            if spec['type']!='decimal':raise ValueError('numeric amount required')
            unit=spec['unit'];scale=Fraction(1)
            if currency=='USD':
                if unit not in {'usd','usd_million'}:raise ValueError('USD amount requires monetary output')
                scale=Fraction(10**6) if unit=='usd_million' else scale
            elif unit!='count':raise ValueError('foreign currency units require count output')
            return format_value(binary(amount,scale,'/'),spec)
        steps=[]
        for slot in question['trace_spec']['slots']:
            description=' '.join(slot['description'].split()).rstrip('.').casefold()
            match=re.fullmatch(r'(?:currency\s+)?('+CODE+r')\s+units\s+after\s+trade\s+('+('|'.join(ORDINAL))+r'|[1-8])',description,re.I)
            if match:
                index=ORDINAL.get(match[2].lower(),int(match[2]) if match[2].isdigit() else 0)
                if not 1<=index<=len(balances) or balances[index-1][0]!=match[1].upper():raise ValueError('checkpoint currency/leg mismatch')
                currency,amount=balances[index-1]
            elif description=='usd after completing the cycle':currency,amount=current,value
            else:raise ValueError('unparsed conversion checkpoint')
            steps.append({'slot_id':slot['slot_id'],'value':render(amount,slot['result_spec'],currency)})
        prediction={'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],'case_id':question['case_id'],
                    'final_answer':{'value':render(final,question['answer_spec'],'USD')},'steps':steps}
        return prediction,{'strategy':'directed_currency_graph','quotes':evidence,'requested_route':route,'trades':proofs,
                           'target':target,'arithmetic_verified':True,'external_rates_used':False}
    except (ValueError,KeyError,TypeError,SyntaxError,ArithmeticError,RecursionError):return None
