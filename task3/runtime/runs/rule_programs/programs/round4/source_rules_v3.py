"""Validated Revenue Service focus convention added without modifying v2.

Selection uses original source aspects and DRS, never a Question ID, known
answer, source hash, or fixed reporting date. The member preference was learned
from provisional feedback; it is not uniqueness established by original Xule.
"""
import re
from decimal import Decimal
from source_rules_v2 import apply as v2_apply
from source_rules import original_metadata,prev,ds,sums
from independent_198 import xml

def revenue_service(p):
    target=p['target']
    if not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}RevenueFromContractWithCustomerExcludingAssessedTax',target):return None
    year=re.search(r'/([0-9]{4})}',target).group(1)
    fixed_axis='{http://fasb.org/srt/'+year+'}ProductOrServiceAxis'
    extension=xml(p['parts']['Schema document']).get('targetNamespace')
    member='{'+extension+'}ServiceSalesMember'
    eligible=[f for f in prev.fs(p) if ds(f)=={fixed_axis:member} and f['unit_signature']==(('{http://www.xbrl.org/2003/iso4217}USD',),())]
    if len(eligible)!=1:return None
    focus=eligible[0];parts,metadata=original_metadata(p)
    axis='{http://fasb.org/us-gaap/'+year+'}StatementBusinessSegmentsAxis'
    programs=[c for c in sums(p,focus,parts) if c['included_facts'] and c['axis']==axis]
    values={Decimal(c['calculated']) for c in programs}
    if len(values)!=1:return None
    if any(prev.aspect(f)!=prev.aspect(focus) for c in programs for f in c['included_facts']):return None
    guard=all(c['notes_overlap_guard_passed'] for c in programs)
    return {'new':{'extracted_value':focus['value'],'calculated_value':str(next(iter(values)))},'rule':'S117_Revenue_ServiceSalesMember_statement_segments','focus':focus,'computations':programs,'metadata':metadata,'same_entity_period_unit_and_fixed_product':True,'question_focus_proved_by_source_alone':False,'focus_preference_learned_from_provisional_feedback':True,'full_original_assertion_applicable':guard,'notes_guard_override_explicit':not guard,'risk':'Service member preference has one successful provisional Development control; source alone does not uniquely select it. Original full notes-overlap guard may skip this focus.'}

def apply(p):
    return v2_apply(p) or revenue_service(p)
