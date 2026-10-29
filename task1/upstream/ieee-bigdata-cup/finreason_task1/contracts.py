"""Strict, gold-free Task 1 JSONL contract validation.

The public validator and the private scorer use this exact module.  It never
loads hidden templates, private taxonomy mappings, or gold values.
"""

from __future__ import annotations

import json
import hashlib
import io
import os
import re
import stat
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


QUESTION_SCHEMA_VERSION = "finreason.task1.question/2.0.0"
PREDICTION_SCHEMA_VERSION = "finreason.task1.prediction/1.0.0"
MANIFEST_SCHEMA_VERSION = "finreason.task1.manifest/1.0.0"
GOLD_SCHEMA_VERSION = "finreason.task1.gold/2.0.0"
REPORT_SCHEMA_VERSION = "finreason.task1.report/2.0.0"

CASE_ID_PATTERN = re.compile(r"t1_[a-z0-9]{16,32}\Z")
IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
ENUM_VALUE_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z0-9_-]*(?: [A-Za-z0-9][A-Za-z0-9_-]*)*\Z"
)
TAXONOMY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
DECIMAL_PATTERN = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?(?:0|[1-9][0-9]{0,2}))?\Z"
)
RATIONAL_PATTERN = re.compile(r"-?[1-9][0-9]*/[1-9][0-9]*\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
INTEGER_STRING_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
POSITIVE_INTEGER_STRING_PATTERN = re.compile(r"[1-9][0-9]*\Z")

MAX_FILE_BYTES = 67_108_864
MAX_JSON_OBJECT_BYTES = 4_194_304
MAX_LINE_BYTES = 65_536
MAX_ISSUES = 100
MAX_RECORDS = 100_000
MAX_JSON_DEPTH = 64
MAX_SIGNIFICANT_DIGITS = 64
MIN_ADJUSTED_EXPONENT = -100
MAX_ADJUSTED_EXPONENT = 100


def validate_exact_lineage_value(value: Any, *, location: str) -> None:
    """Validate one organizer-only exact value shared by lineage consumers."""

    if not isinstance(value, Mapping):
        raise ContractError(f"{location} must be an exact-value object")
    value_type = value.get("type")
    if value_type == "rational":
        if (
            set(value) != {"type", "numerator", "denominator"}
            or not isinstance(value.get("numerator"), str)
            or not INTEGER_STRING_PATTERN.fullmatch(value["numerator"])
            or not isinstance(value.get("denominator"), str)
            or not POSITIVE_INTEGER_STRING_PATTERN.fullmatch(value["denominator"])
        ):
            raise ContractError(f"{location} has an invalid rational exact value")
        return
    if value_type == "boolean":
        if set(value) != {"type", "value"} or type(value.get("value")) is not bool:
            raise ContractError(f"{location} has an invalid Boolean exact value")
        return
    if value_type == "enum":
        enum_value = value.get("value")
        if (
            set(value) != {"type", "value"}
            or not isinstance(enum_value, str)
            or not 1 <= len(enum_value) <= 80
        ):
            raise ContractError(f"{location} has an invalid enum exact value")
        return
    raise ContractError(f"{location} has an unsupported exact-value type")


def exact_lineage_value_matches(
    exact_value: Any,
    result_spec: Mapping[str, Any],
    rendered_value: Any,
) -> bool:
    """Compare one exact lineage value with its typed rendered contract value."""

    if not isinstance(rendered_value, str):
        return False
    try:
        validate_exact_lineage_value(exact_value, location="lineage value")
        value_type = exact_value["type"]
        if result_spec.get("type") == "enum":
            if value_type == "boolean":
                return rendered_value == ("true" if exact_value["value"] else "false")
            return value_type == "enum" and exact_value["value"] == rendered_value
        if result_spec.get("type") != "decimal" or value_type != "rational":
            return False
        value = Fraction(
            int(exact_value["numerator"]),
            int(exact_value["denominator"]),
        )
        rounding = result_spec["rounding"]
        if rounding["mode"] == "exact":
            if "/" in rendered_value:
                numerator, denominator = rendered_value.split("/", 1)
                expected = Fraction(int(numerator), int(denominator))
            else:
                expected = Fraction(Decimal(rendered_value))
            return value == expected
        quantum = Decimal(1).scaleb(-rounding["decimal_places"])
        with localcontext() as context:
            context.prec = 256
            decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
            expected_decimal = decimal_value.quantize(quantum, rounding=ROUND_HALF_UP)
        return expected_decimal == Decimal(rendered_value)
    except (ArithmeticError, ContractError, InvalidOperation, KeyError, TypeError, ValueError):
        return False

UNITS = frozenset(
    {
        "basis_point",
        "count",
        "credits",
        "days",
        "days_per_year",
        "dimensionless",
        "multiple",
        "nominal_percent",
        "percent",
        "ratio",
        "ratio_per_year",
        "real_percent",
        "risk_point",
        "times_per_year",
        "tons_co2e",
        "usd",
        "usd_million",
        "usd_million_percent",
        "usd_million_real_percent",
        "usd_per_count",
        "usd_per_credit",
        "usd_per_day",
        "usd_per_month",
        "usd_per_ton_co2e",
        "usd_per_year",
        "years",
    }
)


class ContractError(ValueError):
    """Raised when organizer-owned question or manifest data is invalid."""


class JsonContractError(ContractError):
    """Raised when a strict JSON object cannot be decoded safely."""


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str
    line: int | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.line is not None:
            result["line"] = self.line
        return result


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    record_count: int
    issues: tuple[ValidationIssue, ...]
    records: tuple[dict[str, Any], ...] = ()

    def as_dict(self, *, include_records: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "valid": self.valid,
            "record_count": self.record_count,
            "errors": [issue.as_dict() for issue in self.issues],
        }
        if include_records:
            result["records"] = list(self.records)
        return result


def _append_issue(
    issues: list[ValidationIssue],
    code: str,
    path: str,
    message: str,
    *,
    line: int | None = None,
) -> None:
    if len(issues) < MAX_ISSUES:
        issues.append(ValidationIssue(code, path, message, line))


def _reject_duplicate_key(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant {value!r}")


def _enforce_json_depth(text: str) -> None:
    """Reject excessive object/array nesting before the recursive JSON decoder."""

    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError(
                    f"JSON nesting exceeds the maximum depth of {MAX_JSON_DEPTH}"
                )
        elif character in "]}" and depth:
            depth -= 1


def _decode_json_strict(text: str) -> Any:
    _enforce_json_depth(text)
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_key,
            parse_constant=_reject_nonfinite_constant,
        )
    except RecursionError as exc:
        raise ValueError(
            f"JSON nesting exceeds the decoder safety limit of {MAX_JSON_DEPTH}"
        ) from exc


def load_jsonl_bytes(content: bytes) -> ValidationResult:
    """Load bounded canonical UTF-8 JSONL bytes with duplicate-key rejection."""

    issues: list[ValidationIssue] = []
    if len(content) > MAX_FILE_BYTES:
        _append_issue(
            issues,
            "E_RESOURCE",
            "",
            f"file exceeds {MAX_FILE_BYTES} bytes",
        )
        return ValidationResult(False, 0, tuple(issues))
    if content and not content.endswith(b"\n"):
        _append_issue(
            issues,
            "E_ENCODING",
            "",
            "JSONL file must end with one LF",
        )

    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(io.BytesIO(content), start=1):
        if line_number > MAX_RECORDS:
            _append_issue(
                issues,
                "E_RESOURCE",
                "",
                f"file exceeds {MAX_RECORDS} JSONL records",
            )
            break
        line_content = raw[:-1] if raw.endswith(b"\n") else raw
        if len(line_content) > MAX_LINE_BYTES:
            _append_issue(
                issues,
                "E_RESOURCE",
                "",
                f"line exceeds {MAX_LINE_BYTES} bytes excluding LF",
                line=line_number,
            )
            continue
        if line_content.startswith(b"\xef\xbb\xbf"):
            _append_issue(
                issues,
                "E_ENCODING",
                "",
                "UTF-8 BOM is forbidden",
                line=line_number,
            )
            continue
        if b"\r" in raw:
            _append_issue(
                issues,
                "E_ENCODING",
                "",
                "only LF line endings are accepted",
                line=line_number,
            )
            continue
        if not line_content:
            _append_issue(
                issues,
                "E_JSONL",
                "",
                "blank lines are forbidden",
                line=line_number,
            )
            continue
        try:
            text = line_content.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _append_issue(
                issues,
                "E_ENCODING",
                "",
                "line is not valid UTF-8",
                line=line_number,
            )
            continue
        try:
            value = _decode_json_strict(text)
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            _append_issue(
                issues,
                "E_JSON",
                "",
                str(exc),
                line=line_number,
            )
            continue
        if not isinstance(value, dict):
            _append_issue(
                issues,
                "E_SCHEMA",
                "",
                "each JSONL record must be an object",
                line=line_number,
            )
            continue
        records.append(value)
    return ValidationResult(not issues, len(records), tuple(issues), tuple(records))


def load_jsonl(path: str | Path) -> ValidationResult:
    """Load one regular JSONL file after applying the canonical byte contract."""

    source = Path(path)
    issues: list[ValidationIssue] = []
    if not source.is_file() or source.is_symlink():
        _append_issue(issues, "E_FILE", "", "input must be one regular file")
        return ValidationResult(False, 0, tuple(issues))
    try:
        if source.stat().st_size > MAX_FILE_BYTES:
            _append_issue(
                issues,
                "E_RESOURCE",
                "",
                f"file exceeds {MAX_FILE_BYTES} bytes",
            )
            return ValidationResult(False, 0, tuple(issues))
        return load_jsonl_bytes(source.read_bytes())
    except OSError as exc:
        _append_issue(issues, "E_FILE", "", f"cannot read input: {exc}")
        return ValidationResult(False, 0, tuple(issues))


def _capture_regular_file_snapshot(path: str | Path, *, max_bytes: int) -> bytes:
    source = Path(path)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("input must be one regular file")
        if before.st_size > max_bytes:
            raise ContractError(f"input exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ContractError(f"input exceeds {max_bytes} bytes")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or total != after.st_size:
            raise ContractError("input changed while its snapshot was captured")
        return b"".join(chunks)
    except OSError as exc:
        raise ContractError(f"cannot capture input snapshot: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_jsonl_snapshot(path: str | Path) -> tuple[bytes, ValidationResult]:
    """Capture and validate one stable regular-file snapshot without following symlinks."""

    content = _capture_regular_file_snapshot(path, max_bytes=MAX_FILE_BYTES)
    return content, load_jsonl_bytes(content)


def load_json_object_snapshot(path: str | Path) -> tuple[bytes, dict[str, Any]]:
    """Capture one bounded strict JSON object and return the exact committed bytes."""

    content = _capture_regular_file_snapshot(path, max_bytes=MAX_JSON_OBJECT_BYTES)
    if content.startswith(b"\xef\xbb\xbf") or b"\r" in content:
        raise ContractError("JSON object must use UTF-8 without BOM and LF line endings")
    try:
        text = content.decode("utf-8", errors="strict")
        value = _decode_json_strict(text)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise JsonContractError(f"invalid JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("top-level JSON value must be an object")
    return content, value


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    issues: list[ValidationIssue],
    path: str,
    *,
    line: int | None,
) -> bool:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        _append_issue(
            issues,
            "E_SCHEMA",
            path,
            f"missing properties: {', '.join(missing)}",
            line=line,
        )
    if extra:
        _append_issue(
            issues,
            "E_SCHEMA",
            path,
            f"unexpected properties: {', '.join(extra)}",
            line=line,
        )
    return not missing and not extra


def validate_result_spec(spec: Any, *, path: str = "/result_spec") -> None:
    """Validate one trusted organizer result specification."""

    if not isinstance(spec, Mapping):
        raise ContractError(f"{path}: result specification must be an object")
    result_type = spec.get("type")
    if result_type == "decimal":
        if set(spec) != {"type", "unit", "rounding"}:
            raise ContractError(f"{path}: decimal result specification has wrong fields")
        if spec.get("unit") not in UNITS:
            raise ContractError(f"{path}: unsupported unit {spec.get('unit')!r}")
        rounding = spec.get("rounding")
        if not isinstance(rounding, Mapping):
            raise ContractError(f"{path}: rounding must be an object")
        if rounding.get("mode") == "exact":
            if set(rounding) != {"mode"}:
                raise ContractError(f"{path}: exact rounding has extra fields")
        elif rounding.get("mode") == "half_up":
            places = rounding.get("decimal_places")
            if set(rounding) != {"mode", "decimal_places"} or not (
                isinstance(places, int)
                and not isinstance(places, bool)
                and 0 <= places <= 12
            ):
                raise ContractError(f"{path}: invalid half-up rounding contract")
        else:
            raise ContractError(f"{path}: unsupported rounding mode")
        return
    if result_type == "enum":
        if set(spec) != {"type", "allowed_values"}:
            raise ContractError(f"{path}: enum result specification has wrong fields")
        allowed = spec.get("allowed_values")
        if not (
            isinstance(allowed, list)
            and 2 <= len(allowed) <= 64
            and all(
                isinstance(item, str)
                and len(item) <= 80
                and ENUM_VALUE_PATTERN.fullmatch(item)
                for item in allowed
            )
            and len(set(allowed)) == len(allowed)
        ):
            raise ContractError(f"{path}: invalid enum vocabulary")
        return
    raise ContractError(f"{path}: unsupported result type {result_type!r}")


def validate_question(question: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "dataset_version",
        "case_id",
        "question",
        "answer_spec",
        "trace_spec",
    }
    if set(question) != expected:
        raise ContractError("question row has wrong fields")
    if question.get("schema_version") != QUESTION_SCHEMA_VERSION:
        raise ContractError("question row has unsupported schema_version")
    if not isinstance(question.get("dataset_version"), str) or not 1 <= len(
        question["dataset_version"]
    ) <= 128:
        raise ContractError("question row has invalid dataset_version")
    if not isinstance(question.get("case_id"), str) or not CASE_ID_PATTERN.fullmatch(
        question["case_id"]
    ):
        raise ContractError("question row has invalid case_id")
    if not isinstance(question.get("question"), str) or not (
        question["question"].strip() and len(question["question"]) <= 32768
    ):
        raise ContractError("question text must be non-empty")
    validate_result_spec(question.get("answer_spec"), path="/answer_spec")
    trace_spec = question.get("trace_spec")
    if not isinstance(trace_spec, Mapping) or set(trace_spec) != {"slots"}:
        raise ContractError("trace_spec must contain only slots")
    slots = trace_spec.get("slots")
    if not isinstance(slots, list) or len(slots) > 32:
        raise ContractError("trace_spec must contain between 0 and 32 slots")
    seen: set[str] = set()
    for index, slot in enumerate(slots, start=1):
        if not isinstance(slot, Mapping) or set(slot) != {
            "slot_id",
            "position",
            "description",
            "result_spec",
        }:
            raise ContractError(f"trace slot {index} has wrong fields")
        slot_id = slot.get("slot_id")
        if not isinstance(slot_id, str) or not IDENTIFIER_PATTERN.fullmatch(slot_id):
            raise ContractError(f"trace slot {index} has invalid slot_id")
        if slot_id == "final_answer" or slot_id in seen:
            raise ContractError(f"trace slot {index} has reserved or duplicate slot_id")
        seen.add(slot_id)
        if slot.get("position") != index:
            raise ContractError(f"trace slot {index} has invalid position")
        if not isinstance(slot.get("description"), str) or not (
            slot["description"].strip() and len(slot["description"]) <= 1024
        ):
            raise ContractError(f"trace slot {index} has empty description")
        validate_result_spec(slot.get("result_spec"), path=f"/trace_spec/slots/{index-1}")


def _validate_decimal_text(text: Any, spec: Mapping[str, Any]) -> str | None:
    if not isinstance(text, str):
        return "value must be a canonical numeric string"
    rounding = spec.get("rounding")
    if isinstance(rounding, Mapping) and rounding.get("mode") == "exact" and "/" in text:
        if not RATIONAL_PATTERN.fullmatch(text):
            return "exact rational value must use canonical numerator/denominator syntax"
        numerator_text, denominator_text = text.split("/", 1)
        numerator = int(numerator_text)
        denominator = int(denominator_text)
        if len(numerator_text.lstrip("-")) > MAX_SIGNIFICANT_DIGITS or len(
            denominator_text
        ) > MAX_SIGNIFICANT_DIGITS:
            return f"rational component exceeds {MAX_SIGNIFICANT_DIGITS} digits"
        value = Fraction(numerator, denominator)
        if value.numerator != numerator or value.denominator != denominator:
            return "exact rational value must be irreducible"
        terminating_denominator = denominator
        while terminating_denominator % 2 == 0:
            terminating_denominator //= 2
        while terminating_denominator % 5 == 0:
            terminating_denominator //= 5
        if terminating_denominator == 1:
            return "terminating exact values must use finite decimal notation"
        with localcontext() as context:
            context.prec = 256
            decimal_value = Decimal(numerator) / Decimal(denominator)
        if decimal_value and not MIN_ADJUSTED_EXPONENT <= decimal_value.adjusted() <= MAX_ADJUSTED_EXPONENT:
            return "exact rational magnitude lies outside the supported exponent range"
        return None
    if not DECIMAL_PATTERN.fullmatch(text):
        if isinstance(rounding, Mapping) and rounding.get("mode") == "exact":
            return "value must be a canonical finite decimal or irreducible non-terminating rational string"
        return "value must be a canonical finite decimal string"
    coefficient = text.split("e", 1)[0].split("E", 1)[0].lstrip("-")
    digits = coefficient.replace(".", "").lstrip("0") or "0"
    if len(digits) > MAX_SIGNIFICANT_DIGITS:
        return f"value exceeds {MAX_SIGNIFICANT_DIGITS} significant digits"
    explicit_exponent = 0
    if "e" in text.lower():
        explicit_exponent = int(text.lower().split("e", 1)[1])
    if not MIN_ADJUSTED_EXPONENT <= explicit_exponent <= MAX_ADJUSTED_EXPONENT:
        return "explicit exponent lies outside -100..100"
    try:
        value = Decimal(text)
    except InvalidOperation:
        return "value is not a valid finite Decimal"
    if not value.is_finite():
        return "value must be finite"
    if value and not MIN_ADJUSTED_EXPONENT <= value.adjusted() <= MAX_ADJUSTED_EXPONENT:
        return "parsed Decimal adjusted exponent lies outside -100..100"
    return None


def _validate_typed_value(
    payload: Any,
    spec: Mapping[str, Any],
    issues: list[ValidationIssue],
    path: str,
    *,
    line: int | None,
) -> None:
    if not isinstance(payload, Mapping) or set(payload) != {"value"}:
        _append_issue(
            issues,
            "E_VALUE",
            path,
            "answer must be null or an object containing only value",
            line=line,
        )
        return
    value = payload.get("value")
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        _append_issue(
            issues,
            "E_VALUE",
            f"{path}/value",
            "value must be a non-empty string of at most 256 characters",
            line=line,
        )
        return
    if spec.get("type") == "decimal":
        error = _validate_decimal_text(value, spec)
        if error:
            _append_issue(issues, "E_VALUE", f"{path}/value", error, line=line)
        return
    if spec.get("type") == "enum":
        if not isinstance(value, str) or value not in spec.get("allowed_values", []):
            _append_issue(
                issues,
                "E_VALUE",
                f"{path}/value",
                "enum value is outside the published case-sensitive vocabulary",
                line=line,
            )
        return
    _append_issue(
        issues,
        "E_INTERNAL",
        path,
        "organizer result specification is unsupported",
        line=line,
    )


def _validate_gold_text(value: Any, spec: Mapping[str, Any], *, path: str) -> None:
    if spec.get("type") == "decimal":
        error = _validate_decimal_text(value, spec)
        if error:
            raise ContractError(f"{path}: {error}")
        return
    if spec.get("type") == "enum":
        if not isinstance(value, str) or value not in spec.get("allowed_values", []):
            raise ContractError(f"{path}: value is outside the case-sensitive vocabulary")
        return
    raise ContractError(f"{path}: unsupported organizer result specification")


def validate_gold_row(gold: Mapping[str, Any], question: Mapping[str, Any]) -> None:
    """Validate one trusted gold projection against its public question contract."""

    validate_question(question)
    expected = {
        "schema_version",
        "dataset_version",
        "case_id",
        "final_value",
        "slot_values",
    }
    if set(gold) != expected:
        raise ContractError("gold row has wrong fields")
    if gold.get("schema_version") != GOLD_SCHEMA_VERSION:
        raise ContractError("gold row has unsupported schema_version")
    if gold.get("dataset_version") != question.get("dataset_version"):
        raise ContractError("gold dataset_version differs from question")
    if gold.get("case_id") != question.get("case_id"):
        raise ContractError("gold case_id differs from question")
    _validate_gold_text(gold.get("final_value"), question["answer_spec"], path="/final_value")
    slot_values = gold.get("slot_values")
    slots = question["trace_spec"]["slots"]
    expected_slot_ids = [slot["slot_id"] for slot in slots]
    if not isinstance(slot_values, Mapping) or set(slot_values) != set(expected_slot_ids):
        raise ContractError("gold slot values do not exactly cover public slots")
    for slot in slots:
        _validate_gold_text(
            slot_values[slot["slot_id"]],
            slot["result_spec"],
            path=f"/slot_values/{slot['slot_id']}",
        )


def validate_manifest_row(
    manifest: Mapping[str, Any], question: Mapping[str, Any]
) -> None:
    """Validate organizer scoring membership without accepting participant metadata."""

    validate_question(question)
    expected = {
        "schema_version",
        "dataset_version",
        "case_id",
        "split",
        "domain_id",
        "topic_id",
        "template_id",
        "difficulty",
        "structure_stratum",
        "question_sha256",
    }
    if set(manifest) != expected:
        raise ContractError("manifest row has wrong fields")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ContractError("manifest row has unsupported schema_version")
    if manifest.get("dataset_version") != question.get("dataset_version"):
        raise ContractError("manifest dataset_version differs from question")
    if manifest.get("case_id") != question.get("case_id"):
        raise ContractError("manifest case_id differs from question")
    split = manifest.get("split")
    permitted_splits = {
        "train_public",
        "dev_local_public",
        "dev_leaderboard_public",
        "test_private_seen",
        "test_private_hidden",
        "reserve_private_hidden",
        "qa_private_hidden",
    }
    if split not in permitted_splits:
        raise ContractError("manifest split is unsupported")
    stratum = manifest.get("structure_stratum")
    expected_stratum = (
        "hidden"
        if split in {"test_private_hidden", "reserve_private_hidden", "qa_private_hidden"}
        else "seen"
    )
    if stratum != expected_stratum:
        raise ContractError("manifest split and structure_stratum conflict")
    difficulty = manifest.get("difficulty")
    if difficulty not in {"basic", "intermediate", "advanced"}:
        raise ContractError("manifest difficulty is unsupported")
    if stratum == "hidden" and difficulty == "basic":
        raise ContractError("hidden structure stratum cannot contain basic cases")
    taxonomy_patterns = {
        "domain_id": IDENTIFIER_PATTERN,
        "topic_id": TAXONOMY_PATTERN,
    }
    for field, pattern in taxonomy_patterns.items():
        value = manifest.get(field)
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ContractError(f"manifest {field} is invalid")
    template_id = manifest.get("template_id")
    if not isinstance(template_id, str) or not 1 <= len(template_id) <= 256:
        raise ContractError("manifest template_id is invalid")
    expected_hash = hashlib.sha256(
        json.dumps(
            question,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if manifest.get("question_sha256") != expected_hash:
        raise ContractError("manifest question_sha256 differs from canonical question")


def validate_prediction_record(
    prediction: Mapping[str, Any],
    question: Mapping[str, Any],
    *,
    line: int | None = None,
) -> tuple[ValidationIssue, ...]:
    """Validate one prediction against its public question specification."""

    validate_question(question)
    issues: list[ValidationIssue] = []
    _exact_keys(
        prediction,
        {"schema_version", "dataset_version", "case_id", "final_answer", "steps"},
        issues,
        "",
        line=line,
    )
    if prediction.get("schema_version") != PREDICTION_SCHEMA_VERSION:
        _append_issue(
            issues,
            "E_SCHEMA_VERSION",
            "/schema_version",
            f"expected {PREDICTION_SCHEMA_VERSION}",
            line=line,
        )
    if prediction.get("dataset_version") != question.get("dataset_version"):
        _append_issue(
            issues,
            "E_DATASET_VERSION",
            "/dataset_version",
            "dataset_version does not match the question bundle",
            line=line,
        )
    if prediction.get("case_id") != question.get("case_id"):
        _append_issue(
            issues,
            "E_CASE_ID",
            "/case_id",
            "case_id does not match the public question",
            line=line,
        )
    final_answer = prediction.get("final_answer")
    if final_answer is not None:
        _validate_typed_value(
            final_answer,
            question["answer_spec"],
            issues,
            "/final_answer",
            line=line,
        )
    steps = prediction.get("steps")
    if not isinstance(steps, list):
        _append_issue(issues, "E_SCHEMA", "/steps", "steps must be an array", line=line)
        return tuple(issues)
    if len(steps) > 32:
        _append_issue(
            issues,
            "E_RESOURCE",
            "/steps",
            "steps exceeds the published maximum of 32",
            line=line,
        )
        steps = steps[:32]
    slots = question["trace_spec"]["slots"]
    slot_by_id = {slot["slot_id"]: slot for slot in slots}
    position_by_id = {slot["slot_id"]: slot["position"] for slot in slots}
    seen_slots: set[str] = set()
    previous_position = 0
    for index, step in enumerate(steps):
        path = f"/steps/{index}"
        if not isinstance(step, Mapping):
            _append_issue(issues, "E_SCHEMA", path, "step must be an object", line=line)
            continue
        _exact_keys(step, {"slot_id", "value"}, issues, path, line=line)
        slot_id = step.get("slot_id")
        if not isinstance(slot_id, str) or slot_id not in slot_by_id:
            _append_issue(
                issues,
                "E_SLOT_ID",
                f"{path}/slot_id",
                "unknown slot_id",
                line=line,
            )
            continue
        if slot_id in seen_slots:
            _append_issue(
                issues,
                "E_SLOT_ID",
                f"{path}/slot_id",
                "duplicate slot_id",
                line=line,
            )
            continue
        seen_slots.add(slot_id)
        position = position_by_id[slot_id]
        if position <= previous_position:
            _append_issue(
                issues,
                "E_SLOT_ORDER",
                f"{path}/slot_id",
                "submitted slots must follow public slot order",
                line=line,
            )
        previous_position = position
        _validate_typed_value(
            {"value": step.get("value")},
            slot_by_id[slot_id]["result_spec"],
            issues,
            path,
            line=line,
        )
    return tuple(issues)


def validate_submission(
    records: Iterable[Mapping[str, Any]],
    questions: Mapping[str, Mapping[str, Any]],
    *,
    require_complete: bool = True,
) -> ValidationResult:
    """Validate a complete submission and perform a gold-free expected-ID join."""

    for question in questions.values():
        validate_question(question)
    issues: list[ValidationIssue] = []
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, prediction in enumerate(records, start=1):
        if not isinstance(prediction, Mapping):
            _append_issue(
                issues,
                "E_SCHEMA",
                "",
                "prediction row must be an object",
                line=line_number,
            )
            continue
        case_id = prediction.get("case_id")
        if not isinstance(case_id, str):
            _append_issue(
                issues,
                "E_CASE_ID",
                "/case_id",
                "case_id must be a string",
                line=line_number,
            )
            continue
        if case_id in seen:
            _append_issue(
                issues,
                "E_DUPLICATE_CASE_ID",
                "/case_id",
                "case_id appears more than once",
                line=line_number,
            )
            continue
        seen.add(case_id)
        question = questions.get(case_id)
        if question is None:
            _append_issue(
                issues,
                "E_UNKNOWN_CASE_ID",
                "/case_id",
                "case_id is not in the expected question bundle",
                line=line_number,
            )
            continue
        for issue in validate_prediction_record(prediction, question, line=line_number):
            if len(issues) < MAX_ISSUES:
                issues.append(issue)
        accepted.append(dict(prediction))
    if require_complete:
        missing = sorted(set(questions) - seen)
        if missing:
            preview = ", ".join(missing[:5])
            suffix = "" if len(missing) <= 5 else f" and {len(missing) - 5} more"
            _append_issue(
                issues,
                "E_MISSING_CASE_IDS",
                "",
                f"submission is missing {len(missing)} expected case IDs: {preview}{suffix}",
            )
    return ValidationResult(not issues, len(accepted), tuple(issues), tuple(accepted))


def validate_submission_file(
    path: str | Path,
    questions: Mapping[str, Mapping[str, Any]],
    *,
    require_complete: bool = True,
) -> ValidationResult:
    loaded = load_jsonl(path)
    if not loaded.valid:
        return loaded
    return validate_submission(loaded.records, questions, require_complete=require_complete)
