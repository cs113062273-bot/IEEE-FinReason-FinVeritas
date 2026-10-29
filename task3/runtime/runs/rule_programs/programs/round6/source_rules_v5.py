"""Spark dual-instrument source focus; earlier sealed rules are preserved."""
import re
from decimal import Decimal
from source_rules_v4 import apply as v4_apply,entity_bound_original_metadata
from source_rules import prev,ds,xml
from helpers import raw
from member_focus_experiments import drs_paths
from independent_198 import drs,inside

def spark(p):
    from pair_facilities import select as paired_source_facilities
    return paired_source_facilities(p)

def apply(p):
    prior=v4_apply(p)
    proposal=spark(p)
    if prior and proposal:
        differs=any(Decimal(prior['new'][k])!=Decimal(proposal['new'][k]) for k in ['extracted_value','calculated_value'])
        return {**proposal,'overridden_single_owner_candidate':prior if differs else None,
                'owner_precedence_basis':'Distinct financial facilities corroborate one value; this source evidence supersedes the earlier single-owner preference as an explicit research hypothesis.',
                'prior_rule_same_value':not differs}
    return proposal or prior
