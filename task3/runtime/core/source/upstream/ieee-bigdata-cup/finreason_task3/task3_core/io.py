"""JSONL reading/writing and prediction-format adapters.

All supported prediction formats are normalised into one internal
representation: an ordered mapping ``case_id -> ParticipantPrediction``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Tuple

from .schema import (
    DevelopmentExample,
    ParticipantPrediction,
    SchemaError,
    TestInput,
)

__all__ = [
    "FORMATS",
    "iter_jsonl",
    "read_jsonl",
    "write_jsonl",
    "sha256_file",
    "load_gold",
    "load_inputs",
    "load_predictions",
]

#: Prediction file formats understood by the validator and the evaluator.
FORMATS = ("native", "lm-eval")


class DataError(ValueError):
    """Raised for malformed files (as opposed to malformed individual records)."""


def iter_jsonl(path: Path | str) -> Iterator[Tuple[int, Any]]:
    """Yield ``(line_number, parsed_object)`` for every non-empty line.

    Line numbers are 1-based so that error messages point at what a text editor
    shows.  A JSON syntax error is re-raised as :class:`DataError` naming the line.
    """
    path = Path(path)
    if not path.exists():
        raise DataError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        lineno = 0
        while True:
            # readline() is used instead of iteration so a decoding error can be
            # caught here; text IO decodes a whole buffer at a time, so the line
            # number comes from the failing byte offset rather than from `lineno`.
            try:
                line = handle.readline()
            except UnicodeDecodeError as exc:
                raise DataError(
                    f"{path}:{_line_of_byte(path, exc.start)}: "
                    f"file is not valid UTF-8 ({exc.reason})"
                ) from exc
            if not line:
                return
            lineno += 1
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield lineno, json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise DataError(f"{path}:{lineno}: invalid JSON ({exc.msg})") from exc


def _line_of_byte(path: Path, offset: int) -> int:
    """1-based line number containing byte ``offset``, for decode-error messages."""
    with path.open("rb") as handle:
        return handle.read(offset + 1).count(b"\n") + 1


def read_jsonl(path: Path | str) -> List[Any]:
    return [obj for _, obj in iter_jsonl(path)]


def write_jsonl(path: Path | str, records: Iterable[Any]) -> int:
    """Write ``records`` as UTF-8 JSONL, creating parent directories. Returns count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_gold(path: Path | str) -> Dict[str, DevelopmentExample]:
    """Load a gold file (``public_dev.jsonl`` or ``private_test_gold.jsonl``)."""
    gold: Dict[str, DevelopmentExample] = {}
    for lineno, obj in iter_jsonl(path):
        try:
            example = DevelopmentExample.from_dict(obj)
        except SchemaError as exc:
            raise DataError(f"{path}:{lineno}: {exc}") from exc
        if example.id in gold:
            raise DataError(f"{path}:{lineno}: duplicate gold id {example.id!r}")
        gold[example.id] = example
    if not gold:
        raise DataError(f"{path}: contains no records")
    return gold


def load_inputs(path: Path | str) -> Dict[str, TestInput]:
    """Load an input-only file (``public_dev_inputs.jsonl``/``public_test_inputs.jsonl``)."""
    inputs: Dict[str, TestInput] = {}
    for lineno, obj in iter_jsonl(path):
        try:
            record = TestInput.from_dict(obj)
        except SchemaError as exc:
            raise DataError(f"{path}:{lineno}: {exc}") from exc
        if record.id in inputs:
            raise DataError(f"{path}:{lineno}: duplicate input id {record.id!r}")
        inputs[record.id] = record
    if not inputs:
        raise DataError(f"{path}: contains no records")
    return inputs


def _lm_eval_record_to_prediction(obj: Any, fallback_id: str) -> ParticipantPrediction:
    """Adapt one lm-evaluation-harness sample record.

    lm-eval writes ``{"doc_id": .., "target": "<gold json>", "filtered_resps": ["<raw model text>"]}``.
    The raw model text is kept verbatim in ``raw_output`` and is what the judge
    sees, so structural errors (label ``S``) remain reachable for legacy runs.
    """
    if not isinstance(obj, dict):
        raise SchemaError("lm-eval record must be a JSON object")
    resps = obj.get("filtered_resps") or obj.get("resps") or []
    if isinstance(resps, str):
        raw = resps
    else:
        if not resps:
            raise SchemaError("lm-eval record has empty 'filtered_resps'")
        first = resps[0]
        raw = first[0] if isinstance(first, (list, tuple)) and first else first
    raw = "" if raw is None else str(raw)

    case_id = obj.get("id")
    if case_id is None:
        doc = obj.get("doc") if isinstance(obj.get("doc"), dict) else {}
        case_id = doc.get("id", obj.get("doc_id", fallback_id))
    extracted, calculated = _extract_answer_fields(raw)
    return ParticipantPrediction(
        id=str(case_id),
        extracted_value=extracted,
        calculated_value=calculated,
        raw_output=raw,
        source_format="lm-eval",
    )


def _extract_answer_fields(raw: str) -> Tuple[str, str]:
    """Best-effort recovery of the two answer fields from free-form model text.

    Returns empty strings when nothing can be recovered; the judge then sees the
    raw text and is free to label the case ``S``.
    """
    text = raw.strip()
    if not text:
        return "", ""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            extracted = parsed.get("extracted_value", "")
            calculated = parsed.get("calculated_value", "")
            return _stringify(extracted), _stringify(calculated)
    return "", ""


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def load_predictions(
    path: Path | str,
    fmt: str = "native",
) -> Tuple[Dict[str, ParticipantPrediction], List[str]]:
    """Load predictions in ``fmt`` and return ``(by_id, errors)``.

    Records that fail schema validation are reported in ``errors`` rather than
    raising, so that :mod:`scripts.validate_submission` can list every problem in
    one pass.  Duplicate IDs keep the *first* occurrence and are reported.
    """
    if fmt not in FORMATS:
        raise DataError(f"Unknown prediction format {fmt!r}; expected one of {FORMATS}")

    by_id: Dict[str, ParticipantPrediction] = {}
    errors: List[str] = []
    for lineno, obj in iter_jsonl(path):
        try:
            if fmt == "native":
                prediction = ParticipantPrediction.from_dict(obj)
            else:
                prediction = _lm_eval_record_to_prediction(obj, fallback_id=str(lineno - 1))
        except SchemaError as exc:
            errors.append(f"line {lineno}: {exc}")
            continue
        if prediction.id in by_id:
            errors.append(f"line {lineno}: duplicate prediction for {prediction.id}")
            continue
        by_id[prediction.id] = prediction
    return by_id, errors
