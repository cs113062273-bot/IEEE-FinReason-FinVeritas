"""Explicit schemas for every artifact exchanged in FinReason Cup 2026 Task 3.

Implemented with the standard library only so that participants can validate a
submission without installing a validation framework.  Every ``from_dict``
raises :class:`SchemaError` with a human-readable, ID-anchored message.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

__all__ = [
    "ANSWER_KEYS",
    "DevelopmentExample",
    "EvaluationResult",
    "GoldAnswer",
    "ParticipantPrediction",
    "SchemaError",
    "SubmissionMetadata",
    "TestInput",
]

#: The two keys that make up a FinMR answer object, in canonical order.
ANSWER_KEYS = ("extracted_value", "calculated_value")


class SchemaError(ValueError):
    """Raised when a record does not conform to the Task 3 schema."""


def _require_mapping(obj: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(obj, Mapping):
        raise SchemaError(f"{what} must be a JSON object, got {type(obj).__name__}")
    return obj


def _require_str(obj: Mapping[str, Any], key: str, what: str, *, allow_number: bool = False) -> str:
    if key not in obj or obj[key] is None:
        raise SchemaError(f"{what} is missing required field '{key}'")
    value = obj[key]
    if isinstance(value, str):
        return value
    if allow_number and isinstance(value, (int, float)) and not isinstance(value, bool):
        # Numbers are accepted but normalised to text: FinMR answers are strings
        # such as "-1,284" whose formatting must survive a round-trip.
        return str(value)
    raise SchemaError(f"{what} field '{key}' must be a string, got {type(value).__name__}")


@dataclass(frozen=True)
class GoldAnswer:
    """The reference answer of one case."""

    extracted_value: str
    calculated_value: str

    @classmethod
    def from_dict(cls, obj: Any, what: str = "answer") -> "GoldAnswer":
        obj = _require_mapping(obj, what)
        return cls(
            extracted_value=_require_str(obj, "extracted_value", what, allow_number=True),
            calculated_value=_require_str(obj, "calculated_value", what, allow_number=True),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "extracted_value": self.extracted_value,
            "calculated_value": self.calculated_value,
        }

    def to_judge_text(self) -> str:
        """Render the answer the way the reference judge prompt expects to see it."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass(frozen=True)
class DevelopmentExample:
    """One fully specified public development case (input + gold answer)."""

    id: str
    dqc_id: str
    query: str
    answer: GoldAnswer
    source: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, obj: Any) -> "DevelopmentExample":
        obj = _require_mapping(obj, "development example")
        case_id = _require_str(obj, "id", "development example", allow_number=True)
        what = f"development example {case_id}"
        source = obj.get("source", {})
        if not isinstance(source, Mapping):
            raise SchemaError(f"{what} field 'source' must be a JSON object")
        return cls(
            id=case_id,
            dqc_id=_require_str(obj, "dqc_id", what),
            query=_require_str(obj, "query", what),
            answer=GoldAnswer.from_dict(obj.get("answer"), f"{what} field 'answer'"),
            source=dict(source),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "dqc_id": self.dqc_id,
            "query": self.query,
            "answer": self.answer.to_dict(),
        }
        if self.source:
            out["source"] = self.source
        return out

    def to_input(self) -> "TestInput":
        return TestInput(id=self.id, dqc_id=self.dqc_id, query=self.query)


@dataclass(frozen=True)
class TestInput:
    """One case as it is handed to a participant system: no answer."""

    id: str
    #: Absent from the development and test inputs on purpose. The practice
    #: set names each case's data-quality rule, which for one of the three
    #: rules gives away the answer's shape; the ranked phases withhold it, so
    #: this loader must accept a record without it or no participant can read
    #: the files they are meant to work on.
    dqc_id: Optional[str]
    query: str

    #: Tells pytest this dataclass is not a test class despite its name.
    __test__ = False

    @classmethod
    def from_dict(cls, obj: Any) -> "TestInput":
        obj = _require_mapping(obj, "input record")
        case_id = _require_str(obj, "id", "input record", allow_number=True)
        what = f"input record {case_id}"
        for forbidden in ("answer", "extracted_value", "calculated_value"):
            if forbidden in obj:
                raise SchemaError(f"{what} must not contain gold field '{forbidden}'")
        return cls(
            id=case_id,
            dqc_id=_require_str(obj, "dqc_id", what) if "dqc_id" in obj else None,
            query=_require_str(obj, "query", what),
        )

    def to_dict(self) -> Dict[str, str]:
        record: Dict[str, str] = {"id": self.id}
        if self.dqc_id is not None:
            record["dqc_id"] = self.dqc_id
        record["query"] = self.query
        return record


