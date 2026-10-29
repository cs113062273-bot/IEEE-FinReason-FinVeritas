"""Normalized historical C117 financial bridges, with source-only inputs.

Original capability preserved: reconcile product revenue to customers and
independently to gross fees less reimbursements; evaluate the original
statement DRS member sum. Metadata selection belongs to SourceCatalog, not an
issuer-specific filesystem path. Financial reconciliation is distinct from
assertion applicability and from the question's missing focus locator.
"""
from collections import defaultdict
from decimal import Decimal
import re
from lxml import etree as E
from task3.exact_arithmetic import add as exact_add,sum_values as exact_sum

L = 'http://www.xbrl.org/2003/linkbase'
X = 'http://www.w3.org/1999/xlink'
DT = 'http://xbrl.org/2005/xbrldt'
XS = 'http://www.w3.org/2001/XMLSchema'


def parsed_from_query(query, filing=None):
    """Small adapter over the current source parser; no historical imports."""
    from task3.xml_core import parse_xml
    from task3.parser import split_sections
    filing = filing or parse_xml(query, allow_complete_prefix=True)
    parts = split_sections(query)
    locations = {}
    try:
        instance = xml(parts['Instance document'])
        for context in instance.findall('{http://www.xbrl.org/2003/instance}context'):
            ds = []
            for node in context.iter('{http://xbrl.org/2006/xbrldi}explicitMember'):
                def expanded(value):
                    prefix, sep, name = value.partition(':')
                    return '{' + node.nsmap[prefix if sep else None] + '}' + (name if sep else prefix)
                ds.append((expanded(node.get('dimension')), 'explicit', expanded(node.text.strip()),
                           E.QName(node.getparent()).localname))
            locations[context.get('id')] = ds
    except E.XMLSyntaxError:
        # The core parser can certify complete prefix facts in truncated XML.
        # Their unavailable dimension locations cannot support this bridge.
        pass
    facts = []
    target_period = [filing.start, filing.end, None] if filing.end else [None, None, filing.start]
    for f in filing.facts:
        c, u = filing.contexts.get(f.context), filing.units.get(f.unit)
        if c is None or u is None:
            continue
        period = [c.start, c.end, c.instant]
        raw_dims = locations.get(c.id)
        unresolved = raw_dims is None or len(raw_dims) != len(c.dimensions)
        context = {'entity_scheme': c.scheme, 'entity': c.entity, 'period': period,
                   'dimensions': raw_dims or [],
                   'opaque_qualifiers': list(c.qualifiers) + (['unresolved/typed dimensional context'] if unresolved else [])}
        facts.append({'QName': f.concept, 'value': str(f.value), 'context_ref': f.context,
                      'unit_ref': f.unit, 'context': context, 'unit_signature': u.signature,
                      'decimals': f.decimals, 'scale': f.scale, 'sign': f.sign,
                      'asked_period': period == target_period, 'id': 'source_fact_' + str(f.index),
                      'source': f.source, 'raw_numeric': f.raw, 'precision': None,
                      'raw_xml': f.source.get('raw_xml', ''), 'line': f.source.get('line')})
    asked = re.search(r'Question1:.*?(?=Question2:|\Z)', query, re.S)
    return {'target': filing.target, 'facts': facts, 'parts': parts,
            'namespaces': filing.namespaces, 'period': target_period,
            'question': asked[0].strip() if asked else '',
            'duplicate_context_ids': any(d.get('kind') == 'duplicate-context-id-conflict' for d in filing.diagnostics),
            'duplicate_unit_ids': any(d.get('kind') == 'duplicate-unit-id-conflict' for d in filing.diagnostics)}


def candidate_from_query(query, filing=None, catalog=None):
    """Current-engine entrypoint; exact source lookup is delegated to catalog.

    A catalog is an existing SourceCatalog with metadata-only reads and exact
    namespace/schemaRef/entity matching. Its presence does not waive full-DTS
    certification: the caller must audit provenance before any promotion.
    """
    parsed = parsed_from_query(query, filing)
    supplied = candidate(parsed)
    if catalog is None or not supplied['source_bridges']:
        return supplied
    enriched, provenance = catalog.enrich(query)
    if enriched is None:
        supplied['metadata_provenance'] = provenance
        return supplied
    from task3.parser import split_sections
    result = candidate(parsed, split_sections(enriched), provenance)
    result['supplied_source_status'] = supplied['status']
    result['metadata_DTS_certification_required_before_promotion'] = True
    return result


def xml(body):
    return E.fromstring(body.strip().encode(), E.XMLParser(resolve_entities=False,
                        no_network=True, load_dtd=False, huge_tree=True))


def local(qname):
    return qname.rsplit('}', 1)[-1]


