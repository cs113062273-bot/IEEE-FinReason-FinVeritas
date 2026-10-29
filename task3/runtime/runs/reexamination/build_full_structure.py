"""Replace a query's structural sections with the original filing's structural documents; Instance untouched."""
import glob, json, os, re, sys
from pathlib import Path
import hashlib
from lxml import etree
C = str(Path(__file__).resolve().parents[2] / 'runs/structural_documents/metadata_catalog')
STRUCT = ['Schema document', 'Presentation linkbase document', 'Calculation linkbase document', 'Definition linkbase document', 'Label linkbase document']
ORDER = ['##Schema document', '##Presentation linkbase document', '##Calculation linkbase document', '##Definition linkbase document',
         '##Label linkbase document', '##Instance document', '##US GAAP Taxonomy']
cat = {}
for p in glob.glob(os.path.join(C, '*', 'manifest.json')):
    m = json.load(open(p, encoding='utf-8'))
    cat.setdefault((m['namespace'], int(m['entity'])), []).append((os.path.dirname(p), m))

def rebuild(q):
    pos = sorted((q.find(s), s) for s in ORDER if q.find(s) >= 0)
    if not pos:
        return None, 'no source sections'
    head = q[:pos[0][0]]
    parts = {name: q[p + len(name):(pos[k + 1][0] if k + 1 < len(pos) else len(q))] for k, (p, name) in enumerate(pos)}
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        schema = etree.fromstring(parts['##Schema document'].strip().encode(), parser)
        instance = etree.fromstring(parts['##Instance document'].strip().encode(), parser)
        entities = {n.text.strip() for n in instance.iter('{http://www.xbrl.org/2003/instance}identifier') if n.text}
        names = {n.get('{http://www.w3.org/1999/xlink}href', '').rsplit('/', 1)[-1]
                 for n in instance.iter('{http://www.xbrl.org/2003/linkbase}schemaRef')}
        if len(entities) != 1 or not names:
            return None, 'unique source entity and schemaRef required'
        candidates = [(directory, manifest) for directory, manifest in
                      cat.get((schema.get('targetNamespace'), int(next(iter(entities)))), [])
                      if manifest['schema_name'] in names]
    except (ValueError, KeyError, etree.XMLSyntaxError):
        return None, 'source join unavailable'
    if len(candidates) != 1:
        return None, 'catalog join absent or ambiguous'
    d, m = candidates[0]
    docs = {x['section']: x for x in m['documents'] if x['section'] in STRUCT}
    out = head
    for name in ORDER:
        if name not in parts:
            continue
        sec = name[2:]
        if sec in docs:
            path = (Path(d) / docs[sec]['file']).resolve()
            if not path.is_relative_to(Path(d).resolve()):
                raise ValueError('Structural document path escaped catalog')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != docs[sec]['SHA256']:
                raise ValueError('Structural document checksum mismatch')
            body = data.decode('utf-8')
            out += name + '\n' + body.strip() + '\n\n\n'
        else:
            out += name + parts[name]
    assert parts['##Instance document'] in out  # supplied facts untouched
    return out, m['filing']['accessionNumber']

if __name__ == '__main__':
    src, dst, ids = sys.argv[1], sys.argv[2], sys.argv[3]
    want = None if ids == 'ALL' else set(ids.split(','))
    n = 0
    with open(dst, 'w', encoding='utf-8', newline='\n') as out:
        for l in open(src, encoding='utf-8'):
            r = json.loads(l)
            if want is not None and r['id'] not in want:
                continue
            q, acc = rebuild(r['query'])
            if q is None:
                continue
            out.write(json.dumps({'id': r['id'], 'query': q, 'accession': acc}, ensure_ascii=False) + '\n'); n += 1
    print(dst, n)
