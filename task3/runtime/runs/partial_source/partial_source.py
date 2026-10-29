"""Partial supplied-source capability when the optional XSD is absent.

This is not a synthetic taxonomy or an Arelle schema-valid DTS. Complete XSD
inputs retain the existing native path. Missing declarations stay unknown.
"""
from functools import lru_cache
from collections import defaultdict
from decimal import Decimal,localcontext
from hashlib import sha256
from lxml import etree as E
from source_equations import aspect
L='{http://www.xbrl.org/2003/linkbase}';X='{http://www.w3.org/1999/xlink}'

def missing(parts):return parts.get('Schema document','').strip() in ('','None','null')

class SourceView:
    def __init__(self,parsed,xml):
        self.parsed=parsed;self.facts=parsed['facts'];self.parts=parsed['parts']
        root=xml(self.parts['Instance document']);self.namespaces=root.nsmap
        self.observed={f['QName'] for f in self.facts}
        for f in self.facts:
            if not f.get('context'):continue
            for a,k,m,place in f['context']['dimensions']:
                self.observed.add(a)
                if k=='explicit':self.observed.add(m)
        self.roots={};self.arcs=[];self.unavailable=[]
        for section in ('Presentation linkbase document','Definition linkbase document','Calculation linkbase document'):
            try:r=E.fromstring(self.parts.get(section,'').strip().encode(),E.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
            except E.XMLSyntaxError:self.unavailable.append(section);continue
            self.roots[section]=r
            for link in r:
                loc=self.locators(link)
                for n in link:
                    if isinstance(n.tag,str) and n.tag.endswith('Arc'):
                        self.arcs.append({'section':section,'role':link.get(X+'role'),'arcrole':n.get(X+'arcrole'),
                            'from':loc.get(n.get(X+'from')),'to':loc.get(n.get(X+'to')),
                            'source_attributes':dict(n.attrib),'resolved':n.get(X+'from') in loc and n.get(X+'to') in loc})
    def locators(self,link):
        out={}
        for n in link.findall(L+'loc'):
            fragment=n.get(X+'href','').partition('#')[2];prefix,sep,name=fragment.partition('_')
            uri=self.namespaces.get(prefix);q='{'+uri+'}'+name if sep and uri else None
            # Only bind an ID convention to a QName already explicitly observed
            # in a supplied fact or context. Unobserved declarations stay unknown.
            if q in self.observed:out[n.get(X+'label')]=q
        return out
    def proof(self):
        return {'kind':'partial-supplied-source','facts':len(self.facts),'observed_QNames':len(self.observed),
            'supplied_roles':sorted({a['role'] for a in self.arcs if a['role']}),
            'source_arcs':len(self.arcs),'unresolved_arcs':sum(not a['resolved'] for a in self.arcs),
            'unavailable_documents':self.unavailable,'schema_definitions_fabricated':False,
            'full_DTS_or_schema_validation_claimed':False,'external_materials_read':False}

def certified_prior(view,prior):
    """Retain an EXISTING source computation after verifying its literal leaves.

    No new axis ranking or missing-value repair is introduced here.
    """
    p=view.parsed;e=prior.evidence;s=e.get('fragment_axis_selected')
    if not e.get('fragment_axis_promoted') or not s or not s.get('eligible') or s.get('blockers'):return None
    if not s.get('leaves'):return None
    targets=[f for f in view.facts if f['QName']==p['target'] and f['asked_period'] and aspect(f) is not None and not f['context']['dimensions']]
    frames={aspect(f) for f in targets}
    if len(frames)!=1 or {Decimal(f['value']) for f in targets}!={Decimal(prior.extracted_value)}:return None
    target=targets[0];base=aspect(target);axis=s['axis'];bound=[]
    for leaf in s['leaves']:
        fs=[f for f in view.facts if f['QName']==p['target'] and f['context_ref']==leaf['context_ref'] and f['unit_ref']==leaf['unit_ref'] and Decimal(f['value'])==Decimal(leaf['value'])]
        if not fs:return None
        f=fs[0];c=f['context'];ds=c['dimensions'];frame=aspect(f)
        if frame is None or len(ds)!=1 or ds[0][0]!=axis or ds[0][1]!='explicit':return None
        if (frame[:3],frame[4])!=(base[:3],base[4]):return None
        bound.append(f)
    # Only one representative for each complete source aspect.
    unique={aspect(f):f for f in bound}
    if len(unique)!=len(bound):return None
    with localcontext() as ctx:
        ctx.prec=100;total=sum((Decimal(f['value']) for f in bound),Decimal(0))
    if total!=Decimal(prior.calculated_value):return None
    return {'new':{'extracted_value':prior.extracted_value,'calculated_value':prior.calculated_value},
        'rule':'retain_recomputed_source_leaves_when_optional_DTS_unavailable','focus':target,
        'leaves':bound,'prior_mechanism':prior.mechanism,'axis':axis,
        'empty_sum_used':False,'missing_values_imputed':False,'source_zero_is_literal_fact':total==0,
        'scope_policy':'preserved existing fragment-axis hypothesis; full cube applicability remains unknown',
        'source_view':view.proof()}

def install(core):
    import source_financial_semantics as sem
    original_locators=sem.locators
    @lru_cache(maxsize=4)
    def view(query):return SourceView(core.engine.raw.source_parse(query),core.engine.raw.xml)
    def locators(parsed,parts,link):
        if not missing(parts):return original_locators(parsed,parts,link)
        return SourceView(parsed,core.engine.raw.xml).locators(link)
    sem.locators=locators
    from calc11 import select as calc11
    @lru_cache(maxsize=4)
    def recovery(query):
        v=view(query);p=v.parsed
        targets=[f for f in v.facts if f['QName']==p['target'] and f['asked_period'] and aspect(f) is not None]
        if not targets:return None,{'source_status':'unresolved','reason':'no complete asked target fact','source_view':v.proof()}
        proposal=calc11(p)
        if proposal:return proposal,None
        prior=core.original(query,policy='document_first')
        proposal=certified_prior(v,prior)
        if proposal:return proposal,None
        consolidated=[f for f in targets if not f['context']['dimensions']]
        known={Decimal(f['value']) for f in consolidated}
        return None,{'source_status':'unresolved','reason':'target reported; no certified usable calculation',
                     'extracted_value':str(next(iter(known))) if len(known)==1 else None,
                     'calculated_value':None,'source_view':v.proof()}
    native=core.native;run_before=native.run;select_before=native.select
    def run(query,seeds=(0,),version=6):
        from task3.parser import split_sections
        if not missing(split_sections(query)):return run_before(query,seeds=seeds,version=version)
        proposal,unresolved=recovery(query)
        return {'query_sha256':sha256(query.encode()).hexdigest(),'case':'partial-source/'+sha256(query.encode()).hexdigest(),
                'partial_supplied_source':True,'proposal':proposal,'unresolved':unresolved,'accesses':[],
                'fresh_Xule_executed':False,'schema_definitions_fabricated':False}
    def select(query,filing,result,prior):
        if not result.get('partial_supplied_source'):return select_before(query,filing,result,prior)
        if result['query_sha256']!=sha256(query.encode()).hexdigest():return None,{'reason':'source hash mismatch'}
        proposal=result['proposal']
        if proposal:return {**prior,**proposal['new']},{'partial_supplied_source':True,'source_evidence':proposal,'fresh_Xule_executed':False}
        return None,result['unresolved']
    native.run=run;native.select=select
    fresh_before=core.fresh_native
    def fresh_native(query,*,policy):
        from task3.parser import split_sections
        partial=missing(split_sections(query));start=len(core.native_records)
        result=fresh_before(query,policy=policy)
        if partial:
            for record in core.native_records[start:]:
                record['fresh_native_executed']=False
                record['partial_supplied_source_executed']=True
                record['full_DTS_or_schema_validation_claimed']=False
        return result
    core.fresh_native=fresh_native
    infer_before=core.infer
    def infer(query,*,output_id,exclusions):
        from task3.parser import split_sections
        from task3.period_semantics import normalize_query
        query,_=normalize_query(query)
        if not missing(split_sections(query)):return infer_before(query,output_id=output_id,exclusions=exclusions)
        # Preserve every existing complete-engine C8 decision before trying the
        # partial native capability. An unavailable native is not a zero answer.
        filing,_=core.engine.c8.normalize(core.engine.c8.parse_xml(query,allow_complete_prefix=True))
        programs,summary=core.engine.c8.make(query,filing,False)
        if core.engine.c8.unique_pair(programs,summary) is not None:return infer_before(query,output_id=output_id,exclusions=exclusions)
        proposal,unresolved=recovery(query)
        if proposal:return infer_before(query,output_id=output_id,exclusions=exclusions)
        return {'id':output_id,**unresolved},{'source_status':'unresolved','source_evidence':unresolved,'programs':programs,'events':[],'fresh_native':[]},view(query).parsed
    core.infer=infer
    return {'partial_source_view':True,'missing_XSD_native_capability':'source-leaf-checked computation or explicit unresolved; never implicit 0','synthetic_taxonomy_generated':False}