def dims(fact):
    return {a: member for a, kind, member, location in fact['context']['dimensions']
            if kind == 'explicit'}


def aspect(fact, removed_axis=None):
    c = fact['context']
    return (c['entity_scheme'], c['entity'], tuple(c['period']),
            tuple(tuple(x) for x in fact['unit_signature']),
            tuple(sorted(tuple(d) for d in c['dimensions'] if d[0] != removed_axis)))


def clean(fact):
    c = fact.get('context')
    return (c and fact.get('unit_signature') and not fact.get('sign')
            and not fact.get('scale') and not c.get('opaque_qualifiers')
            and all(d[1] == 'explicit' for d in c['dimensions']))


def target_facts(parsed):
    groups = defaultdict(list)
    for f in parsed['facts']:
        if f['QName'] == parsed['target'] and f['asked_period'] and clean(f):
            groups[aspect(f)].append(f)
    result = []
    for fs in groups.values():
        if len({Decimal(f['value']) for f in fs}) != 1:
            # Conflicting duplicates must not be resolved by source order.
            return []
        result.append(fs[0])
    return result


def locators(parsed, parts, link):
    """Resolve extension XML IDs using their XSD declarations, not ID prefix."""
    schema = xml(parts['Schema document'])
    # The source parser has already recovered the original root declarations,
    # including on the supported complete-prefix input format. A truncated
    # later numeric fact is irrelevant to resolving a schema/label locator.
    instance_ns = parsed.get('namespaces')
    if instance_ns is None:
        instance_ns = xml(parts['Instance document']).nsmap
    ns = {**schema.nsmap, **instance_ns}
    targetns = schema.get('targetNamespace')
    ids = {n.get('id'): '{' + targetns + '}' + n.get('name')
           for n in schema.findall('{' + XS + '}element') if n.get('id') and n.get('name')}
    result = {}
    for node in link.findall('{' + L + '}loc'):
        fragment = node.get('{' + X + '}href', '').rsplit('#', 1)[-1]
        name = ids.get(fragment)
        if name is None:
            # Standard taxonomy locators have namespace IDs. Never use this
            # fallback to reinterpret an extension schema ID.
            for prefix, uri in ns.items():
                if prefix and uri != targetns and fragment.startswith(prefix + '_'):
                    name = '{' + uri + '}' + fragment[len(prefix) + 1:]
                    break
        if name:
            result[node.get('{' + X + '}label')] = name
    return result


def linked_labels(parsed, parts):
    result = defaultdict(list)
    if not parts.get('Label linkbase document'):
        return result
    for link in xml(parts['Label linkbase document']).iter('{' + L + '}labelLink'):
        loc = locators(parsed, parts, link)
        resources = defaultdict(list)
        for n in link.findall('{' + L + '}label'):
            if n.get('{http://www.w3.org/XML/1998/namespace}lang', 'en').lower().startswith('en'):
                resources[n.get('{' + X + '}label')].append(n)
        for arc in link.findall('{' + L + '}labelArc'):
            if arc.get('use', 'optional') == 'prohibited':
                continue
            name = loc.get(arc.get('{' + X + '}from'))
            if name:
                for n in resources[arc.get('{' + X + '}to')]:
                    result[name].append({'text': ' '.join(''.join(n.itertext()).split()),
                                         'role': n.get('{' + X + '}role', '')})
    return result


