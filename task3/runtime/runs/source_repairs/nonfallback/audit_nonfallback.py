"""Fresh, supplied-source-only audit of all 171 nonfallback candidates.

No C8 parser, selector or numeric engine imports. No network requests, gold
files, native reruns, score solving or submission actions. Existing inventory
is used only for cohort membership and the execution trace to verify.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from lxml import etree

WORK = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ROOT = WORK / "core/source"
OLD = WORK / "runs/task3_error_localization_20261014"
XI = "http://www.xbrl.org/2003/instance"
DI = "http://xbrl.org/2006/xbrldi"
LINK = "http://www.xbrl.org/2003/linkbase"
XLINK = "http://www.w3.org/1999/xlink"
XS = "http://www.w3.org/2001/XMLSchema"
XSI = "http://www.w3.org/2001/XMLSchema-instance"


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sections(query):
    headings = list(re.finditer(r"^##\s*(.*?)\s*$", query, re.M))
    return {m[1]: query[m.end(): headings[i + 1].start() if i + 1 < len(headings) else len(query)] for i, m in enumerate(headings)}


def xml(body):
    return etree.fromstring(body.strip().encode(), etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=True))


def qname(text, node):
    prefix, separator, local = text.partition(":")
    uri = node.nsmap.get(prefix if separator else None)
    return "{" + (uri or "") + "}" + (local if separator else prefix)


def decimal(text):
    try:
        value = Decimal(text)
        return value if value.is_finite() else None
    except (InvalidOperation, TypeError):
        return None


def source_parse(query):
    from task3.period_semantics import canonical
    parts = sections(query)
    root = xml(parts["Instance document"])
    question = re.search(r"Question1:.*?reported value of\s+([\w.-]+:[\w.-]+).*?period\s+(\d{4}-\d{2}-\d{2})(?:\s+to\s+(\d{4}-\d{2}-\d{2}))?", query, re.S)
    assert question, "Question target/period unavailable"
    target = qname(question[1], root)
    contexts = {}
    for context in root.findall("{" + XI + "}context"):
        ident = context.find(".//{" + XI + "}identifier")
        period = context.find("{" + XI + "}period")
        def field(name):
            child = period.find("{" + XI + "}" + name)
            return canonical(child.text.strip(), name) if child is not None else None
        dims = []
        for child in context.iter():
            if child.tag == "{" + DI + "}explicitMember":
                dims.append((qname(child.get("dimension"), child), "explicit", qname(child.text.strip(), child), etree.QName(child.getparent()).localname))
            elif child.tag == "{" + DI + "}typedMember":
                dims.append((qname(child.get("dimension"), child), "typed", etree.tostring(child, method="c14n").decode(), etree.QName(child.getparent()).localname))
        opaque = []
        for container in context.findall(".//{" + XI + "}segment") + context.findall(".//{" + XI + "}scenario"):
            opaque.extend(etree.tostring(child, encoding="unicode") for child in container if child.tag not in {"{" + DI + "}explicitMember", "{" + DI + "}typedMember"})
        contexts[context.get("id")] = {"entity": ident.text.strip() if ident is not None else None,
            "entity_scheme": ident.get("scheme") if ident is not None else None,
            "period": [field("startDate"), field("endDate"), field("instant")], "dimensions": sorted(dims),
            "line": context.sourceline, "opaque_qualifiers": opaque,
            "raw_xml": etree.tostring(context, encoding="unicode", with_tail=False)}
    units = {}
    for unit in root.findall("{" + XI + "}unit"):
        divide = unit.find("{" + XI + "}divide")
        def measures(node):
            return tuple(sorted(qname(m.text.strip(), m) for m in node.findall(".//{" + XI + "}measure")))
        units[unit.get("id")] = (measures(unit), ()) if divide is None else (
            measures(divide.find("{" + XI + "}unitNumerator")), measures(divide.find("{" + XI + "}unitDenominator")))
    facts, target_nodes = [], []
    for node in root:
        value = decimal(node.text or "")
        context = contexts.get(node.get("contextRef"))
        unit = units.get(node.get("unitRef"))
        wanted_period = [question[2], question[3], None] if question[3] else [None, None, question[2]]
        nil = node.get("{" + XSI + "}nil") in {"true", "1"}
        if node.tag == target:
            target_nodes.append({"context_ref": node.get("contextRef"), "context_resolved": context is not None,
                "asked_period": bool(context and context["period"] == wanted_period), "nil": nil,
                "finite_numeric": value is not None, "scale": node.get("scale"), "sign": node.get("sign"),
                "raw_numeric": node.text, "line": node.sourceline})
        if not node.get("contextRef") or value is None or nil:
            continue
        facts.append({"QName": node.tag, "value": str(value), "raw_numeric": node.text,
            "context_ref": node.get("contextRef"), "unit_ref": node.get("unitRef"), "context": context,
            "unit_signature": unit, "decimals": node.get("decimals"), "precision": node.get("precision"),
            "id": node.get("id"), "line": node.sourceline, "scale": node.get("scale"), "sign": node.get("sign"),
            "asked_period": bool(context and context["period"] == wanted_period),
            "raw_xml": etree.tostring(node, encoding="unicode", with_tail=False)})
    return {"target": target, "question": question[0].split("Question2:")[0].strip(),
        "period": wanted_period, "facts": facts, "parts": parts, "namespaces": root.nsmap,
        "target_nodes": target_nodes,
        "duplicate_context_ids": len(contexts) != len(root.findall("{" + XI + "}context")),
        "duplicate_unit_ids": len(units) != len(root.findall("{" + XI + "}unit"))}


def extraction_certificate(parsed, predicted):
    """Certify only Q1 numeric invariance; never infer a Q2 correction."""
    facts = [f for f in parsed["facts"] if f["QName"] == parsed["target"] and f["asked_period"]]
    nodes = parsed["target_nodes"]
    blockers = []
    if parsed["duplicate_context_ids"] or parsed["duplicate_unit_ids"]:
        blockers.append("duplicate context/unit IDs")
    if any(not n["context_resolved"] for n in nodes):
        blockers.append("target with unbound period/context")
    if any(n["asked_period"] and (n["nil"] or not n["finite_numeric"] or n["scale"] or n["sign"]) for n in nodes):
        blockers.append("requested source has nil/nonfinite/unsupported scale/sign semantics")
    if any(not f["unit_signature"] or not f["context"]["entity"] or not f["context"]["entity_scheme"] or f["context"]["opaque_qualifiers"] for f in facts):
        blockers.append("unresolved entity/unit or opaque context qualifier")
    values = sorted({Decimal(f["value"]) for f in facts})
    certified = not blockers and len(values) == 1 and values[0] == Decimal(predicted)
    return {"certified": certified, "scope": "Q1 supplied-source numerical invariance only; Q2 and hidden gold not certified",
        "blockers": blockers, "distinct_values": [str(v) for v in values], "facts": facts,
        "nil_requested_nodes": sum(n["asked_period"] and n["nil"] for n in nodes),
        "source_sign_scale_precision_attributes": [{"fact_id": f["id"], "sign": f["sign"], "scale": f["scale"], "precision": f["precision"], "decimals": f["decimals"]} for f in facts],
        "entity_unit_scopes": sorted({repr((f["context"]["entity_scheme"], f["context"]["entity"], f["unit_signature"])) for f in facts}),
        "all_period_QName_facts_checked_including_nil": True}


def frame(fact):
    context = fact["context"]
    return (context["entity_scheme"], context["entity"], tuple(context["period"]), tuple(context["dimensions"]), fact["unit_signature"])


def exclusions():
    """Read original public registry cells; do not import C8 exclusions()."""
    path = ROOT / "resources/task3_dqc0015/DQC_0015_MemberExclusions.xlsx"
    result = {"strings": set(), "members": set(), "axes": set(), "pairs": set()}
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        texts = ["".join(n.itertext()) for n in etree.fromstring(z.read("xl/sharedStrings.xml"))]
        for name in z.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            for row in etree.fromstring(z.read(name)).findall(".//m:row", ns):
                cells = {}
                for cell in row:
                    col = re.match("[A-Z]+", cell.get("r", ""))
                    value = cell.find("m:v", ns)
                    if col and value is not None:
                        cells[col[0]] = texts[int(value.text)] if cell.get("t") == "s" else value.text
                kind, test, first, second = (cells.get(c, "") for c in ("D", "E", "H", "L"))
                if kind == "Member" and "contains" in test:
                    result["strings"].add(first.lower())
                elif kind == "Member" and test == "Member equals":
                    result["members"].add(first)
                elif kind == "Axis" and test == "Axis equals":
                    if "AND member equals" in cells.get("I", ""):
                        result["pairs"].add((first, second))
                    else:
                        result["axes"].add(first)
    # Literal additional constants in pinned approved-v29 source, lines 209/253.
    result["strings"].update({"basisswap", "unfunded"})
    result["axes"].update({"StatementBusinessSegmentsAxis", "InvestmentIdentifierAxis", "IncomeTaxEffectChangeInLawAxis"})
    return result


def eligibility_0015(fact, parts, exc):
    match = re.fullmatch(r"\{http://fasb.org/(us-gaap|srt)/(20\d\d)(?:-01-31)?\}(.+)", fact["QName"])
    if not match or Decimal(fact["value"]) >= 0:
        return {"subset_eligible": False, "reason": "negative listed concept required"}
    namespace, year, name = match.groups()
    suffix = "-01-31" if year == "2021" else ""
    if fact["QName"].split("}", 1)[0] != "{http://fasb.org/" + namespace + "/" + year + suffix:
        return {"subset_eligible": False, "reason": "namespace does not match published taxonomy version"}
    registry = ROOT / (f"resources/task3_dqc0015/dqc_15_usgaap_{year}_concepts.csv" if namespace == "us-gaap" else f"resources/task3_round4_dqc/dqc_15_srt_{year}_concepts.csv")
    if registry.exists():
        concepts = {r[1].split(":")[-1] for r in csv.reader(registry.open(encoding="utf-8-sig")) if len(r) >= 2}
        if name not in concepts:
            return {"subset_eligible": False, "reason": "not listed in original public concept registry"}
    else:
        from task3.legacy_registry_binding import listed_legacy
        listed = listed_legacy(namespace, year, name)
        if listed is None:
            return {"subset_eligible": None, "reason": "SRT or legacy registry independently unbound"}
        if not listed:
            return {"subset_eligible": False, "reason": "not listed in hash-verified public legacy concept registry"}
    gaap, srt = f"http://fasb.org/us-gaap/{year}{suffix}", f"http://fasb.org/srt/{year}{suffix}"
    expand = lambda uri, local: "{" + uri + "}" + local
    axis_ex = {expand(srt if n == "InvestmentIdentifierAxis" else gaap, n) for n in exc["axes"] if n != "IncomeTaxEffectChangeInLawAxis"}
    schema = xml(parts["Schema document"])
    ext = schema.get("targetNamespace")
    if ext:
        axis_ex.add(expand(ext, "IncomeTaxEffectChangeInLawAxis"))
    members = {expand(gaap, n) for n in exc["members"]}
    pairs = {(expand(srt if a == "ConsolidatedEntitiesAxis" else gaap, a), expand(srt if a == "ConsolidatedEntitiesAxis" else gaap, m)) for a, m in exc["pairs"]}
    for axis, kind, member, location in fact["context"]["dimensions"]:
        if axis in axis_ex:
            return {"subset_eligible": False, "reason": "original exact excluded axis", "axis": axis}
        if kind == "explicit":
            if member in members or any(token in member.split("}")[-1].lower() for token in exc["strings"]):
                return {"subset_eligible": False, "reason": "original exact member/substring exemption", "member": member}
            if (axis, member) in pairs:
                return {"subset_eligible": False, "reason": "original exact SRT/GAAP axis/member exemption", "axis": axis, "member": member}
    return {"subset_eligible": True, "reason": "original nonnegative subset predicates pass",
        "full_form_DTS_certified": False, "absolute_value_proves_original_magnitude": False,
        "typed_dimensions_not_blanket_exempt": True}


def calculation_arcs(parsed):
    """Resolve supplied locator QNames and effective summation-item arcs."""
    parts, namespaces = parsed["parts"], parsed["namespaces"]
    ids = {}
    for title in ("Schema document", "US GAAP Taxonomy"):
        if title not in parts:
            continue
        if not parts[title].lstrip().startswith("<"):
            # Supplied US GAAP Taxonomy is often a prose/JSON concept list.
            # It cannot serve as an XML declaration or imported DTS witness.
            continue
        schema = xml(parts[title])
        uri = schema.get("targetNamespace")
        for node in schema.findall("{" + XS + "}element"):
            if uri and node.get("id") and node.get("name"):
                ids[node.get("id")] = "{" + uri + "}" + node.get("name")
    root = xml(parts["Calculation linkbase document"])
    groups = defaultdict(list)
    unresolved = []
    for link in root.findall(".//{" + LINK + "}calculationLink"):
        role = link.get("{" + XLINK + "}role")
        locators = {}
        for node in link.findall("{" + LINK + "}loc"):
            href = node.get("{" + XLINK + "}href", "")
            fragment = href.split("#")[-1]
            target = ids.get(fragment)
            if target is None and "_" in fragment:
                prefix, local = fragment.split("_", 1)
                if prefix in namespaces:
                    target = "{" + namespaces[prefix] + "}" + local
            locators[node.get("{" + XLINK + "}label")] = target
        for node in link.findall("{" + LINK + "}calculationArc"):
            parent, child = (locators.get(node.get("{" + XLINK + "}" + a)) for a in ("from", "to"))
            weight = decimal(node.get("weight"))
            if not parent or not child or weight is None:
                unresolved.append({"role": role, "line": node.sourceline, "reason": "unbound locator or invalid weight"})
                continue
            arc = {"role": role, "parent": parent, "child": child, "weight": str(weight),
                "priority": int(node.get("priority", "0")), "use": node.get("use", "optional"), "line": node.sourceline}
            # weight is a non-exempt arc attribute and therefore participates
            # in XBRL arc equivalence. Different weights are retained as conflict.
            groups[(role, parent, child, str(weight))].append(arc)
    effective = []
    for arcs in groups.values():
        priority = max(a["priority"] for a in arcs)
        same = [a for a in arcs if a["priority"] == priority]
        if not any(a["use"] == "prohibited" for a in same):
            effective.append(same[0])
    return effective, unresolved


def same_frame_equations(parsed, focus):
    """Independent direct forward/inverse evidence; missing facts never zero."""
    arcs, unresolved = calculation_arcs(parsed)
    groups = defaultdict(list)
    for arc in arcs:
        groups[(arc["role"], arc["parent"])].append(arc)
    relevant = [(key, aa) for key, aa in groups.items() if key[1] == focus["QName"] or any(a["child"] == focus["QName"] for a in aa)]
    bound = defaultdict(list)
    for f in parsed["facts"]:
        if f["context"] and f["unit_signature"] and frame(f) == frame(focus):
            bound[f["QName"]].append(f)
    output = []
    with localcontext() as arithmetic:
        arithmetic.prec = 100
        for (role, parent), aa in relevant:
            same_child = Counter(a["child"] for a in aa)
            missing = [a["child"] for a in aa if len({Decimal(f["value"]) for f in bound[a["child"]]}) != 1]
            conflicting = [name for name, n in same_child.items() if n > 1]
            detail = {"role": role, "parent": parent, "arcs": aa, "same_exact_entity_period_dimensions_unit": True,
                "missing_or_conflicting_children": missing, "conflicting_child_arcs": conflicting, "missing_not_zero": True}
            if parent == focus["QName"]:
                detail["direction"] = "forward"
                if not missing and not conflicting:
                    detail["computed"] = str(sum((Decimal(a["weight"]) * Decimal(bound[a["child"]][0]["value"]) for a in aa), Decimal(0)))
                    detail["anchors"] = [bound[a["child"]][0] for a in aa]
            else:
                detail["direction"] = "inverse"
                parent_values = {Decimal(f["value"]) for f in bound[parent]}
                focus_arcs = [a for a in aa if a["child"] == focus["QName"]]
                other_missing = [name for name in missing if name != focus["QName"]]
                if len(parent_values) == 1 and not other_missing and not conflicting and len(focus_arcs) == 1 and Decimal(focus_arcs[0]["weight"]) != 0:
                    other = sum((Decimal(a["weight"]) * Decimal(bound[a["child"]][0]["value"]) for a in aa if a["child"] != focus["QName"]), Decimal(0))
                    detail["computed"] = str((next(iter(parent_values)) - other) / Decimal(focus_arcs[0]["weight"]))
                    detail["anchors"] = [bound[parent][0]] + [bound[a["child"]][0] for a in aa if a["child"] != focus["QName"]]
            # Equation arithmetic alone does not assert anchors are uncorrupted.
            detail["unique_corrected_answer_certified"] = False
            output.append(detail)
    return output, unresolved


def verify_trace(parsed, trace):
    source = trace["parent"]
    found = [f for f in parsed["facts"] if f["QName"] == source["concept"] and f["context_ref"] == source["context_ref"]
             and f["unit_ref"] == source["unit_ref"] and Decimal(f["value"]) == Decimal(trace["reported"])]
    return found


def audit(row, old, exc):
    parsed = source_parse(row["query"])
    assert hashlib.sha256(row["query"].encode()).hexdigest() == old["query_sha256"]
    asked = [f for f in parsed["facts"] if f["QName"] == parsed["target"] and f["asked_period"]]
    values = sorted({Decimal(f["value"]) for f in asked})
    trace = old["C8_selection"]
    found = verify_trace(parsed, trace)
    assert found, "C8 selected raw source not reproduced"
    focus = found[0]
    issues = []
    if focus not in asked:
        issues.append("C8 selected source does not match literal target/period")
    certificate = extraction_certificate(parsed, old["C8"]["extracted_value"])
    extraction_invariant = certificate["certified"]
    negatives = [f for f in asked if Decimal(f["value"]) < 0]
    nonnegative = [{"fact_id": f["id"], "value": f["value"], "context_ref": f["context_ref"], "proof": eligibility_0015(f, parsed["parts"], exc)} for f in negatives]
    members_verified = None
    if old["locally_inferred_DQC"] == "0015":
        selected_elig = eligibility_0015(focus, parsed["parts"], exc)
        if selected_elig["subset_eligible"] is False:
            issues.append("C8 selected source violates independently read nonnegative subset predicates")
        magnitude_is_hypothesis = True
    else:
        selected_elig = None
        member_results = []
        for source in trace["proof"].get("reported_members", []):
            matches = [f for f in parsed["facts"] if f["QName"] == source["concept"] and f["context_ref"] == source["context_ref"]
                and f["unit_ref"] == source["unit_ref"] and Decimal(f["value"]) == Decimal(source["value"])]
            assert matches, "selected member raw source missing"
            member = matches[0]
            fc, pc = member["context"], focus["context"]
            aligned = (fc["entity"], fc["entity_scheme"], fc["period"], member["unit_signature"]) == (pc["entity"], pc["entity_scheme"], pc["period"], focus["unit_signature"])
            member_results.append({"fact": member, "exact_entity_period_unit_alignment": aligned})
        member_sum = sum((Decimal(r["fact"]["value"]) for r in member_results), Decimal(0))
        members_verified = {"members": member_results, "sum": str(member_sum),
            "agrees_C8_calculated": member_sum == Decimal(old["C8"]["calculated_value"]),
            "all_aligned": all(r["exact_entity_period_unit_alignment"] for r in member_results),
            "source_cube_choice_independently_gold_certified": False}
        if not members_verified["agrees_C8_calculated"] or not members_verified["all_aligned"]:
            issues.append("C8 dimensional arithmetic/source alignment mismatch")
        magnitude_is_hypothesis = False
    equations, unresolved = same_frame_equations(parsed, focus)
    competing_equations = []
    for fact in asked:
        if frame(fact) == frame(focus):
            continue
        eq, _ = same_frame_equations(parsed, fact)
        if any("computed" in e for e in eq):
            competing_equations.append({"source": fact, "equations": eq})
    complete_values = sorted({Decimal(e["computed"]) for e in equations if "computed" in e})
    disagree = [str(v) for v in complete_values if v != Decimal(old["C8"]["calculated_value"])]
    return {"id": row["id"], "DQC": old["locally_inferred_DQC"], "query_sha256": old["query_sha256"],
        "source_section_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k,v in parsed["parts"].items()},
        "question": parsed["question"], "target": parsed["target"], "period": parsed["period"],
        "C8": old["C8"], "historical_status_reused_without_resolving": old["score_constraint_all_history"],
        "cohort": "nonfallback171", "all_exact_QName_period_facts": asked, "distinct_reported_values": [str(v) for v in values],
        "C8_selected_fact_independently_reproduced": focus, "extraction_numeric_invariant_certificate": extraction_invariant,
        "extraction_certificate": certificate,
        "extraction_certificate_scope": "all supplied numeric facts with literal QName and requested period share C8 value; no full-answer/gold claim",
        "all_negative_subset_eligibility": nonnegative, "C8_0015_independent_subset_eligibility": selected_elig,
        "DQC0015_absolute_magnitude_is_hypothesis": magnitude_is_hypothesis, "DQC0117_raw_member_validation": members_verified,
        "same_frame_raw_calculation_equations": equations, "competing_frame_complete_equations": competing_equations,
        "calculation_locator_issues": unresolved, "direct_equations_disagree_with_C8_calculation": disagree,
        "new_structural_issues": issues, "prior_risk_tags_for_comparison_only": old["risk_tags"],
        "official_error_proved": False, "independently_unique_new_answer_proved": False,
        "diagnosis": "Q1 extraction invariant across supplied contexts" if extraction_invariant else "question lacks explicit entity/unit/dimension scope; several literal requested-period sources survive",
        "reopen_condition": "independent supplied equation anchors or question-to-context witness; arbitrary majority/first fact not accepted",
        "hidden_gold_accessed": False, "external_filing_answers_used": False}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    resource_hashes = {}
    for path in (ROOT / "resources/task3_dqc0015/source_manifest.json", ROOT / "resources/task3_round4_dqc/dqc0015_legacy_source_manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf8"))
        for record in manifest["files"]:
            filename = Path(record.get("file", record.get("path", "")).replace("\\", "/")).name
            resource = path.parent / filename
            assert sha(resource) == record["sha256"], f"Original generic resource SHA changed: {filename}"
            resource_hashes[str(resource.relative_to(WORK))] = sha(resource)
    old_rows = rows(OLD / "source_evidence_inventory.jsonl")
    high = [r for r in old_rows if r["score_constraint_all_history"]["state"] != "necessarily_correct"]
    cohort = {r["id"]: r for r in high if r["C8_selection"] is not None}
    assert len(high) == 196 and len(cohort) == 171
    source = ROOT / "data/raw/task3/development_inputs.jsonl"
    inputs = [r for r in rows(source) if r["id"] in cohort]
    exc = exclusions()
    output = [audit(r, cohort[r["id"]], exc) for r in inputs]
    path = OUT / "nonfallback_diagnostics.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in output), encoding="utf8")
    certificates = [{"id": r["id"], "DQC": r["DQC"], "C8": r["C8"], "target": r["target"], "period": r["period"],
        "query_sha256": r["query_sha256"], "section_sha256": r["source_section_sha256"]["Instance document"],
        **r["extraction_certificate"]} for r in output if r["extraction_numeric_invariant_certificate"]]
    (OUT / "Q1_numeric_invariant_certificates.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in certificates), encoding="utf8")
    (OUT / "Q1_numeric_invariant_case_ids.json").write_text(json.dumps([r["id"] for r in certificates], indent=2) + "\n", encoding="utf8")
    with (OUT / "nonfallback_audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["id", "DQC", "C8_extracted", "C8_calculated", "raw_values", "numeric_invariant_extraction", "same_frame_equations", "complete_equations", "equation_disagreements", "new_issues", "official_error_proved", "new_answer_proved"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in output:
            writer.writerow({"id": r["id"], "DQC": r["DQC"], "C8_extracted": r["C8"]["extracted_value"], "C8_calculated": r["C8"]["calculated_value"],
                "raw_values": " | ".join(r["distinct_reported_values"]), "numeric_invariant_extraction": r["extraction_numeric_invariant_certificate"],
                "same_frame_equations": len(r["same_frame_raw_calculation_equations"]), "complete_equations": sum("computed" in e for e in r["same_frame_raw_calculation_equations"]),
                "equation_disagreements": " | ".join(r["direct_equations_disagree_with_C8_calculation"]), "new_issues": " | ".join(r["new_structural_issues"]),
                "official_error_proved": False, "new_answer_proved": False})
    summary = {"cohort": len(output), "DQC_counts": dict(Counter(r["DQC"] for r in output)),
        "raw_source_selected_reproduced": len(output), "numeric_invariant_extraction_certificates": sum(r["extraction_numeric_invariant_certificate"] for r in output),
        "still_context_ambiguous": sum(not r["extraction_numeric_invariant_certificate"] for r in output),
        "new_structural_issue_cases": [r["id"] for r in output if r["new_structural_issues"]],
        "complete_same_frame_equation_cases": [r["id"] for r in output if any("computed" in e for e in r["same_frame_raw_calculation_equations"])],
        "direct_equation_disagreement_cases": [r["id"] for r in output if r["direct_equations_disagree_with_C8_calculation"]],
        "independent_SRT_registry_unresolved": [r["id"] for r in output if r["C8_0015_independent_subset_eligibility"] and r["C8_0015_independent_subset_eligibility"]["subset_eligible"] is None],
        "new_proven_official_errors": 0, "independently_proved_unique_new_answers": 0, "candidate_numeric_changes": 0,
        "input_sha256": sha(source), "old_inventory_sha256": sha(OLD / "source_evidence_inventory.jsonl"),
        "generic_resource_sha256": resource_hashes,
        "audit_script_sha256": sha(Path(__file__)), "diagnostics_sha256": sha(path),
        "method_independence": "fresh lxml raw-instance, ZIP workbook registry and raw effective calculation arc implementation; no C8 engine imports",
        "no_native_rerun": True, "no_score_solver_rerun": True, "no_hidden_gold": True, "no_network_in_script": True,
        "claim_limits": "Extraction invariants are supplied-source certificates; neither hidden labels nor full corrected answer certification. Direct equations require trustworthy anchors, and DQC0015 alone cannot prove absolute magnitude."}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
