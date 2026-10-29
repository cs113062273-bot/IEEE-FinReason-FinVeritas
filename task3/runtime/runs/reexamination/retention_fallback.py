"""Retention fallback: input-only post-rule for Task3 engine predictions.

Trigger
    The engine's final row reports calculated_value == extracted_value ("reported-value retention").
    Every item is a DQC finding, so the corrected value differs from the reported fact: Practice Gold
    has Q2 == Q1 in 0/332 rows and the official 680/680-A Development payload in 0/680 rows.
    A retained row therefore cannot be a DQC answer. No other row is touched.

Rules (applied to the supplied slice; the supplied role is treated like a statement cube)
    R1  DQC_US_0015  Target concept on the public DQC non-negative concept list and negative,
                     non-excluded facts exist for the asked period (member/axis/substring exclusions
                     of DQC_0015 constants).  Q1 = modal eligible negative value over distinct
                     contexts (tie: smallest magnitude), Q2 = |Q1|.
    R2  DQC_US_0117.9574  Unique non-dimensional total equal to Q1 and, on a DQC_0117 axis, the
                     single-member facts sum to a different value.  Members restricted to the
                     definition-tree descendants of the axis first ("strict"); if none, every
                     single-member fact on the axis ("loose").  Members whose ancestor (excluding the
                     domain) has a value are skipped.  Several axes: last in the DQC axis list.

Inputs read: the item's own query text and the engine's row.  No id, company, split, Gold, or
historical answer mapping is consulted.  Generic resources: DQC_0015 concept CSVs (XBRL US
dqc_us_rules commit 15523c24, see resources/task3_dqc0015/source_manifest.json).
"""
import csv
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

from lxml import etree

SECTIONS = ['##Schema document', '##Presentation linkbase document', '##Calculation linkbase document',
            '##Definition linkbase document', '##Label linkbase document', '##Instance document', '##US GAAP Taxonomy']
XBRLI = 'http://www.xbrl.org/2003/instance'
XBRLDI = 'http://xbrl.org/2006/xbrldi'
XLINK = 'http://www.w3.org/1999/xlink'
LINK = 'http://www.xbrl.org/2003/linkbase'
XSI_NIL = '{http://www.w3.org/2001/XMLSchema-instance}nil'

# DQC_0117.xule (both assertions) axis list, in rule order.
AXES_0117 = ['StatementClassOfStockAxis', 'ProductOrServiceAxis', 'PropertyPlantAndEquipmentByTypeAxis', 'LongtermDebtTypeAxis',
             'RelatedPartyTransactionsByRelatedPartyAxis', 'StatementBusinessSegmentsAxis', 'LimitedPartnersCapitalAccountByClassAxis',
             'PartnerTypeOfPartnersCapitalAccountAxis', 'FiniteLivedIntangibleAssetsByMajorClassAxis', 'FinancialInstrumentAxis',
             'InformationByCategoryOfDebtSecurityAxis']

# DQC_0015 exclusions (constant-us-gaap.xule documented defaults + 'basisswap', 'unfunded').
EX_STR = ('adjust', 'consolidat', 'eliminat', 'netting', 'reconcili', 'reclass', 'basisswap', 'unfunded')
EX_MEM = {'CorporateNonSegmentMember', 'FairValueConcentrationOfRiskMarketRiskManagementEffectsOnIncomeOrNetAssetsMember',
          'AccumulatedNetGainLossFromDesignatedOrQualifyingCashFlowHedgesMember', 'AccumulatedNetUnrealizedInvestmentGainLossMember',
          'DeferredDerivativeGainLossMember', 'AboveMarketLeasesMember', 'NewAccountingPronouncementEarlyAdoptionEffectMember',
          'UnallocatedFinancingReceivablesMember', 'DifferenceBetweenRevenueGuidanceInEffectBeforeAndAfterTopic606Member'}
