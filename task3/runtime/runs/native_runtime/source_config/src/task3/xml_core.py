"""Namespace-aware, offline XBRL fragment reader.

Only the documents embedded in a case are read. No DTS fetch, DTD expansion,
external entity resolution, or lxml ``recover=True`` is permitted. Missing
namespace declarations can be restored from the *same case*, and every such
restoration is recorded. This is a calculation-subset reader, not an XBRL
conformance processor or a complete implementation of Calculation 1.1.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import html
import re
from urllib.parse import unquote, urlsplit

from lxml import etree

from .period_semantics import canonical, period_key
from .parser import format_number, split_sections

XBRLI = "http://www.xbrl.org/2003/instance"
LINK = "http://www.xbrl.org/2003/linkbase"
XLINK = "http://www.w3.org/1999/xlink"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
XS = "http://www.w3.org/2001/XMLSchema"
IX = {"http://www.xbrl.org/2013/inlineXBRL", "http://www.xbrl.org/2008/inlineXBRL"}
SUMMATION_ROLES = {"http://www.xbrl.org/2003/arcrole/summation-item",
                   "https://xbrl.org/2023/arcrole/summation-item"}
QUESTION = re.compile(r"Question1:.*?reported value of\s+([\w.-]+:[\w.-]+).*?period\s+"
                      r"(\d{4}-\d{2}-\d{2})(?:\s+to\s+(\d{4}-\d{2}-\d{2}))?", re.S)
DECLARATION = re.compile(r"\bxmlns(?::([\w.-]+))?\s*=\s*(['\"])(.*?)\2", re.S)
XML_DECL = re.compile(r"<\?xml\b[^?]*\?>", re.I)
SOURCE_FACT = re.compile(r"<([\w.-]+(?::[\w.-]+)?)\b([^>]*)>([^<]*)</\1\s*>", re.S)
SOURCE_ATTR = re.compile(r"([\w:.-]+)\s*=\s*(['\"])(.*?)\2", re.S)


def number(raw: str) -> Decimal | None:
    """Normalize a literal without applying the process's Decimal precision."""
    text = html.unescape(raw).strip().replace("\u2212", "-")
    parenthesized = text.startswith("(") and text.endswith(")")
    if parenthesized:
        text = text[1:-1]
    text = re.sub(r"[,\s\u00a0$\u20ac\u00a3]", "", text)
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    return value.copy_negate() if parenthesized else value


def clark(uri: str, local: str) -> str:
    return "{" + uri + "}" + local if uri else local


def expanded(text: str, namespaces: dict, *, default: bool = True) -> str | None:
    if text.startswith("{"):
        return text
    if ":" in text:
        prefix, local = text.split(":", 1)
        uri = namespaces.get(prefix)
        return clark(uri, local) if uri else None
    return clark(namespaces.get(None, "") if default else "", text)


def tag_parts(element: etree._Element) -> tuple[str, str]:
    if not isinstance(element.tag, str):
        return "", ""
    q = etree.QName(element)
    return q.namespace or "", q.localname


def attr(element: etree._Element, name: str, namespace: str | None = None) -> str:
    return element.get(clark(namespace, name) if namespace else name, "")


def child_text(element: etree._Element, local: str, uri: str = XBRLI) -> str | None:
    for candidate in element.iter():
        if tag_parts(candidate) in {(uri, local), ("", local)}:
            return "".join(candidate.itertext()).strip() or None
    return None


def canonical_node(element: etree._Element) -> tuple:
    """Prefix-independent typed-member/segment signature."""
    return (element.tag, tuple(sorted(element.attrib.items())), (element.text or "").strip(),
            tuple(canonical_node(c) for c in element if isinstance(c.tag, str)))


