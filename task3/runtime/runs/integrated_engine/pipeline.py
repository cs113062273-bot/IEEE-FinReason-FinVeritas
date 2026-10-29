"""Integrated source-conditioned 670 inference; no Development ID dispatch.

C8, the document-first fallback, and every subsequent successful selector are
rerun against the supplied query. Four Development native C5 exceptions retain
explicitly disclosed legacy priors. Test can execute with no numeric priors.
No feedback or labels are consulted. C117 retains its notes-overlap limitation.
"""
import importlib.util,sys,re
from pathlib import Path
from decimal import Decimal
W=Path(__file__).resolve().parents[2]
ROOT=W/'core/source'
sys.path.insert(0,str(W/'runs/calculation_semantics'))
import strategies_new as cn
old=cn.prev.old
raw=cn.raw
earlier=old.previous
ownership=earlier.ownership
reserve=old.parent
loss=cn.prev.prior
sys.path.insert(0,str(W/'runs/focus_selection'))
import focus_selectors as options
spec=importlib.util.spec_from_file_location('integrated_efc_metadata',W/'runs/focus_selection/common.py')
efc=importlib.util.module_from_spec(spec);spec.loader.exec_module(efc)
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import task3_semantics_candidate_trial as c8
from task3.round5_engine import predict as source_document_first
raw.xml=ownership.s.closed_xml

def same(a,b):return all(Decimal(a[k])==Decimal(b[k]) for k in ['extracted_value','calculated_value'])

def infer(query,legacy_prior,exclusions,output_id=None):
    """Apply identical source conditions on any split; ID is output metadata."""
    legacy_cache_present=legacy_prior is not None
    if legacy_prior is None:legacy_prior={'id':output_id or 'source_only','extracted_value':'0','calculated_value':'0'}
    value=dict(legacy_prior);events=[];programs=[]
    try:
        filing,_=c8.normalize(c8.parse_xml(query,allow_complete_prefix=True))
        programs,summary=c8.make(query,filing,False)
        selected=c8.unique_pair(programs,summary)
        if selected:value.update(extracted_value=selected['reported'],calculated_value=selected['value'])
        events.append({'rule':'C8_v34','changed':not same(value,legacy_prior),'selected':selected,'program_count':len(programs)})
    except Exception as e:
        events.append({'rule':'C8_v34','changed':False,'legacy_fallback':True,'error':repr(e)})
    if events[0].get('selected') is None:
        # Recompute the historical document-first fallback from source. The
        # remaining native C5 exceptions are explicit cache dependencies; they
        # are never silently relabelled as freshly computed source results.
        rebuilt=source_document_first(query,policy='document_first')
        source_value={**legacy_prior,'extracted_value':rebuilt.extracted_value,'calculated_value':rebuilt.calculated_value}
        retained=legacy_cache_present and not same(source_value,legacy_prior)
        value=dict(legacy_prior) if retained else source_value
        events[0].update(document_first_source_recomputed=True,document_first_prediction=source_value,legacy_native_cache_retained=retained,document_first_mechanism=rebuilt.mechanism)
    c8_value=dict(value)
    match=re.search(r'Question1:.*?reported value of\s+[\w.-]+:([\w.-]+)',query)
    local=match[1] if match else None
    active=[]
    if 'OwnershipAxis' in query:active.append(('H15',lambda p,b:ownership.select(p,b,exclusions)[:2]))
    if sum(p['rule'].startswith('DQC.US.0117.') and p.get('eligible') and p.get('relation_verified') and p.get('violation') for p in programs)>=2:
        active.append(('N117',lambda p,b:earlier.terminal_violation(p,b,programs,exclusions)))
    if local=='PaymentsForRestructuring':active.append(('R15_plan',lambda p,b:reserve.reserve_closed_plan(p,b,programs,exclusions)))
    if local=='StockIssuedDuringPeriodSharesStockOptionsExercised':active.append(('E15',lambda p,b:options.semantic_options_exercise(efc.augment_external_metadata(p),b,programs,exclusions)))
    if local=='UnrealizedLossOnSecurities':active.append(('L15',lambda p,b:loss.loss_component_partition(p,b,programs,exclusions)))
    if local=='RevenueFromContractWithCustomerExcludingAssessedTax':active.append(('C117',lambda p,b:cn.statement_member_scope(p,b,programs,exclusions)))
    if local=='DerivativeNotionalAmount':active.append(('N15',lambda p,b:cn.liability_notional_partition(p,b,programs,exclusions)))
    parsed=raw.source_parse(query) if active else None
    for name,selector in active:
        before=value
        new,proof=selector(parsed,before)
        value=new or before
        events.append({'rule':name,'changed':not same(value,before),'old':before,'new':value,'evidence':proof})
    return value,events,c8_value,programs
