"""Complete supplied Calculation 1.1 sums, separate from legacy DQC0126.

No missing-child imputation, recursive reconstruction, source-order tie,
external instance, issuer, filing name, question ID, or answer is used.
"""
from collections import defaultdict
from fractions import Fraction

from lxml import etree as E

from source_equations import aspect
from refine import decimal_text

L = '{http://www.xbrl.org/2003/linkbase}'
X = '{http://www.w3.org/1999/xlink}'
ARCROLE = 'https://xbrl.org/2023/arcrole/summation-item'


def radius(f):
    if f.get('decimals') == 'INF':
        return Fraction(0)
    try:
        decimals = int(f['decimals'])
        if abs(decimals) > 4096:
            return None
        return Fraction(10) ** (-decimals) / 2
    except (KeyError, TypeError, ValueError):
        return None


def networks(parsed):
    from source_financial_semantics import locators
    body = parsed['parts'].get('Calculation linkbase document')
    if not body:
        return []
    try:
        root = E.fromstring(body.strip().encode(), E.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    except E.XMLSyntaxError:
        return []
    groups = defaultdict(list)
    for link in root.iter(L + 'calculationLink'):
        loc = locators(parsed, parsed['parts'], link)
        for arc in link.findall(L + 'calculationArc'):
            if arc.get(X + 'arcrole') != ARCROLE:
                continue
            parent, child = loc.get(arc.get(X + 'from')), loc.get(arc.get(X + 'to'))
            if not parent or not child:
                # An unresolved endpoint makes the entire role untrustworthy.
                groups[link.get(X + 'role'), None, None].append(arc)
            else:
                groups[link.get(X + 'role'), parent, child].append(arc)
    result = defaultdict(dict)
    blocked_roles = set()
    blocked_parents = set()
    for (role, parent, child), arcs in groups.items():
        if parent is None:
            blocked_roles.add(role)
            continue
        # Conservatively abstain on priority/prohibition ambiguity instead of
        # treating an excluded arc as a zero-valued or nonexistent addend.
        if any(a.get('use') == 'prohibited' for a in arcs):
            blocked_parents.add((role, parent))
            continue
        try:
            weights = {Fraction(a.get('weight', '')) for a in arcs}
        except (ValueError, ZeroDivisionError):
            blocked_parents.add((role, parent))
            continue
        if len(weights) != 1 or not next(iter(weights)):
            blocked_parents.add((role, parent))
            continue
        result[role, parent][child] = weights.pop()
    return [{'role': role, 'parent': parent, 'children': children}
            for (role, parent), children in result.items()
            if role not in blocked_roles and (role, parent) not in blocked_parents]


def bind(facts):
    """Require exact duplicates and known precision; no first-value choice."""
    if not facts or len({Fraction(f['value']) for f in facts}) != 1:
        return None
    if any(radius(f) is None for f in facts):
        return None
    return min(facts, key=radius)


def select(parsed):
    source = defaultdict(list)
    targets = defaultdict(list)
    for fact in parsed['facts']:
        key = aspect(fact)
        if key is None:
            continue
        source[fact['QName'], key].append(fact)
        if fact['QName'] == parsed['target'] and fact.get('asked_period'):
            targets[key].append(fact)
    # A generic question without a member locator uses only a uniquely bound
    # nondimensional source target; dimensional alternatives are not ranked.
    targets = {k: fs for k, fs in targets.items() if not fs[0]['context']['dimensions']}
    if len(targets) != 1:
        return None
    frame, target_facts = next(iter(targets.items()))
    focus = bind(target_facts)
    if focus is None:
        return None
    direct = [e for e in networks(parsed) if e['parent'] == parsed['target']]
    if not direct:
        return None
    witnesses = []
    for equation in direct:
        terms = []
        total = Fraction(0)
        uncertainty = Fraction(0)
        for concept, weight in equation['children'].items():
            child = bind(source.get((concept, frame), []))
            if child is None:
                # Every target equation must be complete; a complete role
                # cannot silently outrank another incomplete target role.
                return None
            total += weight * Fraction(child['value'])
            uncertainty += abs(weight) * radius(child)
            terms.append({'fact': child, 'weight': str(weight)})
        text = decimal_text(total)
        if text is None:
            return None
        witnesses.append({'role': equation['role'], 'parent': equation['parent'],
                          'sum': text, 'sum_rounding_radius': str(uncertainty), 'terms': terms})
    values = {Fraction(w['sum']) for w in witnesses}
    if len(values) != 1:
        return None
    return {'new': {'extracted_value': focus['value'], 'calculated_value': decimal_text(values.pop())},
            'rule': 'complete_supplied_calculation11_direct_sum', 'arcrole': ARCROLE,
            'focus': focus, 'equations': witnesses, 'all_target_equations_complete': True,
            'legacy_arcroles_combined': False, 'missing_values_imputed': False,
            'external_instance_read': False, 'full_calculation11_conformance_claimed': False}