@dataclass(frozen=True)
class XmlContext:
    id: str
    scheme: str
    entity: str
    start: str | None
    end: str | None
    instant: str | None
    dimensions: tuple
    qualifiers: tuple
    source: dict

    def __post_init__(self):
        values = period_key(self.start, self.end, self.instant)
        for name, value in zip(("start", "end", "instant"), values):
            object.__setattr__(self, name, value)

    @property
    def signature(self) -> tuple:
        return self.scheme, self.entity, *period_key(self.start, self.end, self.instant), self.dimensions, self.qualifiers

    @property
    def consolidated(self) -> bool:
        return not self.dimensions and not self.qualifiers

    def evidence(self) -> dict:
        return {"id": self.id, "entity": self.entity, "entity_scheme": self.scheme,
                "start": self.start, "end": self.end, "instant": self.instant,
                "dimensions": self.dimensions, "qualifiers": self.qualifiers, "source": self.source}


@dataclass(frozen=True)
class XmlUnit:
    id: str
    numerator: tuple[str, ...]
    denominator: tuple[str, ...]
    source: dict

    @property
    def signature(self) -> tuple:
        return self.numerator, self.denominator

    def evidence(self) -> dict:
        return {"id": self.id, "numerator": self.numerator, "denominator": self.denominator,
                "source": self.source}


@dataclass(frozen=True)
class XmlFact:
    concept: str
    lexical_concept: str
    context: str
    unit: str
    value: Decimal
    raw: str
    decimals: str
    scale: str
    sign: str
    index: int
    source: dict

    def evidence(self, filing: "XmlFiling") -> dict:
        context = filing.contexts.get(self.context)
        unit = filing.units.get(self.unit)
        return {"kind": "fact", "concept": self.concept, "lexical_concept": self.lexical_concept,
                "value": format_number(self.value), "raw": self.raw, "decimals": self.decimals,
                "scale": self.scale, "sign": self.sign, "context_ref": self.context,
                "context": context.evidence() if context else None,
                "unit_ref": self.unit, "unit": unit.evidence() if unit else None,
                "source": self.source}


@dataclass(frozen=True)
class XmlArc:
    parent: str
    child: str
    role: str
    weight: Decimal
    order: Decimal
    arcrole: str
    source: dict

    def evidence(self) -> dict:
        return {"parent": self.parent, "child": self.child, "role": self.role,
                "weight": format_number(self.weight), "order": format_number(self.order),
                "arcrole": self.arcrole, "source": self.source}


@dataclass
class XmlFiling:
    target: str | None = None
    target_lexical: str | None = None
    start: str | None = None
    end: str | None = None
    contexts: dict[str, XmlContext] = field(default_factory=dict)
    units: dict[str, XmlUnit] = field(default_factory=dict)
    facts: list[XmlFact] = field(default_factory=list)
    arcs: list[XmlArc] = field(default_factory=list)
    role_definitions: dict[str, str] = field(default_factory=dict)
    balances: dict[str, str] = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)
    document_sha256: dict[str, str] = field(default_factory=dict)
    namespaces: dict = field(default_factory=dict)


