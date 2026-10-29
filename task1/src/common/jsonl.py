"""Canonical UTF-8 LF bytes across operating systems."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any,Iterable

def write_jsonl(path:Path, records:Iterable[dict[str,Any]]) -> None:
    payload=''.join(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n' for row in records)
    path.write_bytes(payload.encode('utf8'))
