"""Query-only DQC0126 direct-addend semantics with explicit Xule policies.

Public rule sources and their license are preserved in resources/task3_dqc0126.
Generic Xule processor source is pinned under resources/task3_round6_xule.
This is a bounded supplied-document adapter, not a complete DTS validator.
No IDs, labels, answer tables, external filings or model calls enter inference.
"""
from __future__ import annotations

from collections import Counter,defaultdict
from decimal import Decimal,localcontext
from functools import lru_cache
import hashlib
from pathlib import Path
import re

from .dqc_statement_sum import _document,_locators
from .round4_dimensional import ROLE_EXCLUSIONS,CUBE_EXCLUSIONS,CONSTANT_SHA
from .round4_statement import RULE_SHA,LIB_FUNCTION_SHA,PRES_EXTRA_EXCLUSIONS,decimals_rank
from .period_semantics import canonical, period_key
from .parser import format_number
from .exact_arithmetic import product as exact_product, add as exact_add
from .xml_core import LINK,XLINK,attr,tag_parts

ROOT=Path(__file__).resolve().parents[2]
INDEXER_SHA='3a32024002e0ac7e8f60669c6a41ebfb17119a71ddb8a98ebd84ad41d0f9876e'
PROCESSOR_COMMIT='7ca1d7637f333f5c3a02379dbe6f6d6c17c88acc'
DIM='http://xbrl.org/int/dim/arcrole/'
LEGACY_SUMMATION='http://www.xbrl.org/2003/arcrole/summation-item'

def legacy_calculation_arcs(filing):
    """DQC0126 navigates Xule's summation-item network, not Calc1.1.

    Calculation 1.1 section 4.1 requires the two arcroles to remain separate.
    Both remain available in filing.arcs for other explicitly scoped adapters.
    """
    return [arc for arc in filing.arcs if arc.arcrole==LEGACY_SUMMATION]


@lru_cache(maxsize=1)
def verify_sources():
    files={'resources/task3_dqc0126/DQC_0126.xule':RULE_SHA,
           'resources/task3_round4_dqc/constant.xule':CONSTANT_SHA,
           'resources/task3_round4_dqc/functions-lib.xule':LIB_FUNCTION_SHA,
           'resources/task3_round6_xule/XuleModelIndexer.py':INDEXER_SHA}
    for name,digest in files.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Pinned generic semantic source changed: '+name)
    return files


def alignment(filing,fact,*,include_dimensions=True):
    """Xule builtins: entity, period, unit; XML IDs are not alignment aspects."""
    ctx,unit=filing.contexts.get(fact.context),filing.units.get(fact.unit)
    if (ctx is None or unit is None or not unit.numerator or not ctx.scheme or not ctx.entity
            or not (ctx.instant or ctx.start and ctx.end)):
        return None
    return (ctx.scheme,ctx.entity,*period_key(ctx.start,ctx.end,ctx.instant),unit.signature,
            ctx.dimensions if include_dimensions else ())


def _round(value,decimals):
    if decimals.is_infinite():
        return value
    with localcontext() as arithmetic:
        # quantize/round must accommodate the result's integer digits too:
        # Decimal('1E300') has one coefficient digit but 301 integer digits.
        arithmetic.prec=max(80,len(value.as_tuple().digits)+5,
                            max(1,value.adjusted()+1)+max(0,int(decimals))+5)
        return round(value,int(decimals))


def indexed_facts(filing,policy='xule_default'):
    """Reproduce documented default Xule indexing; raw is include-dups ablation.

    R4's closed interval intersection is not the same test. Equal values at
    different accuracy are indexed once; inconsistent duplicates remain.
    Unknown decimals are retained as explicit ambiguity, never fabricated.
    """
    if policy not in {'xule_default','raw_include_dups'}:
        raise ValueError('Unknown duplicate policy')
    source=[f for f in filing.facts if alignment(filing,f) is not None]
    if policy=='raw_include_dups':
        return source,{'policy':policy,'source_fact_count':len(source),'indexed_fact_count':len(source),'removed_indexes':[]}
    groups=defaultdict(list)
    for fact in sorted(source,key=lambda f:f.index):
        key=(fact.concept,alignment(filing,fact))
        matches=False
        current_decimals=decimals_rank(fact.decimals)
        for position,saved in enumerate(groups[key]):
            saved_decimals=decimals_rank(saved.decimals)
            if current_decimals is None or saved_decimals is None:
                continue
            precision=min(current_decimals,saved_decimals)
            if _round(fact.value,precision)==_round(saved.value,precision):
                matches=True
                if current_decimals>saved_decimals:
                    groups[key][position]=fact
        if not matches:
            groups[key].append(fact)
    # Upstream index buckets and the all-facts index are sets.
    chosen={f.index:f for facts in groups.values() for f in facts}
    return sorted(chosen.values(),key=lambda f:f.index),{
        'policy':policy,'source_fact_count':len(source),'indexed_fact_count':len(chosen),
        'removed_indexes':sorted({f.index for f in source}-set(chosen)),
        'same_aspect_test':'entity/period/unit/reported dimensions; concept also held equal',
        'numeric_duplicate_test':'equal after rounding both values to minimum declared decimals',
        'processor_commit':PROCESSOR_COMMIT,'processor_indexer_sha256':INDEXER_SHA,
        'full_schema_validation_available':False}