def _completed_instance_prefix(body: str, section: str, diagnostics: list) -> etree._Element | None:
    """Retain only parser-certified complete siblings before an EOF truncation.

    This never repairs a number, attribute, nesting error or incomplete fact.
    An error before the last nonempty line, or any non-EOF syntax failure,
    rejects the whole fragment. Historical callers leave this option disabled.
    """
    parser = etree.XMLPullParser(events=("start", "end"), resolve_entities=False,
                                 no_network=True, load_dtd=False, recover=False)
    failure = None
    try:
        parser.feed(body.encode("utf-8"))
        parser.close()
    except etree.XMLSyntaxError as exc:
        failure = exc
    if failure is None:
        return None
    last_line = len(body.rstrip().splitlines())
    entries = list(parser.error_log) or list(parser.feed_error_log)
    eof_codes = {"ERR_DOCUMENT_END", "ERR_TAG_NOT_FINISHED", "ERR_ATTRIBUTE_NOT_FINISHED",
                 "ERR_ATTRIBUTE_WITHOUT_VALUE", "ERR_GT_REQUIRED", "ERR_SPACE_REQUIRED",
                 "ERR_NAME_REQUIRED", "ERR_STRING_NOT_CLOSED"}
    if re.search(r"</[\w:.-]*$", body.rstrip()):
        eof_codes.add("ERR_TAG_NAME_MISMATCH")
    if re.search(r"[\w:.-]+\s*=\s*$", body.rstrip()):
        eof_codes.update({"ERR_ATTRIBUTE_NOT_STARTED", "ERR_INTERNAL_ERROR"})
    if not entries or any(e.line < last_line or e.type_name not in eof_codes for e in entries):
        return None
    root, completed = None, []
    for event, node in parser.read_events():
        if event == "start" and root is None:
            root = node
        if event == "end" and node is root:
            return None  # A complete root followed by bad extra content is not truncation.
        if event == "end" and node.getparent() is root:
            completed.append(node)
    if root is None or tag_parts(root) not in {(XBRLI, "xbrl"), ("", "xbrl")} or not completed:
        return None
    import copy
    safe = etree.Element(root.tag, attrib=dict(root.attrib), nsmap=root.nsmap)
    for node in completed:
        safe.append(copy.deepcopy(node))
    diagnostics.append({"kind": "complete-prefix-only", "section": section,
                        "complete_top_level_children": len(completed), "source_truncated": True,
                        "suffix_never_reconstructed": True, "error": str(failure).split("\n")[0]})
    return safe


def _safe_xml(text: str, section: str, same_case_ns: dict, diagnostics: list, *,
              allow_complete_prefix: bool = False) -> etree._Element | None:
    if not text.strip():
        diagnostics.append({"kind": "missing-document", "section": section})
        return None
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        diagnostics.append({"kind": "forbidden-dtd-or-entity", "section": section})
        return None
    body = XML_DECL.sub("", text).strip()
    def read(candidate: str) -> etree._Element:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                                 recover=False, remove_comments=False, huge_tree=False)
        return etree.fromstring(candidate.encode("utf-8"), parser)
    try:
        return read(body)
    except etree.XMLSyntaxError as original:
        if allow_complete_prefix and section == "Instance document":
            prefix = _completed_instance_prefix(body, section, diagnostics)
            if prefix is not None:
                return prefix
        # A wrapper recovers only a well-formed sequence of elements. It does
        # not repair truncation, bad nesting, bad entity references or numbers.
        prefixes = set(re.findall(r"(?:</?|\s)([\w.-]+):[\w.-]+", body))
        unresolved = sorted(p for p in prefixes if p not in same_case_ns and p != "xml")
        if unresolved:
            diagnostics.append({"kind": "xml-parse-failed", "section": section,
                                "error": str(original).split("\n")[0], "unresolved_prefixes": unresolved})
            return None
        declarations = " ".join('xmlns' + (":" + p if p else "") + '="' + html.escape(u, quote=True) + '"'
                                for p, u in sorted(same_case_ns.items(), key=lambda item: str(item[0])))
        try:
            root = read("<case-fragments " + declarations + ">" + body + "</case-fragments>")
            diagnostics.append({"kind": "same-case-fragment-wrapper", "section": section,
                                "original_error": str(original).split("\n")[0]})
            return root
        except etree.XMLSyntaxError as exc:
            diagnostics.append({"kind": "xml-parse-failed", "section": section,
                                "error": str(exc).split("\n")[0]})
            return None


