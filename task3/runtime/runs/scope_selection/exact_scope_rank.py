"""The existing loan-scope hypothesis with context-free exact magnitudes.

This preserves its disclosed inductive Focus preference. A source value's
absolute magnitude must not be rounded by Python's ambient Decimal context.
No question identifier, issuer, gold, split or amount threshold is used.
"""
from decimal import Decimal
from normalized_metadata import catalog
import source_financial_semantics as sem
from helpers import raw

LOAN_CLASS='FinancingReceivableRecordedInvestmentByClassOfFinancingReceivableAxis'
ALLOWANCE='FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest'

def select(parsed, incumbent, programs):
    if parsed['target'].split('}')[-1]!=ALLOWANCE:return None
    eligible={Decimal(p['reported']) for p in programs if p.get('eligible')
              and p['rule'].startswith('DQC.US.0015.') and Decimal(p['reported'])<0}
    if len(eligible)<2 or Decimal(incumbent['extracted_value']) not in eligible:return None
    facts=[f for f in sem.target_facts(parsed) if Decimal(f['value']) in eligible]
    if not any(not sem.dims(f) for f in facts):return None
    parts,provenance=catalog().bind(parsed,labels=False)
    parts=parts or parsed['parts'];cubes=sem.drs(parsed,parts)
    supported=[]
    exclusions=raw.exclusions()
    for fact in facts:
        dims=sem.dims(fact)
        if dims and (len(dims)!=1 or next(iter(dims)).split('}')[-1]!=LOAN_CLASS):continue
        if raw.eligibility_0015(fact,parsed['parts'],exclusions)['subset_eligible'] is not True:continue
        witnesses=[c for c in cubes if sem.inside(fact,c)]
        if witnesses:supported.append((fact,witnesses))
    if not any(sem.dims(f) for f,c in supported):return None
    if not any(not sem.dims(f) for f,c in supported):return None
    largest=max(Decimal(f['value']).copy_abs() for f,c in supported)
    winners=[(f,c) for f,c in supported if Decimal(f['value']).copy_abs()==largest]
    values={Decimal(f['value']) for f,c in winners}
    if len(values)!=1:return None
    x=next(iter(values))
    if x==Decimal(incumbent['extracted_value']):return None
    return {'new':{'extracted_value':str(x),'calculated_value':str(x.copy_abs())},
            'rule':'loan_allowance_scope_valid_negative_severity',
            'experimental_ranking_not_unique_focus_proof':True,
            'source_witnesses':[{'fact':f,'roles':[{'role':c['role'],'cube':c['cube'],'description':c['description']} for c in cs]} for f,cs in supported],
            'structural_metadata':provenance}
