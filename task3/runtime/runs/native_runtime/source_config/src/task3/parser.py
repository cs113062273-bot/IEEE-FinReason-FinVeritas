"""Offline parser for XBRL fragments, contexts and role-specific calculations."""
from __future__ import annotations

from .period_semantics import canonical, period_key
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import html
import re
from typing import Iterable


@dataclass(frozen=True)
class Target:
    concept: str
    start: str
    end: str | None = None


@dataclass(frozen=True)
class Context:
    id: str
    start: str | None
    end: str | None
    instant: str | None
    dimensions: tuple[tuple[str, str], ...]
    entity: str

    def __post_init__(self):
        values = period_key(self.start, self.end, self.instant)
        for name, value in zip(("start", "end", "instant"), values):
            object.__setattr__(self, name, value)

    @property
    def signature(self) -> tuple:
        return (*period_key(self.start, self.end, self.instant), self.dimensions, self.entity)

    def matches(self, target: Target) -> bool:
        return (period_key(self.start, self.end, None) == period_key(target.start, target.end, None) if target.end
                else canonical(self.instant, 'instant') == canonical(target.start, 'instant'))


@dataclass(frozen=True)
class Fact:
    concept: str
    context: str
    unit: str
    value: Decimal
    raw: str
    decimals: str | None
    position: int


@dataclass(frozen=True)
class Arc:
    parent: str
    child: str
    weight: Decimal
    role: str


@dataclass
class Filing:
    target: Target | None
    contexts: dict[str, Context]
    facts: list[Fact]
    arcs: list[Arc]
    balances: dict[str, str]
    sections: dict[str, str]
    units: dict[str, tuple[str, ...]]


_ATTRIBUTE = re.compile(r"([\w:.-]+)\s*=\s*(['\"])(.*?)\2", re.S)
_QUESTION = re.compile(r"Question1:.*?reported value of\s+([\w.-]+:[\w.-]+).*?"
                       r"period\s+(\d{4}-\d{2}-\d{2})(?:\s+to\s+(\d{4}-\d{2}-\d{2}))?", re.S)
_HEADERS = re.compile(r"^##\s*(.*?)\s*$", re.M)
_CONTEXT = re.compile(r"<(?:[\w.-]+:)?context\b([^>]*)>(.*?)</(?:[\w.-]+:)?context\s*>", re.S)
_FACT = re.compile(r"<([\w.-]+(?::[\w.-]+)?)\b([^>]*)>([^<]*)</\1\s*>", re.S)


def attributes(text: str) -> dict[str, str]:
    return {m[1]: html.unescape(m[3]) for m in _ATTRIBUTE.finditer(text)}


def number(raw: str) -> Decimal | None:
    text = html.unescape(raw).strip().replace("\u2212", "-")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"[,\s\u00a0$\u20ac\u00a3]", "", text)
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite():
        return None
    return -result if negative else result