def bridged_focus(parsed, parts=None):
    """Same historical financial identities, independent of extension names."""
    if local(parsed['target']) != 'RevenueFromContractWithCustomerExcludingAssessedTax':
        return []
    parts = parts or parsed['parts']
    labels = linked_labels(parsed, parts)
    gross_members, reimbursement_members = set(), set()
    for member, texts in labels.items():
        for row in texts:
            words = row['text'].lower()
            if 'management' in words and 'fee' in words and 'before' in words and 'reimbursement' in words:
                gross_members.add(member)
            if 'expense' in words and 'reimbursement' in words and 'before' not in words:
                reimbursement_members.add(member)
    ff, result = target_facts(parsed), []
    value = lambda f: Decimal(f['value'])
    for focus in ff:
        d = dims(focus)
        if len(d) != 1 or local(next(iter(d))) != 'ProductOrServiceAxis' or value(focus) <= 0:
            continue
        product = next(iter(d))
        members = [f for f in ff if len(dims(f)) == 2 and dims(f).get(product) == d[product]
                   and any(local(a) == 'MajorCustomersAxis' for a in dims(f))
                   and aspect(f, next(a for a in dims(f) if a != product)) == aspect(focus)]
        if len(members) < 3 or any(value(f) <= 0 for f in members) or exact_sum(map(value, members)) != value(focus):
            continue
        customer_axes = {a for f in members for a in dims(f) if a != product}
        if len(customer_axes) != 1:
            continue
        customer_axis = next(iter(customer_axes))
        bridges = []
        for customer in members:
            member = dims(customer)[customer_axis]
            matches = []
            for gross in ff:
                gd = dims(gross)
                related = [a for a in gd if local(a) == 'RelatedPartyTransactionsByRelatedPartyAxis'
                           and gd[a] == member]
                if len(gd) != 2 or gd.get(product) not in gross_members or len(related) != 1:
                    continue
                ra = related[0]
                for reimbursement in ff:
                    rd = dims(reimbursement)
                    if set(rd) != {product, ra} or rd[ra] != member or rd[product] not in reimbursement_members:
                        continue
                    if aspect(gross, product) != aspect(reimbursement, product):
                        continue
                    # Both sources also share customer entity, period, unit.
                    if aspect(gross, product)[:4] != aspect(customer, product)[:4]:
                        continue
                    if value(reimbursement) > 0 and exact_add(value(gross),value(reimbursement).copy_negate()) == value(customer):
                        matches.append({'customer': customer, 'gross_fee': gross,
                                        'reimbursement': reimbursement,
                                        'gross_member_labels': labels[gd[product]],
                                        'reimbursement_member_labels': labels[rd[product]],
                                        'identity': 'gross fee - expense reimbursement = customer revenue'})
            if len(matches) == 1:
                bridges.extend(matches)
        if len(bridges) >= 2:
            result.append({'focus': focus, 'customer_facts': members,
                           'independent_gross_net_bridges': bridges,
                           'financial_source_scope_not_question_binding': True})
    return result


def drs(parsed, parts):
    """Historical original DRS equations, with effective arcs and XML IDs."""
    schema, definitions = xml(parts['Schema document']), xml(parts['Definition linkbase document'])
    roles = {r.get('roleURI'): r.findtext('{' + L + '}definition', '')
             for r in schema.iter('{' + L + '}roleType')}
    arcs = []
    for link in definitions.iter('{' + L + '}definitionLink'):
        role, loc = link.get('{' + X + '}role'), locators(parsed, parts, link)
        for n in link.findall('{' + L + '}definitionArc'):
            a, b = loc.get(n.get('{' + X + '}from')), loc.get(n.get('{' + X + '}to'))
            if a and b:
                arcs.append({'role': role, 'kind': n.get('{' + X + '}arcrole', '').rsplit('/', 1)[-1],
                             'parent': a, 'child': b, 'next_role': n.get('{' + DT + '}targetRole', role),
                             'usable': n.get('{' + DT + '}usable', 'true') not in ['false', '0'],
                             'closed': n.get('{' + DT + '}closed') in ['true', '1'],
                             'use': n.get('use', 'optional'), 'priority': int(n.get('priority', '0')),
                             'xml': E.tostring(n, encoding='unicode')})
    groups, effective = defaultdict(list), []
    for a in arcs:
        groups[(a['role'], a['kind'], a['parent'], a['child'])].append(a)
    for aa in groups.values():
        active = [a for a in aa if a['priority'] == max(x['priority'] for x in aa)]
        if not any(a['use'] == 'prohibited' for a in active):
            effective.append(active[0])
    graph = defaultdict(list)
    for a in effective:
        graph[(a['role'], a['kind'], a['parent'])].append(a)

    def walk(role, node, kind, seen=frozenset()):
        if (role, node, kind) in seen:
            return {}
        result = {node: []}
        for arc in graph[(role, kind, node)]:
            for k, path in walk(arc['next_role'], arc['child'], kind, seen | {(role, node, kind)}).items():
                result.setdefault(k, [arc] + path)
        return result

    def unusable_members(role, node, seen=frozenset()):
        # Dimensions 1.0 2.5.3.3: false excludes the target, not its
        # descendants; any false incoming membership excludes that member.
        if (role,node) in seen:
            return set()
        blocked = set()
        for arc in graph[(role,'domain-member',node)]:
            if not arc['usable']:
                blocked.add(arc['child'])
            blocked |= unusable_members(arc['next_role'],arc['child'],seen | {(role,node)})
        return blocked

    cubes = []
    for a in effective:
        if a['kind'] != 'all':
            continue
        axes = {}
        for b in graph[(a['next_role'], 'hypercube-dimension', a['child'])]:
            members, domains, blocked = {}, set(), set()
            for c in graph[(b['next_role'], 'dimension-domain', b['child'])]:
                domains.add(c['child'])
                if not c['usable']:
                    blocked.add(c['child'])
                blocked |= unusable_members(c['next_role'],c['child'])
                for m, path in walk(c['next_role'], c['child'], 'domain-member').items():
                    members.setdefault(m, [b, c] + path)
            members = {m:path for m,path in members.items() if m not in blocked}
            defaults = {c['child'] for c in effective if c['kind'] == 'dimension-default' and c['parent'] == b['child']}
            axes[b['child']] = {'members': members, 'domains': domains, 'defaults': defaults}
        cubes.append({'role': a['role'], 'description': roles.get(a['role'], ''),
                      'cube': a['child'], 'primary': walk(a['role'], a['parent'], 'domain-member'),
                      'axes': axes, 'closed': a['closed']})
    return cubes


