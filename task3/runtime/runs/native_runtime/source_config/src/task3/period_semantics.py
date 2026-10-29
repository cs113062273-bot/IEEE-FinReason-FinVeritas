"""XBRL 2.1 section 4.7.2 period value equality.

Dates denote midnight at the beginning for startDate and at the end for
endDate/instant. Timezone-unspecified values are never equated to zoned ones.
Fractional seconds retain all supplied digits. Financial dates are not rounded.
"""
from datetime import date
import re

SOURCE = ('https://www.xbrl.org/Specification/XBRL-2.1/REC-2003-12-31/'
          'XBRL-2.1-REC-2003-12-31%2Bcorrected-errata-2013-02-20.html#_4.7.2')
_LEXICAL = re.compile(
    r'(?P<day>\d{4}-\d{2}-\d{2})'
    r'(?:T(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})(?P<fraction>\.\d+)?)?'
    r'(?P<zone>Z|[+-]\d{2}:\d{2})?\Z')


def boundary(value, kind):
    """Return exact (ordinal, second, fraction, zoned) or raise on invalid input."""
    if kind not in {'startDate', 'endDate', 'instant'}:
        raise ValueError('Unknown period boundary type')
    m = _LEXICAL.fullmatch(value.strip())
    if not m:
        raise ValueError('Unsupported or invalid XML Schema date/dateTime')
    day = date.fromisoformat(m['day']).toordinal()
    fraction = (m['fraction'] or '').removeprefix('.').rstrip('0')
    if m['hour'] is None:
        seconds = 0
        if kind != 'startDate':
            day += 1
    else:
        h, minute, sec = (int(m[k]) for k in ('hour', 'minute', 'second'))
        if h > 24 or minute > 59 or sec > 59 or h == 24 and (minute or sec or fraction):
            raise ValueError('Invalid time in XML Schema dateTime')
        seconds = h * 3600 + minute * 60 + sec
    zone = m['zone']
    if zone and zone != 'Z':
        hours, minutes = map(int, zone[1:].split(':'))
        if hours > 14 or minutes > 59 or hours == 14 and minutes:
            raise ValueError('Invalid timezone offset')
        offset = (hours * 60 + minutes) * 60
        seconds -= offset if zone[0] == '+' else -offset
    carry, seconds = divmod(seconds, 86400)
    return day + carry, seconds, fraction, zone is not None


def canonical(value, kind):
    """Canonical legal lexical form; unsupported literals retain distinct keys."""
    if value is None:
        return None
    try:
        ordinal, seconds, fraction, zoned = boundary(value, kind)
        suffix = 'Z' if zoned else ''
        if seconds == 0 and not fraction:
            if kind != 'startDate':
                ordinal -= 1
            return date.fromordinal(ordinal).isoformat() + suffix
        day = date.fromordinal(ordinal).isoformat()
        h, rem = divmod(seconds, 3600)
        minute, sec = divmod(rem, 60)
        return f'{day}T{h:02d}:{minute:02d}:{sec:02d}' + ('.' + fraction if fraction else '') + suffix
    except (ValueError, OverflowError):
        # This helper is an equality adapter, not a substitute schema validator.
        # Invalid literals must not collapse into a valid boundary or each other.
        return value


def period_key(start, end, instant):
    return canonical(start, 'startDate'), canonical(end, 'endDate'), canonical(instant, 'instant')


def normalize_query(query):
    """Canonicalize only period children inside supplied xbrli:context nodes.

    Keep the original markup/namespace declarations and all other source bytes,
    including notes, labels, schemaRefs, IDs and numeric facts. This works on
    complete context prefixes of the existing truncated-instance input format.
    """
    from collections import defaultdict
    from task3.parser import split_sections
    parts = split_sections(query)
    instance = parts.get('Instance document')
    if not instance:
        return query, []
    xi = 'http://www.xbrl.org/2003/instance'
    # Prefix recognition is based on declarations, never an assumed prefix.
    declarations = defaultdict(set)
    for p, _, uri in re.findall(r'xmlns(?::([\w.-]+))?\s*=\s*([\'"])(.*?)\2', instance):
        declarations[p or ''].add(uri)
    # A locally rebound prefix is not safe for lexical replacement. Its period
    # values are still handled by the namespace-aware parser's canonical key.
    prefixes = [re.escape(p) + ':' if p else '' for p, uris in declarations.items() if uris == {xi}]
    if not prefixes:
        return query, []
    prefix = '(?:' + '|'.join(prefixes) + ')'
    ctx_pattern = re.compile(r'<(?P<tag>' + prefix + r'context)\b[^>]*>.*?</(?P=tag)\s*>', re.S)
    period_pattern = re.compile(r'<(?P<tag>' + prefix + r'period)\b[^>]*>.*?</(?P=tag)\s*>', re.S)
    value_pattern = re.compile(r'(?P<open><(?P<prefix>' + prefix + r')(?P<kind>startDate|endDate|instant)\b[^>]*>)'
                               r'(?P<value>[^<]*)(?P<close></(?P=prefix)(?P=kind)\s*>)')
    changes = []

    def replace_value(m):
        original = m['value']
        normalized = canonical(original.strip(), m['kind'])
        if normalized == original.strip():
            return m[0]
        changes.append({'kind': m['kind'], 'original': original, 'canonical': normalized})
        return m['open'] + normalized + m['close']

    def replace_period(m):
        return value_pattern.sub(replace_value, m[0])

    protected = [(m.start(), m.end()) for m in re.finditer(r'<!--.*?-->|<!\[CDATA\[.*?\]\]>', instance, re.S)]

    def replace_context(m):
        if any(a <= m.start() < b for a, b in protected):
            return m[0]
        return period_pattern.sub(replace_period, m[0])

    normalized = ctx_pattern.sub(replace_context, instance)
    if normalized == instance:
        return query, []
    return query.replace(instance, normalized, 1), changes