def modal_decimals(filing,role,*,duplicate_policy='xule_default',facts=None):
    """[] excludes unspecified taxonomy dimensions even with covered keyword."""
    facts= indexed_facts(filing,duplicate_policy)[0] if facts is None else facts
    source_concepts={arc.parent for arc in legacy_calculation_arcs(filing) if arc.role==role}
    selected=[f for f in facts if f.concept in source_concepts
              and f.context in filing.contexts and not filing.contexts[f.context].dimensions]
    counts=Counter(decimals_rank(f.decimals) for f in selected)
    unknown=counts.pop(None,0)
    modes=sorted(d for d,n in counts.items() if n==max(counts.values())) if counts else []
    modal=modes[0] if len(modes)==1 and not unknown else None
    return modal,{'modal_decimals':str(modal) if modal is not None else None,
        'decimals_counts':{str(d):n for d,n in sorted(counts.items())},'unknown_decimals_count':unknown,
        'tied_modes':[str(d) for d in modes] if len(modes)>1 else [],
        'source_concepts':sorted(source_concepts),'modal_fact_indexes':[f.index for f in selected],
        'covered_policy':'all supplied nonnil NONDIMENSIONAL source-concept facts across all alignments',
        'square_bracket_selection_preserved':True,'duplicate_policy':duplicate_policy,
        'tie_policy':'abstain; most_frequent uses a frequency-keyed dictionary with ambiguous ties'}


def choose_addend(facts,modal):
    tiers=[('decimals==modal',[f for f in facts if decimals_rank(f.decimals)==modal]),
           ('decimals>=modal',[f for f in facts if decimals_rank(f.decimals) is not None and decimals_rank(f.decimals)>=modal]),
           ('decimals<modal',[f for f in facts if decimals_rank(f.decimals) is not None and decimals_rank(f.decimals)<modal])]
    for name,tier in tiers:
        if not tier:
            continue
        values={f.value for f in tier}
        proof={'tier':name,'alternative_indexes':[f.index for f in tier],
               'alternative_values':sorted(format_number(v) for v in values),
               'ambiguous':len(values)!=1,'first_list_order_assumed':False}
        if len(values)!=1:
            return None,proof
        selected=min(tier,key=lambda f:f.index)
        proof['selected_index']=selected.index
        return selected,proof
    return None,{'tier':'unbound','ambiguous':any(decimals_rank(f.decimals) is None for f in facts),
                 'first_list_order_assumed':False}


def statement_roles(query,filing,*,allow_inferred_statement=False):
    """Select statement presentation networks; target need not be presented.

    DQC0126 navigates every calculation source in the shared statement role.
    It does not filter sources by membership in the presentation network.
    """
    presentation=_document(query,filing,'Presentation linkbase document')
    definition=_document(query,filing,'Definition linkbase document')
    if presentation is None or definition is None:
        return {},{'blocked':'presentation/definition document unavailable; table absence not certified'}
    cube_roles=set()
    for link in definition.iter('{'+LINK+'}definitionLink'):
        role=attr(link,'role',XLINK)
        locators=_locators(link,filing)
        for arc in link:
            if tag_parts(arc)==(LINK,'definitionArc') and attr(arc,'arcrole',XLINK) in {DIM+'all',DIM+'notAll'}:
                # Even an unsupported prohibited/priority combination makes
                # absence of a supplied statement cube uncertified.
                cube=locators.get(attr(arc,'to',XLINK),'')
                if not cube or cube.partition('}')[2] not in CUBE_EXCLUSIONS:
                    cube_roles.add(role)
    roles={}
    for link in presentation.iter('{'+LINK+'}presentationLink'):
        role=attr(link,'role',XLINK)
        description=filing.role_definitions.get(role) or attr(link,'title',XLINK)
        inferred=False
        if (allow_inferred_statement and not description and 'statement' in role.lower()
                and any(k in role.lower() for k in ('balance','income','operation','cashflow','financialposition'))):
            description='- Statement - (inferred supplied role URI)';inferred=True
        if ('- Statement -' not in description or any(s in role.lower() for s in ROLE_EXCLUSIONS+PRES_EXTRA_EXCLUSIONS)
                or any(s in description.lower() for s in ('schedule iii','schedule iv')) or role in cube_roles):
            continue
        arcs=[a for a in link if tag_parts(a)==(LINK,'presentationArc') and attr(a,'arcrole',XLINK)=='http://www.xbrl.org/2003/arcrole/parent-child']
        if not arcs or any(attr(a,'use')=='prohibited' for a in arcs):
            continue
        locators=_locators(link,filing)
        involved=set()
        for arc in arcs:
            involved.update(filter(None,[locators.get(attr(arc,'from',XLINK)),locators.get(attr(arc,'to',XLINK))]))
        roles[role]={'description':description,'inferred_from_uri':inferred,
                     'description_from_schema':role in filing.role_definitions,
                     'target_in_presentation':filing.target in involved,
                     'target_presentation_membership_required_by_source_rule':False}
    return roles,{'cube_roles_excluded':sorted(cube_roles),'effective_presentation_arc_resolution_complete':False}