EX_AXIS = {'StatementEquityComponentsAxis', 'ErrorCorrectionsAndPriorPeriodAdjustmentsRestatementByRestatementPeriodAndAmountAxis',
           'AdjustmentsForChangeInAccountingPrincipleAxis', 'AdjustmentsForNewAccountingPronouncementsAxis',
           'ProspectiveAdoptionOfNewAccountingPronouncementsAxis', 'QuantifyingMisstatementInCurrentYearFinancialStatementsByNatureOfErrorAxis',
           'PartnerCapitalComponentsAxis', 'ChangeInAccountingEstimateByTypeAxis', 'PartnerTypeOfPartnersCapitalAccountAxis',
           'StatementBusinessSegmentsAxis', 'InvestmentIdentifierAxis', 'IncomeTaxEffectChangeInLawAxis'}
EX_AXMEM = {'StatementBusinessSegmentsAxis': {'CorporateAndOtherMember', 'CorporateMember', 'AllOtherSegmentsMember'},
            'ConsolidatedEntitiesAxis': {'ParentCompanyMember', 'SubsidiariesMember', 'GuarantorSubsidiariesMember',
                                         'NonGuarantorSubsidiariesMember', 'SubsidiaryIssuerMember'},
            'FairValueByMeasurementBasisAxis': {'ChangeDuringPeriodFairValueDisclosureMember'}}


def load_nonneg(resource_dir):
    names = set()
    for p in sorted(Path(resource_dir).glob('dqc_15_usgaap_*_concepts.csv')):
        with open(p, encoding='utf-8') as fh:
            for row in csv.reader(fh):
                if len(row) >= 2:
                    names.add(row[-1].strip())
    return names


def _local(name):
    return name.split(':')[-1] if name else name


def _qname(node, value):
    if ':' in value:
        prefix, local = value.split(':', 1)
        namespace = node.nsmap.get(prefix)
    else:
        local, namespace = value, node.nsmap.get(None)
    return '{' + namespace + '}' + local if namespace else None


def _href_local(h):
    frag = h.split('#')[-1]
    return frag.split('_', 1)[1] if '_' in frag else frag


def _dec(s):
    try:
        value = Decimal(str(s).strip().replace(',', ''))
        return value if value.is_finite() else None
    except (InvalidOperation, AttributeError):
        return None


def _fmt(d):
    d = Decimal(d)
    if d == d.to_integral_value():
        return format(d, 'f').partition('.')[0]
    return format(d, 'f')


def _sum_exact(values):
    value = sum((Fraction(v) for v in values), Fraction())
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2; twos += 1
    while denominator % 5 == 0:
        denominator //= 5; fives += 1
    if denominator != 1:
        raise ValueError('Sum of finite decimal facts must terminate')
    scale = max(twos, fives)
    coefficient = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    sign = '-' if coefficient < 0 else ''
    digits = str(abs(coefficient)).rjust(scale + 1, '0')
    return Decimal(sign + (digits[:-scale] + '.' + digits[-scale:] if scale else digits))


def _xml(txt):
    txt = (txt or '').strip()
    if not txt:
        return None
    try:
        return etree.fromstring(txt.encode('utf-8'), etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False, no_network=True))
    except Exception:
        return None


