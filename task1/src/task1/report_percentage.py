"""Bind percentage computations to raw report rows and dated prose.

No case IDs, reference answers, model answers, or amount-specific rules are used.
This bounded reader preserves explicit column/date/scale witnesses. Where a
lease question omits its column, the selected finance-lease interpretation is
an estimate and remains disclosed as such.
"""
from __future__ import annotations

from datetime import date
from fractions import Fraction
import re

from src.common.arithmetic import execute, format_value
from src.common.fraction_budget import checked
from src.task1.hidden_program import execute as second_execute

NUM=r'[-+]?\d[\d,]*(?:\.\d+)?'
YEAR=re.compile(r'\b(?:19|20)\d{2}\b')
SCALE={'billion':10**9,'million':10**6,'thousand':10**3}
STOP=set('what was were is are the of a an in on at to from between and as or for by with total percent percentage change increase decrease during number'.split())


def tokens(s):
    s=re.sub(r'\bof(?=shares|units|publicly)', 'of ', s.lower())
    s=re.sub(r'\bnon[\s-]+(?=interest|cancelable|cancellable|vested)', 'non', s)
    return [w.rstrip('s') for w in re.findall(r'[a-z]+',s) if w not in STOP]


def words(s):
    return set(tokens(s))


def score(label,target):
    a,b=words(label),words(target)
    def pairs(s):
        ts=tokens(s)
        return set(zip(ts,ts[1:]))
    pa,pb=pairs(label),pairs(target)
    return len(a&b)/max(1,len(b))+.15*len(pa&pb)/max(1,len(pb))


def number(s):
    m=re.search(NUM,s.replace('\u2212','-'))
    if m is None:raise ValueError('no numeric cell')
    value=checked(Fraction(m[0].replace(',','')))
    # Accounting parentheses, including OCR's duplicated negative rendering.
    if re.match(r'^\s*\$?\s*\(',s) and value>0:value=-value
    return value


def years(s):return [int(x) for x in YEAR.findall(s)]


def pick(items,target,minimum=0.35):
    ranked=sorted(((score(label,target),label,value) for label,value in items),key=lambda x:(-x[0],x[1]))
    if not ranked or ranked[0][0]<minimum:return None
    tied=[x for x in ranked if x[0]==ranked[0][0]]
    if len({repr(x[2]) for x in tied})!=1:return None
    return ranked[0][2]


def prose_series(lines,target):
    candidates=[]
    for line in lines:
        if '$' not in line:continue
        # Exclude the actual-return comparator from an expected-return series.
        part=re.split(r'\bcompared with the actual\b',line,flags=re.I)[0]
        ms=list(re.finditer(r'\$\s*\(?\s*('+NUM+r')\s*\)?\s*(billion|million|thousand)?',part,re.I))
        ys=years(part)
        if not ms or len(ms)!=len(ys) or len(set(ys))!=len(ys):continue
        if len(ms)>1 and 'respectively' not in part.lower() and not re.search(r'\b(?:in|at december 31\s*,?)\s+(?:19|20)\d{2}',part):continue
        label=part[:ms[0].start()]
        if 'vested' in target and 'vested' not in label:continue
        if 'total fair value' in target and 'total fair value' not in label:continue
        if 'expected return' in target and ('expected return' not in label or 'rate' in target):continue
        unit=next((m[2].lower() for m in ms if m[2]),None)
        vals={y:Fraction(m[1].replace(',',''))*SCALE.get((m[2] or unit or '').lower(),1) for y,m in zip(ys,ms)}
        candidates.append((label,{'values':vals,'source':line,'label':label}))
    if not candidates:return None
    best=max(score(label,target) for label,_ in candidates)
    selected=[value for label,value in candidates if score(label,target)==best]
    if best<0.35:return None
    if len(selected)==1:return selected[0]
    # Adjacent clauses may describe different years of one named measure.
    # Conflicting values for the same year are never silently ranked.
    if 'expected return' not in target:return None
    merged={}
    for entry in selected:
        for y,v in entry['values'].items():
            if y in merged and merged[y]!=v:return None
            merged[y]=v
    return {'values':merged,'source':'\n'.join(x['source'] for x in selected),'label':'expected return'}


