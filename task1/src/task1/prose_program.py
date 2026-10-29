"""Generic explicit prose-to-equation compiler; no financial family lookup.

Declared named quantities and explicit ``X equals Y plus Z`` relations compile
to the existing bounded unit-aware DAG executor. The final public solver still
has an always-answer fallback when this internal candidate cannot compile.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from fractions import Fraction
import re

from src.task1.equation_fallback import solve_equations,_segments,_unit

NUMBER=r'[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:/\d+)?'
UNIT=r'(?:usd_per_count|usd_per_year|USD\s+per\s+(?:share|unit|year)|(?:thousand|million|billion)\s+(?:shares|units|count)|USD(?:\s+(?:thousand|million|billion))?|(?:thousand|million|billion)\s+USD|percent|%|basis\s+points?|bps?|ratio|multiple|times|dimensionless|count|shares|years|days)'
CONNECT=r'(?:is|are|was|were|of|=)'


def words(text):
    text=re.sub(r'(?<=[A-Za-z])[-–](?=[A-Za-z])',' ',text.lower())
    text=re.sub(r'\s+',' ',text).strip(' .')
    text=re.sub(r'^(?:the|an?|exact|signed|unrounded|report|compute|calculate|derive)\s+','',text)
    return text


@dataclass
class Item:
    name:str
    symbol:str
    source:str
    start:int
    end:int
    literal:str|None=None
    expression:str|None=None


def clauses(body):
    # Commas inside grouped numbers remain numeric; other comma-separated
    # declarations preserve each clause's original offsets.
    for segment in _segments(body):
        cuts=[0]+[m.end() for m in re.finditer(r',\s*(?:and\s+)?(?=[A-Za-z])',segment[0])]
        ends=[m.start() for m in re.finditer(r',\s*(?:and\s+)?(?=[A-Za-z])',segment[0])]+[len(segment[0])]
        for begin,end in zip(cuts,ends):
            raw=segment[0][begin:end];text=raw.strip(' .')
            if text:
                start=segment.start()+begin+len(raw)-len(raw.lstrip(' .'))
                yield text,start,start+len(text)


def compile_question(question,*,allow_implicit_target=False):
    body=question['question'].split('\n\nAnswer format:')[0]
    if len(body)>16000 or question['answer_spec']['type']!='decimal':return None
    try:
        items=[];by_name={};declaration_names=set();unparsed=[]
        def add(name,text,start,end,*,literal=None,expression=None):
            name=words(name)
            if not re.fullmatch(r'[a-z][a-z0-9 /&]*',name) or len(name.split())>12 or name in by_name:
                raise ValueError('invalid or duplicate named quantity')
            item=Item(name,'quantity'+str(len(items)),text,start,end,literal,expression)
            items.append(item);by_name[name]=item
            if literal is not None:declaration_names.add(name)
        for text,start,end in clauses(body):
            relation=re.fullmatch(r'(.+?)\s+(?:equals?|equal)\s+(.+)',text,re.I)
            if relation:
                formula=re.sub(r'\s+and\s+may\s+be\s+negative$','',relation[2],flags=re.I)
                add(relation[1],text,start,end,expression=formula);continue
            declaration=re.fullmatch(rf'(.+?)\s+{CONNECT}\s*({NUMBER})\s*({UNIT})?',text,re.I)
            if declaration:
                label,value,unit=declaration.groups()
                embedded=re.search(rf'\s+in\s+({UNIT})$',label,re.I)
                if embedded:
                    if unit and unit.lower()!=embedded[1].lower():raise ValueError('conflicting stated denominations')
                    unit=embedded[1];label=label[:embedded.start()]
                if not unit:
                    if re.search(r'\b(?:percent|percentage)$',label,re.I):unit='percent'
                    elif re.search(r'\bratio$',label,re.I):unit='ratio'
                    else:unit='dimensionless'
                unit=' '.join(unit.lower().split())
                multiplier=Fraction(1)
                if unit.lower() in {'multiple','times'}:unit='ratio'
                if re.fullmatch(r'USD\s+per\s+(?:share|unit)',unit,re.I):unit='usd_per_count'
                elif re.fullmatch(r'USD\s+per\s+year',unit,re.I):unit='usd_per_year'
                elif (count_unit:=re.fullmatch(r'(thousand|million|billion)\s+(?:shares|units|count)',unit,re.I)):
                    multiplier=Fraction({'thousand':1000,'million':1000000,'billion':1000000000}[count_unit[1].lower()]);unit='count'
                _unit(unit)
                value=str(Fraction(value.replace(',',''))*multiplier)
                add(label,text,start,end,literal=value+' '+unit);continue
            unparsed.append(text)
        if not items or len(items)>64 or not any(i.expression for i in items):return None
        # Qualifying constraints cannot silently disappear into a prose ignore
        # list. These require an explicit supported conditional, not a guess.
        if any(re.search(r'\b(?:unless|if|otherwise|cap|capped|minimum|maximum|replace|round\s+each|not|exclude|ignore|except|instead|without)\b',text,re.I) for text in unparsed):return None

        def aliases(item):
            tokens=item.name.split();result={item.name}
            for first in range(len(tokens)):
                for end in range(first+1,len(tokens)+1):
                    phrase=' '.join(tokens[first:end])
                    if phrase not in {'the','in','of','one','period','new','original','total','ratio','percent','rate'}:result.add(phrase)
            if re.search(r'\b(?:ratio|rate|percent)$',item.name):
                result|={name+' ratio' for name in list(result)}
                result.add('ratio')
            return result
        alias_map={}
        for item in items:
            for alias in aliases(item):alias_map.setdefault(alias,[]).append(item)
        def identify(phrase,exclude=None):
            phrase=words(phrase)
            if phrase in by_name and phrase!=exclude:return by_name[phrase]
            options=[i for i in alias_map.get(phrase,[]) if i.name!=exclude]
            source=[i for i in options if i.name in declaration_names]
            if len(source)==1:return source[0]
            if len(options)==1:return options[0]
            raise ValueError('unbound or ambiguous quantity phrase: '+phrase)

        def expression(text,exclude=None):
            normalized=words(text)
            # Multiplication by the explicitly named (one +/- rate) factor.
            factor=re.fullmatch(r'(.+?)\s+(?:times|multiplied by)\s+one\s+(minus|plus)\s+(.+)',normalized)
            if factor:
                left=expression(factor[1],exclude);right=identify(factor[3],exclude).symbol
                return '('+left+')*(1'+('-' if factor[2]=='minus' else '+')+right+')'
            for phrase,op in [('divided by','/'),('multiplied by','*'),('times','*'),('minus','-'),('less','-'),('plus','+')]:
                normalized=re.sub(r'\b'+phrase+r'\b',' '+op+' ',normalized)
            pieces=re.split(r'([()+*/\-])',normalized);result=[]
            for piece in pieces:
                piece=piece.strip()
                if not piece:continue
                if piece in {'(',')','+','-','*','/'}:result.append(piece);continue
                if piece in {'zero','one','two'}:result.append({'zero':'0','one':'1','two':'2'}[piece]);continue
                if re.fullmatch(NUMBER,piece):
                    value=Fraction(piece.replace(',',''));result.append(f'({value.numerator}/{value.denominator})');continue
                result.append(identify(piece,exclude).symbol)
            code=''.join(result);ast.parse(code,mode='eval');return code

        generated=[]
        for item in items:
            generated.append(item.symbol+'='+(item.literal if item.literal is not None else expression(item.expression,item.name)))
        # An explicitly identified final quantity outranks a separate request
        # to report intermediate checkpoint values.
        explicit=[]
        for name,item in by_name.items():
            if re.search(r'\bfinal\s+'+re.escape(name)+r'\b',words(body)):explicit.append(item)
        if len(explicit)>1:return None
        basis='explicit final quantity'
        if explicit:target=explicit[0]
        else:
            requests=list(re.finditer(r'\b(?:compute|calculate|find|determine|what is|report)\s+(.+)',body,re.I))
            if requests:
                text=requests[-1][1].strip(' .')
                names=re.split(r'\s+and\s+|,\s*|\s+then\s+',text,flags=re.I)
                targets=[identify(name) for name in names];target=targets[-1];basis='explicit request'
            elif allow_implicit_target:
                target=next(i for i in reversed(items) if i.expression is not None);basis='last explicit relation, estimated target'
            else:return None
        slots=[]
        for slot in question['trace_spec']['slots']:
            description=slot.get('description','')
            for _ in range(4):
                changed=re.sub(r'^(?:report|exact|signed|unrounded|value of)\s+','',description,flags=re.I)
                if changed==description:break
                description=changed
            description=re.sub(r',\s+which\s+may\s+be\s+negative\.?$','',description,flags=re.I).strip(' .')
            try:item=identify(description);symbol=item.symbol
            except ValueError:
                implied=re.fullmatch(r'(.+?)\s+(?:implied|computed|calculated)\s+by\s+(.+)',description,re.I)
                if implied:
                    item=identify(implied[1]);dependency=identify(implied[2])
                    if item.expression is None or dependency.symbol not in {n.id for n in ast.walk(ast.parse(expression(item.expression,item.name),mode='eval')) if isinstance(n,ast.Name)}:raise ValueError('checkpoint explanation differs from declared relation')
                    symbol=item.symbol
                else:
                    code=expression(description);symbol='checkpointvalue'+str(len(slots));generated.append(symbol+'='+code)
            slots.append({**slot,'description':'Exact value of '+symbol})
        generated.append('Compute '+target.symbol)
        translated={**question,'question':'; '.join(generated)+'.','trace_spec':{'slots':slots}}
        return translated,{'strategy':'compiled_named_prose','target_basis':basis,'target_name':target.name,
                           'generated_program':translated['question'],
                           'source_items':[{'name':i.name,'symbol':i.symbol,'source':i.source,'start':i.start,'end':i.end,'literal':i.literal,'relation':i.expression} for i in items],
                           'unparsed_context':unparsed,'contains_financial_family_lookup':False}
    except (ValueError,KeyError,TypeError,SyntaxError,ZeroDivisionError,OverflowError):return None


def solve(question,*,allow_implicit_target=False):
    compiled=compile_question(question,allow_implicit_target=allow_implicit_target)
    if compiled is None:return None
    translated,audit=compiled;result=solve_equations(translated)
    if result is None:return None
    prediction,math_audit=result
    return prediction,{**audit,'mathematical_execution':math_audit,'semantic_verified':False,
                       'answer_status':'estimate' if 'estimated target' in audit['target_basis'] else 'explicit_program'}