class Slice:
    """Facts, contexts and definition trees of one query."""

    def __init__(self, q):
        idx = sorted((q.find(s), s) for s in SECTIONS if q.find(s) >= 0)
        self.sec = {name: q[pos + len(name):(idx[n + 1][0] if n + 1 < len(idx) else len(q))] for n, (pos, name) in enumerate(idx)}
        m = re.search(r"Question1: What's the reported value of (\S+) in the Instance document for the period (\S+) to (\S+)\?", q)
        if m:
            self.concept, self.period = m.group(1), ('D', m.group(2), m.group(3))
        else:
            m = re.search(r"Question1: What's the reported value of (\S+) in the Instance document (?:as of|for|on|at) (?:the )?(?:date |period )?(\S+?)\?", q)
            self.concept, self.period = (m.group(1), ('I', m.group(2))) if m else (None, None)
        self.facts = []
        inst = _xml(self.sec.get('##Instance document'))
        self.target_qname = _qname(inst, self.concept) if inst is not None and self.concept else None
        if inst is not None:
            ctx = {}
            units = {}
            for unit in inst.findall('{%s}unit' % XBRLI):
                divide = unit.find('{%s}divide' % XBRLI)
                numerator = unit.findall('{%s}measure' % XBRLI) if divide is None else divide.findall('{%s}unitNumerator/{%s}measure' % (XBRLI, XBRLI))
                denominator = [] if divide is None else divide.findall('{%s}unitDenominator/{%s}measure' % (XBRLI, XBRLI))
                units[unit.get('id')] = (tuple(sorted(_qname(n, n.text) for n in numerator)), tuple(sorted(_qname(n, n.text) for n in denominator)))
            for c in inst.iter('{%s}context' % XBRLI):
                p = c.find('{%s}period' % XBRLI)
                per = None
                if p is not None:
                    i = p.find('{%s}instant' % XBRLI)
                    if i is not None and i.text:
                        per = ('I', i.text.strip())
                    else:
                        s, e = p.find('{%s}startDate' % XBRLI), p.find('{%s}endDate' % XBRLI)
                        if s is not None and e is not None and s.text and e.text:
                            per = ('D', s.text.strip(), e.text.strip())
                dims = [(_local(x.get('dimension')), _local((x.text or '').strip())) for x in c.iter('{%s}explicitMember' % XBRLDI)]
                dims += [(_local(x.get('dimension')), 'TYPED:' + ''.join(x.itertext()).strip()) for x in c.iter('{%s}typedMember' % XBRLDI)]
                identifier = c.find('.//{%s}identifier' % XBRLI)
                entity = (identifier.get('scheme'), identifier.text) if identifier is not None else None
                full_dims = tuple(sorted((_qname(x, x.get('dimension')), _qname(x, (x.text or '').strip())) for x in c.iter('{%s}explicitMember' % XBRLDI)))
                typed = tuple(sorted((_qname(x, x.get('dimension')), E) for x in c.iter('{%s}typedMember' % XBRLDI) for E in [etree.tostring(x, method='c14n')]))
                ctx[c.get('id')] = (per, tuple(sorted(dims)), entity, full_dims, typed)
            for el in inst.iter():
                if not isinstance(el.tag, str) or not el.get('contextRef') or el.get('unitRef') is None:
                    continue
                c = ctx.get(el.get('contextRef'))
                if not c:
                    continue
                nil = el.get(XSI_NIL) == 'true'
                raw = (el.text or '').strip()
                # (local, period, dims, value, decimals, nil, contextRef, raw)
                if el.get('unitRef') not in units:
                    continue
                aspect = (c[2], c[0], c[3], c[4], units[el.get('unitRef')])
                self.facts.append((etree.QName(el).localname, c[0], c[1], None if nil else _dec(raw), el.get('decimals'), nil, el.get('contextRef'), raw,
                                   el.tag, aspect))
        self.kids = defaultdict(set)
        self.parents = defaultdict(set)
        self.domains = defaultdict(set)
        self.networks = []
        schema = _xml(self.sec.get('##Schema document'))
        declarations = {}
        imports = {}
        if schema is not None:
            ns = schema.get('targetNamespace')
            declarations = {e.get('id'): '{' + ns + '}' + e.get('name')
                            for e in schema.iter('{http://www.w3.org/2001/XMLSchema}element')
                            if ns and e.get('id') and e.get('name')}
            for e in schema.iter('{http://www.w3.org/2001/XMLSchema}import'):
                if e.get('schemaLocation') and e.get('namespace'):
                    imports.setdefault(e.get('schemaLocation').rsplit('/', 1)[-1], set()).add(e.get('namespace'))
        def endpoint(href, node):
            resource, _, fragment = (href or '').partition('#')
            if fragment in declarations:
                return declarations[fragment]
            prefix, separator, name = fragment.partition('_')
            bound = imports.get(resource.rsplit('/', 1)[-1], set())
            if len(bound) == 1 and separator:
                return '{' + next(iter(bound)) + '}' + name
            uri = node.nsmap.get(prefix)
            if separator and uri and uri.startswith(('http://fasb.org/us-gaap/', 'http://fasb.org/srt/')):
                return '{' + uri + '}' + name
            return None
        defn = _xml(self.sec.get('##Definition linkbase document'))
        if defn is not None:
            for dl in defn.iter('{%s}definitionLink' % LINK):
                locs = {l.get('{%s}label' % XLINK): _href_local(l.get('{%s}href' % XLINK) or '') for l in dl.iter('{%s}loc' % LINK)}
                exact = {l.get('{%s}label' % XLINK): endpoint(l.get('{%s}href' % XLINK), l) for l in dl.iter('{%s}loc' % LINK)}
                network = {'role': dl.get('{%s}role' % XLINK), 'kids': defaultdict(set),
                           'parents': defaultdict(set), 'domains': defaultdict(set), 'blocked': set()}
                grouped = defaultdict(list)
                for a in dl.iter('{%s}definitionArc' % LINK):
                    ar = (a.get('{%s}arcrole' % XLINK) or '').rsplit('/', 1)[-1]
                    if ar in ('domain-member', 'dimension-domain'):
                        source, target = exact.get(a.get('{%s}from' % XLINK)), exact.get(a.get('{%s}to' % XLINK))
                        if source and target:
                            grouped[(ar, source, target)].append(a)
                        f, t = locs.get(a.get('{%s}from' % XLINK)), locs.get(a.get('{%s}to' % XLINK))
                        self.kids[f].add(t)
                        self.parents[t].add(f)
                        if ar == 'dimension-domain':
                            self.domains[f].add(t)
                for (ar, source, target), arcs in grouped.items():
                    priority = max(int(a.get('priority', '0')) for a in arcs)
                    effective = [a for a in arcs if int(a.get('priority', '0')) == priority]
                    if any(a.get('use') == 'prohibited' for a in effective):
                        network['blocked'].add(target)
                        continue
                    network['kids'][source].add(target)
                    network['parents'][target].add(source)
                    if ar == 'dimension-domain':
                        network['domains'][source].add(target)
                self.networks.append(network)

    def target_facts(self):
        return [f for f in self.facts if f[8] == self.target_qname and f[1] == self.period]

    def descendants(self, node):
        seen, stack = set(), [node]
        while stack:
            for k in self.kids.get(stack.pop(), ()):
                if k not in seen:
                    seen.add(k)
                    stack.append(k)
        return seen

    def ancestors(self, node):
        seen, stack = set(), [node]
        while stack:
            for p in self.parents.get(stack.pop(), ()):
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
        return seen


