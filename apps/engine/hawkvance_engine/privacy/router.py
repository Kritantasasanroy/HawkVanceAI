"""The PrivacyTaskRouter: spec sections 5, 6 and 35.

This is the component that keeps HawkVance light. It decides which detectors are allowed to wake up
for a given piece of text, and its default answer is "the cheapest ones that can do the job".

    "Call me at john@example.com"        -> FAST     -> regex only, no model loads
    "John joined Microsoft in London"    -> STANDARD -> Presidio, spaCy loads
    a signed client contract             -> HIGH     -> Presidio + GLiNER

Getting this wrong in the cheap direction leaks data. Getting it wrong in the expensive direction
loads a 700 MB model to find an email address. The router exists so neither happens by accident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .detection import Detection
from .detectors import DetectorSelection, RegexDetector, SecretDetector
from .gliner_detector import GlinerDetector, GlinerUnavailable
from .presidio_detector import PresidioDetector, PresidioUnavailable
from .redaction import RedactionMap, RedactionStyle


class PrivacyMode(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    HIGH_SECURITY = "highSecurity"
    ENTERPRISE = "enterprise"

    @property
    def uses_presidio(self) -> bool:
        return self is not PrivacyMode.FAST

    @property
    def uses_gliner(self) -> bool:
        return self in (PrivacyMode.HIGH_SECURITY, PrivacyMode.ENTERPRISE)

    @property
    def double_checks(self) -> bool:
        """ENTERPRISE runs the verification gate over its own output before anything else sees it."""
        return self is PrivacyMode.ENTERPRISE


@dataclass(frozen=True, slots=True)
class PrivacyPolicy:
    """What the user or the enterprise administrator chose."""

    mode: PrivacyMode = PrivacyMode.STANDARD
    selection: DetectorSelection = field(default_factory=DetectorSelection)
    style: RedactionStyle = RedactionStyle.PSEUDONYMISE
    custom_rules: tuple[str, ...] = ()
    #: Words and phrases the user chose to protect, matched literally rather than as expressions.
    protected_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Why the router chose what it chose, so the choice is auditable rather than mysterious."""

    mode: PrivacyMode
    detectors_used: tuple[str, ...]
    models_loaded: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "detectorsUsed": list(self.detectors_used),
            "modelsLoaded": list(self.models_loaded),
            "reason": self.reason,
        }


@dataclass(slots=True)
class ScanResult:
    redaction_map: RedactionMap
    sanitised_text: str
    decision: RoutingDecision
    degraded: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "sanitisedText": self.sanitised_text,
            "redactions": [redaction.as_dict() for redaction in self.redaction_map.redactions],
            "needsReview": [
                redaction.as_dict() for redaction in self.redaction_map.needing_review()
            ],
            "countsByCategory": self.redaction_map.counts_by_category(),
            "routing": self.decision.as_dict(),
            "degraded": list(self.degraded),
        }


class PrivacyTaskRouter:
    """Selects the minimum set of components that can safely handle this text.

    Owns the detectors so their lazily-loaded models can be released together when the queue drains.
    """

    # Text that is plainly structured identifiers and nothing else needs no language model at all.
    _NARRATIVE = re.compile(r"\b(?:[A-Z][a-z]+\s+){1,}[A-Z][a-z]+\b")
    _SHORT_TEXT_CHARACTERS = 280

    def __init__(self, policy: PrivacyPolicy | None = None) -> None:
        self._policy = policy or PrivacyPolicy()
        self._secrets = SecretDetector()
        self._patterns = self._build_patterns(self._policy)
        self._presidio = PresidioDetector()
        self._gliner = GlinerDetector()

    @staticmethod
    def _build_patterns(policy: PrivacyPolicy) -> RegexDetector:
        detector = RegexDetector()
        for expression in policy.custom_rules:
            detector.with_custom_rule(expression)
        for term in policy.protected_terms:
            detector.with_protected_term(term)
        return detector

    @property
    def policy(self) -> PrivacyPolicy:
        return self._policy

    def mode_for(self, text: str, requested: PrivacyMode | None = None) -> tuple[PrivacyMode, str]:
        """Chooses a mode when the caller did not force one.

        An explicit request always wins: this never quietly downgrades what the user asked for.
        """
        if requested is not None:
            return requested, "the caller asked for this mode explicitly"

        configured = self._policy.mode
        if configured is not PrivacyMode.STANDARD:
            return configured, "the configured default privacy mode"

        if not self._policy.selection.names_orgs_and_places:
            return (
                PrivacyMode.FAST,
                "names, organisations and places are switched off, so no language model is needed",
            )

        if len(text) <= self._SHORT_TEXT_CHARACTERS and not self._NARRATIVE.search(text):
            return (
                PrivacyMode.FAST,
                "short text with no narrative phrasing, so deterministic patterns are sufficient",
            )

        return PrivacyMode.STANDARD, "prose that may carry names, so contextual recognition applies"

    def scan(self, text: str, requested: PrivacyMode | None = None) -> ScanResult:
        mode, reason = self.mode_for(text, requested)
        selection = self._policy.selection

        if selection.nothing_enabled:
            return ScanResult(
                redaction_map=RedactionMap(),
                sanitised_text=text,
                decision=RoutingDecision(
                    mode=mode,
                    detectors_used=(),
                    models_loaded=(),
                    reason="every detector group was switched off by the user",
                ),
            )

        detections: list[Detection] = []
        used: list[str] = []
        loaded: list[str] = []
        degraded: list[str] = []

        if selection.secrets_and_credentials:
            detections.extend(self._secrets.detect(text))
            used.append("secrets")

        detections.extend(self._patterns.detect(text, selection))
        used.append("regex")

        if mode.uses_presidio:
            try:
                detections.extend(self._presidio.detect(text, selection))
                used.append("presidio")
                loaded.append("presidio")
            except PresidioUnavailable as unavailable:
                degraded.append(str(unavailable))

        if mode.uses_gliner and selection.names_orgs_and_places:
            try:
                detections.extend(self._gliner.detect(text, selection))
                used.append("gliner")
                loaded.append("gliner")
            except GlinerUnavailable as unavailable:
                degraded.append(str(unavailable))

        redaction_map = RedactionMap.resolve(detections, self._policy.style)
        return ScanResult(
            redaction_map=redaction_map,
            sanitised_text=redaction_map.apply(text),
            decision=RoutingDecision(
                mode=mode,
                detectors_used=tuple(used),
                models_loaded=tuple(loaded),
                reason=reason,
            ),
            degraded=tuple(degraded),
        )

    def release_models(self) -> list[str]:
        """Drops every lazily-loaded model. Called when the queue drains or memory gets tight."""
        released: list[str] = []
        if self._presidio.is_loaded:
            self._presidio.release()
            released.append("presidio")
        if self._gliner.is_loaded:
            self._gliner.release()
            released.append("gliner")
        return released

    @property
    def loaded_models(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, detector in (("presidio", self._presidio), ("gliner", self._gliner))
            if detector.is_loaded
        )
