"""Additional validated focus conventions: Equipment and Kansas legal entity.

No case ID, query hash, expected amount, filing date, or taxonomy-year ranking
selects an answer. CECL CRE is deliberately not generalized: the two original
filings have identical asked-period fact/context structures yet opposite
provisional focus labels.
"""
import re
from decimal import Decimal
from source_rules import apply as sop_apply,original_metadata,prev,ds,local,sums,select
from member_focus_experiments import drs_paths
from helpers import raw
from independent_198 import xml

def equipment(p):
    target=p['target']
    if not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}CostOfGoodsAndServicesSold',target):return None
    year=re.search(r'/([0-9]{4})}',target).group(1)
    axis='{http://fasb.org/srt/'+year+'}ProductOrServiceAxis'
    extension=xml(p['parts']['Schema document']).get('targetNamespace')
    member='{'+extension+'}SalesOfEquipmentMember'
    eligible=[f for f in prev.fs(p) if ds(f)=={axis:member} and f['unit_signature']==(('{http://www.xbrl.org/2003/iso4217}USD',),())]
    if len(eligible)!=1:return None
    focus=eligible[0];parts,metadata=original_metadata(p)
    computations=[c for c in sums(p,focus,parts) if c['included_facts'] and c['axis']=='{http://fasb.org/us-gaap/'+year+'}StatementBusinessSegmentsAxis']
    values={Decimal(c['calculated']) for c in computations}
    if len(values)!=1:return None
    return {'new':{'extracted_value':focus['value'],'calculated_value':str(next(iter(values)))},'rule':'E117_EquipmentMember_statement_segment_sum','focus':focus,'computations':computations,'metadata':metadata,'notes_guard_override_explicit':not all(c['notes_overlap_guard_passed'] for c in computations),'full_original_assertion_applicable':all(c['notes_overlap_guard_passed'] for c in computations),'question_focus_proved_by_source_alone':False,'risk':'Equipment member preference is supported by a single scored Development case. Full original notes guard still skips this focus.'}

def kansas(p):
    if not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}IncomeTaxReconciliationNondeductibleExpenseLifeInsurance',p['target']):return None
    extension=xml(p['parts']['Schema document']).get('targetNamespace')
    member='{'+extension+'}EvergyKansasCentralIncMember'
    eligible=[]
    for f in prev.fs(p):
        d=ds(f)
        if len(d)!=1 or Decimal(f['value'])>=0 or f['unit_signature']!=(('{http://www.xbrl.org/2003/iso4217}USD',),()):continue
        axis=next(iter(d))
        if not re.fullmatch(r'\{http://xbrl.sec.gov/dei/20\d\d\}LegalEntityAxis',axis) or d[axis]!=member:continue
        if raw.eligibility_0015(f,p['parts'],raw.exclusions())['subset_eligible'] is not True:continue
        paths=drs_paths(p,axis,member)
        if paths:eligible.append((f,paths))
    if len(eligible)!=1:return None
    focus,paths=eligible[0]
    return {'new':{'extracted_value':focus['value'],'calculated_value':str(abs(Decimal(focus['value'])))},'rule':'K15_KansasCentral_legal_entity','focus':focus,'DRS_paths':paths,'question_focus_proved_by_source_alone':False,'calculation_basis':'DQC0015 sign-repair hypothesis; no fabricated calculation arcs.','risk':'Issuer-named legal entity preference is supported by a single scored Development case; generic question itself omits legal entity.'}

def apply(p):
    return sop_apply(p) or equipment(p) or kansas(p)
