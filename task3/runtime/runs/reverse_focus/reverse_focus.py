"""Prefer a sign candidate independently corroborated by a complete inverse.

This resolves a conflict between an existing direct-sum candidate and an
existing public nonnegative candidate in the SAME source financial frame.
No missing values are solved, substituted, or imputed. Reverse equations use
the reported parent and every other directly reported child, never the target.
The preference is an inductive error-localisation policy, not conformance law.
"""
from fractions import Fraction

from source_equations import witnesses,aspect


def select(parsed, programs):
    eligible=[p for p in programs if p.get('eligible') and p.get('violation')]
    pairs={(Fraction(p['reported']),Fraction(p['value'])) for p in eligible}
    if len(pairs)<2 or len({x for x,y in pairs})!=1:
        return None
    signs=[p for p in eligible if p['rule'].startswith('DQC.US.0015.')]
    if len({(p['reported'],p['value']) for p in signs})!=1:
        return None
    candidate=signs[0]
    pair=(Fraction(candidate['reported']),Fraction(candidate['value']))
    if pair[0]>=0 or pair[1]!=-pair[0]:
        return None
    # Keep unrelated assertion families and genuine dimensional Focus
    # alternatives outside this policy; they require separate scope evidence.
    if any(not p['rule'].startswith(('DQC.US.0015.','DQC.US.0126.')) for p in eligible):
        return None
    frames={(p['parent']['context_ref'],p['parent']['unit_ref']) for p in eligible}
    if len(frames)!=1:
        return None
    context,unit=next(iter(frames))
    inverse=[w for w in witnesses(parsed) if w['direction']=='reverse'
             and w['focus']['context_ref']==context and w['focus']['unit_ref']==unit
             and Fraction(w['focus']['value'])==pair[0]]
    if not inverse or {Fraction(w['value']) for w in inverse}!={pair[1]}:
        return None
    # Verify explicitly that the independent anchors cannot include the target
    # or any of its duplicate reported values as the same concept.
    if any(w['parent_fact']['QName']==parsed['target'] or any(t['fact']['QName']==parsed['target'] for t in w['terms']) for w in inverse):
        return None
    direct=[p for p in eligible if p['rule'].startswith('DQC.US.0126.')]
    if not direct or any(not p['proof'].get('all_direct_children_present') for p in direct):
        return None
    return {'selected':candidate,'rule':'public_sign_and_complete_inverse_agreement',
            'source_inverse_equations':inverse,'competing_direct_sums':direct,
            'target_used_as_anchor':False,'missing_values_inferred':False,
            'same_context_and_unit':True,'inductive_error_localisation':True,
            'hidden_Test_accuracy_improvement_proved':False}


def install(core):
    adapter=core.engine.c8
    make_before=adapter.make
    unique_before=adapter.unique_pair

    def make(query,filing,native_duration):
        programs,summary=make_before(query,filing,native_duration)
        if (unique_before(programs,summary) is None and not summary['fatal_source']
                and not summary['conflicting_target_groups'] and summary['entity_unit_scopes']==1):
            proof=select(core.engine.raw.source_parse(query),programs)
            if proof:summary={**summary,'source_inverse_focus_resolution':proof}
        return programs,summary

    def unique(programs,summary,**kwargs):
        before=unique_before(programs,summary,**kwargs)
        if before is not None:return before
        proof=summary.get('source_inverse_focus_resolution')
        if not proof or kwargs.get('relations_only'):return None
        return {**proof['selected'],'selection_refinement':{k:v for k,v in proof.items() if k!='selected'}}
    adapter.make=make
    adapter.unique_pair=unique
