"""Treat the supplied role as a statement cube: rewrite '- Disclosure -' to '- Statement -' in roleType definitions only."""
import json, re, sys
DEF = re.compile(r'(<(?:link:)?definition>[^<]*?) - Disclosure - ([^<]*</(?:link:)?definition>)')
def relabel(q):
    return DEF.subn(r'\1 - Statement - \2', q)
if __name__ == '__main__':
    src, dst, ids = sys.argv[1], sys.argv[2], sys.argv[3]
    want = None if ids == 'ALL_DISCLOSURE' else set(ids.split(','))
    n = 0
    with open(dst, 'w', encoding='utf-8', newline='\n') as out:
        for l in open(src, encoding='utf-8'):
            if not l.strip(): continue
            r = json.loads(l)
            q, k = relabel(r['query'])
            if (want is None and k) or (want is not None and r['id'] in want):
                out.write(json.dumps({'id': r['id'], 'query': q}, ensure_ascii=False) + '\n'); n += 1
    print(dst, n)
