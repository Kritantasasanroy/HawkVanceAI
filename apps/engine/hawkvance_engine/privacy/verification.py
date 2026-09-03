"""The final privacy gate, per spec sections 12 and 48.

Never assume the first redaction pass was sufficient. Everything about to cross the external
boundary is scanned a second time, with fresh eyes and no knowledge of what the first pass thought
it had handled. If a high-risk value survives, the request is blocked rather than sent.

Fail-safe direction is fixed: when uncertain, BLOCK. A false block costs the user a click. A false
allow costs them a credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .detection import Detection, PiiCategory, RedactionDisposition
from .detectors import DetectorSelection, RegexDetector, SecretDetector


class VerificationOutcome(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needsReview"


@dataclass(frozen=True, slots=True)
class SurvivingValue:
    """A sensitive value the first pass missed, described without quoting it."""

    category: PiiCategory
    confidence: float
    start: int
    end: int
    preview: str

    @staticmethod
    def preview_of(value: str) -> str:
        """Enough for the user to recognise the value, never enough to reconstruct it."""
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}{'*' * min(len(value) - 4, 8)}{value[-2:]}"

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "confidence": self.confidence,
            "start": self.start,
            "end": self.end,
            "preview": self.preview,
        }


@dataclass(frozen=True, slots=True)
class VerificationVerdict:
    outcome: VerificationOutcome
    survivors: tuple[SurvivingValue, ...]
    message: str

    @property
    def may_transmit(self) -> bool:
        return self.outcome is VerificationOutcome.ALLOWED

    def as_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "mayTransmit": self.may_transmit,
            "message": self.message,
            "survivors": [survivor.as_dict() for survivor in self.survivors],
        }


class PrivacyVerificationGate:
    """Second-pass scanner over the fully assembled context pack.

    Deliberately uses only the deterministic detectors. This pass must be fast, must never need a
    model to be resident, and must never itself be the reason a send is slow enough that someone
    turns it off.
    """

    def __init__(self) -> None:
        self._secrets = SecretDetector()
        self._patterns = RegexDetector()

    def verify(self, outbound_text: str) -> VerificationVerdict:
        survivors = self._survivors(outbound_text)

        high_risk = tuple(survivor for survivor in survivors if survivor.category.is_high_risk)
        if high_risk:
            return VerificationVerdict(
                outcome=VerificationOutcome.BLOCKED,
                survivors=high_risk,
                message=(
                    "Sensitive information was detected in the context prepared for external AI. "
                    "Review and redact it, or cancel the request."
                ),
            )

        if survivors:
            return VerificationVerdict(
                outcome=VerificationOutcome.NEEDS_REVIEW,
                survivors=survivors,
                message=(
                    "Possible personal information remains in the context prepared for external AI. "
                    "Check it before sending."
                ),
            )

        return VerificationVerdict(
            outcome=VerificationOutcome.ALLOWED,
            survivors=(),
            message="No unresolved sensitive values were found in the outbound context.",
        )

    def _survivors(self, text: str) -> tuple[SurvivingValue, ...]:
        everything = DetectorSelection()
        detections: list[Detection] = [
            *self._secrets.detect(text),
            *self._patterns.detect(text, everything),
        ]

        found: list[SurvivingValue] = []
        for detection in detections:
            if detection.confidence.disposition is RedactionDisposition.IGNORED:
                continue
            if self._is_a_placeholder(text, detection):
                continue
            found.append(
                SurvivingValue(
                    category=detection.category,
                    confidence=detection.confidence.value,
                    start=detection.start,
                    end=detection.end,
                    preview=SurvivingValue.preview_of(detection.original),
                )
            )

        found.sort(key=lambda survivor: (not survivor.category.is_high_risk, -survivor.confidence))
        return tuple(found)

    @staticmethod
    def _is_a_placeholder(text: str, detection: Detection) -> bool:
        """A already-redacted span looks like `[PERSON_001]`, which some patterns will re-match.

        Without this the gate would block on its own output, which is the classic way a second pass
        becomes noise that everybody disables.
        """
        opening = text.rfind("[", 0, detection.start + 1)
        if opening == -1:
            return False
        closing = text.find("]", detection.end - 1)
        if closing == -1:
            return False
        inner = text[opening + 1 : closing]
        return inner.replace("_", "").isalnum() and inner.upper() == inner
