"""Validate user-supplied question/output files and two-run byte determinism.

No questions, expected answers, or scoring implementation are bundled here.
An optional caller-supplied reference may be a JSONL or a submission ZIP.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NUMBER = re.compile(r'[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f'nonfinite JSON constant: {value}')


def read_payload(path):
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as archive:
            if archive.namelist() != ['predictions.jsonl']:
                raise ValueError('submission ZIP must contain only root predictions.jsonl')
            return archive.read('predictions.jsonl')
    return path.read_bytes()


def rows(payload):
    if not payload or not payload.endswith(b'\n') or payload.startswith(b'\xef\xbb\xbf'):
        raise ValueError('expected nonempty UTF-8 JSONL with final newline and no BOM')
    records = []
    for line in payload.decode('utf8').splitlines():
        if not line.strip():
            raise ValueError('blank JSONL line')
        row = json.loads(line, object_pairs_hook=unique_object, parse_constant=reject_constant)
        if not isinstance(row, dict):
            raise ValueError('each JSONL record must be an object')
        records.append(row)
    return records


def index(records, field):
    result = {}
    for row in records:
        key = row.get(field)
        if not isinstance(key, str) or not key or key in result:
            raise ValueError(f'missing, invalid, or duplicate {field}')
        result[key] = row
    return result


def decimal(value):
    if not isinstance(value, str) or not NUMBER.fullmatch(value):
        raise ValueError('Task 3 numeric fields must be finite decimal strings with valid grouping')
    try:
        number = Decimal(value.replace(',', ''))
    except InvalidOperation as error:
        raise ValueError('invalid decimal') from error
    if not number.is_finite():
        raise ValueError('nonfinite decimal')
    return number


def validate(task, questions, predictions, payload):
    field = 'case_id' if task == 'task1' else 'id'
    qindex, pindex = index(questions, field), index(predictions, field)
    if set(qindex) != set(pindex):
        raise ValueError('prediction IDs must cover supplied question IDs exactly')
    if task == 'task1':
        sys.path.insert(0, str(ROOT/'task1/upstream/ieee-bigdata-cup'))
        from finreason_task1.contracts import load_jsonl_bytes, validate_submission
        loaded = load_jsonl_bytes(payload)
        if not loaded.valid:
            raise ValueError(loaded.as_dict())
        result = validate_submission(predictions, qindex, require_complete=True)
        if not result.valid:
            raise ValueError(result.as_dict())
    else:
        for row in predictions:
            if set(row) != {'id', 'extracted_value', 'calculated_value'}:
                raise ValueError('Task 3 requires exactly id, extracted_value, calculated_value')
            decimal(row['extracted_value'])
            decimal(row['calculated_value'])
    return pindex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', choices=('task1', 'task3'), required=True)
    parser.add_argument('--questions', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--repeat-predictions', type=Path, required=True,
                        help='Output from an independent second invocation on the same questions.')
    parser.add_argument('--reference', type=Path, help='Optional user-supplied JSONL or submission ZIP.')
    parser.add_argument('--reference-numeric', action='store_true',
                        help='Task 3: compare Decimal values to the reference, ignoring thousands formatting.')
    args = parser.parse_args()
    if args.reference_numeric and (args.task != 'task3' or not args.reference):
        parser.error('--reference-numeric requires Task 3 and --reference')
    questions = rows(args.questions.read_bytes())
    payload = read_payload(args.predictions)
    predictions = rows(payload)
    current = validate(args.task, questions, predictions, payload)
    repeated = read_payload(args.repeat_predictions)
    validate(args.task, questions, rows(repeated), repeated)
    if payload != repeated:
        raise ValueError('independent executions differ byte for byte')
    result = {'task': args.task, 'rows': len(predictions), 'format_valid': True,
              'two_run_bytes_identical': True, 'sha256': hashlib.sha256(payload).hexdigest()}
    if args.reference:
        reference = read_payload(args.reference)
        if args.reference_numeric:
            expected = validate(args.task, questions, rows(reference), reference)
            for key, row in current.items():
                for field in ('extracted_value', 'calculated_value'):
                    if decimal(row[field]) != decimal(expected[key][field]):
                        raise ValueError(f'numeric reference mismatch: {key} {field}')
            result['reference_decimal_rows_equal'] = len(predictions)
            result['reference_decimal_fields_equal'] = 2*len(predictions)
        else:
            if payload != reference:
                raise ValueError('reference differs byte for byte')
            result['reference_bytes_identical'] = True
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        print(f'Verification failed: {error}', file=sys.stderr)
        raise SystemExit(1)
