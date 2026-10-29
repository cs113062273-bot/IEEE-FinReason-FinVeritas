"""Retention fallback v6: original DQC rules decide 0117/0126; self-written code only where the rules cannot run.

usage: python pipeline_v6.py --inputs X.jsonl --predictions engine.jsonl --output <new dir>
Rows with calculated_value != extracted_value are copied byte-for-byte. For retention rows:
  R1   DQC_0015 (fixed module; eligible set verified equal to native Xule findings); focus = selection policy.
  Source gate (in-source, before native): the query's schema section must parse with a targetNamespace.
  R2f  original filing structure (permitted structural data only): when the exact entity + targetNamespace join finds
       the filing in the local structural catalog, the query's schema/presentation/calculation/definition/label are
       replaced by the original documents (Instance and question untouched) and native Xule runs WITHOUT relabeling.
       Used only if the run log has no DTS/schema load or validation errors (xbrl.*, xmlSchema*, arelle:*). Bound 0117/0126 findings: one value -> adopted; several ->
       same ambiguity policy as R2n; none -> continue with R2n.
       Fails -> 'source_insufficient': native is not run; R2s may apply (marked conditional).
  R2n  native Xule (original compiled rules, engine native.run) on the query with the role definition
       '- Disclosure -' read as '- Statement -'. 0117 findings bound to the asked target (full QName, supplied
       context in the asked period, unit, typed value == Q1):
         exactly one value  -> adopted.
         several values     -> ambiguous: adopted only if the simulator value is one of them
                               ('R2n_ambiguous_simulator_choice'); otherwise the row is left unchanged.
         none               -> R2s (fixed-module simulation, marked conditional).
       Any native exception on a source that passed the gate is retried; after 3 failures the run aborts.
"""
import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'runs' / 'source_engine'))
from retention_fallback import apply as fallback_apply, load_nonneg, Slice  # noqa: E402
from relabel import relabel  # noqa: E402
from build_full_structure import rebuild  # noqa: E402

DQC15 = ROOT / 'core' / 'source' / 'resources' / 'task3_dqc0015'
_NATIVE = None


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dec(x):
    try:
        return Decimal(str(x).replace(',', ''))
    except Exception:
        return None


def fmt(d):
    s = format(d, 'f')
    return s.rstrip('0').rstrip('.') if '.' in s else s


