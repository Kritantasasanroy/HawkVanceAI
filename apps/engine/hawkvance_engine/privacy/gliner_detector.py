"""GLiNER: contextual entity recognition, used only when the mode actually calls for it.

Spec section 9. This is the heaviest thing in the privacy path, so it is loaded on demand, used,
and released. Raw text never leaves the machine: GLiNER runs locally, and there is deliberately no
code path here that would call a hosted NER service.
"""

from __future__ import annotations

from typing import Any

from .detection import Confidence, Detection, DetectorKind, PiiCategory
from .detectors import DetectorSelection

# GLiNER takes plain-language labels rather than a fixed schema, which is what makes the enterprise
# entities (project, client, case) possible without retraining anything.
_LABEL_CATEGORIES: dict[str, PiiCategory] = {
    "person": PiiCategory.PERSON,
    "organization": PiiCategory.ORGANIZATION,
    "location": PiiCategory.LOCATION,
    "country": PiiCategory.GPE,
    "city": PiiCategory.GPE,
    "address": PiiCategory.STREET_ADDRESS,
    "date of birth": PiiCategory.DATE_OF_BIRTH,
    "project name": PiiCategory.PROJECT,
    "client name": PiiCategory.CLIENT,
    "case number": PiiCategory.CASE,
    "employee id": PiiCategory.EMPLOYEE_ID,
    "customer id": PiiCategory.CUSTOMER_ID,
}


class GlinerUnavailable(RuntimeError):
    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "The contextual entity model is not installed. "
            "HIGH_SECURITY mode needs it; STANDARD and FAST modes do not."
        )
        self.cause = cause


class GlinerDetector:
    """Contextual NER, lazily loaded and explicitly released.

    The default model is the small quantised multi-task GLiNER, chosen so an 8 GB machine can run
    HIGH_SECURITY mode without swapping.
    """

    name = "gliner"

    def __init__(self, model_name: str = "urchade/gliner_small-v2.1", threshold: float = 0.5) -> None:
        self._model_name = model_name
        self._threshold = threshold
        self._model: Any | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @staticmethod
    def is_available() -> bool:
        try:
            import gliner  # noqa: F401
        except Exception:
            return False
        return True

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from gliner import GLiNER
        except Exception as cause:  # pragma: no cover - exercised only without GLiNER installed
            raise GlinerUnavailable(cause) from cause
        self._model = GLiNER.from_pretrained(self._model_name)

    def release(self) -> None:
        self._model = None

    def estimated_memory_bytes(self) -> int:
        return 700 * 1024 * 1024

    def labels_for(self, selection: DetectorSelection) -> list[str]:
        return [
            label
            for label, category in _LABEL_CATEGORIES.items()
            if selection.includes(category.group)
        ]

    def detect(self, text: str, selection: DetectorSelection) -> list[Detection]:
        labels = self.labels_for(selection)
        if not labels:
            return []

        self.load()
        model = self._model
        if model is None:  # pragma: no cover - load() raises before this can happen
            raise GlinerUnavailable(RuntimeError("model did not initialise"))

        found: list[Detection] = []
        for entity in model.predict_entities(text, labels, threshold=self._threshold):
            category = _LABEL_CATEGORIES.get(entity["label"])
            if category is None:
                continue
            score = min(max(float(entity.get("score", self._threshold)), 0.0), 1.0)
            found.append(
                Detection(
                    start=int(entity["start"]),
                    end=int(entity["end"]),
                    category=category,
                    confidence=Confidence(score),
                    detector=DetectorKind.GLINER,
                    original=entity["text"],
                )
            )
        return found