def _eligible_0015(f):
    if f[3] is None or f[3] >= 0:
        return False
    for ax, mem in f[2]:
        if any(s in mem.lower() for s in EX_STR) or mem in EX_MEM or ax in EX_AXIS or mem in EX_AXMEM.get(ax, ()):
            return False
    return True


def _sum_0117(sl, axis, strict):
    axes = {a for f in sl.target_facts() for a, _ in f[9][2]
            if a and a.rsplit('}', 1)[-1] == axis and a.startswith('{' + 'http://fasb.org/us-gaap/')}
    if len(axes) != 1:
        return None, []
    exact_axis = next(iter(axes))
    single = {}
    for f in sl.target_facts():
        dimensions = f[9][2]
        if f[3] is not None and not f[9][3] and len(dimensions) == 1 and dimensions[0][0] == exact_axis:
            single.setdefault(dimensions[0][1], f)
    def closure(graph, start):
        seen, pending = set(), [start]
        while pending:
            for child in graph.get(pending.pop(), ()):
                if child not in seen:
                    seen.add(child); pending.append(child)
        return seen
    results = []
    networks = [n for n in sl.networks if exact_axis in n['domains']]
    observed_members = {value for n in sl.networks for values in n['kids'].values() for value in values}
    observed_members.update(value for n in sl.networks for value in n.get('blocked', set()))
    if not strict and not networks:
        networks = [{'kids': {}, 'parents': {}, 'domains': {}, 'blocked': set()}]
    for network in networks:
        domains = network['domains'].get(exact_axis, set())
        allowed = closure(network['kids'], exact_axis)
        candidates = {m: f for m, f in single.items() if m not in domains and
                      m not in network.get('blocked', set()) and
                      (m in allowed or (not strict and m not in observed_members))}
        used = [(m, f[3]) for m, f in candidates.items()
                if not ((closure(network['parents'], m) - domains - {exact_axis}) & set(candidates))]
        if used:
            results.append((_sum_exact(v for _, v in used), used))
    values = {value for value, _ in results}
    return results[0] if len(values) == 1 else (None, [])


