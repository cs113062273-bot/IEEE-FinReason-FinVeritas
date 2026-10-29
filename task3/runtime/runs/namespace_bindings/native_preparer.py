"""Portable native preparation with namespace aliases bound by exact URI.

The restored runtime referenced this module but did not include it. The pinned
source-bundle preparer remains the implementation; this adapter changes only
its lexical namespace lookup, never supplied monetary facts or target values.
"""
import argparse
import importlib.util
from pathlib import Path
import re
import sys

WORK = Path(__file__).resolve().parents[2]
SOURCE = WORK / 'runs/native_runtime/source_config'
sys.path[:0] = [str(SOURCE / 'src'), str(SOURCE / 'scripts')]
spec = importlib.util.spec_from_file_location('pinned_native_bundle', SOURCE / 'scripts/task3_desktop_source_bundle_v6.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)
original = bundle.parse_xml


def parse(query, *, allow_complete_prefix=False):
    filing = original(query, allow_complete_prefix=allow_complete_prefix)
    for name, pattern in [('us-gaap', r'http://fasb.org/us-gaap/20\d\d(?:-\d{2}-\d{2})?'),
                          ('srt', r'http://fasb.org/srt/20\d\d(?:-\d{2}-\d{2})?')]:
        candidates = {uri for uri in filing.namespaces.values() if re.fullmatch(pattern, uri or '')}
        if len(candidates) == 1:
            filing.namespaces[name] = next(iter(candidates))
        elif name == 'us-gaap':
            raise ValueError('Unique source-bound US GAAP namespace required')
    return filing


bundle.parse_xml = parse

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--case-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    bundle.prepare(args.input, args.case_id, args.output)