def adapt_report_amount_contract(question):
    """Repair only the ancillary formatter's percent-vs-amount contradiction.

    Call explicitly in dataset adaptation; never override competition specs.
    """
    text=question.get('question','')
    if '\nTable (full rows):\n' not in text or '\n\nQuestion:' not in text:return question,None
    target=text.rsplit('\n\nQuestion:',1)[1].split('\nGive the requested',1)[0].strip().lower()
    if question['answer_spec'].get('unit')!='percent':return question,None
    if re.search(r'what (?:was|were|is|are) (?:the )?gross revenues?',target) and 'percent' in target and re.search(r'dollars in millions',text,re.I):
        unit='usd_million';instruction='Give the requested gross revenue in USD millions.'
    elif re.search(r'percentage rents totaled what in thousands',target):
        unit='usd_thousand';instruction='Give the requested total percentage rent in USD thousands.'
    else:return question,None
    changed={**question,'answer_spec':{**question['answer_spec'],'unit':unit},
             'question':text.split('\nGive the requested',1)[0]+'\n'+instruction}
    return changed,{'reason':'Raw financial question asks a monetary amount; legacy percentage-keyword formatter incorrectly assigned percent units.','old_unit':'percent','new_unit':unit,'uses_answer_labels':False}


def solve_report_percentage(question):
    text=question.get('question','')
    marker='\nTable (full rows):\n'
    if marker not in text or '\n\nQuestion:' not in text:return None
    if question['answer_spec'].get('unit') not in {'percent','usd_million','usd_thousand'} or question['trace_spec']['slots']:return None
    context,target=text.rsplit('\n\nQuestion:',1)
    target=target.split('\nGive the requested',1)[0].strip().lower()
    if not re.search(r'\bpercent(?:age)?\b',target):return None
    if re.search(r'\bexcluding\b|\bexcept\b',target):return None
    before,after=context.split(marker,1)
    lines=after.splitlines();rawrows=[]
    while lines and ' | ' in lines[0]:rawrows.append(lines.pop(0).split(' | '))
    if len(rawrows)<2:return None
    headers=rawrows[0];rows=rawrows[1:]
    if len(headers)==2 and YEAR.fullmatch(headers[0].strip()):
        try:number(headers[1])
        except ValueError:pass
        else:headers=['fiscal year','amount'];rows=rawrows
    if any(len(r)!=len(headers) for r in rows):return None
    prose=before.splitlines()+lines
    operands={};evidence=[];assumptions=[]

    def difference(old,new):
        return old-new if re.search(r'\bpercentage decrease\b|\bdecreased\b',target) else new-old

    def share_column():
        candidates=[]
        for j,h in enumerate(headers[1:],1):
            if re.search(r'maximum|may yet|price|dollar|fair.?value',h,re.I):continue
            if not re.search(r'share|unit',h,re.I):continue
            requested_plan=bool(re.search(r'plan|program',target))
            column_plan=bool(re.search(r'plan|program',h,re.I))
            if requested_plan!=column_plan:continue
            candidates.append((h,j))
        return pick(candidates,target,minimum=1/max(1,len(words(target))))

    def finish(numerator,denominator,kind,scale=100):
        if denominator==0:return None
        operands.update(numerator=numerator,denominator=denominator)
        expression=f'{scale} * numerator / denominator'
        value=execute(expression,operands)
        if value!=second_execute(expression,operands):raise ValueError('report arithmetic disagreement')
        p={'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],
           'case_id':question['case_id'],'final_answer':{'value':format_value(value,question['answer_spec'])},'steps':[]}
        a={'strategy':'source_bound_report_percentage','operation':kind,'expression':expression,
           'operands':{k:str(v) for k,v in operands.items()},'source_witnesses':evidence,
           'arithmetic_verified':True,'semantic_verified':not assumptions,'answer_status':'estimate' if assumptions else 'source_bound',
           'assumptions':assumptions}
        return p,a

    def full_label(items,phrase):
        t=words(phrase)
        ranked=[(len(words(label)),label,value) for label,value in items if words(label) and words(label)<=t]
        if not ranked:return None
        n=max(x[0] for x in ranked);best=[x for x in ranked if x[0]==n]
        if len({repr(x[2]) for x in best})!=1:return None
        return best[0][2]

    def totals():
        return [r for r in rows if re.match(r'^\s*total(?:\b|$)',r[0],re.I) and (r[0].strip().lower()=='total' or words(r[0])<=words(target))]

    def dated_columns(y):return [j for j,h in enumerate(headers) if years(h)==[y]]

    if question['answer_spec']['unit']=='usd_thousand':
        if not re.search(r'percentage rents.*totaled',target):return None
        data=prose_series(prose,'percentage rents');wanted=years(target)
        if data is None or not wanted or any(y not in data['values'] for y in wanted):return None
        evidence.append({'source':data['source'],'year_values_usd':{str(y):str(data['values'][y]) for y in wanted},'requested_output_scale_usd':1000})
        return finish(sum((data['values'][y] for y in wanted),Fraction()),Fraction(1000),'summed_percentage_rents_amount',scale=1)

    if question['answer_spec']['unit']=='usd_million':
        if not re.search(r'gross revenues?',target):return None
        requested=years(target)
        if len(requested)!=1:return None
        cols=dated_columns(requested[0]);expense=full_label([(r[0],r) for r in rows if 'expense' in r[0].lower()],target)
        percentages=[r for r in rows if 'revenues' in r[0].lower() and '%' in ' '.join(r)]
        if len(cols)!=1 or expense is None or len(percentages)!=1:return None
        j=cols[0]
        evidence.extend([{'row':r[0],'column':headers[j],'literal':r[j]} for r in (expense,percentages[0])])
        return finish(number(expense[j]),number(percentages[0][j]),'inverse_expense_percentage_amount')

    # A date-qualified subset uses the same share-category column as its total.
    cut=re.search(r'on or after\s+(\d{1,2})/(\d{1,2})/(\d{4})',target)
    if cut and ('share' in target or 'purchased' in target):
        cutoff=date(int(cut[3]),int(cut[1]),int(cut[2]))
        columns=[]
        for j,h in enumerate(headers[1:],1):
            if ('plan' in target or 'program' in target) and not re.search(r'plan|program',h,re.I):continue
            if re.search(r'maximum|may yet|price|dollar',h,re.I):continue
            columns.append((h,j))
        j=pick(columns,target)
        if j is None:return None
        totals=[r for r in rows if r[0].strip().lower()=='total']
        if len(totals)!=1:return None
        selected=[]
        for r in rows:
            ds=list(re.finditer(r'(\d{1,2})/(\d{1,2})/(\d{2,4})',r[0]))
            if len(ds)!=2:continue
            def dt(m):
                y=int(m[3]);y=y if y>=100 else (cutoff.year//100)*100+y
                return date(y,int(m[1]),int(m[2]))
            start,end=map(dt,ds)
            if start>=cutoff:selected.append(r)
            elif start<cutoff<=end:return None  # No interpolation of an overlapping period.
        if not selected:return None
        evidence.extend([{'column':headers[j],'rows':[r[0] for r in selected],'literals':[r[j] for r in selected]},
                         {'column':headers[j],'row':totals[0][0],'literal':totals[0][j]}])
        return finish(sum((number(r[j]) for r in selected),Fraction()),number(totals[0][j]),'dated_subset_share')

    # Flow/stock questions with an explicit as-of year bind the closing stock.
    if 'forfeited' in target and len(years(target))==1 and re.search(r'\bas of\b',target):
        y=years(target)[0];j=share_column()
        forfeited=[r for r in rows if r[0].strip().lower()=='forfeited']
        closing=[r for r in rows if years(r[0])==[y] and re.search(r'non.?vested|outstanding|balance|total',r[0],re.I)]
        if j is None or len(forfeited)!=1 or len(closing)!=1:return None
        evidence.extend([{'row':r[0],'column':headers[j],'literal':r[j]} for r in (forfeited[0],closing[0])])
        assumptions.append('Interpret the requested as-of forfeiture percentage relative to the explicitly dated closing nonvested-share balance.')
        return finish(abs(number(forfeited[0][j])),number(closing[0][j]),'forfeiture_to_closing_stock')

    # Lease maturity shares must retain the numerator/denominator column.
    if 'lease' in target and re.search(r'after\s+5\s+years?',target):
        totals=[r for r in rows if 'total minimum lease payments' in r[0].lower()]
        tails=[r for r in rows if r[0].strip().lower() in {'thereafter','after five years','after 5 years'}]
        if len(totals)!=1 or len(tails)!=1:return None
        wanted='operating' if 'operating' in target else 'capital'
        cols=[j for j,h in enumerate(headers) if wanted in h.lower()]
        if len(cols)!=1:return None
        j=cols[0]
        if 'operating' not in target and 'capital' not in target and 'finance' not in target:
            assumptions.append('Lease column not specified; interpret minimum lease payments as the capital/finance lease schedule.')
        evidence.extend([{'row':r[0],'column':headers[j],'literal':r[j]} for r in (tails[0],totals[0])])
        return finish(number(tails[0][j]),number(totals[0][j]),'lease_maturity_share')

    qyears=years(target)
    ischange=bool(re.search(r'\bchange|increase|decrease|decline|difference\b',target))
    ispoints=bool(re.search(r'percentage.point|percent.point|difference in the percentage',target))
    if len(qyears)>=2:
        from_year=re.search(r'\bfrom\s+((?:19|20)\d{2})',target)
        if from_year:
            first=int(from_year[1]);remaining=[y for y in qyears if y!=first]
            if remaining:qyears=[first,remaining[0]]
        elif 'versus' in target:qyears=sorted(qyears[:2])
    if ischange and len(qyears)>=2 and qyears[1]==qyears[0]+1:
        starts=[r for r in rows if re.search(r'\bbalance.*beginning.*year\b',r[0],re.I)]
        ends=[r for r in rows if re.search(r'\bbalance.*end.*year\b',r[0],re.I)]
        if len(starts)==len(ends)==1:
            scored=[(score(re.sub(r'\b(?:19|20)\d{2}\b','',h),target),j) for j,h in enumerate(headers[1:],1)]
            best=max((s for s,j in scored),default=0)
            cols=[j for s,j in scored if s==best and s>=.5]
            chain=[]
            for current in cols:
                for previous in cols:
                    if current==previous:continue
                    try:linked=number(starts[0][current])==number(ends[0][previous])
                    except ValueError:continue
                    if linked:chain.append((current,previous))
            if len(chain)==1:
                j,prev=chain[0]
                old,new=number(starts[0][j]),number(ends[0][j])
                evidence.extend([{'row':r[0],'column':headers[j],'literal':r[j]} for r in (starts[0],ends[0])])
                evidence.append({'continuity_prior_column':headers[prev],'prior_closing':ends[0][prev],'current_opening':starts[0][j]})
                if years(headers[j])==years(headers[prev]):assumptions.append('Duplicate year headers are resolved using the unique exact prior-closing/current-opening continuity and adjacent years requested by the question.')
                return finish(difference(old,new),abs(old),'linked_balance_rollforward_change')
    if 'cumulative return' in target and len(qyears)==1:
        nwords={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
        span=re.search(r'for (?:the )?(\d+|one|two|three|four|five|six|seven|eight|nine|ten) years?',target)
        if span:
            count=int(span[1]) if span[1].isdigit() else nwords[span[1]];end=qyears[0]
            c0,c1=dated_columns(end-count),dated_columns(end)
            row=full_label([(r[0],r) for r in rows],target)
            if row is not None and len(c0)==len(c1)==1:
                old,new=number(row[c0[0]]),number(row[c1[0]])
                evidence.extend([{'row':row[0],'column':headers[j],'literal':row[j]} for j in (c0[0],c1[0])])
                return finish(new-old,abs(old),'cumulative_index_return')
    months=re.findall(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b',target)
    if ischange and len(months)==2 and 'share' in target:
        j=share_column();dated=[]
        if j is None:return None
        for m in months:
            found=[r for r in rows if re.match(m+r'\b',r[0],re.I)]
            if len(found)!=1:return None
            dated.append(found[0])
        old,new=(number(r[j]) for r in dated)
        evidence.extend([{'row':r[0],'column':headers[j],'literal':r[j]} for r in dated])
        return finish(difference(old,new),abs(old),'month_share_change')

    # Prefer an explicitly matching table cell to a loosely related prose sum.
    if not ischange:
        total_rows=totals();grandcols=[j for j,h in enumerate(headers) if h.strip().lower()=='total']
        if len(total_rows)==1 and not re.search(r'\bas (?:a )?percentage of\b',target):
            calendar=r'^\s*(?:january|february|march|april|may|june|july|august|september|october|november|december|\d{1,4}[/ -])\b'
            numrow=full_label([(r[0],r) for r in rows if r is not total_rows[0] and not re.search(calendar,r[0],re.I)],target)
            j=None;global_den=False
            if len(qyears)==1:
                cols=dated_columns(qyears[0]);j=cols[0] if len(cols)==1 else None
            condition=re.search(r'considering (?:the )?([^,]+)',target)
            if condition:j=full_label([(h,i) for i,h in enumerate(headers[1:],1)],condition[1])
            if j is None:
                j=full_label([(h,i) for i,h in enumerate(headers[1:],1) if h.strip().lower()!='total'],target)
                global_den=j is not None and bool(re.search(r'located in|and located',target))
            if j is None and len(grandcols)==1:j=grandcols[0]
            if numrow is not None and j is not None:
                denj=grandcols[0] if global_den and len(grandcols)==1 else j
                evidence.extend([{'row':numrow[0],'column':headers[j],'literal':numrow[j]},
                                 {'row':total_rows[0][0],'column':headers[denj],'literal':total_rows[0][denj]}])
                return finish(number(numrow[j]),number(total_rows[0][denj]),'table_part_total_share')
        # A ratio of two explicitly requested row measures in one year.
        parts=re.split(r'\bas (?:a )?percentage of\b',target,maxsplit=1)
        if len(parts)==2 and len(qyears)==1:
            nr=full_label([(r[0],r) for r in rows],parts[0]);dr=full_label([(r[0],r) for r in rows],parts[1])
            # Unit annotations in labels need not be repeated in the question.
            if nr is None:nr=pick([(r[0],r) for r in rows],parts[0])
            if dr is None:dr=pick([(r[0],r) for r in rows],parts[1])
            cols=dated_columns(qyears[0])
            if nr is not None and dr is not None and nr is not dr and len(cols)==1:
                j=cols[0];evidence.extend([{'row':r[0],'column':headers[j],'literal':r[j]} for r in (nr,dr)])
                return finish(number(nr[j]),number(dr[j]),'same_year_measure_ratio')
        if 'lease' in target and 'current' in target:
            total_rows=[r for r in rows if 'total minimum lease payments' in r[0].lower()]
            future=[r for r in rows if YEAR.fullmatch(r[0].strip())]
            if len(headers)==2 and len(total_rows)==1 and future:
                first=min(future,key=lambda r:int(r[0]));evidence.extend([{'row':r[0],'column':headers[1],'literal':r[1]} for r in (first,total_rows[0])])
                assumptions.append('Current portion means the first future fiscal-year maturity in the supplied schedule.')
                return finish(number(first[1]),number(total_rows[0][1]),'current_lease_maturity_share')
        if 'lease' in target and 'due' in target and len(qyears)==1 and len(headers)==2:
            wanted=[r for r in rows if r[0].strip()==str(qyears[0])]
            total_rows=totals()
            if len(wanted)==len(total_rows)==1:
                evidence.extend([{'row':r[0],'column':headers[1],'literal':r[1]} for r in (wanted[0],total_rows[0])])
                return finish(number(wanted[0][1]),number(total_rows[0][1]),'specified_year_lease_maturity_share')

    # Explicitly included narrative amounts use a shared, disclosed precision
    # frame instead of mixing a rounded prose numerator with a precise table.
    if not ischange and 'acquisition' in target and 'investing activities' in target:
        for line in prose:
            if 'including' not in line or 'investing activities' not in line:continue
            ms=list(re.finditer(r'\$\s*('+NUM+r')\s*(billion|million|thousand)',line,re.I))
            labeled=[]
            for k,m in enumerate(ms):
                tail=line[m.end():ms[k+1].start() if k+1<len(ms) else len(line)]
                labeled.append((tail,(m,tail)))
            nr=pick(labeled,target.split('in the investing',1)[0]);dr=pick(labeled,'investing activities',minimum=.5)
            if nr and dr and nr[0].start()!=dr[0].start():
                n,d=nr[0],dr[0];evidence.extend([{'source':line,'literal':m[0],'description':v[1]} for m,v in ((n,nr),(d,dr))])
                assumptions.append('Use the explicitly related, rounded narrative amounts consistently; precise table totals may imply a slightly different ratio.')
                return finish(number(n[1])*SCALE[n[2].lower()],number(d[1])*SCALE[d[2].lower()],'narrative_inclusion_share')
    series=prose_series(prose,target)
    if ischange and series and len(qyears)>=2:
        y0,y1=qyears[:2]
        if y0 in series['values'] and y1 in series['values']:
            old,new=series['values'][y0],series['values'][y1]
            evidence.append({'source':series['source'],'year_values':{str(k):str(v) for k,v in series['values'].items()}})
            return finish(difference(old,new),abs(old),'prose_year_change')

    # A regional amount from prose is compared with the aligned table total.
    if not ischange and len(qyears)==1 and series and re.search(r'percent(?:age)?\s+of\s+(?:the\s+)?total',target):
        y=qyears[0];cols=[j for j,h in enumerate(headers) if years(h)==[y]]
        if len(cols)!=1 or y not in series['values']:return None
        j=cols[0]
        total_target=re.split(r'\btotal\b',target,maxsplit=1)[-1]
        row=pick([(r[0],r) for r in rows],total_target,minimum=1/max(1,len(words(total_target))))
        if row is None:return None
        scale=next((v for u,v in SCALE.items() if u in headers[0].lower()),1)
        evidence.extend([{'source':series['source'],'year':y,'scaled_value':str(series['values'][y])},
                         {'row':row[0],'column':headers[j],'literal':row[j],'scale':scale}])
        return finish(series['values'][y],number(row[j])*scale,'prose_to_table_share')

    if not ischange:return None
    if len(qyears)==1:
        y=qyears[0]
        cols=[j for j,h in enumerate(headers) if years(h)==[y]]
        opening=[r for r in rows if re.search(r'\bbalance at january 1\b',r[0],re.I)]
        closing=[r for r in rows if re.search(r'\bbalance at december 31\b',r[0],re.I)]
        if len(cols)==len(opening)==len(closing)==1:
            j=cols[0];old,new=number(opening[0][j]),number(closing[0][j])
            evidence.extend([{'row':r[0],'column':headers[j],'literal':r[j]} for r in (opening[0],closing[0])])
            return finish(difference(old,new),abs(old),'within_year_balance_change')
        # A single-year request may compare consecutive closing balances.
        available={v for r in rows for v in years(r[0])}
        if y in available and y-1 in available:qyears=[y-1,y]
    if len(qyears)<2:return None
    y0,y1=qyears[:2]
    if re.search(r'\baverage\b',target):
        dated={int(r[0]):r for r in rows if YEAR.fullmatch(r[0].strip())}
        j=pick([(h,i) for i,h in enumerate(headers[1:],1)],target)
        if j is None and len(headers)==2:j=1
        if j is not None and all(y in dated for y in range(y0,y1+1)) and y1>y0:
            vals=[number(dated[y][j]) for y in range(y0,y1+1)]
            if all(vals[:-1]):
                v=sum((difference(a,b)/abs(a) for a,b in zip(vals,vals[1:])),Fraction())/(len(vals)-1)
                evidence.extend([{'row':dated[y][0],'column':headers[j],'literal':dated[y][j]} for y in range(y0,y1+1)])
                return finish(v,Fraction(1),'mean_annual_percentage_change')
    # Both table orientations are supported: dated columns or dated rows.
    pairs=[(years(h)[0],j) for j,h in enumerate(headers) if len(years(h))==1]
    if len({y for y,j in pairs})!=len(pairs):return None
    ycols=dict(pairs)
    old=new=None
    if y0 in ycols and y1 in ycols:
        candidates=[]
        for r in rows:
            try:a,b=number(r[ycols[y0]]),number(r[ycols[y1]])
            except ValueError:continue
            candidates.append((r[0],(a,b,r)))
        selected=full_label(candidates,target) or pick(candidates,target)
        if selected:
            old,new,row=selected
            evidence.extend([{'row':row[0],'column':headers[ycols[y]],'literal':row[ycols[y]]} for y in (y0,y1)])
    else:
        dated={}
        for r in rows:
            ys=years(r[0])
            if len(ys)==1 and re.search(r'december|january|march|june|september|outstanding|balance|year.end',r[0],re.I):
                if ys[0] in dated:return None
                dated[ys[0]]=r
        j=pick([(h,i) for i,h in enumerate(headers[1:],1)],target)
        if j is None and len(headers)==2 and y0 in dated and y1 in dated:j=1
        if j is not None and y0 in dated and y1 in dated:
            try:old,new=number(dated[y0][j]),number(dated[y1][j])
            except ValueError:return None
            evidence.extend([{'row':dated[y][0],'column':headers[j],'literal':dated[y][j]} for y in (y0,y1)])
    if old is None or new is None:return None
    if ispoints:return finish(new-old,Fraction(1),'table_percentage_point_difference',scale=1)
    return finish(difference(old,new),abs(old),'table_year_change')
