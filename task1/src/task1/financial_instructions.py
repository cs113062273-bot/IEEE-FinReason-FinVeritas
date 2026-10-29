"""Typed, source-quoted adjustments over explicitly named graph quantities.

No financial rule is supplied here. Each supported instruction binds a graph
quantity and a typed amount; unsupported imperative clauses remain errors.
"""
import re
from fractions import Fraction
from src.task1.equation_fallback import _segments,_unit,COUNT
from src.task1.program_reexecution import parse_number

NUMBER=r'[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d{1,3})?(?:/\d+)?'
AMOUNT=r'(?:'+NUMBER+r'|zero)'
UNIT=r'(?:USD\s+per\s+(?:share|unit)|usd_per_count|(?:thousand|million|billion)\s+(?:USD|shares|units|count)|USD(?:\s+(?:thousand|million|billion))?|percentage\s+points?|basis\s+points?|percent|%|bps?|ratio|multiple|times|count|shares|days)'


def parse_instructions(body,identify,dimension):
    controls=[];masked=list(body)
    def name(text):
        result=identify(text.strip())
        if not re.fullmatch(r'[a-z][a-z0-9_]*',result):raise ValueError('instruction requires a single named quantity')
        dimension(result) # unknown names cannot become new sources
        return result
    def amount(text,unit,expected):
        value=Fraction(0) if text.lower()=='zero' else parse_number(text.replace(',',''))
        if unit is None:
            if value!=0:raise ValueError('nonzero adjustment must state its unit')
            return value,expected
        unit=' '.join(unit.lower().split())
        counts=re.fullmatch(r'(thousand|million|billion)\s+(?:shares|units|count)',unit)
        if counts:return value*{'thousand':1000,'million':10**6,'billion':10**9}[counts[1]],COUNT
        if re.fullmatch(r'usd\s+per\s+(?:share|unit)',unit):unit='usd_per_count'
        if unit in {'multiple','times'}:unit='ratio'
        if unit=='percentage point':unit='percentage points'
        if unit=='basis point':unit='bp'
        dim,scale=_unit(unit);return value*scale,dim
    for segment in _segments(body):
        source=segment[0].strip(' \t\r\n.;');start=segment.start()+len(segment[0])-len(segment[0].lstrip(' \t\r\n.;'))
        if not source:continue
        m=re.fullmatch(r'(?P<op>cap|floor|increase|reduce|scale)\s+(?P<target>.+?)\s+(?:at|by)\s+(?P<amount>'+AMOUNT+r')(?:\s*(?P<unit>'+UNIT+r'))?(?P<relative>\s+of\s+its\s+current\s+value)?',source,re.I)
        if m:
            target=name(m['target']);expected=dimension(target);value,dim=amount(m['amount'],m['unit'],expected);op=m['op'].lower()
            relative=bool(m['relative'])
            if op=='scale' or relative:
                if dim!=(0,0,0) or op not in {'scale','increase','reduce'}:raise ValueError('relative adjustments require an explicit dimensionless factor')
            elif dim!=expected:raise ValueError('adjustment unit differs from target')
            control={'kind':op,'target':target,'amount':value,'relative':relative}
        else:
            m=re.fullmatch(r'If\s+(?P<predicate>.+?)\s+is\s+(?P<sign>negative|positive|zero),\s*set\s+(?P<target>.+?)\s+to\s+(?P<amount>'+AMOUNT+r')(?:\s*(?P<unit>'+UNIT+r'))?',source,re.I)
            if not m:
                if re.match(r'(?:cap|floor|limit|reduce|increase|scale|if|unless|set|adjust|replace|apply)\b',source,re.I):
                    raise ValueError('unparsed financial instruction')
                continue
            predicate=name(m['predicate']);target=name(m['target']);value,dim=amount(m['amount'],m['unit'],dimension(target))
            if dim!=dimension(target):raise ValueError('conditional result unit differs from target')
            control={'kind':'conditional_set','target':target,'amount':value,'predicate':predicate,'comparison':m['sign'].lower()}
        if len(controls)>=24:raise ValueError('instruction count bound')
        control.update(source=source,start=start,end=start+len(source));controls.append(control)
        for i in range(start,start+len(source)):
            if not masked[i].isspace():masked[i]=' '
    return ''.join(masked),controls
