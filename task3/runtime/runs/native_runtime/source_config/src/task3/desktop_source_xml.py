"""Certified supplied-document prefixes for independent DTS experiments."""
import copy
import html
import re
from collections import defaultdict
from lxml import etree
from .xml_core import DECLARATION, XML_DECL, LINK, XS, XBRLI, _safe_xml


def complete_document_prefix(text, expected, section, diagnostics):
    body = XML_DECL.sub('', text).strip()
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', body, re.I):
        return None
    parser = etree.XMLPullParser(events=('start', 'end'), resolve_entities=False,
                                 no_network=True, load_dtd=False, recover=False)
    try:
        parser.feed(body.encode('utf8'))
        parser.close()
        return None
    except etree.XMLSyntaxError:
        pass
    errors = list(parser.error_log) or list(parser.feed_error_log)
    eof = {'ERR_DOCUMENT_END', 'ERR_TAG_NOT_FINISHED', 'ERR_ATTRIBUTE_NOT_FINISHED',
           'ERR_ATTRIBUTE_WITHOUT_VALUE', 'ERR_GT_REQUIRED', 'ERR_SPACE_REQUIRED',
           'ERR_NAME_REQUIRED', 'ERR_STRING_NOT_CLOSED'}
    if re.search(r'</[\w:.-]*$', body.rstrip()):
        eof.add('ERR_TAG_NAME_MISMATCH')
    if re.search(r'[\w:.-]+\s*=\s*$', body.rstrip()):
        eof.update({'ERR_ATTRIBUTE_NOT_STARTED', 'ERR_INTERNAL_ERROR'})
    last_line = len(body.rstrip().splitlines())
    if not errors or any(e.line < last_line or e.type_name not in eof for e in errors):
        return None
    root = None
    completed = []
    for event, node in parser.read_events():
        if event == 'start' and root is None:
            root = node
        if event == 'end' and node is root:
            return None
        if event == 'end' and node.getparent() is root:
            completed.append(node)
    if root is None or root.tag != expected:
        return None
    # Empty linkbase prefixes carry no relations; they never imply completeness.
    safe = etree.Element(root.tag, attrib=dict(root.attrib), nsmap=root.nsmap)
    for node in completed:
        safe.append(copy.deepcopy(node))
    diagnostics.append({'kind': 'complete-document-prefix-only', 'section': section,
                        'complete_top_level_children': len(completed),
                        'source_truncated': True, 'suffix_never_reconstructed': True,
                        'discarded_incomplete_subtrees': True})
    return safe


def supplied_roots(sections):
    bindings = defaultdict(set)
    for section, text in sections.items():
        if section != 'US GAAP Taxonomy':
            for m in DECLARATION.finditer(text):
                bindings[m[1] or None].add(html.unescape(m[3]))
    safe_ns = {p: next(iter(u)) for p, u in bindings.items() if len(u) == 1}
    roots = {}
    diagnostics = []
    for section, text in sections.items():
        if section == 'US GAAP Taxonomy':
            continue
        expected = '{'+(XS if section == 'Schema document' else
                         XBRLI if section == 'Instance document' else LINK)+'}'+(
                         'schema' if section == 'Schema document' else
                         'xbrl' if section == 'Instance document' else 'linkbase')
        root = _safe_xml(text, section, safe_ns, diagnostics, allow_complete_prefix=True)
        if root is not None and root.tag == 'case-fragments':
            matches = [c for c in root if c.tag == expected]
            root = matches[0] if len(matches) == 1 and len(root) == 1 else None
        if root is None and section != 'Instance document':
            root = complete_document_prefix(text, expected, section, diagnostics)
        if root is None or root.tag != expected:
            raise ValueError('No certified expected root: '+section)
        if section == 'Schema document' and not root.get('targetNamespace'):
            raise ValueError('Supplied schema targetNamespace required')
        roots[section] = root
    return roots, diagnostics