def candidates(query,filing,parent,*,duplicate_policy='xule_default',allow_inferred_statement=False):
    """Return applicability and calculation for a supplied target fact/frame.

    Only directly reported compatible children enter the sum. An unbound
    first-value branch contributes no list item; there is no zero fact, inverse
    inference or recursive missing-child reconstruction. Source-order first()
    is not assumed when a selected tier has unequal alternative values.
    """
    sources=verify_sources()
    roles,scope=statement_roles(query,filing,allow_inferred_statement=allow_inferred_statement)
    facts,index_proof=indexed_facts(filing,duplicate_policy)
    parent_key=alignment(filing,parent)
    ctx=filing.contexts.get(parent.context)
    if parent_key is None or ctx is None or ctx.dimensions:
        return []
    grouped=defaultdict(list)
    for arc in legacy_calculation_arcs(filing):
        if arc.parent==parent.concept and arc.role in roles:
            grouped[arc.role].append(arc)
    output=[]
    for role,arcs in grouped.items():
        modal,mode=modal_decimals(filing,role,duplicate_policy=duplicate_policy,facts=facts)
        blockers=[]
        if modal is None:
            blockers.append('non-dimensional source-network mode unavailable or tied')
        elif decimals_rank(parent.decimals)!=modal:
            blockers.append('requested target decimals differ from source-network mode')
        if parent.index not in {f.index for f in facts}:
            blockers.append('requested target removed by selected duplicate-indexing policy')
        if any(d.get('kind') in {'conflicting-arc-weights','unresolved-arc','unresolved-locator','invalid-arc-priority'}
               and d.get('role')==role for d in filing.diagnostics):
            blockers.append('calculation effective relationships not certified')
        terms,missing,total=[],[],Decimal(0)
        for arc in arcs:
            aligned=[f for f in facts if f.concept==arc.child and alignment(filing,f)==parent_key
                     and not filing.contexts[f.context].dimensions]
            selected,choice=choose_addend(aligned,modal) if modal is not None else (None,{'tier':'mode-unbound','ambiguous':True})
            if choice.get('ambiguous'):
                blockers.append('ambiguous direct-child precision tier:'+arc.child)
            if selected is None:
                missing.append(arc.child)
                terms.append({'arc':arc.evidence(),'fact':None,'choice':choice,'unbound_list_iteration':True})
            else:
                weighted=exact_product(arc.weight,selected.value)
                total=exact_add(total,weighted)
                terms.append({'arc':arc.evidence(),'fact':selected.evidence(filing),'choice':choice,
                              'weighted_value':format_number(weighted),'unbound_list_iteration':False})
        if len(terms)==len(missing):
            blockers.append('all direct addends unbound; list sum is none')
        chapter11={'liabilities_subject_to_compromise_component':False,'exception_applies':False}
        if any(re.fullmatch(r'\{http://fasb\.org/us-gaap/20\d\d(?:-\d{2}-\d{2})?\}LiabilitiesSubjectToCompromise',arc.child) for arc in arcs):
            chapter11['liabilities_subject_to_compromise_component']=True
            instance=_document(query,filing,'Instance document')
            if instance is None:
                blockers.append('Chapter11 text-block exception applicability not certified')
                chapter11['supplied_instance_complete']=False
            else:
                chapter11['supplied_instance_complete']=True
                found=[element for element in instance.iter() if isinstance(element.tag,str) and
                       re.fullmatch(r'\{http://fasb\.org/us-gaap/20\d\d(?:-\d{2}-\d{2})?\}ReorganizationUnderChapter11OfUSBankruptcyCodeDisclosureTextBlock',element.tag)
                       and element.get('contextRef')]
                chapter11['text_block_supplied_count']=len(found)
                chapter11['exception_applies']=bool(found)
                if found:
                    blockers.append('source Chapter11 conjunction excludes this statement calculation')
        applicable=not blockers
        output.append({'rule_family':'0126','rule':'DQC.US.0126.9590','rule_subset':'DQC.US.0126.9590',
            'role':role,'role_scope':roles[role],'scope':scope,'parent':parent.evidence(filing),
            'value':format_number(total),'applicable':applicable,'eligible':applicable,
            'ambiguous':any('ambig' in b or 'tied' in b for b in blockers),'blockers':sorted(set(blockers)),
            'terms':terms,'missing':missing,'all_direct_children_present':not missing,
            'observed_direct_children':len(terms)-len(missing),'recursion_used':False,'inverse_used':False,
            'missing_zero_fact_invented':False,'modal':mode,'indexing':index_proof,
            'chapter11_exception':chapter11,
            'period_policy':'explicitly requested period; omitted DEI/current-period applicability remains unproven',
            'unit_entity_period_alignment_certified':True,'full_DTS_Xule_implementation':False,
            'source_sha256':sources,'accuracy_verified':False})
    return output
