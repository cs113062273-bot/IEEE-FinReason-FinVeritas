"""Remap supplied documents locally for an independent generic DTS processor.

Instance values come exclusively from the supplied case. General taxonomy
imports retain their original generic URLs; external company documents are
never acquired. This creates an oracle research input, not a prediction.
"""
import argparse
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'scripts')]
from task3.parser import split_sections
from task3.xml_core import parse_xml
from task3.desktop_source_xml import supplied_roots
from task3.desktop_dimension_metadata import complete_dimension_metadata
from task3_round4_practice import rows,sha,save


def prepare(input_path,case_id,out):
    record = next(r for r in rows(input_path) if r['id'] == case_id)
    if set(record) != {'id','query'}:
        raise ValueError('Input-only records required')
    sections = split_sections(record['query'])
    out.mkdir(parents=True,exist_ok=False)
    roots, xml_diagnostics = supplied_roots(sections)
    filing = parse_xml(record['query'],allow_complete_prefix=True)
    LINK = 'http://www.xbrl.org/2003/linkbase'; XLINK = 'http://www.w3.org/1999/xlink'; XS = 'http://www.w3.org/2001/XMLSchema'
    dimension_declarations = complete_dimension_metadata(roots,filing)
    schema = roots['Schema document']
    inferred_declarations = []
    schema_namespace = schema.get('targetNamespace')
    existing_names = {e.get('name') for e in schema.iter('{'+XS+'}element')}
    prefixes = [p for p,uri in schema.nsmap.items() if p and uri == schema_namespace]
    prefix = sorted(prefixes)[0] if prefixes else None
    if prefix:
        from collections import defaultdict
        grouped = defaultdict(list)
        for fact in filing.facts:
            if fact.concept.startswith('{'+schema_namespace+'}'):
                grouped[fact.concept.rsplit('}',1)[-1]].append(fact)
        for name,facts in grouped.items():
            if name in existing_names:
                continue
            period_types = {('instant' if filing.contexts[f.context].instant else 'duration')
                            for f in facts if f.context in filing.contexts}
            units = [filing.units[f.unit] for f in facts if f.unit in filing.units]
            if len(period_types) != 1 or len(units) != len(facts):
                continue
            monetary = all(not u.denominator and len(u.numerator)==1 and
                           u.numerator[0].startswith('{http://www.xbrl.org/2003/iso4217}') for u in units)
            item_type = 'xbrli:monetaryItemType' if monetary else 'xbrli:decimalItemType'
            declaration = etree.SubElement(schema,'{'+XS+'}element',name=name,id=prefix+'_'+name,
                type=item_type,substitutionGroup='xbrli:item',nillable='true',abstract='false')
            declaration.set('{http://www.xbrl.org/2003/instance}periodType',next(iter(period_types)))
            inferred_declarations.append({'name':name,'namespace':schema_namespace,'type':item_type,
                'period_type':next(iter(period_types)),'source_fact_indexes':[f.index for f in facts],
                'original_schema_declaration_absent':True,'source_metadata_completion_hypothesis':True})
    identifiers = {e.get('id') for e in schema.iter() if e.get('id')}
    supplied_schema_names = {urlsplit(e.get('{'+XLINK+'}href','')).path.rsplit('/',1)[-1]
                            for e in roots['Instance document'].iter('{'+LINK+'}schemaRef')}
    files = {'Schema document':'schema.xsd','Instance document':'instance.xml',
        'Presentation linkbase document':'presentation.xml','Calculation linkbase document':'calculation.xml',
        'Definition linkbase document':'definition.xml','Label linkbase document':'label.xml'}
    for section,root in roots.items():
        for element in root.iter():
            href = element.get('{'+XLINK+'}href')
            if href and (href.partition('#')[2] in identifiers or
                         urlsplit(href.partition('#')[0]).path.rsplit('/',1)[-1] in supplied_schema_names):
                element.set('{'+XLINK+'}href','schema.xsd#'+href.partition('#')[2])
            if element.tag == '{'+LINK+'}schemaRef':
                element.set('{'+XLINK+'}href','schema.xsd')
    for reference in list(schema.iter('{'+LINK+'}linkbaseRef')):
        reference.getparent().remove(reference)
    annotation = next(schema.iter('{'+XS+'}annotation'),None)
    if annotation is None:
        annotation = etree.SubElement(schema,'{'+XS+'}annotation')
    appinfo = etree.SubElement(annotation,'{'+XS+'}appinfo')
    for section,file in files.items():
        if section in ('Schema document','Instance document'):
            continue
        ref = etree.SubElement(appinfo,'{'+LINK+'}linkbaseRef')
        ref.set('{'+XLINK+'}type','simple');ref.set('{'+XLINK+'}href',file)
        ref.set('{'+XLINK+'}arcrole','http://www.w3.org/1999/xlink/properties/linkbase')
    for section,root in roots.items():
        (out/files[section]).write_bytes(etree.tostring(root,encoding='utf8',xml_declaration=True))
    (out/'query.txt').write_text(record['query'],encoding='utf8')
    base = ROOT/'reports/round6_arelle/desktop_original0117_v1'
    shutil.copyfile(base/'DQC_0117.xule',out/'DQC_0117.xule')
    shutil.copyfile(ROOT/'resources/task3_dqc0126/DQC_0126.xule',out/'DQC_0126.xule')
    shutil.copyfile(ROOT/'resources/task3_dqc0015/DQC_0015.xule',out/'DQC_0015.xule')
    # Bind the explicitly asked period. This is a named semantic variant;
    # it does not assert DEI current-document applicability or invent facts.
    asked_start = filing.start
    asked_end = filing.end or filing.start
    if not asked_start or not asked_end:
        raise ValueError('Explicit asked period required')
    days = (date.fromisoformat(asked_end)-date.fromisoformat(asked_start)).days+1 if filing.end else 0
    for rule_file in ('DQC_0117.xule','DQC_0126.xule'):
        path = out/rule_file
        body = path.read_text(encoding='utf8')
        body = body.replace('$document_period_duration = $document_period.period.days;',
                            '$document_period_duration = '+str(days)+';')
        body = body.replace('$document_period_end_date = $document_period.period.end - time-span("P1D");',
                            "$document_period_end_date = date('"+asked_end+"');")
        body = body.replace('$document_period_start_date = $document_period.period.start;',
                            "$document_period_start_date = date('"+asked_start+"');")
        path.write_text(body,encoding='utf8')
    shutil.copyfile(base/'License.md',out/'License.md')
    namespace = filing.namespaces.get('us-gaap')
    if not namespace or not re.fullmatch(r'http://fasb.org/us-gaap/20\d\d(?:-\d{2}-\d{2})?',namespace):
        raise ValueError('Explicit supplied US-GAAP namespace required')
    year = re.search(r'20\d\d',namespace)[0]
    srt = filing.namespaces.get('srt') or 'http://fasb.org/srt/'+year
    if not re.fullmatch(r'http://fasb.org/srt/20\d\d(?:-\d{2}-\d{2})?',srt):
        raise ValueError('Unsupported supplied SRT namespace')
    helper = (base/'fixture_dependencies.xule').read_text(encoding='utf8').replace(
        'namespace http://fasb.org/us-gaap/2024','namespace '+namespace).replace(
        'namespace srt = http://fasb.org/srt/2024','namespace srt = '+srt)
    constants = (ROOT/'resources/task3_round4_dqc/constant.xule').read_text(encoding='utf8')
    functions = (ROOT/'resources/task3_round4_dqc/functions-lib.xule').read_text(encoding='utf8')
    for name in ('PRES_NETWORKS','STATEMENT_PRES_NETWORKS'):
        helper += '\n'+re.search(r'^constant \$'+name+r'\b.*?(?=^constant |^function |\Z)',constants,re.M|re.S)[0]
    for name in ('most_frequent','tolerance_for_decimals'):
        helper += '\n'+re.search(r'^function '+name+r'\(.*?(?=^function |\Z)',functions,re.M|re.S)[0]
    forms = dict(csv.reader((ROOT/'resources/task3_desktop_rule_metadata/rule-form-lookup.csv').open(encoding='utf8')))
    helper = re.sub(r'constant \$RULE-FORM-LOOKUP[^\n]+',
        "constant $RULE-FORM-LOOKUP = dict(list('0117', '"+forms['0117']+"'),list('0126', '"+forms['0126']+"'))",helper)
    helper = helper.replace("list('10093',date('2020-01-01')))",
                            "list('10093',date('2020-01-01')),list('9590',date('2020-01-01')))")
    helper = extend_nonnegative_dependencies(helper,filing,schema,forms,functions)
    (out/'source_dependencies.xule').write_text(helper,encoding='utf8')
    save(out/'manifest.json',{'input_query_sha256':hashlib.sha256(record['query'].encode()).hexdigest(),
        'case_id_is_output_join_only':True,'no_gold':True,'input_file_sha256':sha(input_path),
        'schema_imports':[e.get('schemaLocation') for e in schema.iter('{'+XS+'}import')],
        'supplied_xml_diagnostics':xml_diagnostics,'complete_prefix_enabled':True,
        'inferred_dimension_schema_declarations':dimension_declarations,
        'inferred_numeric_schema_declarations':inferred_declarations,'original_rule_body_unmodified':False,'original_math_and_applicability_clauses_preserved':True,'asked_period_override':True,'virtual_financial_facts_invented':False,'metadata_dependencies_are_reduced':True,
        'full_original_ruleset_claimed':False,'nonnegative_metadata_is_generic_CSV_and_exclusion_workbook_subset':True,'official_accuracy':None,
        'files_sha256':{p.name:sha(p) for p in out.iterdir() if p.is_file()},
        'preparer_sha256':sha(Path(__file__))})
    print(json.dumps({'supplied_bundle_created':str(out),'namespace':namespace}))


