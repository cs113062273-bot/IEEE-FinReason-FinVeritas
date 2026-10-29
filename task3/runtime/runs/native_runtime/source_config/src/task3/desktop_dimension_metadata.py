"""Disclosed schema-completion hypothesis from supplied structural QNames.

Completes only missing elements in the supplied corporate targetNamespace.
Does not add relationships, contexts, financial values or taxonomy namespaces.
"""
from collections import defaultdict
from lxml import etree
from .xml_core import XS, LINK, XLINK, XBRLI

XBRLDT = 'http://xbrl.org/2005/xbrldt'


def complete_dimension_metadata(roots, filing):
    original = roots['Schema document']
    namespace = original.get('targetNamespace')
    roles = defaultdict(set)
    sources = defaultdict(list)
    typed_axes = set()
    for fact in filing.facts:
        context = filing.contexts.get(fact.context)
        if context is None:
            continue
        for axis, member in context.dimensions:
            if not isinstance(member,str):
                typed_axes.add(axis)
                continue
            for concept, role in ((axis, 'axis'), (member, 'member')):
                if isinstance(concept, str) and concept.startswith('{'+namespace+'}'):
                    name=concept.rsplit('}',1)[-1];roles[name].add(role)
                    sources[name].append({'kind':'complete_source_explicit_context','context_ref':context.id})
    definition = roots.get('Definition linkbase document')
    prefixes = {p for p,u in original.nsmap.items() if p and u==namespace}
    identifiers = {e.get('id'):e.get('name') for e in original.iter('{'+XS+'}element') if e.get('id')}
    if definition is not None:
        for link in definition.iter('{'+LINK+'}definitionLink'):
            locs={}
            for loc in link.iter('{'+LINK+'}loc'):
                href=loc.get('{'+XLINK+'}href','');fragment=href.partition('#')[2]
                name=identifiers.get(fragment)
                if name is None:
                    for prefix in sorted(prefixes):
                        if fragment.startswith(prefix+'_'):
                            name=fragment[len(prefix)+1:];break
                if name:
                    locs[loc.get('{'+XLINK+'}label')]=name
            for arc in link.iter('{'+LINK+'}definitionArc'):
                role=arc.get('{'+XLINK+'}arcrole','').rsplit('/',1)[-1]
                source=locs.get(arc.get('{'+XLINK+'}from'));target=locs.get(arc.get('{'+XLINK+'}to'))
                types = {'all':(None,'cube'),'notAll':(None,'cube'),
                         'hypercube-dimension':('cube','axis'),'dimension-domain':('axis','member'),
                         'dimension-default':('axis','member'),'domain-member':('member','member')}.get(role)
                if types:
                    for name,kind in ((source,types[0]),(target,types[1])):
                        if name and kind:
                            roles[name].add(kind);sources[name].append({'kind':'complete_source_definition_arc','arcrole':role})
    existing={e.get('name') for e in original.iter('{'+XS+'}element')}
    required=[n for n,k in roles.items() if n not in existing and len(k)==1 and
              '{'+namespace+'}'+n not in typed_axes]
    if not required:
        return []
    # Establish the prefixes used by new declarations without overwriting a
    # conflicting supplied binding. Existing QName-valued attributes survive.
    nsmap=dict(original.nsmap)
    for prefix,uri in (('xbrli',XBRLI),('xbrldt',XBRLDT)):
        if prefix in nsmap and nsmap[prefix]!=uri:
            raise ValueError('Conflicting metadata namespace binding: '+prefix)
        nsmap[prefix]=uri
    schema=etree.Element(original.tag,attrib=dict(original.attrib),nsmap=nsmap)
    schema.text=original.text
    for child in list(original):schema.append(child)
    roots['Schema document']=schema
    imports={e.get('namespace') for e in schema.iter('{'+XS+'}import')}
    for uri,url in ((XBRLI,'http://www.xbrl.org/2003/xbrl-instance-2003-12-31.xsd'),
                    (XBRLDT,'http://www.xbrl.org/2005/xbrldt-2005.xsd')):
        if uri not in imports:
            schema.insert(0,etree.Element('{'+XS+'}import',namespace=uri,schemaLocation=url))
    prefix=min(prefixes) if prefixes else None
    if prefix is None:
        raise ValueError('Corporate source prefix required for fragment IDs')
    notes=[]
    for name in sorted(required):
        kind=next(iter(roles[name]));substitution={'axis':'xbrldt:dimensionItem','cube':'xbrldt:hypercubeItem','member':'xbrli:item'}[kind]
        element=etree.SubElement(schema,'{'+XS+'}element',name=name,id=prefix+'_'+name,
            type='xbrli:stringItemType',substitutionGroup=substitution,abstract='true',nillable='true')
        element.set('{'+XBRLI+'}periodType','duration')
        notes.append({'name':name,'namespace':namespace,'hypothesized_structural_kind':kind,
                      'source_evidence':sources[name],'financial_values_invented':False,
                      'original_schema_declaration_absent':True})
    return notes
