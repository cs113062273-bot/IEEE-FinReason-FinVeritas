"""Complete-aspect, nonempty supplied calculation equations.

No issuer, question identifier, phase, numeric prior, or external facts enter
this module. Missing children are never interpreted as zero. A reverse
equation is evidence only when its parent and every other child are present.
"""
from collections import defaultdict
from decimal import Decimal, localcontext
from lxml import etree

L = '{http://www.xbrl.org/2003/linkbase}'
X = '{http://www.w3.org/1999/xlink}'
ARC = 'http://www.xbrl.org/2003/arcrole/summation-item'


def aspect(f):
    c = f.get('context')
    if not c or not f.get('unit_signature') or c.get('opaque_qualifiers'):
        return None
    return (c['entity_scheme'], c['entity'], tuple(c['period']),
            tuple(sorted(tuple(d) for d in c['dimensions'])),
            tuple(tuple(x) for x in f['unit_signature']))


def equations(parsed):
    """Extract effective, unambiguous summation networks from supplied XML."""
    from source_financial_semantics import locators
    body = parsed['parts'].get('Calculation linkbase document')
    if not body:
        return []
    try:
        root = etree.fromstring(body.strip().encode(), etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError:
        return []
    groups = defaultdict(list)
    for link in root.iter(L+'calculationLink'):
        try:
            loc = locators(parsed, parsed['parts'], link)
        except etree.XMLSyntaxError:
            return []
        role = link.get(X+'role')
        for node in link.findall(L+'calculationArc'):
            if node.get(X+'arcrole') != ARC:
                continue
            parent, child = loc.get(node.get(X+'from')), loc.get(node.get(X+'to'))
            if parent and child:
                groups[role, parent, child].append(node)
    networks = defaultdict(dict)
    blocked = set()
    for (role, parent, child), arcs in groups.items():
        # Distinct weights for the same endpoints are not safely one equation.
        priority = max(int(a.get('priority', '0')) for a in arcs)
        active = [a for a in arcs if int(a.get('priority', '0')) == priority]
        if any(a.get('use') == 'prohibited' for a in active):
            continue
        weights = {Decimal(a.get('weight', 'NaN')) for a in active}
        if len(weights) != 1 or not all(w.is_finite() and w != 0 for w in weights):
            blocked.add((role, parent))
            continue
        networks[role, parent][child] = weights.pop()
    return [{'role': role, 'parent': parent, 'children': children}
            for (role, parent), children in networks.items()
            if (role, parent) not in blocked and children]


def witnesses(parsed):
    """All complete direct and reverse equations for the asked target/period."""
    indexed = defaultdict(list)
    targets = {}
    for f in parsed['facts']:
        frame = aspect(f)
        if frame is None:
            continue
        indexed[f['QName'], frame].append(f)
        if f['QName'] == parsed['target'] and f.get('asked_period'):
            targets[frame] = f

    def bind(qname, frame):
        fs = indexed.get((qname, frame), [])
        # Exact duplicates may share a semantic context; conflicts abstain.
        if not fs or len({Decimal(f['value']) for f in fs}) != 1:
            return None
        return fs[0]

    result = []
    with localcontext() as ctx:
        ctx.prec = 100
        for equation in equations(parsed):
            parent, children = equation['parent'], equation['children']
            if parsed['target'] != parent and parsed['target'] not in children:
                continue
            for frame, focus in targets.items():
                if bind(parsed['target'], frame) is None:
                    continue
                bound = {}
                if parsed['target'] == parent:
                    for qname, weight in children.items():
                        f = bind(qname, frame)
                        if f is None:
                            break
                        bound[qname] = (f, weight)
                    else:
                        value = sum((Decimal(f['value'])*w for f, w in bound.values()), Decimal(0))
                        result.append({'direction': 'direct', 'focus': focus, 'value': str(value),
                                       'role': equation['role'], 'parent': parent,
                                       'terms': [{'fact': f, 'weight': str(w)} for f, w in bound.values()]})
                else:
                    pf = bind(parent, frame)
                    if pf is None or len(children) < 2:
                        continue
                    for qname, weight in children.items():
                        if qname == parsed['target']:
                            continue
                        f = bind(qname, frame)
                        if f is None:
                            break
                        bound[qname] = (f, weight)
                    else:
                        value = (Decimal(pf['value']) - sum((Decimal(f['value'])*w for f, w in bound.values()), Decimal(0))) / children[parsed['target']]
                        result.append({'direction': 'reverse', 'focus': focus, 'value': str(value),
                                       'role': equation['role'], 'parent': parent, 'parent_fact': pf,
                                       'target_weight': str(children[parsed['target']]),
                                       'terms': [{'fact': f, 'weight': str(w)} for f, w in bound.values()]})
    return result


def select(parsed, incumbent, programs):
    """Replace an unsupported sign fallback only with complete equations.

    Applicable source assertions retain their existing priority. This does not
    treat dimensional membership alone as an aggregation equation.
    """
    if any(p.get('eligible') for p in programs):
        return None, None
    extracted = Decimal(incumbent['extracted_value'])
    calculated = Decimal(incumbent['calculated_value'])
    if extracted >= 0 or calculated != -extracted:
        return None, None
    evidence = [w for w in witnesses(parsed) if Decimal(w['focus']['value']) == extracted]
    if not evidence or len({aspect(w['focus']) for w in evidence}) != 1:
        return None, None
    values = {Decimal(w['value']) for w in evidence}
    if len(values) != 1:
        return None, None
    value = values.pop()
    return {**incumbent, 'calculated_value': str(value)}, {
        'rule': 'complete_supplied_calculation_over_unsupported_sign_fallback',
        'numeric_facts_from_query_only': True, 'equations': evidence}


def radius(f):
    """Conservative half-unit radius for a source numeric fact."""
    dec = f.get('decimals')
    if dec == 'INF':
        return Decimal(0)
    try:
        return Decimal(5).scaleb(-int(dec)-1)
    except (TypeError, ValueError):
        return None


def bounded_witnesses(parsed, nonnegative):
    """Affine bounds from incomplete equations; absent addends stay variables.

    ``nonnegative(qname, context_fact)`` proves a variable's domain from a
    public rule. It does not fabricate a fact or assume its value is zero.
    """
    indexed = defaultdict(list)
    targets = {}
    for f in parsed['facts']:
        frame = aspect(f)
        if frame is None:
            continue
        indexed[f['QName'], frame].append(f)
        if f['QName'] == parsed['target'] and f.get('asked_period'):
            targets[frame] = f
    def bind(qname, frame):
        fs = indexed.get((qname, frame), [])
        if not fs:
            return 'absent', None
        if len({Decimal(f['value']) for f in fs}) != 1:
            return 'conflict', None
        return 'present', fs[0]
    output=[]
    with localcontext() as ctx:
        ctx.prec=100
        for equation in equations(parsed):
            parent, children = equation['parent'], equation['children']
            if parsed['target'] != parent and parsed['target'] not in children:
                continue
            coefficients={q: -w for q,w in children.items()}
            coefficients[parent]=coefficients.get(parent,Decimal(0))+1
            target_coefficient=coefficients.pop(parsed['target'])
            if not target_coefficient:
                continue
            for frame,focus in targets.items():
                if bind(parsed['target'],frame)[0]!='present' or radius(focus) is None:
                    continue
                constant=Decimal(0);uncertainty=abs(target_coefficient)*radius(focus)
                known=[];unknown=[];blocked=False
                for qname,coefficient in coefficients.items():
                    state,f=bind(qname,frame)
                    if state=='conflict':blocked=True;break
                    if state=='present':
                        rounding=radius(f)
                        if rounding is None:blocked=True;break
                        constant-=coefficient*Decimal(f['value'])
                        uncertainty+=abs(coefficient)*rounding
                        known.append({'fact':f,'coefficient':str(coefficient)})
                    else:
                        proof=nonnegative(qname,focus)
                        if not proof:blocked=True;break
                        unknown.append({'concept':qname,'coefficient':str(coefficient),
                                        'lower_bound':'0','upper_bound':None,'domain_proof':proof})
                if blocked or not known or not unknown:
                    continue
                signs={Decimal(u['coefficient']).compare(Decimal(0)) for u in unknown}
                if signs=={Decimal(1)}:relation='<='
                elif signs=={Decimal(-1)}:relation='>='
                else:continue
                output.append({'focus':focus,'role':equation['role'],'parent':parent,
                    'target_coefficient':str(target_coefficient),'relation':relation,
                    'constant':str(constant),'rounding_radius':str(uncertainty),
                    'known_terms':known,'unknown_nonnegative_terms':unknown,
                    'missing_values_imputed':False})
    return output


def feasible(value, witness):
    with localcontext() as ctx:
        ctx.prec=100
        residual=Decimal(witness['target_coefficient'])*Decimal(value)-Decimal(witness['constant'])
        tolerance=Decimal(witness['rounding_radius'])
        return residual<=tolerance if witness['relation']=='<=' else residual>=-tolerance