def extend_nonnegative_dependencies(helper,filing,schema,forms,functions):
    from task3.round4_rules import registry
    from task3.round3_engine import public_constraints, member_exclusions
    generic,_ = registry()
    modern,_ = public_constraints()
    generic = dict(generic)
    generic.update({('us-gaap',year):values for year,values in modern.items()})
    entries = {}
    for fact in filing.facts:
        match = re.fullmatch(r'\{http://fasb.org/(us-gaap|srt)/(20\d\d)(?:-01-31)?\}(.+)',fact.concept)
        if match:
            rule = generic.get((match[1],int(match[2])),{}).get(match[3])
            if rule:
                namespace = fact.concept[1:].partition('}')[0]
                entries[(namespace,match[3])] = rule
    literal = lambda value: "'"+str(value).replace("'", "\\'")+"'"
    qname = lambda uri,name: 'qname('+literal(uri)+','+literal(name)+')'
    body = '\nconstant $NON_NEG_ITEMS = dict('+','.join('list('+qname(ns,name)+','+literal(rule)+')' for (ns,name),rule in sorted(entries.items()))+')\n'
    excludes = member_exclusions()
    gaap = filing.namespaces['us-gaap']; srt=filing.namespaces.get('srt') or gaap.replace('/us-gaap/','/srt/')
    extension = schema.get('targetNamespace')
    def excluded_qname(name):
        if name=='IncomeTaxEffectChangeInLawAxis':return qname(extension,name)
        return qname(srt if name=='InvestmentIdentifierAxis' else gaap,name)
    for label,key in [('EXCLUDE_NON_NEG_STRING_MEMBERS','strings'),('EXCLUDE_NON_NEG_MEMBERS','members'),('EXCLUDE_NON_NEG_AXIS','axes')]:
        values = [literal(v) if key=='strings' else excluded_qname(v) for v in sorted(excludes[key])]
        body += 'constant $'+label+' = set('+','.join(values)+')\n'
    pairs = {}
    for axis,member in excludes['axis_members']:
        pairs.setdefault(axis,[]).append(member)
    body += 'constant $EXCLUDE_NON_NEG_AXIS_MEMBERS = list('+','.join('list('+qname(gaap,axis)+',set('+','.join(qname(srt if axis=='ConsolidatedEntitiesAxis' else gaap,member) for member in sorted(members))+'))' for axis,members in sorted(pairs.items()))+')\n'
    helper=re.sub(r'constant \$RULE-FORM-LOOKUP[^\n]+',lambda m:m[0][:-1]+",list('0015',"+literal(forms['0015'])+'))',helper)
    helper=re.sub(r'constant \$effective_dates[^\n]+',lambda m:m[0][:-1]+''.join(",list("+literal(rule)+",date('2020-01-01'))" for rule in sorted(set(entries.values())))+')',helper)
    for name in ('match_set_substring','not_elim_adjust','applicable_form_string'):
        body += '\n'+re.search(r'^function '+name+r'\(.*?(?=^function |\Z)',functions,re.M|re.S)[0]
    return helper+body


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--case-id',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    prepare(args.input,args.case_id,args.output)
