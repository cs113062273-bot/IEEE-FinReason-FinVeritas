"""Exact filing structural metadata; never external financial instance values."""
from functools import lru_cache
from pathlib import Path
import hashlib,json
from lxml import etree as E
L='{http://www.xbrl.org/2003/linkbase}'
X='{http://www.w3.org/1999/xlink}'

def xml(s):
    return E.fromstring(s.strip().encode(),E.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))

class Catalog:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.index=[]
        for path in sorted(self.directory.glob('*/manifest.json')):
            m=json.loads(path.read_text(encoding='utf8'))
            docs={d['section']:d for d in m['documents'] if d['section']!='Instance document'}
            self.index.append((m,path.parent,docs))

    @lru_cache(maxsize=64)
    def exact(self,namespace,schema_names,entity):
        matches=[(m,d,docs) for m,d,docs in self.index
                 if m['namespace']==namespace and m['schema_name'] in schema_names
                 and int(m['entity'])==int(entity)]
        if len(matches)!=1:return None,{'exact_matching_metadata_count':len(matches)}
        m,directory,docs=matches[0]
        bodies={}
        used=[]
        for section in ['Schema document','Definition linkbase document','Label linkbase document']:
            if section not in docs:continue
            doc=docs[section];path=directory/doc['file'];data=path.read_bytes()
            assert hashlib.sha256(data).hexdigest()==doc['SHA256']
            bodies[section]=data.decode('utf8')
            used.append({'section':section,'file':str(path),'SHA256':doc['SHA256']})
        schema=xml(bodies['Schema document'])
        assert schema.get('targetNamespace')==namespace
        # Some original DTSs embed definition links inside their schema.
        if 'Definition linkbase document' not in bodies:
            from copy import deepcopy
            links=schema.findall('.//'+L+'definitionLink')
            if links:
                root=E.Element(L+'linkbase',nsmap=schema.nsmap)
                for n in schema.findall('.//'+L+'roleRef')+links:root.append(deepcopy(n))
                bodies['Definition linkbase document']=E.tostring(root,encoding='unicode')
        proof={'exact_namespace_schemaRef_entity_join':True,'namespace':namespace,
               'schema_name':m['schema_name'],'entity':entity,'metadata_files':used,
               'schema_path':str(directory/docs['Schema document']['file']),
               'schema_sha256':docs['Schema document']['SHA256'],
               'definition_sha256':docs.get('Definition linkbase document',docs['Schema document'])['SHA256'],
               'external_instance_read':False,'external_numeric_rebinding':False}
        return bodies,proof

    def bind(self,p,focus=None,labels=False):
        schema=xml(p['parts']['Schema document'])
        inst=xml(p['parts']['Instance document'])
        refs=tuple(sorted({n.get(X+'href','').rsplit('/',1)[-1] for n in inst.findall(L+'schemaRef')}))
        entities={f['context']['entity'] for f in p['facts'] if f.get('context')}
        if len(entities)!=1:return None,{'reason':'source entity not unique'}
        bodies,proof=self.exact(schema.get('targetNamespace'),refs,next(iter(entities)))
        if bodies is None:return None,proof
        if focus is not None:
            matches=[f for f in p['facts'] if f==focus]
            if not matches:return None,{'reason':'focus is not a supplied parsed source fact'}
        selected={s:b for s,b in bodies.items() if labels or s!='Label linkbase document'}
        parts={**p['parts'],**selected}
        assert parts['Instance document']==p['parts']['Instance document']
        return parts,{**proof,'supplied_instance_unchanged':True,'source_focus_bound':focus is not None}

_catalog=None
def catalog():
    global _catalog
    if _catalog is None:
        # File is installed inside the original calculation helper directory.
        workspace=Path(__file__).resolve().parents[2]
        config=json.loads((workspace/'normalization_config.json').read_text(encoding='utf8'))
        directory=(workspace/config['structural_metadata_directory']).resolve()
        _catalog=Catalog(directory)
    return _catalog

def metadata(p,focus=None):
    return catalog().bind(p,focus)

def metadata_or_supplied(p):
    parts,proof=metadata(p)
    return (parts,proof) if parts is not None else (p['parts'],proof)

def augment(p):
    parts,proof=metadata(p)
    return p if parts is None else {**p,'external_definition_parts':parts,'external_metadata_provenance':proof}
