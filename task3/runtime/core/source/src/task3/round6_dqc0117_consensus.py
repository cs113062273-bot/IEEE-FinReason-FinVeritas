"""Independent, bounded native-duration and second-axis unanimity trial.

Every possible second axis must independently pass the supplied-DRS adapter
and yield the same number. This never predicts which unordered set item is
first. QName/entity/unit/period alignment and source witnesses are retained.
"""
from datetime import date
from decimal import Decimal
from .round6_dqc0117_v3 import candidates as strict,cubes,membership,_tolerance_violation
from .round6_dqc0126 import alignment
from .parser import split_sections
from .xml_core import _safe_xml,attr,tag_parts

AMBIGUITY='second-axis first(set) selection is ambiguous or absent'

def document_duration(query,filing):
    root=_safe_xml(split_sections(query).get('Instance document',''),'Instance document',filing.namespaces,[],allow_complete_prefix=True)
    witnesses=[]
    if root is not None:
        for node in root.iter():
            if tag_parts(node)[1]!='DocumentType' or not attr(node,'contextRef'):continue
            context=filing.contexts.get(attr(node,'contextRef'))
            days=None
            if context and context.start and context.end:
                days=(date.fromisoformat(context.end)-date.fromisoformat(context.start)).days+1
            witnesses.append({'QName':node.tag,'text':node.text,'context_ref':attr(node,'contextRef'),'context':context.evidence() if context else None,'duration_days':days,'source_line':node.sourceline})
    values={w['duration_days'] for w in witnesses}
    value=next(iter(values)) if len(values)==1 and None not in values else None
    return value,{'source':'DocumentType fact CONTEXT, not its string value','possible_duration_days':sorted(values,key=str),'all_possible_first_items_agree':value is not None,'witnesses':witnesses}

def candidates(query,filing,parent,*,duplicate_policy='xule_default',allow_inferred_statement=False,native_duration=True):
    programs=strict(query,filing,parent,duplicate_policy=duplicate_policy,allow_inferred_statement=allow_inferred_statement)
    context=filing.contexts.get(parent.context)
    base=dict(context.dimensions) if context else {}
    for cube in cubes(query,filing) if base else []:
        alternatives={axis for fact in filing.facts if fact.concept==parent.concept and
            alignment(filing,fact,include_dimensions=False)==alignment(filing,parent,include_dimensions=False) and membership(filing,fact,cube)[0] and
            len(filing.contexts[fact.context].dimensions)==2 and all(dict(filing.contexts[fact.context].dimensions).get(a)==m for a,m in base.items())
            for axis in dict(filing.contexts[fact.context].dimensions) if axis not in base}
        group=[p for p in programs if (p['role'],p['cube'])==(cube['role'],cube['cube']) and p['axis'] in alternatives]
        complete=bool(alternatives) and {p['axis'] for p in group}==alternatives
        other_clear=all(not(set(p['blockers'])-{AMBIGUITY}) for p in group)
        unanimous=complete and other_clear and len({Decimal(p['value']) for p in group})==1
        witness={'possible_axes':sorted(alternatives),'each_axis_independently_evaluated':complete,'all_applicability_checks_pass':other_clear,
            'all_possible_first_results_equal':unanimous,'first_set_order_assumed':False,
            'axis_results':[{'axis':p['axis'],'value':p['value'],'blockers':p['blockers'][:],'source_members':p['reported_members']} for p in group]}
        for p in group:
            p['second_axis_unanimity']=witness
            if unanimous and AMBIGUITY in p['blockers']:
                p['blockers'].remove(AMBIGUITY);p['eligible']=p['applicable']=True;p['ambiguous']=False
                selected=[f for f in filing.facts if f.evidence(filing) in p['reported_members']]
                violation,_=_tolerance_violation(parent,Decimal(p['value']),selected)
                p['violates']=bool(violation)
    days,proof=document_duration(query,filing) if native_duration else (None,None)
    for p in programs:
        p['adapter_version']='independent-native-duration-unanimity-v1'
        if native_duration:
            parent_days=0 if context.instant else (date.fromisoformat(context.end)-date.fromisoformat(context.start)).days+1
            p['document_duration']=proof;p['parent_duration_days']=parent_days
            # The original where clause explicitly permits instant facts
            # even when DocumentType is absent. Verified with pinned Xule.
            if parent_days!=0:
                if days is None:p['blockers'].append('DocumentType context duration is absent or ambiguous')
                elif parent_days!=days:p['blockers'].append('native DocumentType context duration mismatch')
            if p['blockers']:p['eligible']=p['applicable']=p['violates']=False
            p['period_policy']='asked source frame AND native DocumentType context duration'
    return programs
