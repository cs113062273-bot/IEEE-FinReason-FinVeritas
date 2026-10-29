"""Bounded exact-QName DQC0015 applicability; incumbent stays unchanged.

The pinned public exclusion registry is distinct from rule semantics. Rules
do not inspect statement role or walk issuer definition ancestors here:
hierarchy navigation builds generic exclusion constants, then predicates
compare literal fact dimensions. Original magnitude remains a hypothesis.
"""
import re
from .round3_engine import public_constraints,member_exclusions
from .round4_rules import registry

def not_elim_adjust(dimensions,axis_member_pairs):
    explicit={a:m for a,m in dimensions if isinstance(m,str)}
    return all(explicit.get(axis) not in members for axis,members in axis_member_pairs.items())

def eligibility(filing,fact,context,*,query=None):
    result={'eligible':False,'rule':None,'exclusion':None,'full_DTS_certified':False,'full_form_applicability':False,
        'constraint_proves_original_magnitude':False,'typed_dimension_blanket_exemption':False,'matching':'exact QName except official explicit-member substring predicate'}
    match=re.fullmatch(r'\{http://fasb.org/(us-gaap|srt)/(20\d\d)(?:-01-31)?\}(.+)',fact.concept)
    if not match or fact.value>=0:result['exclusion']='negative listed concept required';return result
    taxonomy,year,name=match[1],int(match[2]),match[3]
    gaap=f'http://fasb.org/us-gaap/{year}'+('-01-31' if year==2021 else '')
    srt=f'http://fasb.org/srt/{year}'+('-01-31' if year==2021 else '')
    if fact.concept[1:].partition('}')[0]!=(gaap if taxonomy=='us-gaap' else srt):result['exclusion']='unsupported namespace';return result
    modern,_=public_constraints();legacy,_=registry()
    rule=(modern.get(year,{}).get(name) if taxonomy=='us-gaap' else None) or legacy.get((taxonomy,year),{}).get(name)
    if not rule:result['exclusion']='unlisted concept';return result
    if context.qualifiers or not context.entity or not context.scheme or fact.unit not in filing.units or not filing.units[fact.unit].numerator:
        result['exclusion']='unresolved entity/unit/context qualifiers';return result
    excluded=member_exclusions();q=lambda uri,n:'{'+uri+'}'+n
    excluded_axes={q(srt if n=='InvestmentIdentifierAxis' else gaap,n) for n in excluded['axes'] if n!='IncomeTaxEffectChangeInLawAxis'}
    excluded_members={q(gaap,n) for n in excluded['members']}
    pairs={}
    for axis,member in excluded['axis_members']:
        uri=srt if axis=='ConsolidatedEntitiesAxis' else gaap
        pairs.setdefault(q(uri,axis),set()).add(q(uri,member))
    # A QName($EXTENSION_NS,...) exemption needs the supplied extension schema.
    from .parser import split_sections
    from .xml_core import _safe_xml
    extensions=set()
    for section,body in split_sections(query or '').items():
        if 'schema' not in section.lower():continue
        schema=_safe_xml(body,section,filing.namespaces,[])
        if schema is not None and schema.tag=='{http://www.w3.org/2001/XMLSchema}schema' and schema.get('targetNamespace'):
            extensions.add(schema.get('targetNamespace'))
    extension=next(iter(extensions)) if len(extensions)==1 else None
    for axis,_ in context.dimensions:
        if axis.rsplit('}',1)[-1]=='IncomeTaxEffectChangeInLawAxis':
            # Without that exact binding, preserve conservative applicability.
            if extension is None:result['exclusion']='extension namespace for IncomeTaxEffectChangeInLawAxis unavailable';return result
            excluded_axes.add(q(extension,'IncomeTaxEffectChangeInLawAxis'))
    for axis,member in context.dimensions:
        if axis in excluded_axes:result['exclusion']='exact excluded axis';return result
        if not isinstance(member,str):continue
        local=member.rsplit('}',1)[-1].lower()
        if member in excluded_members or any(token and token in local for token in excluded['strings']):result['exclusion']='exact member or official member substring exemption';return result
    result['not_elim_adjust']=not_elim_adjust(context.dimensions,pairs)
    result['axis_member_constants']={a:sorted(ms) for a,ms in pairs.items()}
    if not result['not_elim_adjust']:result['exclusion']='exact axis/member pair exemption';return result
    result.update(eligible=True,rule='DQC.US.0015.'+rule,member_exclusions_sha256=excluded['source_sha256'],constant_source_sha256=excluded['constant_sha256'])
    return result
