"""Selective public-rule sign hypothesis; no hidden rule labels or findings.

Copyright notices and permission for the generic DQC concept definitions are
preserved in resources/task3_dqc0015/License.md. Only a listed concept in its
exact supplied US-GAAP namespace version is eligible, with no dimensions or
other context qualifiers. Balance credit/debit alone is never a sign signal.
"""
from __future__ import annotations

import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from .engine import Prediction
from .xml_core import number
from .xml_engine import guarded_fallback

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "resources/task3_dqc0015"


@lru_cache(maxsize=1)
def public_constraints() -> tuple[dict, dict]:
    manifest = json.loads((RESOURCES / "source_manifest.json").read_text(encoding="utf-8"))
    for record in manifest["files"]:
        path = ROOT / record["file"].replace("\\", "/")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Pinned public DQC rule resource hash mismatch")
    registry = {}
    for year in (2023, 2024, 2025, 2026):
        with (RESOURCES / f"dqc_15_usgaap_{year}_concepts.csv").open(encoding="utf-8-sig", newline="") as source:
            registry[year] = {row[1]: row[0] for row in csv.reader(source) if len(row) >= 2}
    return registry, manifest


def selective_nonnegative(result: Prediction) -> Prediction:
    """Use complete equations first; test a listed-concept sign hypothesis later.

    DQC eligibility proves a nonnegative constraint, not the original magnitude
    of an erroneous fact. Negating the supplied magnitude is a scoreable repair
    hypothesis, explicitly unverified until actual gold/Development feedback.
    """
    evidence = dict(result.evidence)
    evidence.update({"fallback_policy": "dqc0015_selective_sign", "fallback_applied": False,
                     "fallback_accuracy_verified": False})
    # Reuse the target-integrity gate, without promoting its agree value.
    guard = guarded_fallback(result, policy="agree")
    if not guard.evidence.get("fallback_applied"):
        evidence["fallback_gate"] = "blocked by target/context/unit/document/role integrity, or complete equation already present"
        return Prediction(result.extracted_value, result.calculated_value, result.mechanism, evidence)
    concept = evidence.get("target") or evidence.get("parent", {}).get("concept", "")
    match = re.fullmatch(r"\{http://fasb\.org/us-gaap/(202[3-6])\}(.+)", concept)
    value = number(result.extracted_value)
    if match is None or value is None or value >= 0:
        evidence["fallback_gate"] = "blocked: no supported US-GAAP namespace and negative fact"
        return Prediction(result.extracted_value, result.calculated_value, result.mechanism, evidence)
    registry, manifest = public_constraints()
    rule_suffix = registry[int(match[1])].get(match[2])
    if rule_suffix is None:
        evidence["fallback_gate"] = "blocked: concept is not in the pinned DQC nonnegative set; credit/debit ignored"
        return Prediction(result.extracted_value, result.calculated_value, result.mechanism, evidence)
    evidence.update({"fallback_applied": True, "fallback_gate": "negative listed nonnegative concept; dimension-free unambiguous target",
                     "fallback_calculation_unverified": True, "independent_calculation_evidence": False,
                     "public_constraint_rule": "DQC.US.0015." + rule_suffix,
                     "public_constraint_namespace_version": match[1], "public_constraint_commit": manifest["commit"],
                     "public_constraint_manifest_sha256": hashlib.sha256((RESOURCES / "source_manifest.json").read_bytes()).hexdigest(),
                     "dimension_exemptions": "All dimensions and segment/scenario qualifiers excluded by the target integrity gate",
                     "constraint_proves_original_magnitude": False,
                     "fallback_reason": "General public nonnegative-concept constraint; sign repair of supplied magnitude remains a Development hypothesis"})
    return Prediction(result.extracted_value, str(value.copy_negate()), "dqc0015-selective-sign-hypothesis", evidence)