def parse_xml(query: str, *, allow_complete_prefix: bool = False) -> XmlFiling:
    sections = split_sections(query)
    filing = XmlFiling()
    # Global restoration is never used to override a declaration on an element.
    # Conflicting same-case prefix declarations remain unavailable to recovery.
    bindings = defaultdict(set)
    for name, document in sections.items():
        if name == "US GAAP Taxonomy":
            continue
        for declaration in DECLARATION.finditer(document):
            bindings[declaration[1] or None].add(html.unescape(declaration[3]))
    safe_ns = {prefix: next(iter(uris)) for prefix, uris in bindings.items() if len(uris) == 1}
    roots = {}
    for name in ("Schema document", "Calculation linkbase document", "Instance document"):
        text = sections.get(name, "")
        filing.document_sha256[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        roots[name] = _safe_xml(text, name, safe_ns, filing.diagnostics,
                                allow_complete_prefix=allow_complete_prefix)
    instance = roots["Instance document"]
    namespaces = dict(safe_ns)
    if instance is not None:
        namespaces.update(instance.nsmap)
    filing.namespaces = namespaces
    question = QUESTION.search(query)
    if question:
        filing.target_lexical, filing.start, filing.end = question[1], question[2], question[3]
        filing.target = expanded(question[1], namespaces)
        if filing.target is None:
            filing.diagnostics.append({"kind": "unresolved-target-namespace", "target": question[1]})
    else:
        filing.diagnostics.append({"kind": "unresolved-question"})

    schema_ids, schema_urls = {}, {}
    schema = roots["Schema document"]
    if schema is not None:
        namespace = schema.get("targetNamespace", "")
        for element in schema.iter():
            uri, local = tag_parts(element)
            if (uri, local) == (XS, "element") and attr(element, "name"):
                concept = clark(namespace, attr(element, "name"))
                if attr(element, "id"):
                    schema_ids[attr(element, "id")] = concept
                balance = attr(element, "balance", XBRLI)
                if balance:
                    filing.balances[concept] = balance
            elif (uri, local) == (XS, "import"):
                url = attr(element, "schemaLocation")
                if url:
                    schema_urls[url] = attr(element, "namespace")
                    schema_urls[urlsplit(url).path.rsplit("/", 1)[-1]] = attr(element, "namespace")
            elif (uri, local) == (LINK, "roleType"):
                filing.role_definitions[attr(element, "roleURI")] = child_text(element, "definition", LINK) or ""

    source_positions = defaultdict(list)
    instance_text = sections.get("Instance document", "")
    for match in SOURCE_FACT.finditer(instance_text):
        attrs = {m[1]: html.unescape(m[3]) for m in SOURCE_ATTR.finditer(match[2])}
        if attrs.get("contextRef"):
            key = (match[1], attrs["contextRef"], attrs.get("unitRef", ""), html.unescape(match[3]).strip())
            source_positions[key].append({"section_char_start": match.start(), "section_char_end": match.end(),
                                          "raw_xml": match[0]})

    def source(element: etree._Element, section: str) -> dict:
        return {"section": section, "line": element.sourceline,
                "xml_path": element.getroottree().getpath(element),
                "section_sha256": filing.document_sha256[section]}

    if instance is not None:
        for element in instance.iter():
            uri, local = tag_parts(element)
            if (uri, local) in {(XBRLI, "context"), ("", "context")}:
                if not uri:
                    filing.diagnostics.append({"kind": "unqualified-xbrl-structure", "local": local, "line": element.sourceline})
                context_id = attr(element, "id")
                if not context_id:
                    continue
                entity, scheme, dimensions, qualifiers = "", "", [], []
                for child in element.iter():
                    cu, cl = tag_parts(child)
                    if (cu, cl) in {(XBRLI, "identifier"), ("", "identifier")}:
                        entity, scheme = "".join(child.itertext()).strip(), attr(child, "scheme")
                    if (cu, cl) == (XBRLDI, "explicitMember"):
                        dimensions.append((expanded(attr(child, "dimension"), child.nsmap),
                                           expanded("".join(child.itertext()).strip(), child.nsmap)))
                    elif (cu, cl) == (XBRLDI, "typedMember"):
                        dimensions.append((expanded(attr(child, "dimension"), child.nsmap),
                                           tuple(canonical_node(c) for c in child)))
                    elif (cu, cl) in {(XBRLI, "segment"), (XBRLI, "scenario"), ("", "segment"), ("", "scenario")}:
                        other = [c for c in child if tag_parts(c)[0] != XBRLDI]
                        if other or (child.text or "").strip():
                            qualifiers.append((cl, (child.text or "").strip(), tuple(canonical_node(c) for c in other)))
                context = XmlContext(context_id, scheme, entity, child_text(element, "startDate"),
                                     child_text(element, "endDate"), child_text(element, "instant"),
                                     tuple(sorted(dimensions, key=repr)), tuple(sorted(qualifiers, key=repr)),
                                     source(element, "Instance document"))
                if context_id in filing.contexts and filing.contexts[context_id].signature != context.signature:
                    filing.diagnostics.append({"kind": "duplicate-context-id-conflict", "id": context_id})
                else:
                    filing.contexts[context_id] = context
            elif (uri, local) in {(XBRLI, "unit"), ("", "unit")}:
                if not uri:
                    filing.diagnostics.append({"kind": "unqualified-xbrl-structure", "local": local, "line": element.sourceline})
                unit_id = attr(element, "id")
                numerator, denominator = [], []
                for child in element.iter():
                    if tag_parts(child) not in {(XBRLI, "measure"), ("", "measure")}:
                        continue
                    measure = expanded("".join(child.itertext()).strip(), child.nsmap)
                    if measure is None:
                        filing.diagnostics.append({"kind": "unresolved-unit-measure", "unit": unit_id})
                        continue
                    den = any(tag_parts(p)[1] == "unitDenominator" for p in child.iterancestors())
                    (denominator if den else numerator).append(measure)
                if unit_id:
                    unit = XmlUnit(unit_id, tuple(sorted(numerator)), tuple(sorted(denominator)),
                                   source(element, "Instance document"))
                    if unit_id in filing.units and filing.units[unit_id].signature != unit.signature:
                        filing.diagnostics.append({"kind": "duplicate-unit-id-conflict", "id": unit_id})
                    else:
                        filing.units[unit_id] = unit
            if attr(element, "contextRef"):
                if attr(element, "nil", XSI).lower() in {"true", "1"}:
                    continue
                raw = "".join(element.itertext()).strip()
                value = number(raw)
                if value is None:
                    continue
                lexical = ((element.prefix + ":") if element.prefix else "") + local
                concept = expanded(attr(element, "name"), element.nsmap) if uri in IX and local == "nonFraction" else element.tag
                if not concept:
                    filing.diagnostics.append({"kind": "unresolved-inline-concept", "line": element.sourceline})
                    continue
                sign, scale = attr(element, "sign"), attr(element, "scale")
                if sign == "-":
                    value = value.copy_abs().copy_negate()
                if scale:
                    try:
                        exponent = int(scale)
                        if abs(exponent) > 100:
                            raise ValueError("scale outside supported safe bound")
                        with localcontext() as literal_precision:
                            literal_precision.prec = max(80, len(value.as_tuple().digits) + 2)
                            value = value.scaleb(exponent)
                    except (ValueError, ArithmeticError):
                        filing.diagnostics.append({"kind": "invalid-scale", "line": element.sourceline, "scale": scale})
                        continue
                ref, unit = attr(element, "contextRef"), attr(element, "unitRef")
                provenance = source(element, "Instance document")
                spans = source_positions.get((lexical, ref, unit, raw), [])
                if spans:
                    provenance.update(spans.pop(0))
                else:
                    provenance["serialized_xml"] = etree.tostring(element, encoding="unicode", with_tail=False)
                filing.facts.append(XmlFact(concept, lexical, ref, unit, value, raw, attr(element, "decimals"),
                                            scale, sign, len(filing.facts), provenance))

    taxonomy = sections.get("US GAAP Taxonomy", "")
    # Taxonomy metadata never changes fact signs. Record balance for audit only.
    for match in re.finditer(r"ID:\s*([\w.-]+:[\w.-]+)\s*.*?Balance:\s*(\w+)", taxonomy, re.S):
        concept = expanded(match[1], namespaces)
        if concept and match[2].lower() in {"debit", "credit"}:
            filing.balances[concept] = match[2].lower()

    def locator_concept(href: str) -> str | None:
        resource, _, fragment = href.partition("#")
        fragment = unquote(fragment)
        if fragment in schema_ids:
            return schema_ids[fragment]
        if ":" in fragment:
            return expanded(fragment, namespaces)
        prefix, separator, local = fragment.partition("_")
        if not separator:
            return None
        expected_uri = schema_urls.get(resource) or schema_urls.get(urlsplit(resource).path.rsplit("/", 1)[-1])
        uri = expected_uri or namespaces.get(prefix)
        return clark(uri, local) if uri else None

    raw_arcs = defaultdict(list)
    calculation = roots["Calculation linkbase document"]
    if calculation is not None:
        for link in calculation.iter(clark(LINK, "calculationLink")):
            role = attr(link, "role", XLINK)
            locators = defaultdict(list)
            for node in link:
                if tag_parts(node) == (LINK, "loc"):
                    concept = locator_concept(attr(node, "href", XLINK))
                    if concept:
                        locators[attr(node, "label", XLINK)].append(concept)
                    else:
                        filing.diagnostics.append({"kind": "unresolved-locator", "role": role,
                                                   "href": attr(node, "href", XLINK)})
            for node in link:
                if tag_parts(node) != (LINK, "calculationArc"):
                    continue
                arcrole = attr(node, "arcrole", XLINK)
                if arcrole not in SUMMATION_ROLES:
                    filing.diagnostics.append({"kind": "unsupported-arcrole", "arcrole": arcrole, "role": role})
                    continue
                parents, children = locators.get(attr(node, "from", XLINK), []), locators.get(attr(node, "to", XLINK), [])
                weight = number(attr(node, "weight"))
                order = number(attr(node, "order")) or Decimal(0)
                if not parents or not children or weight is None:
                    filing.diagnostics.append({"kind": "unresolved-arc", "role": role, "source": source(node, "Calculation linkbase document")})
                    continue
                try:
                    priority = int(attr(node, "priority") or "0")
                except ValueError:
                    filing.diagnostics.append({"kind": "invalid-arc-priority", "role": role})
                    continue
                for parent in set(parents):
                    for child in set(children):
                        provenance = source(node, "Calculation linkbase document")
                        provenance["serialized_xml"] = etree.tostring(node, encoding="unicode", with_tail=False)
                        provenance["from_locator_label"] = attr(node, "from", XLINK)
                        provenance["to_locator_label"] = attr(node, "to", XLINK)
                        arc = XmlArc(parent, child, role, weight, order, arcrole, provenance)
                        raw_arcs[(role, parent, child, arcrole)].append((priority, attr(node, "use") == "prohibited", arc))
    # Priority/prohibition handling is deliberately conservative. Conflicting
    # weights at the effective priority invalidate the pair instead of adding it.
    for key, candidates in raw_arcs.items():
        priority = max(c[0] for c in candidates)
        effective = [c for c in candidates if c[0] == priority]
        if any(c[1] for c in effective):
            filing.diagnostics.append({"kind": "prohibited-arc", "role": key[0], "parent": key[1], "child": key[2]})
            continue
        weights = {c[2].weight for c in effective}
        if len(weights) != 1:
            filing.diagnostics.append({"kind": "conflicting-arc-weights", "role": key[0], "parent": key[1], "child": key[2]})
            continue
        if len(candidates) > 1:
            filing.diagnostics.append({"kind": "duplicate-or-overridden-arcs", "role": key[0],
                                       "parent": key[1], "child": key[2], "raw_count": len(candidates)})
        filing.arcs.append(sorted((c[2] for c in effective), key=lambda a: a.order)[0])
    return filing
