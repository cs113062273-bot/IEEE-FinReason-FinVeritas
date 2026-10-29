"""Exact affine bounds through absent calculation intermediates.

Each witness is one supplied equation with absent nodes expanded only through
that same role's unique acyclic network. Reported intermediate facts are never
silently recomputed. Missing leaves stay symbolic variables, not zero values.
This is local candidate elimination, not an all-assertions single-fault model.
"""
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction


def radius(f):
    if f.get('decimals')=='INF':return Fraction(0)
    try:return Fraction(10)**(-int(f['decimals']))/2
    except (KeyError,TypeError,ValueError):return None


def certificates(parsed,focus,networks,domain,aspect):
    frame=aspect(focus)
    if frame is None or radius(focus) is None:return []
    source=defaultdict(list)
    for f in parsed['facts']:
        if aspect(f)==frame:source[f['QName']].append(f)
    by_role=defaultdict(dict)
    for e in networks:by_role[e['role']][e['parent']]=e['children']
    target=parsed['target'];out=[]
    for role,parents in by_role.items():
        for parent,children in parents.items():
            trace=[];unknown={};failed=[]
            def term(q,active=frozenset()):
                # Returns constant, target coefficient, frontier coefficients,
                # and the radius induced by explicitly reported anchor facts.
                if q==target:return Fraction(0),Fraction(1),{},Fraction(0)
                fs=source.get(q,[])
                if fs:
                    if len({Fraction(Decimal(f['value'])) for f in fs})!=1 or any(radius(f) is None for f in fs):
                        failed.append('conflicting/unknown-accuracy source anchor');return None
                    f=min(fs,key=radius);trace.append({'kind':'reported_anchor','fact':f})
                    return Fraction(Decimal(f['value'])),Fraction(0),{},radius(f)
                if q in active:
                    failed.append('calculation cycle');return None
                if q in parents:
                    total=[Fraction(0),Fraction(0),defaultdict(Fraction),Fraction(0)]
                    trace.append({'kind':'absent_intermediate_expansion','concept':q,'role':role})
                    for child,weight in parents[q].items():
                        value=term(child,active|{q})
                        if value is None:return None
                        w=Fraction(weight);total[0]+=w*value[0];total[1]+=w*value[1]
                        for name,coefficient in value[2].items():total[2][name]+=w*coefficient
                        total[3]+=abs(w)*value[3]
                    return total
                proof=domain(q,focus)
                unknown[q]=proof
                return Fraction(0),Fraction(0),{q:Fraction(1)},Fraction(0)
            # Bind the equation parent as an observed anchor, target, or
            # symbolic variable; do not recursively expand this same equation.
            if parent==target:left=(Fraction(0),Fraction(1),{},Fraction(0))
            elif source.get(parent):left=term(parent)
            else:
                unknown[parent]=domain(parent,focus)
                left=(Fraction(0),Fraction(0),{parent:Fraction(1)},Fraction(0))
            if left is None:continue
            constant,a,frontier,tolerance=left[0],left[1],defaultdict(Fraction,left[2]),left[3]
            for q,w0 in children.items():
                part=term(q,frozenset({parent}))
                if part is None:break
                w=Fraction(w0);constant-=w*part[0];a-=w*part[1]
                for name,c in part[2].items():frontier[name]-=w*c
                tolerance+=abs(w)*part[3]
            else:
                if failed or not a:continue
                frontier={q:c for q,c in frontier.items() if c}
                if any(not unknown.get(q) for q in frontier):continue
                signs={c>0 for c in frontier.values()}
                # Mixed-sign nonnegative unknowns impose no one-sided bound.
                if len(signs)>1:continue
                relation='=' if not signs else ('<=' if True in signs else '>=')
                tolerance+=abs(a)*radius(focus)
                out.append({'role':role,'parent':parent,'focus':focus,
                    'target_coefficient':str(a),'constant':str(-constant),
                    'relation':relation,'rounding_radius':str(tolerance),
                    'frontier':[{'concept':q,'coefficient':str(c),'domain_proof':unknown[q]} for q,c in frontier.items()],
                    'trace':trace,'missing_values_imputed':False})
    return out


def accepts(value,w):
    residual=Fraction(w['target_coefficient'])*Fraction(Decimal(value))-Fraction(w['constant'])
    r=Fraction(w['rounding_radius'])
    return abs(residual)<=r if w['relation']=='=' else residual<=r if w['relation']=='<=' else residual>=-r