def format_number(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def split_sections(query: str) -> dict[str, str]:
    headers = list(_HEADERS.finditer(query))
    return {m[1].strip(): query[m.end():headers[i + 1].start() if i + 1 < len(headers) else len(query)]
            for i, m in enumerate(headers)}


def _tag_text(body: str, tag: str) -> str | None:
    match = re.search(r"<(?:[\w.-]+:)?" + tag + r"\b[^>]*>(.*?)</(?:[\w.-]+:)?" + tag + r"\s*>", body, re.S)
    return html.unescape(match[1].strip()) if match else None


def parse_contexts(instance: str) -> dict[str, Context]:
    result = {}
    for match in _CONTEXT.finditer(instance):
        attrs, body = attributes(match[1]), match[2]
        context_id = attrs.get("id")
        if not context_id:
            continue
        dimensions = []
        for member in re.finditer(r"<(?:[\w.-]+:)?(?:explicitMember|typedMember)\b([^>]*)>(.*?)</(?:[\w.-]+:)?(?:explicitMember|typedMember)\s*>", body, re.S):
            dimensions.append((attributes(member[1]).get("dimension", ""), html.unescape(member[2].strip())))
        # Non-XBRL segment/scenario content is also a context qualifier.
        if not dimensions:
            for qualifier in ("segment", "scenario"):
                value = _tag_text(body, qualifier)
                if value and value.strip():
                    dimensions.append((qualifier, value))
        result[context_id] = Context(context_id, _tag_text(body, "startDate"),
                                     _tag_text(body, "endDate"), _tag_text(body, "instant"),
                                     tuple(sorted(dimensions)), _tag_text(body, "identifier") or "")
    return result


def parse_facts(instance: str) -> list[Fact]:
    result = []
    for match in _FACT.finditer(instance):
        attrs = attributes(match[2])
        ref = attrs.get("contextRef")
        if not ref or attrs.get("xsi:nil", "").lower() in {"true", "1"}:
            continue
        raw = html.unescape(match[3]).strip()
        value = number(raw)
        if value is None:
            continue
        if attrs.get("sign") == "-" and value >= 0:
            value = -value
        scale = attrs.get("scale")
        if scale:
            try:
                value *= Decimal(10) ** int(scale)
            except (ValueError, InvalidOperation):
                continue
        concept = attrs.get("name", match[1]) if match[1].split(":")[-1] == "nonFraction" else match[1]
        result.append(Fact(concept, ref, attrs.get("unitRef", ""), value, raw,
                           attrs.get("decimals"), match.start()))
    return result


def _concept_from_locator(label: str, href: str | None = None) -> str | None:
    if href and "#" in href:
        fragment = href.rsplit("#", 1)[-1]
        prefix, separator, local = fragment.partition("_")
        if separator:
            return prefix + ":" + local
        if ":" in fragment:
            return fragment
    match = re.match(r"^loc_([\w.-]+?)_([A-Za-z][\w.-]*?)(?:_[\w-]+)?$", label)
    return match[1] + ":" + match[2] if match else None


def parse_arcs(calculation: str) -> list[Arc]:
    result: list[Arc] = []
    all_seen = set()
    links = list(re.finditer(r"<(?:[\w.-]+:)?calculationLink\b([^>]*)>(.*?)</(?:[\w.-]+:)?calculationLink\s*>", calculation, re.S))
    bodies: Iterable[tuple[str, str]] = ((attributes(m[1]).get("xlink:role", ""), m[2]) for m in links) if links else [("", calculation)]
    for role, body in bodies:
        locators = {}
        for loc in re.finditer(r"<(?:[\w.-]+:)?loc\b([^>]*)/?>", body):
            attrs = attributes(loc[1])
            label = attrs.get("xlink:label", "")
            concept = _concept_from_locator(label, attrs.get("xlink:href"))
            if concept:
                locators[label] = concept
        seen = set()
        for arc in re.finditer(r"<(?:[\w.-]+:)?calculationArc\b([^>]*)/?>", body):
            attrs = attributes(arc[1])
            if attrs.get("use") == "prohibited":
                continue
            parent_label, child_label = attrs.get("xlink:from", ""), attrs.get("xlink:to", "")
            parent = locators.get(parent_label) or _concept_from_locator(parent_label)
            child = locators.get(child_label) or _concept_from_locator(child_label)
            weight = number(attrs.get("weight", ""))
            if not parent or not child or weight is None:
                continue
            key = (parent, child, weight)
            if key in seen or (role, *key) in all_seen:
                continue
            seen.add(key)
            all_seen.add((role, *key))
            result.append(Arc(parent, child, weight, role))
    return result


def parse(query: str) -> Filing:
    sections = split_sections(query)
    question = _QUESTION.search(query)
    target = Target(question[1], question[2], question[3]) if question else None
    instance = sections.get("Instance document", "")
    balances = {}
    taxonomy = sections.get("US GAAP Taxonomy", "")
    for match in re.finditer(r"ID:\s*([\w.-]+:[\w.-]+)\s*.*?Balance:\s*(\w+)", taxonomy, re.S):
        if match[2].lower() in {"debit", "credit"}:
            balances[match[1]] = match[2].lower()
    units = {}
    for match in re.finditer(r"<(?:[\w.-]+:)?unit\b([^>]*)>(.*?)</(?:[\w.-]+:)?unit\s*>", instance, re.S):
        attrs = attributes(match[1])
        measures = tuple(re.findall(r"<(?:[\w.-]+:)?measure\b[^>]*>(.*?)</(?:[\w.-]+:)?measure\s*>", match[2], re.S))
        if attrs.get("id"):
            # Keep numerator/denominator structure for compound units.
            units[attrs["id"]] = (("divide",) if "unitDenominator" in match[2] else ()) + measures
    return Filing(target, parse_contexts(instance), parse_facts(instance),
                  parse_arcs(sections.get("Calculation linkbase document", "")), balances, sections, units)
