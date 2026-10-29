"""Identical source inference pipeline for any input set; no split option.

No official answers, saved Development predictions or case-ID dispatch enter
numeric inference. Stage two consumes only this invocation's source output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'runtime'
BASE = RUNTIME / 'runs/orchestration/entrypoint/predict.py'
POST = RUNTIME / 'runs/reexamination/pipeline_v6.py'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def execute(command, log):
    with log.open('w', encoding='utf-8') as stream:
        proc = subprocess.run([str(x) for x in command], stdout=stream, stderr=subprocess.STDOUT)
    if proc.returncode:
        raise RuntimeError('Source inference failed; inspect ' + str(log))


def finish(inputs, base, output):
    """Finish an already freshly generated, input-bound stage-one run."""
    summary = json.loads((base / 'summary.json').read_text(encoding='utf-8'))
    records = [json.loads(l) for l in inputs.read_text(encoding='utf-8').splitlines() if l.strip()]
    assert summary['input_SHA256'] == sha(inputs)
    assert not summary['errors'] and summary['rows'] == len(records)
    assert summary['prediction_SHA256'] == sha(base / 'predictions.jsonl')
    # Imported modules are unchanged from actual execution. Compare file
    # hashes, not stale creation times or old machine absolute paths.
    for record in summary['modules'].values():
        path = Path(record['path'])
        assert path.is_relative_to(RUNTIME) and sha(path) == record['SHA256'], path
    execute([sys.executable, POST, '--inputs', inputs, '--predictions', base / 'predictions.jsonl',
             '--output', output / 'retention'], output / 'retention.log')
    from shutil import copyfile
    copyfile(output / 'retention/predictions.jsonl', output / 'predictions.jsonl')
    post_summary = json.loads((output / 'retention/summary.json').read_text(encoding='utf-8'))
    hashes = {str(p.relative_to(RUNTIME)).replace('\\', '/'): sha(p)
              for p in RUNTIME.rglob('*.py') if '__pycache__' not in p.parts}
    config = {'base': 'source 10/18 required-output engine with portable dependencies',
              'post': 'v7 role/QName/domain/priority/exact-arithmetic repair',
              'case_id_numeric_input': False, 'phase_numeric_input': False,
              'source_code_sha256': hashes}
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    (output / 'manifest.json').write_text(json.dumps({'input_sha256': sha(inputs), 'rows': len(records),
        'base_output_directory': str(base), 'base_summary_sha256': sha(base / 'summary.json'),
        'prediction_sha256': sha(output / 'predictions.jsonl'), 'config_sha256': digest,
        'same_source_engine_for_any_input': True, 'config': config,
        'base_unresolved_rows': summary['unresolved_rows'], 'post': post_summary,
        'organizer_test_accuracy_known': False, 'official_submission_performed': False}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'rows': len(records), 'prediction_sha256': sha(output / 'predictions.jsonl'), 'config_sha256': digest}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verified-source-run', type=Path,
                        help='Resume only a freshly generated input/hash-bound stage-one run; never a submission ZIP.')
    args = parser.parse_args()
    inputs, output = args.inputs.resolve(), args.output.resolve()
    assert not output.exists(), 'Use a fresh output directory'
    output.mkdir(parents=True)
    if args.verified_source_run:
        base = args.verified_source_run.resolve()
    else:
        base = output / 'source'
        execute([sys.executable, BASE, '--inputs', inputs, '--output', base], output / 'source.log')
    finish(inputs, base, output)


if __name__ == '__main__':
    main()