def inside(fact, cube):
    if fact['QName'] not in cube['primary']:
        return False
    d = dims(fact)
    if cube['closed'] and set(d) - set(cube['axes']):
        return False
    for axis, spec in cube['axes'].items():
        member = d.get(axis)
        if member is None:
            if len(spec['defaults']) != 1:
                return False
            member = next(iter(spec['defaults']))
        if member not in spec['members']:
            return False
    return True


def statement(cube):
    # Literal original DQC statement applicability; this is not a new ranking.
    banned = ['parenthetical', 'equity', 'deficit', 'stockholders', 'capital', 'investment',
              'changes', 'shareholder', 'convertible', 'preferred', 'temporaryequity',
              'redeemable', 'netproceedsfromallsources', 'membersinterest']
    return '- Statement -' in cube['description'] and not any(x in cube['role'].lower() for x in banned)


def sums(parsed, focus, parts):
    cubes, ff, base, result = drs(parsed, parts), target_facts(parsed), dims(focus), []
    if len(base) != 1:
        return []
    value = lambda f: Decimal(f['value'])
    for cube in cubes:
        if not statement(cube) or not inside(focus, cube):
            continue
        for axis, spec in cube['axes'].items():
            if axis in base:
                continue
            fs = [f for f in ff if set(dims(f)) == set(base) | {axis}
                  and all(dims(f).get(a) == m for a, m in base.items())
                  and aspect(f, axis) == aspect(focus)]
            # Domain facts are not monetary member addends (DQC0117 rule).
            included = [f for f in fs if inside(f, cube) and dims(f)[axis] not in spec['domains']]
            excluded = [f for f in fs if f not in included]
            notes = [f for f in included if any('- Disclosure -' in c['description']
                     and set(dims(f)) <= set(c['axes']) and inside(f, c) for c in cubes)]
            guard = not notes or max(map(value, notes)) > value(focus)
            result.append({'role': cube['role'], 'axis': axis, 'focus': focus,
                           'included_facts': included, 'excluded_source_facts': excluded,
                           'member_paths': {dims(f)[axis]: spec['members'][dims(f)[axis]] for f in included},
                           'calculated': str(exact_sum(map(value, included))) if included else None,
                           'notes_max': str(max(map(value, notes))) if notes else None,
                           'notes_overlap_guard_passed': guard,
                           'full_original_assertion_applicable': guard and bool(included),
                           'statement_DRS_membership_independently_checked': True})
    return result


def candidate(parsed, metadata_parts=None, provenance=None):
    parts = metadata_parts or parsed['parts']
    # The caller may supply only certified SourceCatalog metadata. No external
    # numerical facts may enter this financial bridge or the member sum.
    if parts.get('Instance document') != parsed['parts'].get('Instance document'):
        raise ValueError('metadata completion changed supplied numerical instance')
    evidence = bridged_focus(parsed, parts)
    result = {'rule': 'normalized_C117_source_customer_bridge', 'source_bridges': evidence,
              'metadata_provenance': provenance, 'proposed': None,
              'formal_eligible': False, 'question_focus_proved': False,
              'notes_guard_waived': False, 'issuer_member_or_phase_preferences_used': False}
    if len(evidence) != 1:
        result['status'] = 'no unique financially corroborated revenue scope'
        return result
    focus = evidence[0]['focus']
    computations = [r for r in sums(parsed, focus, parts)
                    if local(r['axis']) == 'MajorCustomersAxis'
                    and r['included_facts'] and r['excluded_source_facts']]
    result['assertion_computations'] = computations
    values = {Decimal(r['calculated']) for r in computations}
    if len(values) != 1:
        result['status'] = 'no unique nonempty statement DRS member sum'
        return result
    result['proposed'] = {'extracted_value': focus['value'],
                          'calculated_value': str(next(iter(values)))}
    result['formal_eligible'] = all(r['full_original_assertion_applicable'] for r in computations)
    result['status'] = ('source_assertion_eligible_focus_binding_still_required' if result['formal_eligible']
                        else 'source_arithmetic_retained_original_notes_guard_blocks_assertion')
    return result
