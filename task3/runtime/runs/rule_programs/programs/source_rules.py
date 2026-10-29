"""Source-conditioned S/O/P selectors. No split, case ID, or numeric prior gate.

The Product selector is a provisional-judge focus convention, not a claim that
the original Xule notes-overlap guard fires. Its explicit guard waiver is kept
in every decision record.
"""
import sys,re,hashlib
from pathlib import Path
from decimal import Decimal
W=next(p for p in Path(__file__).resolve().parents if (p/'core').is_dir())
sys.path.insert(0,str(W/'runs/calculation_semantics'))
from helpers import prev,local,ds,val
from independent_198 import sums,xml
sys.path.insert(0,str(W/'runs/member_focus/selectors'))
from member_focus_experiments import select

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def original_metadata(p):
    from normalized_metadata import metadata_or_supplied
    return metadata_or_supplied(p)

def product(p):
    target=p['target']
    if not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}CostOfGoodsAndServicesSold',target):return None
    ns=target.split('}')[0]+'}';year=re.search(r'/([0-9]{4})}',target).group(1)
    axis='{http://fasb.org/srt/'+year+'}ProductOrServiceAxis';member=ns+'ProductMember'
    candidates=[f for f in prev.fs(p) if ds(f)=={axis:member} and f['unit_signature']==(('{http://www.xbrl.org/2003/iso4217}USD',),())]
    if len(candidates)!=1:return None
    focus=candidates[0];parts,meta=original_metadata(p)
    computations=[r for r in sums(p,focus,parts) if r['included_facts'] and r['axis']==ns+'RelatedPartyTransactionsByRelatedPartyAxis']
    if not computations:return None
    values={Decimal(r['calculated']) for r in computations}
    if len(values)!=1:return None
    return {'new':{'extracted_value':focus['value'],'calculated_value':str(next(iter(values)))},'focus':focus,'computations':computations,'metadata':meta,'rule':'P117_ProductMember_related_party_statement','question_focus_proved_by_source_alone':False,'notes_guard_override_explicit':not all(r['notes_overlap_guard_passed'] for r in computations),'full_original_assertion_applicable':all(r['notes_overlap_guard_passed'] for r in computations),'risk':'Member preference is a provisional-judge convention; notes-overlap guard may skip this focus in full Xule. Related-party sum can be an allocated component rather than the complete financial total.'}

def apply(parsed):
    for mode in ['state_local','opeb']:
        proposal=select(parsed,mode)
        if proposal:return proposal
    return product(parsed)