def source_schema_usable(query):
    """In-source check: the supplied schema section parses and declares a targetNamespace."""
    a = query.find('##Schema document')
    b = query.find('##Presentation linkbase document')
    text = query[a + len('##Schema document'):b].strip() if a >= 0 and b > a else ''
    if not text:
        return False
    try:
        root = etree.fromstring(text.encode('utf-8'), etree.XMLParser(recover=False, huge_tree=True, resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError:
        return False
    return root is not None and root.get('targetNamespace') is not None


def get_native(work):
    global _NATIVE
    if _NATIVE is None:
        import common_core as core
        # The native child must use the same URI-based preparation on renamed
        # XML aliases as stage one, rather than reverting to prefix lookups.
        sys.path.insert(0, str(ROOT / 'runs/namespace_bindings'))
        from uri_bindings import install
        install(core)
        core.configure(work)
        _NATIVE = core.native
    return _NATIVE


# DTS/schema load and validation errors: XBRL 2.1 (xbrl.*), XML Schema (xmlSchema*), Arelle loader (arelle:*)
LOAD_ERROR = re.compile(r'^\[(xbrl\.[0-9.]+:[A-Za-z]+|xmlSchema[A-Za-z0-9.]*:[A-Za-z]+|arelle:[A-Za-z]+)\]', re.M)


def native_bound(native, query, q1, mode='relabel', families=('0117',)):
    """Native findings bound to the asked target (facts always from the supplied query).
    mode 'relabel': role definition Disclosure->Statement; mode 'full': original filing structure, no relabel.
    Returns (case, [(code, value)], load_errors)."""
    sl = Slice(query)
    if mode == 'full':
        run_query, _ = rebuild(query)
    else:
        run_query, _ = relabel(query)
    res = native.run(run_query)
    log = (Path(native.O) / res['case'] / 'native_v6_seed0.log')
    load_errors = sorted(set(LOAD_ERROR.findall(log.read_text(encoding='utf-8', errors='replace')))) if log.exists() else ['missing native log']
    ctx_ok = {f[6] for f in sl.target_facts()}
    inst = sl.sec.get('##Instance document', '').strip()
    root = etree.fromstring(inst.encode('utf-8'), etree.XMLParser(recover=True, huge_tree=True))
    bound = {(el.get('contextRef'), el.get('unitRef')) for el in root.iter(sl.target_qname)} if sl.target_qname else set()
    vals = set()
    for acc in res['accesses']:
        for f in acc['computed_DQC_findings']:
            if f['code'].split('.')[2] not in families:
                continue
            if '{' + f['concept_namespace'] + '}' + f['concept_local_name'] != sl.target_qname:
                continue
            if f.get('schema_validation_state') != 4:
                continue
            if f['context_ref'] not in ctx_ok or (f['context_ref'], f['unit_ref']) not in bound:
                continue
            if dec(f['typed_value']) != q1:
                continue
            calculated = native.calculated_from_message(f['code'], f['message'])
            if calculated is not None:
                vals.add((f['code'], calculated))
    return res['case'], sorted(vals), load_errors


def native_with_retry(native, query, q1, row_id, attempts=3, **kw):
    last = None
    for _ in range(attempts):
        try:
            return native_bound(native, query, q1, **kw)
        except Exception as e:  # source already passed the in-source gate: any failure is environmental
            last = e
    raise RuntimeError(f'{row_id}: native Xule failed {attempts} times on a source with a usable schema; aborting: {last!r}'[:600])


def decide(row, query, nonneg, work):
    """Return (new_row, certificate or None) for one retention row."""
    q1 = dec(row['extracted_value'])
    old = dict(extracted_value=row['extracted_value'], calculated_value=row['calculated_value'])
    sim_row, sim = fallback_apply(query, row, nonneg)
    if sim and sim['rule'].startswith('R1'):
        return sim_row, sim
    if not source_schema_usable(query):
        if sim:
            return sim_row, dict(sim, rule=sim['rule'] + '_conditional_source_insufficient', source_gate='schema not usable')
        return row, None
    full_query, accession = rebuild(query)
    if full_query is not None:
        fcase, fvals, ferrs = native_with_retry(get_native(work), query, q1, row['id'], mode='full', families=('0117', '0126'))
        if not ferrs:
            fdistinct = sorted({v for _, v in fvals})
            ffind = [[c, str(v)] for c, v in fvals]
            if len(fdistinct) == 1:
                new = dict(row, calculated_value=fmt(fdistinct[0]))
                return new, dict(rule='R2f_original_structure_native', accession=accession, native_case=fcase, findings=ffind,
                                 simulator_alternative=(sim or {}).get('new'), old=old,
                                 new=dict(extracted_value=new['extracted_value'], calculated_value=new['calculated_value']))
            if len(fdistinct) > 1:
                sim_value = dec((sim or {}).get('new', {}).get('calculated_value')) if sim else None
                if sim_value is not None and sim_value in fdistinct:
                    return sim_row, dict(sim, rule='R2f_ambiguous_simulator_choice', accession=accession, native_findings=ffind)
                return row, dict(rule='R2f_ambiguous_not_adopted', accession=accession, native_findings=ffind, old=old, new=None)
    case, vals, _errs = native_with_retry(get_native(work), query, q1, row['id'])
    distinct = sorted({v for _, v in vals})
    findings = [[c, str(v)] for c, v in vals]
    if len(distinct) == 1:
        new = dict(row, calculated_value=fmt(distinct[0]))
        return new, dict(rule='R2n_native_DQC_0117', native_case=case, findings=findings, simulator_alternative=(sim or {}).get('new'),
                         old=old, new=dict(extracted_value=new['extracted_value'], calculated_value=new['calculated_value']))
    if len(distinct) > 1:
        sim_value = dec((sim or {}).get('new', {}).get('calculated_value')) if sim else None
        if sim_value is not None and sim_value in distinct:
            return sim_row, dict(sim, rule='R2n_ambiguous_simulator_choice', native_case=case, native_findings=findings)
        return row, dict(rule='R2n_ambiguous_not_adopted', native_case=case, native_findings=findings,
                         simulator_alternative=(sim or {}).get('new'), old=old, new=None)
    if sim:
        return sim_row, dict(sim, rule=sim['rule'] + '_conditional_no_native_finding', native_case=case)
    return row, None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--inputs', required=True)
    ap.add_argument('--predictions', required=True)
    ap.add_argument('--output', required=True)
    a = ap.parse_args(argv)
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    queries = {}
    for line in open(a.inputs, encoding='utf-8'):
        if line.strip():
            r = json.loads(line)
            queries[r['id']] = r['query']
    nonneg = load_nonneg(DQC15)
    changed = 0
    stats = {}
    with open(a.predictions, 'rb') as fin, open(out / 'predictions.jsonl', 'wb') as fp, \
            open(out / 'certificates.jsonl', 'w', encoding='utf-8', newline='\n') as fc:
        for raw in fin:
            body = raw.rstrip(b'\r\n')
            if not body.strip():
                fp.write(raw)
                continue
            row = json.loads(body.decode('utf-8'))
            q1, q2 = dec(row['extracted_value']), dec(row['calculated_value'])
            if q1 is None or q1 != q2:
                fp.write(raw)
                continue
            new, cert = decide(row, queries[row['id']], nonneg, out / 'native_work')
            key = (cert or {}).get('rule', 'unchanged')
            stats[key] = stats.get(key, 0) + 1
            if cert:
                fc.write(json.dumps(dict(id=row['id'], **cert), ensure_ascii=False, default=str) + '\n')
            if cert and cert.get('new'):
                changed += 1
                line = json.dumps({'id': new['id'], 'extracted_value': new['extracted_value'], 'calculated_value': new['calculated_value']}, ensure_ascii=False)
                fp.write(line.encode('utf-8') + raw[len(body):])
            else:
                fp.write(raw)
    summary = dict(changed=changed, retention_rule_counts=stats, output_sha256=sha(out / 'predictions.jsonl'),
                   pipeline_sha256=sha(__file__), fallback_sha256=sha(HERE / 'retention_fallback.py'), relabel_sha256=sha(HERE / 'relabel.py'))
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1))
    return summary


if __name__ == '__main__':
    main()
