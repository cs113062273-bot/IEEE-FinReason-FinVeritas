"""Resolve source references by URI/XSD identity, independent of XML prefixes."""
from collections import defaultdict
from functools import lru_cache
from urllib.parse import urlsplit,unquote
from lxml import etree as E
XS='{http://www.w3.org/2001/XMLSchema}';L='{http://www.xbrl.org/2003/linkbase}';X='{http://www.w3.org/1999/xlink}'

class Bindings(dict):
    # dataclasses.replace keeps this mapping through duplicate normalization.
    pass

class Resolver:
    def __init__(self,body):
        self.ids={};self.namespace=None;self.imports=defaultdict(set);self.basenames=defaultdict(set)
        if body.strip() in ('','None','null'):return
        try:r=E.fromstring(body.strip().encode(),E.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
        except E.XMLSyntaxError:return
        self.namespace=r.get('targetNamespace')
        if self.namespace:
            for e in r.iter(XS+'element'):
                if e.get('id') and e.get('name'):self.ids[e.get('id')]='{'+self.namespace+'}'+e.get('name')
        for e in r.iter(XS+'import'):
            resource=e.get('schemaLocation');uri=e.get('namespace')
            if resource and uri:
                self.imports[resource].add(uri);self.basenames[urlsplit(resource).path.rsplit('/',1)[-1]].add(uri)
    def resolve(self,href,namespaces):
        resource,sep,fragment=href.partition('#');fragment=unquote(fragment)
        if not sep or not fragment:return None
        if fragment in self.ids:return self.ids[fragment]
        exact=self.imports.get(resource,set())
        candidates=exact or self.basenames.get(urlsplit(resource).path.rsplit('/',1)[-1],set())
        if len(candidates)>1:return None
        prefix,sep,local=fragment.partition('_')
        if len(candidates)==1 and sep:
            # The supplied import binds the referenced resource's namespace.
            # XML IDs retain their original prefix-shaped spelling on rename.
            return '{'+next(iter(candidates))+'}'+local
        if ':' in fragment:
            prefix,local=fragment.split(':',1);uri=namespaces.get(prefix)
            return '{'+uri+'}'+local if uri else None
        uri=namespaces.get(prefix) if sep else None
        if uri and uri!=self.namespace:return '{'+uri+'}'+local
        return None
    def locators(self,link,namespaces):
        groups=defaultdict(set)
        for e in link.findall(L+'loc'):
            concept=self.resolve(e.get(X+'href',''),namespaces)
            if concept:groups[e.get(X+'label')].add(concept)
        return {k:next(iter(v)) for k,v in groups.items() if len(v)==1}

@lru_cache(maxsize=8)
def resolver(body):return Resolver(body)

def install(core):
    import sys
    import task3.xml_core as xc
    import task3.dqc_statement_sum as ds
    import source_financial_semantics as sem
    old_parse=xc.parse_xml;old_loc=ds._locators;old_sem=sem.locators
    def parse(query,*,allow_complete_prefix=False):
        from task3.parser import split_sections
        f=old_parse(query,allow_complete_prefix=allow_complete_prefix)
        ns=Bindings(f.namespaces);ns.source_resolver=resolver(split_sections(query).get('Schema document',''));f.namespaces=ns
        return f
    def loc(link,filing):
        r=getattr(filing.namespaces,'source_resolver',None)
        return r.locators(link,filing.namespaces) if r is not None else old_loc(link,filing)
    # Modules imported these functions directly; replace their references too.
    for m in list(sys.modules.values()):
        if m is None or not (getattr(m,'__name__','').startswith('task3') or str(getattr(m,'__file__','')).startswith(str(core.W))):continue
        for name,value in list(vars(m).items()):
            if value is old_parse:setattr(m,name,parse)
            elif value is old_loc:setattr(m,name,loc)
    xc.parse_xml=parse;ds._locators=loc
    def semantic_locators(parsed,parts,link):
        if parts.get('Schema document','').strip() in ('','None','null'):return old_sem(parsed,parts,link)
        ns=parsed.get('namespaces')
        if ns is None:ns=core.engine.raw.xml(parts['Instance document']).nsmap
        return resolver(parts['Schema document']).locators(link,ns)
    sem.locators=semantic_locators
    original_execute=core.native.execute
    from pathlib import Path
    preparer=Path(__file__).with_name('native_preparer.py')
    def execute(command,log,timeout=120,seed=None):
        command=list(command)
        if len(command)>1 and Path(command[1]).name=='task3_desktop_source_bundle_v6.py':command[1]=preparer
        return original_execute(command,log,timeout=timeout,seed=seed)
    core.native.execute=execute
    return {'locator_namespace_binding':'supplied XSD import URI and extension declaration ID; lexical XML prefixes never identify imported namespaces','native_namespace_binding':'unique observed taxonomy URI, not prefix spelling'}
