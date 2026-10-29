"""Source-equation refinement; no issuer, ID, answer, or magnitude ranking.

Missing facts remain variables. Only same-role acyclic substitution can close
a missing intermediate. Every available independent bound must agree before
an existing candidate is preferred. Public sign constraints are retained.
"""
from decimal import Decimal
from fractions import Fraction

from source_equations import aspect, equations
from partial_bounds import certificates, accepts


def pair(value):
    return tuple(Decimal(value[k]) for k in ('extracted_value', 'calculated_value'))


def decimal_text(value):
    """Only terminating rational results are submission values."""
    q = Fraction(value)
    d = q.denominator
    for prime in (2, 5):
        while d % prime == 0:
            d //= prime
    if d != 1:
        return None
    twos = fives = 0
    d = q.denominator
    while d % 2 == 0:
        twos += 1
        d //= 2
    while d % 5 == 0:
        fives += 1
        d //= 5
    places = max(twos, fives)
    integer = q.numerator * 2 ** (places - twos) * 5 ** (places - fives)
    sign = '-' if integer < 0 else ''
    digits = str(abs(integer)).zfill(places + 1)
    text = sign + (digits[:-places] + '.' + digits[-places:] if places else digits)
    return text.rstrip('0').rstrip('.') if '.' in text else text


def refine(parsed, incumbent, programs, raw, exclusions):
    target = parsed['target']
    networks = equations(parsed)
    if not networks:
        return incumbent, None
    source = [f for f in parsed['facts'] if f['QName'] == target and f.get('asked_period') and aspect(f)]
    if not source:
        return incumbent, None

    def domain(qname, focus):
        proof = raw.eligibility_0015({**focus, 'QName': qname, 'value': '-1'}, parsed['parts'], exclusions)
        return proof if proof['subset_eligible'] is True else None

    candidates = {pair(incumbent)}
    eligible = [p for p in programs if p.get('eligible')]
    candidates.update((Decimal(p['reported']), Decimal(p['value'])) for p in eligible)
    frames = {}
    for fact in source:
        key = aspect(fact)
        if key in frames:
            if Decimal(frames[key]['focus']['value']) != Decimal(fact['value']):
                frames[key]['conflicting_duplicates'] = True
            continue
        ws = certificates(parsed, fact, networks, domain, aspect)
        if ws:
            frames[key] = {'focus': fact, 'certificates': ws, 'conflicting_duplicates': False}
    if not frames:
        return incumbent, None

    checks = []
    for reported, calculated in sorted(candidates):
        bindings = [v for v in frames.values() if Decimal(v['focus']['value']) == reported]
        # A numeric value shared by distinct contexts never identifies a focus.
        if len(bindings) != 1 or bindings[0]['conflicting_duplicates']:
            checks.append({'pair': [str(reported), str(calculated)], 'state': 'unbound', 'rejected': False})
            continue
        record = bindings[0]
        ws = record['certificates']
        failures = [i for i, w in enumerate(ws) if not accepts(str(calculated), w)]
        checks.append({'pair': [str(reported), str(calculated)], 'state': 'checked',
                       'rejected': bool(failures), 'rejected_by': failures,
                       'focus': record['focus'], 'certificates': ws})

    survivors = [r for r in checks if not r['rejected']]
    selected = None
    if len(candidates) > 1 and len(survivors) == 1 and survivors[0]['state'] == 'checked':
        selected = survivors[0]['pair']
        # A negative result cannot override an applicable public nonnegative
        # constraint; contradictory source assertions are kept unresolved.
        if Decimal(selected[1]) < 0 and domain(target, survivors[0]['focus']):
            selected = None

    # A unique complete substituted equation may replace a partial/native
    # result only for a single source focus and a target without a sign rule.
    completion = None
    bindings = [v for v in frames.values() if Decimal(v['focus']['value']) == pair(incumbent)[0]]
    if selected is None and len(bindings) == 1 and not bindings[0]['conflicting_duplicates']:
        b = bindings[0]
        exact = [w for w in b['certificates'] if w['relation'] == '=' and not w['frontier']]
        values = {Fraction(w['constant']) / Fraction(w['target_coefficient']) for w in exact}
        if len(values) == 1 and domain(target, b['focus']) is None:
            text = decimal_text(next(iter(values)))
            if text is not None and all(accepts(text, w) for w in b['certificates']):
                # Require an actual absent-intermediate expansion. Existing
                # direct sums already have their original adapter precedence.
                if any(any(t['kind'] == 'absent_intermediate_expansion' for t in w['trace']) for w in exact):
                    selected = [str(pair(incumbent)[0]), text]
                    completion = exact

    result = incumbent if selected is None else {**incumbent, 'extracted_value': selected[0], 'calculated_value': selected[1]}
    return result, {'rule': 'source_affine_candidate_refinement', 'checks': checks,
                    'changed': pair(result) != pair(incumbent), 'selected_pair': selected,
                    'same_role_completion': completion, 'missing_values_imputed': False,
                    'question_focus_uniqueness_claimed': False}
