"""Bind optional structural metadata without reparsing a truncated numeric tail.

The core parser already retains only complete supplied top-level nodes. Use
that same certified prefix for schemaRef lookup, keep the original numerical
instance unchanged, and abstain if the exact join cannot be established.
"""
def install(core):
    import normalized_metadata as metadata
    original=metadata.Catalog.bind

    def bind(self,p,focus=None,labels=False):
        try:
            return original(self,p,focus=focus,labels=labels)
        except metadata.E.XMLSyntaxError as error:
            failure={'optional_metadata_unavailable':True,'strict_XML_error':str(error),
                     'external_instance_read':False,'external_numeric_rebinding':False}
            try:
                schema=metadata.xml(p['parts']['Schema document'])
                instance=core.engine.raw.xml(p['parts']['Instance document'])
                refs=tuple(sorted({n.get(metadata.X+'href','').rsplit('/',1)[-1]
                    for n in instance.findall(metadata.L+'schemaRef')}))
                entities={f['context']['entity'] for f in p['facts'] if f.get('context')}
                if len(entities)!=1 or not refs:
                    return None,{**failure,'reason':'complete source schemaRef or unique source entity unavailable'}
                bodies,proof=self.exact(schema.get('targetNamespace'),refs,next(iter(entities)))
                if bodies is None:return None,{**failure,**proof}
                if focus is not None and focus not in p['facts']:
                    return None,{**failure,'reason':'focus is not a supplied parsed source fact'}
                selected={s:b for s,b in bodies.items() if labels or s!='Label linkbase document'}
                parts={**p['parts'],**selected}
                assert parts['Instance document']==p['parts']['Instance document']
                return parts,{**proof,'supplied_instance_unchanged':True,'source_focus_bound':focus is not None,
                              'schemaRef_from_complete_source_nodes':True,'numeric_tail_reconstructed':False}
            except metadata.E.XMLSyntaxError as incomplete:
                return None,{**failure,'reason':'optional structural XML cannot be certified','details':str(incomplete)}
    metadata.Catalog.bind=bind
