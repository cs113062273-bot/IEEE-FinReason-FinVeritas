"""Only the frozen667 release is the research baseline."""
import importlib.util,json,sys,hashlib
from pathlib import Path
WORK=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('e15_frozen_source_common',WORK/'runs/focus_selection/common.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
ROOT=prior.ROOT;BEST=WORK/'DELIVERY/task3_E15_best_provisional_98_09_20261015';MODEL=WORK/'runs/e15_feedback_20261015'
raw=prior.raw;previous=prior.previous;parent=prior.parent
rows=prior.rows;read=prior.read;sha=prior.sha;same=prior.same;save=prior.save;parsed=prior.parsed
spec=importlib.util.spec_from_file_location('e15_source_labels',WORK/'runs/focus_selection/focus_inventory.py')
# The old module imports common by name; retain identical source helpers here.
labels_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(labels_module)
member_labels=labels_module.member_labels
LINK=raw.LINK;XLINK=raw.XLINK
local=lambda x:x.split('}')[-1]
def augment(p):
    directory=OUT/'public_sources/EFC_2025'
    if not directory.exists():return p
    schema_path=directory/'efc-20251231.xsd';definition_path=directory/'efc-20251231_def.xml'
    schema=raw.xml(schema_path.read_text(encoding='utf-8'))
    try:supplied=raw.xml(p['parts']['Schema document'])
    except (KeyError,raw.etree.XMLSyntaxError):return p
    if supplied.get('targetNamespace')!=schema.get('targetNamespace'):return p
    if {f['context']['entity'] for f in p['facts'] if f['context']}!={'0001411342'}:return p
    if p['namespaces'].get('us-gaap')!='http://fasb.org/us-gaap/2024':return p
    return {**p,'external_definition_parts':{**p['parts'],'Schema document':schema_path.read_text(encoding='utf-8'),'Definition linkbase document':definition_path.read_text(encoding='utf-8')},'public_metadata_provenance':{'issuer_CIK':'0001411342','extension_namespace':schema.get('targetNamespace'),'source_manifest_sha256':sha(OUT/'public_source_manifest.json'),'schema_sha256':sha(schema_path),'definition_sha256':sha(definition_path)}}
