"""ID-based submission validation.

Validation never relies on row order: a submission is checked against the set of
reference case IDs.  See EVALUATION.md for the official
``missing_prediction_policy`` and why incomplete final submissions are rejected
before scoring rather than silently truncated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .io import DataError, load_gold, load_inputs, load_predictions
from .schema import ParticipantPrediction

__all__ = ["ValidationReport", "validate_predictions", "validate_submission_file"]

#: Maximum number of individual IDs echoed in an error message.
_MAX_LISTED = 20


def _format_ids(ids: Sequence[str]) -> str:
    listed = list(ids[:_MAX_LISTED])
    suffix = "" if len(ids) <= _MAX_LISTED else f" ... (+{len(ids) - _MAX_LISTED} more)"
    return ", ".join(listed) + suffix


@dataclass
class ValidationReport:
    """Outcome of validating one submission file."""

    predictions_path: str
    reference_path: str
    num_reference: int = 0
    num_predictions: int = 0
    missing_ids: List[str] = field(default_factory=list)
    unexpected_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "predictions": self.predictions_path,
            "reference": self.reference_path,
            "num_reference": self.num_reference,
            "num_predictions": self.num_predictions,
            "num_missing": len(self.missing_ids),
            "num_unexpected": len(self.unexpected_ids),
            "missing_ids": self.missing_ids,
            "unexpected_ids": self.unexpected_ids,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def render(self) -> str:
        lines = [
            "FinReason Cup 2026 - Task 3 Submission Validation",
            "=" * 48,
            "",
            f"Predictions: {self.predictions_path}",
            f"Reference:   {self.reference_path}",
            "",
            f"Reference cases:      {self.num_reference}",
            f"Predictions found:    {self.num_predictions}",
            f"Missing predictions:  {len(self.missing_ids)}",
            f"Unexpected IDs:       {len(self.unexpected_ids)}",
            "",
        ]
        for warning in self.warnings:
            lines.append(f"WARNING: {warning}")
        if self.warnings:
            lines.append("")
        if self.errors:
            for error in self.errors:
                lines.append(f"ERROR: {error}")
            lines.append("")
            lines.append(f"RESULT: INVALID ({len(self.errors)} error(s))")
        else:
            lines.append("RESULT: VALID")
        return "\n".join(lines)


def validate_predictions(
    predictions: Dict[str, ParticipantPrediction],
    reference_ids: Iterable[str],
    *,
    load_errors: Optional[Sequence[str]] = None,
    predictions_path: str = "<predictions>",
    reference_path: str = "<reference>",
    allow_empty_values: bool = False,
    allow_missing: bool = False,
) -> ValidationReport:
    """Validate an already-loaded prediction mapping against reference IDs.

    ``allow_missing`` downgrades missing-prediction errors to warnings. It exists
    for local development under a non-official ``missing_prediction_policy``;
    official scoring always leaves it False, so an incomplete submission is
    rejected before it is scored.
    """
    reference = list(dict.fromkeys(str(i) for i in reference_ids))
    reference_set = set(reference)

    report = ValidationReport(
        predictions_path=predictions_path,
        reference_path=reference_path,
        num_reference=len(reference),
        num_predictions=len(predictions),
    )
    report.errors.extend(load_errors or [])

    report.missing_ids = [cid for cid in reference if cid not in predictions]
    report.unexpected_ids = sorted(set(predictions) - reference_set)

    if report.missing_ids:
        message = (
            f"Missing prediction for {len(report.missing_ids)} case(s): "
            f"{_format_ids(report.missing_ids)}"
        )
        (report.warnings if allow_missing else report.errors).append(message)
    if report.unexpected_ids:
        report.errors.append(
            f"Unexpected id(s) not present in the reference set: "
            f"{_format_ids(report.unexpected_ids)}"
        )
    if len(predictions) != len(reference) and not (report.missing_ids or report.unexpected_ids):
        report.errors.append(
            f"Expected {len(reference)} predictions but found {len(predictions)}"
        )
    if report.missing_ids and allow_missing:
        report.warnings.append(
            f"Scoring only the {len(predictions)} case(s) present. This is a development "
            "convenience; the official rule rejects incomplete submissions."
        )

    empty_fields: List[str] = []
    for case_id, prediction in predictions.items():
        if case_id not in reference_set:
            continue
        # For an lm-eval record the raw model text IS the answer and is what the
        # judge sees; empty parsed fields simply mean the text was not a valid
        # answer object, which is a structural error to be scored, not a
        # malformed submission to be rejected.
        if getattr(prediction, "source_format", "native") == "lm-eval":
            continue
        for key in ("extracted_value", "calculated_value"):
            if not str(getattr(prediction, key)).strip():
                empty_fields.append(f"{case_id}.{key}")
    if empty_fields:
        message = (
            f"Empty value in {len(empty_fields)} field(s): {_format_ids(empty_fields)}. "
            "Emit \"0\" when your system cannot determine a value."
        )
        (report.warnings if allow_empty_values else report.errors).append(message)

    return report


def validate_submission_file(
    predictions_path: Path | str,
    reference_path: Path | str,
    *,
    fmt: str = "native",
    reference_kind: str = "auto",
    allow_empty_values: bool = False,
    allow_missing: bool = False,
) -> ValidationReport:
    """Validate ``predictions_path`` against an inputs or gold reference file.

    ``reference_kind`` is ``"inputs"``, ``"gold"`` or ``"auto"`` (detect by
    probing the first record for an ``answer`` field).
    """
    predictions_path = Path(predictions_path)
    reference_path = Path(reference_path)

    if reference_kind == "auto":
        reference_kind = _detect_reference_kind(reference_path)
    if reference_kind == "gold":
        reference_ids = list(load_gold(reference_path))
    elif reference_kind == "inputs":
        reference_ids = list(load_inputs(reference_path))
    else:
        raise DataError(f"Unknown reference_kind {reference_kind!r}")

    try:
        predictions, load_errors = load_predictions(predictions_path, fmt=fmt)
    except DataError as exc:
        report = ValidationReport(
            predictions_path=str(predictions_path),
            reference_path=str(reference_path),
            num_reference=len(reference_ids),
        )
        report.errors.append(str(exc))
        return report

    return validate_predictions(
        predictions,
        reference_ids,
        load_errors=load_errors,
        predictions_path=str(predictions_path),
        reference_path=str(reference_path),
        allow_empty_values=allow_empty_values,
        allow_missing=allow_missing,
    )


def _detect_reference_kind(path: Path) -> str:
    from .io import iter_jsonl

    for _, obj in iter_jsonl(path):
        if isinstance(obj, dict) and "answer" in obj:
            return "gold"
        return "inputs"
    raise DataError(f"{path}: contains no records")
