"""Presidio integration: the primary PII orchestration framework, per spec section 7.

Loaded lazily. Constructing this class costs nothing; the spaCy pipeline behind it is only built on
the first `detect` call, and `release` drops it again when the queue drains.
"""

from __future__ import annotations

from typing import Any

from .detection import Confidence, Detection, DetectorKind, PiiCategory
from .detectors import DetectorSelection

# Presidio's entity names to ours. Anything Presidio reports that is not in this map is ignored
# rather than guessed at, so an upstream addition can never silently produce an untyped category.
_ENTITY_CATEGORIES: dict[str, PiiCategory] = {
    "EMAIL_ADDRESS": PiiCategory.EMAIL,
    "PHONE_NUMBER": PiiCategory.PHONE,
    "CREDIT_CARD": PiiCategory.CREDIT_CARD,
    "IBAN_CODE": PiiCategory.IBAN,
    "IP_ADDRESS": PiiCategory.IP_ADDRESS,
    "URL": PiiCategory.URL,
    "PERSON": PiiCategory.PERSON,
    "ORGANIZATION": PiiCategory.ORGANIZATION,
    "NRP": PiiCategory.ORGANIZATION,
    "LOCATION": PiiCategory.LOCATION,
    "GPE": PiiCategory.GPE,
    # Presidio reports any date under this one label, so it can only mean a date.
    "DATE_TIME": PiiCategory.DATE,
    "US_SSN": PiiCategory.NATIONAL_ID,
    "UK_NINO": PiiCategory.NATIONAL_ID,
    "IN_PAN": PiiCategory.NATIONAL_ID,
    "IN_AADHAAR": PiiCategory.NATIONAL_ID,
    "IN_VOTER": PiiCategory.NATIONAL_ID,
    "IN_PASSPORT": PiiCategory.NATIONAL_ID,
    "US_BANK_NUMBER": PiiCategory.BANK_ACCOUNT,
    "CRYPTO": PiiCategory.BANK_ACCOUNT,
}


class PresidioUnavailable(RuntimeError):
    """Raised when Presidio is asked for but not installed.

    Surfaced rather than swallowed: a privacy pipeline that silently skips a detector is worse than
    one that refuses to run, because the user believes they are protected.
    """

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "Presidio is not installed in the HawkVance engine environment. "
            "Reinstall the engine, or drop to FAST mode, which needs no model."
        )
        self.cause = cause


class PresidioDetector:
    """Wraps Presidio's AnalyzerEngine with HawkVance's category vocabulary.

    Not constructed at start-up and not held resident. Spec section 4 forbids loading every model
    when the application starts, and the spaCy pipeline behind Presidio is the largest thing in the
    STANDARD path.
    """

    name = "presidio"

    def __init__(self, language: str = "en", model_name: str = "en_core_web_sm") -> None:
        self._language = language
        self._model_name = model_name
        self._analyzer: Any | None = None

    @property
    def is_loaded(self) -> bool:
        return self._analyzer is not None

    @staticmethod
    def is_available() -> bool:
        try:
            import presidio_analyzer  # noqa: F401
        except Exception:
            return False
        return True

    def load(self) -> None:
        """Builds the analyzer against the *small* spaCy pipeline, explicitly.

        Presidio's default configuration asks for en_core_web_lg and downloads 400 MB the first time
        it is used. On a 4 GB machine that is both a surprise and a problem, so the model is pinned
        here rather than left to the default.

        The spaCy recognizer is also told to emit ORG. Presidio's default entity list omits it, so
        without this an organisation name reaches the model unredacted in STANDARD mode.
        """
        if self._analyzer is not None:
            return
        try:
            from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_analyzer.predefined_recognizers import SpacyRecognizer
        except Exception as cause:  # pragma: no cover - exercised only without Presidio installed
            raise PresidioUnavailable(cause) from cause

        try:
            nlp_engine = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": self._language, "model_name": self._model_name}],
                    "ner_model_configuration": {
                        "model_to_presidio_entity_mapping": {
                            "PERSON": "PERSON",
                            "ORG": "ORGANIZATION",
                            "GPE": "LOCATION",
                            "LOC": "LOCATION",
                            "FAC": "LOCATION",
                            "DATE": "DATE_TIME",
                            "NORP": "NRP",
                        },
                        "low_score_entity_names": [],
                        "labels_to_ignore": ["CARDINAL", "ORDINAL", "QUANTITY", "PERCENT"],
                    },
                }
            ).create_engine()
        except Exception as cause:
            raise PresidioUnavailable(cause) from cause

        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=nlp_engine, languages=[self._language])
        registry.add_recognizer(
            SpacyRecognizer(
                supported_language=self._language,
                supported_entities=["PERSON", "ORGANIZATION", "LOCATION", "NRP", "DATE_TIME"],
            )
        )

        self._analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine, registry=registry, supported_languages=[self._language]
        )

    def release(self) -> None:
        """Drops the spaCy pipeline. Called by the model manager under memory pressure."""
        self._analyzer = None

    def estimated_memory_bytes(self) -> int:
        return 220 * 1024 * 1024

    def detect(self, text: str, selection: DetectorSelection) -> list[Detection]:
        self.load()
        analyzer = self._analyzer
        if analyzer is None:  # pragma: no cover - load() raises before this can happen
            raise PresidioUnavailable(RuntimeError("analyzer did not initialise"))

        wanted = [
            entity
            for entity, category in _ENTITY_CATEGORIES.items()
            if selection.includes(category.group)
        ]
        if not wanted:
            return []

        results = analyzer.analyze(text=text, entities=wanted, language=self._language)

        found: list[Detection] = []
        for result in results:
            category = _ENTITY_CATEGORIES.get(result.entity_type)
            if category is None:
                continue
            score = min(max(float(result.score), 0.0), 1.0)
            found.append(
                Detection(
                    start=result.start,
                    end=result.end,
                    category=category,
                    confidence=Confidence(score),
                    detector=DetectorKind.PRESIDIO,
                    original=text[result.start : result.end],
                )
            )
        return found
