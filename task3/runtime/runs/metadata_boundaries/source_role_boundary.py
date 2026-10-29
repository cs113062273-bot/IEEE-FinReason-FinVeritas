"""Source-only statement role recovery when an optional XSD is absent.

A declared role definition always wins. An omitted definition can use a
canonical main-statement URI only when the same role and asked concept are
present in both supplied presentation and definition networks. This is a
scope hypothesis, not a reconstructed roleType or a full-DTS certificate.
"""
import re
from dataclasses import replace
from urllib.parse import urlsplit
from lxml import etree as E

L='{http://www.xbrl.org/2003/linkbase}'
X='{http://www.w3.org/1999/xlink}'

def recover(query,filing):
    from task3.parser import split_sections
    from task3.dqc_statement_sum import _document,_locators
    parts=split_sections(query)
    # Restrict recovery to missing metadata, never override supplied semantics.
    if parts.get('Schema document','').strip() not in ('','None','null'):return filing,[]
    defs=_document(query,filing,'Definition linkbase document')
    pres=_document(query,filing,'Presentation linkbase document')
    if defs is None or pres is None:return filing,[]
    present=set()
    for link in pres.iter(L+'presentationLink'):
        if filing.target in _locators(link,filing).values():present.add(link.get(X+'role'))
    declared=dict(filing.role_definitions);proof=[]
    for link in defs.iter(L+'definitionLink'):
        role=link.get(X+'role','');tail=urlsplit(role).path.rstrip('/').rsplit('/',1)[-1]
        words=re.sub('[^a-z0-9]','',tail.lower())
        if role in declared or role not in present or filing.target not in _locators(link,filing).values():continue
        if any(s in words for s in ('note','detail','parenthetical','equity','schedule','segment')):continue
        # Exact generic statement vocabulary, with only display qualifiers.
        text=words
        for term in ('unaudited','condensed','consolidated','combined','currentperiod','comparative','statementsof','statements','statement'):
            text=text.replace(term,'')
        if text not in ('operations','income','balancesheets','balancesheet','cashflows','comprehensiveincome','incomeandcomprehensiveincome'):continue
        declared[role]='- Statement - Source URI scope hypothesis'
        proof.append({'role':role,'target':filing.target,'same_role_target_in_supplied_presentation_and_definition':True,
                      'supplied_role_definition_missing':True,'scope_hypothesis':True,'external_metadata_read':False})
    return (replace(filing,role_definitions=declared),proof) if proof else (filing,[])

def install(core):
    old=core.engine.c8.make
    def make(query,filing,native_duration):
        baseline,base_summary=old(query,filing,native_duration)
        if core.engine.c8.unique_pair(baseline,base_summary) is not None:
            return baseline,base_summary
        recovered,proof=recover(query,filing)
        if not proof:return baseline,base_summary
        ps,summary=old(query,recovered,native_duration)
        if proof:
            summary={**summary,'missing_statement_role_recovery':proof}
            for p in ps:
                if p['rule'].startswith('DQC.US.0117.'):
                    p['proof']['missing_statement_role_recovery']=proof
                    p['proof']['role_scope_independent_blindly_verified']=False
        return ps,summary
    core.engine.c8.make=make
