from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
m=json.loads((p/'runtime_manifest.json').read_text())
for name,expected in m['files'].items():
 f=p/'runtime'/name
 assert f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest()==expected,name
print('Verified',len(m['files']),'pinned runtime files')
