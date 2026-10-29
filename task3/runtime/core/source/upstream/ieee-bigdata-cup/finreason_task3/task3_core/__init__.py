"""FinReason Cup 2026 - Task 3 (Financial Audit Verification) starter kit."""

from .schema import (
    DevelopmentExample,
    EvaluationResult,
    GoldAnswer,
    ParticipantPrediction,
    SubmissionMetadata,
    TestInput,
)

#: Version of this starter kit.
__version__ = "1.0.0"

#: Version string recorded in every evaluation run.
EVALUATION_VERSION = "1.0"

#: Version of the public development package built by scripts/prepare_public_dev.py
DATASET_VERSION = "task3-public-dev-v1.0"

__all__ = [
    "DevelopmentExample",
    "EvaluationResult",
    "GoldAnswer",
    "ParticipantPrediction",
    "SubmissionMetadata",
    "TestInput",
    "EVALUATION_VERSION",
    "DATASET_VERSION",
    "__version__",
]
