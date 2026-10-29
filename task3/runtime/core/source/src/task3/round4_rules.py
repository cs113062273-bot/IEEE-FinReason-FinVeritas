"""Generic historical DQC0015 constraints, with exact namespace and exemptions.

Source lists are public rule definitions. No case IDs, answers, or query labels
are loaded. A listed negative value supports an auditable sign-repair candidate,
whose original magnitude remains a benchmark hypothesis rather than a theorem.
"""
from __future__ import annotations

import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from .round3_engine import member_exclusions, nonnegative_eligibility

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "resources/task3_round4_dqc"


@lru_cache(maxsize=1)
def registry():
    manifest_path = RESOURCES / "dqc0015_legacy_source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = {}
    for record in manifest["files"]:
        name = Path(record.get("file", record.get("path", "")).replace("\\", "/")).name
        path = RESOURCES / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Generic historical DQC resource hash mismatch")
        if not name.endswith(".csv"):
            continue
        if name == "v18_dqc_15_srt_concepts.csv":
            with path.open(encoding="utf-8-sig", newline="") as stream:
                concepts = {row[1].split(":")[-1]: row[0] for row in csv.reader(stream) if len(row) > 1}
            result[("srt", 2021)] = concepts
            result[("srt", 2022)] = concepts
            continue
        if "srt" in name:
            match = re.search(r"_(20\d\d)_concepts", name)
            year = int(match[1]) if match else 2022
            namespace = "srt"
        else:
            match = re.search(r"_(20\d\d)_concepts", name)
            if not match:
                continue
            namespace, year = "us-gaap", int(match[1])
        with path.open(encoding="utf-8-sig", newline="") as stream:
            result[(namespace, year)] = {row[1].split(":")[-1]: row[0]
                                         for row in csv.reader(stream) if len(row) > 1}
    return result, manifest


def eligibility(filing, fact, context):
    existing = nonnegative_eligibility(filing, fact, context)
    if existing["eligible"]:
        return existing
    match = re.fullmatch(r"\{http://fasb\.org/(us-gaap|srt)/(20\d\d)(?:-01-31)?\}(.+)", fact.concept)
    result = {"eligible": False, "constraint_proves_original_magnitude": False,
              "concept": fact.concept, "exclusion": "unsupported or unlisted concept"}
    if not match or fact.value >= 0:
        return result
    expected_uri = f"http://fasb.org/{match[1]}/{match[2]}" + ("-01-31" if match[2] == "2021" else "")
    if fact.concept.split("}", 1)[0][1:] != expected_uri:
        result["exclusion"] = "namespace does not match the published taxonomy version"
        return result
    data, manifest = registry()
    rule = data.get((match[1], int(match[2])), {}).get(match[3])
    if not rule:
        return result
    if not context.entity or not context.scheme or context.qualifiers or fact.unit not in filing.units or not filing.units[fact.unit].numerator:
        result["exclusion"] = "unresolved entity, unit or context qualifier"
        return result
    exemptions = member_exclusions()
    for axis, member in context.dimensions:
        if not isinstance(member, str):
            result["exclusion"] = "opaque typed dimension"
            return result
        axis_name, member_name = axis.partition("}")[2], member.partition("}")[2]
        if (axis_name in exemptions["axes"] or member_name in exemptions["members"]
                or any(token in member_name.lower() for token in exemptions["strings"])
                or (axis_name, member_name) in exemptions["axis_members"]):
            result["exclusion"] = "public member/axis exemption"
            return result
    result.update(eligible=True, exclusion=None, rule="DQC.US.0015." + rule,
                  namespace_year=match[2], taxonomy=match[1], definition_commit=manifest.get("commit"),
                  source_manifest_sha256=hashlib.sha256((RESOURCES / "dqc0015_legacy_source_manifest.json").read_bytes()).hexdigest(),
                  member_exclusions_sha256=exemptions["source_sha256"], full_form_applicability=False)
    return result
