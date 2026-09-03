"""Conflict resolution, redaction and pseudonymisation.

The `RedactionMap` here is the single most sensitive object in HawkVance. It holds the mapping from
placeholder back to original value, it lives only on this machine, and it has no serialiser that
targets the wire. See docs/designs/privacy-redaction.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from .detection import (
    Confidence,
    Detection,
    DetectorKind,
    PiiCategory,
    RedactionDisposition,
)


class RedactionStyle(str, Enum):
    """Spec section 10 allows the policy to choose how a value is replaced."""

    PSEUDONYMISE = "pseudonymise"
    MASK = "mask"
    REMOVE = "remove"
    REPLACE = "replace"


@dataclass(frozen=True, slots=True)
class Redaction:
    """One replacement of one span.

    Carries `original_hash`, never the original value, so counting and cross-document matching work
    without holding the secret. This is the shape that may be shown to the user and stored.
    """

    start: int
    end: int
    category: PiiCategory
    placeholder: str
    confidence: Confidence
    detector: DetectorKind
    original_hash: str
    disposition: RedactionDisposition

    def as_dict(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "category": self.category.value,
            "placeholder": self.placeholder,
            "confidence": self.confidence.value,
            "detector": self.detector.value,
            "originalHash": self.original_hash,
            "disposition": self.disposition.value,
        }


class ConflictResolver:
    """Spec section 11.

    Detectors disagree constantly: Presidio calls characters 10-20 a PERSON, GLiNER calls 10-24 the
    same thing, and the secret detector claims 8-30 is an API key. Exactly one of them can win a
    given span, because two overlapping replacements corrupt the offsets of everything after them.
    """

    @staticmethod
    def resolve(detections: list[Detection]) -> list[Detection]:
        considered = [
            detection
            for detection in detections
            if detection.length > 0
            and detection.confidence.disposition is not RedactionDisposition.IGNORED
        ]

        # Strongest first, so the sweep below keeps the winner of every overlap.
        considered.sort(
            key=lambda detection: (
                detection.detector_priority,
                detection.confidence.value,
                detection.category.specificity,
                detection.length,
            ),
            reverse=True,
        )

        kept: list[Detection] = []
        for candidate in considered:
            if not any(held.overlaps(candidate) for held in kept):
                kept.append(candidate)

        kept.sort(key=lambda detection: detection.start)
        return kept


@dataclass(slots=True)
class RedactionMap:
    """The conflict-resolved set of redactions over one text, plus the local-only reverse mapping.

    Invariants, enforced at construction rather than checked later:
      1. no two redactions overlap
      2. redactions are ordered by start offset
      3. one original value has exactly one placeholder, so [PERSON_001] is the same person
         everywhere in the text
      4. placeholder numbering restarts per category and is stable within the map
    """

    redactions: list[Redaction] = field(default_factory=list)
    _originals: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def resolve(
        cls, detections: list[Detection], style: RedactionStyle = RedactionStyle.PSEUDONYMISE
    ) -> "RedactionMap":
        kept = ConflictResolver.resolve(detections)

        redaction_map = cls()
        assigned: dict[tuple[PiiCategory, str], str] = {}
        counters: dict[PiiCategory, int] = {}

        for detection in kept:
            key = (detection.category, detection.original)
            placeholder = assigned.get(key)
            if placeholder is None:
                counters[detection.category] = counters.get(detection.category, 0) + 1
                placeholder = cls._placeholder_for(
                    detection, counters[detection.category], style
                )
                assigned[key] = placeholder
                if style is RedactionStyle.PSEUDONYMISE:
                    redaction_map._originals[placeholder] = detection.original

            redaction_map.redactions.append(
                Redaction(
                    start=detection.start,
                    end=detection.end,
                    category=detection.category,
                    placeholder=placeholder,
                    confidence=detection.confidence,
                    detector=detection.detector,
                    original_hash=cls.digest(detection.original),
                    disposition=detection.confidence.disposition,
                )
            )

        return redaction_map

    @staticmethod
    def _placeholder_for(detection: Detection, ordinal: int, style: RedactionStyle) -> str:
        if style is RedactionStyle.PSEUDONYMISE:
            return f"[{detection.category.placeholder_stem}_{ordinal:03d}]"
        if style is RedactionStyle.MASK:
            return "*" * min(detection.length, 12)
        if style is RedactionStyle.REMOVE:
            return ""
        return f"[{detection.category.placeholder_stem}]"

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @property
    def is_empty(self) -> bool:
        return not self.redactions

    def needing_review(self) -> list[Redaction]:
        """What the Privacy Gate renders amber: the 0.50 to 0.85 band, where the user decides."""
        return [
            redaction
            for redaction in self.redactions
            if redaction.disposition is RedactionDisposition.NEEDS_REVIEW
        ]

    def automatic(self) -> list[Redaction]:
        return [
            redaction
            for redaction in self.redactions
            if redaction.disposition is RedactionDisposition.AUTO_REDACT
        ]

    def keep_in_clear(self, placeholders: list[str]) -> None:
        """Drops what the user chose to keep. Called after the gate, before `apply`."""
        dropped = set(placeholders)
        self.redactions = [
            redaction for redaction in self.redactions if redaction.placeholder not in dropped
        ]
        still_used = {redaction.placeholder for redaction in self.redactions}
        self._originals = {
            placeholder: original
            for placeholder, original in self._originals.items()
            if placeholder in still_used
        }

    def apply(self, text: str) -> str:
        """Produces the text that may leave the device.

        Applied back to front so earlier offsets stay valid as the string changes length.
        """
        sanitised = text
        for redaction in sorted(self.redactions, key=lambda item: item.start, reverse=True):
            if redaction.end <= len(sanitised):
                sanitised = (
                    sanitised[: redaction.start] + redaction.placeholder + sanitised[redaction.end :]
                )
        return sanitised

    def restore(self, text: str) -> str:
        """The local-only reverse direction.

        Runs on a model's response, on this machine, so the user reads real names instead of
        placeholders. The table it reads has never left the device and never will.
        """
        restored = text
        # Longest placeholder first, so [PERSON_1] never partially matches inside [PERSON_10].
        for placeholder in sorted(self._originals, key=len, reverse=True):
            restored = restored.replace(placeholder, self._originals[placeholder])
        return restored

    def export_entries(self) -> list[dict[str, str]]:
        """The reverse mapping, for the desktop to keep in its encrypted vault.

        This is the one method that hands originals out of this object, so it is worth being precise
        about why it exists and what it does not change.

        A document is scanned once, at the moment it is added. Only the sanitised text is stored, so
        without this the mapping died with the scan and every placeholder in that document became
        permanently unresolvable: a later answer could only ever show [ORG_003]. Restoration for
        documents was not merely broken, it was impossible.

        P2 still holds. "Never leaves the device" is the invariant, and the only caller is the Rust
        core on this machine, which seals each value before writing it to the local vault. There is
        still no wire serialiser, no shared-contract type, and no field on any request the backend
        could receive. Nothing here narrows that.
        """
        return [
            {"placeholder": placeholder, "original": original}
            for placeholder, original in self._originals.items()
        ]

    def load_entries(self, entries: list[dict[str, str]]) -> int:
        """Re-adopts a mapping the desktop kept from an earlier scan.

        Existing entries win. A placeholder resolved by this scan is the one that matches the text in
        front of us, whereas a stored one may belong to an older version of the same document.
        """
        added = 0
        for entry in entries:
            placeholder = entry.get("placeholder", "")
            original = entry.get("original", "")
            if not placeholder or not original or placeholder in self._originals:
                continue
            self._originals[placeholder] = original
            added += 1
        return added

    def counts_by_category(self) -> dict[str, int]:
        """What the privacy ledger records: counts and categories, never values."""
        counts: dict[str, int] = {}
        for redaction in self.redactions:
            counts[redaction.category.value] = counts.get(redaction.category.value, 0) + 1
        return counts

    @property
    def placeholder_count(self) -> int:
        return len(self._originals)


class RedactionEngine:
    """Applies a resolved map to text. Deliberately thin: the decisions are all in the map."""

    @staticmethod
    def sanitise(text: str, redaction_map: RedactionMap) -> str:
        return redaction_map.apply(text)


class PseudonymizationEngine:
    """Restores placeholders in a model response, locally.

    Separate from `RedactionEngine` because the two directions have different trust properties: one
    produces text that may leave, the other consumes text that came back and must never leave again.
    """

    @staticmethod
    def restore(text: str, redaction_map: RedactionMap) -> str:
        return redaction_map.restore(text)
