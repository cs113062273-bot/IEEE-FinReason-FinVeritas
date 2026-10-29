"""Arelle CLI with generic taxonomy URL allowlist and a resource access log."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from arelle import CntlrCmdLine,WebCache,ModelXbrl

HOSTS = {'www.xbrl.org','xbrl.org','xbrl.fasb.org','xbrl.sec.gov'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--access-log',type=Path,required=True)
    args,remaining = parser.parse_known_args()
    original = WebCache.WebCache.getfilename
    accesses = []
    findings = []
    original_model_log = ModelXbrl.ModelXbrl.log

    def capture(self,level,code,message,**keywords):
        if str(code).startswith('DQC.'):
            focus = keywords.get('modelObject')
            focuses = focus if isinstance(focus,(list,tuple,set)) else [focus]
            try:
                rendered = str(message) % keywords
            except Exception:
                rendered = str(message)
            for fact in focuses:
                if fact is None or not hasattr(fact,'contextID'):
                    continue
                findings.append({'code':str(code),'message':rendered,
                    'concept_namespace':fact.qname.namespaceURI,'concept_local_name':fact.qname.localName,
                    'context_ref':fact.contextID,'unit_ref':fact.unitID,'raw_value':fact.value,
                    'typed_value':str(fact.xValue),'decimals':fact.decimals,'fact_id':fact.get('id'),
                    'source_document':fact.modelDocument.filepath,'schema_validation_state':getattr(fact,'xValid',None)})
        return original_model_log(self,level,code,message,**keywords)

    def guarded(self,url,*positional,**keywords):
        parsed = urlparse(str(url))
        remote = parsed.scheme in {'http','https'}
        if remote and (parsed.hostname not in HOSTS or '/Archives/' in parsed.path or
                       not parsed.path.lower().endswith(('.xsd','.xml'))):
            raise PermissionError('External company/finding resources prohibited: '+str(url))
        path = original(self,url,*positional,**keywords)
        if remote:
            record = {'url':str(url),'generic_taxonomy_only':True,'cached_file':path}
            if path and Path(path).is_file():
                body = Path(path).read_bytes()
                record.update(sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
            accesses.append(record)
        return path

    WebCache.WebCache.getfilename = guarded
    ModelXbrl.ModelXbrl.log = capture
    try:
        CntlrCmdLine.parseAndRun(remaining)
    finally:
        args.access_log.parent.mkdir(parents=True,exist_ok=True)
        args.access_log.write_text(json.dumps({'accesses':accesses,
            'computed_DQC_findings':findings,
            'external_company_or_findings_resources_allowed':False,
            'generic_taxonomy_imports_not_competition_answers':True},indent=2),encoding='utf8')
