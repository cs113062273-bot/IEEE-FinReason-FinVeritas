"""Install the pinned public DQC support workbook; never download case data.

The upstream workbook is intentionally excluded from Git because its Office
metadata contains its original author's local saved-file path. Keep the
upstream bytes unchanged and verify them before installing either runtime copy.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = ('https://raw.githubusercontent.com/DataQualityCommittee/dqc_us_rules/'
       '15523c24c6997d9384a6aef82b7205ccd53feea2/'
       'docs/DQC_US_0015/DQC_0015_MemberExclusions.xlsx')
SHA256 = '5c666f28fcd6c90032fe661347c5efbfcf2447e3e1902e0fa5752b329d1318bd'
TARGETS = (
    'task3/runtime/core/source/resources/task3_dqc0015/DQC_0015_MemberExclusions.xlsx',
    'task3/runtime/runs/native_runtime/source_config/resources/task3_dqc0015/DQC_0015_MemberExclusions.xlsx',
)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-file', type=Path,
                        help='Use an already downloaded official workbook instead of the public URL.')
    args = parser.parse_args()
    paths = [ROOT / name for name in TARGETS]
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('Runtime asset path must stay inside this checkout')
        if path.exists() and digest(path.read_bytes()) != SHA256:
            raise ValueError('Existing workbook differs from the pinned upstream asset: ' + str(path))
    if all(path.is_file() for path in paths):
        print('Verified 2 installed copies of the pinned DQC support workbook')
        return
    if args.source_file:
        payload = args.source_file.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=45) as response:
            payload = response.read(1024 * 1024 + 1)
    if digest(payload) != SHA256:
        raise ValueError('DQC support workbook SHA-256 mismatch; nothing installed')
    for path in paths:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(payload)
        if digest(path.read_bytes()) != SHA256:
            raise ValueError('Installed workbook verification failed: ' + str(path))
    print('Installed and verified 2 copies of the pinned public DQC support workbook')


if __name__ == '__main__':
    main()