def apply(query, row, nonneg):
    """Return (row, certificate); certificate is None when the row is unchanged."""
    q1, q2 = _dec(row['extracted_value']), _dec(row['calculated_value'])
    if q1 is None or q2 is None or q1 != q2:
        return row, None
    sl = Slice(query)
    if sl.concept is None:
        return row, None
    # Preserve one entity/unit frame, never merge unknown scopes silently.
    source_frames = {(f[9][0], f[9][-1]) for f in sl.target_facts() if f[3] is not None}
    if len(source_frames) != 1:
        return row, None
    aspect_values = defaultdict(set)
    for fact in sl.target_facts():
        if fact[3] is not None:
            aspect_values[fact[9]].add(fact[3])
    if any(len(values) != 1 for values in aspect_values.values()):
        return row, None
    base = dict(trigger='calculated_value == extracted_value', concept=sl.concept, period=list(sl.period),
                old=dict(extracted_value=row['extracted_value'], calculated_value=row['calculated_value']))
    if _local(sl.concept) in nonneg:
        by_ctx = {}
        for f in sl.target_facts():
            if _eligible_0015(f):
                by_ctx.setdefault(f[9], f)
        facts = list(by_ctx.values())
        if facts:
            counts = Counter(f[3] for f in facts)
            value = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))[0][0]
            raw = next(f[7] for f in facts if f[3] == value)
            new = dict(row, extracted_value=raw if _dec(raw) == value else _fmt(value), calculated_value=_fmt(-value))
            return new, dict(base, rule='R1_DQC_US_0015', focus='modal eligible negative, tie smallest magnitude',
                             unique=len(counts) == 1,
                             eligible=[dict(value=str(f[3]), context=f[6], dimensions=[list(d) for d in f[2]]) for f in facts],
                             new=dict(extracted_value=new['extracted_value'], calculated_value=new['calculated_value']))
    nondim = sorted(set(f[3] for f in sl.target_facts() if not f[2] and f[3] is not None))
    if len(nondim) != 1 or nondim[0] != q1:
        return row, None
    for strict in (True, False):
        finds = [(ax,) + _sum_0117(sl, ax, strict) for ax in AXES_0117]
        finds = [x for x in finds if x[1] is not None and x[1] != nondim[0]]
        if finds:
            ax, s, used = finds[-1]
            new = dict(row, calculated_value=_fmt(s))
            return new, dict(base, rule='R2_DQC_US_0117.9574', member_set='strict' if strict else 'loose', axis=ax,
                             total=str(nondim[0]), members=[dict(member=m, value=str(v)) for m, v in used], sum=str(s),
                             other_axis_findings=[dict(axis=a, sum=str(t)) for a, t, _ in finds[:-1]],
                             new=dict(extracted_value=new['extracted_value'], calculated_value=new['calculated_value']))
    return row, None