@dataclass(frozen=True)
class ParticipantPrediction:
    """One line of ``predictions.jsonl``.

    ``raw_output`` is optional and is never used for scoring in the native
    format; it exists so teams can keep an audit trail of what their system
    actually emitted.
    """

    id: str
    extracted_value: str
    calculated_value: str
    raw_output: Optional[str] = None
    #: Which file format this came from. "native" submissions are always judged on
    #: the two parsed fields, so attaching `raw_output` for your own audit trail
    #: can never change your score. Only the "lm-eval" adapter sets this to
    #: "lm-eval", where the model's raw text IS the answer and must be judged as
    #: such for structural errors to remain reachable.
    source_format: str = "native"

    @classmethod
    def from_dict(cls, obj: Any) -> "ParticipantPrediction":
        obj = _require_mapping(obj, "prediction")
        case_id = _require_str(obj, "id", "prediction", allow_number=True)
        what = f"prediction {case_id}"
        raw = obj.get("raw_output")
        if raw is not None and not isinstance(raw, str):
            raise SchemaError(f"{what} field 'raw_output' must be a string when present")
        return cls(
            id=case_id,
            extracted_value=_require_str(obj, "extracted_value", what, allow_number=True),
            calculated_value=_require_str(obj, "calculated_value", what, allow_number=True),
            raw_output=raw,
        )

    def to_dict(self, *, include_raw: bool = False) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "extracted_value": self.extracted_value,
            "calculated_value": self.calculated_value,
        }
        if include_raw and self.raw_output is not None:
            out["raw_output"] = self.raw_output
        return out

    def to_judge_text(self) -> str:
        """Canonical JSON text shown to the judge as ``pred_answer``."""
        return json.dumps(
            {
                "extracted_value": self.extracted_value,
                "calculated_value": self.calculated_value,
            },
            ensure_ascii=False,
        )

    def judge_text(self) -> str:
        """Exactly what the judge sees for this prediction.

        For a native submission this is always the canonical two-key object built
        from the declared fields - never `raw_output`, so an optional audit field
        cannot change a score. For an lm-eval record the raw model text is the
        answer, so it is judged verbatim.
        """
        if self.source_format == "lm-eval" and self.raw_output is not None:
            return self.raw_output
        return self.to_judge_text()


@dataclass(frozen=True)
class EvaluationResult:
    """The case-level audit record written to ``case_results.jsonl``."""

    id: str
    gold: Dict[str, str]
    prediction: Optional[Dict[str, str]]
    label: Optional[str]
    judge_model: str
    prompt_version: str
    raw_judge_output: Optional[str] = None
    from_cache: bool = False
    error: Optional[str] = None
    attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubmissionMetadata:
    """Optional ``metadata.json`` submitted alongside ``predictions.jsonl``."""

    team_name: str
    contact_email: str
    method_name: str
    system_description: str = ""
    models_used: List[str] = field(default_factory=list)
    uses_external_api: bool = False
    submission_version: str = "final"

    @classmethod
    def from_dict(cls, obj: Any) -> "SubmissionMetadata":
        obj = _require_mapping(obj, "submission metadata")
        models = obj.get("models_used", [])
        if isinstance(models, str):
            models = [models]
        if not isinstance(models, (list, tuple)):
            raise SchemaError("submission metadata field 'models_used' must be a list")
        return cls(
            team_name=_require_str(obj, "team_name", "submission metadata"),
            contact_email=_require_str(obj, "contact_email", "submission metadata"),
            method_name=_require_str(obj, "method_name", "submission metadata"),
            system_description=str(obj.get("system_description", "")),
            models_used=[str(m) for m in models],
            uses_external_api=bool(obj.get("uses_external_api", False)),
            submission_version=str(obj.get("submission_version", "final")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
