"""The local summariser: spec section 18.

This is the one place a general-purpose language model runs on the user's machine, and it is
deliberately not exposed as a chatbot. It performs summarisation, classification, memory-candidate
extraction and importance estimation, and nothing else. There is no method here that takes an
arbitrary user prompt.

The model is loaded on demand, used, and released, exactly like every other component.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .memory.model import MemoryCandidate, MemoryScope

# What the model is allowed to be asked. Prompts are constructed here, from templates, never taken
# from the user, which is what keeps this an internal component rather than a chat surface.
_SUMMARY_PROMPT = """You are a document summarisation function inside a privacy tool.
The text below has already been redacted: values in square brackets like [PERSON_001] are
placeholders for real names. Treat them as stable identities and keep them exactly as written.

Write {sentences} sentences summarising what this document is and what it says.
Write nothing else: no preamble, no bullet points, no commentary.

DOCUMENT:
{text}

SUMMARY:"""

_FACTS_PROMPT = """You are a fact extraction function inside a privacy tool.
Extract the durable facts from the text below: decisions, preferences, obligations, dates and
positions. Keep placeholders like [PERSON_001] exactly as written.

Return a JSON array of at most {limit} strings and nothing else.

TEXT:
{text}

JSON:"""

_CLASSIFY_PROMPT = """Classify the document below into exactly one of these categories:
legal, financial, technical, medical, correspondence, research, personal, other.

Answer with the single word and nothing else.

DOCUMENT:
{text}

CATEGORY:"""

# A placeholder opening a sentence, so the fact guard can tell one from a JSON array.
_PLACEHOLDER_AT_START = re.compile(r"^\[[A-Z][A-Z0-9_]*\]")

_CATEGORIES = frozenset(
    {"legal", "financial", "technical", "medical", "correspondence", "research", "personal", "other"}
)


class SummariserUnavailable(RuntimeError):
    """Raised when summarisation is asked for but the runtime or model is not present.

    Surfaced rather than silently skipped: a memory built from no summary is a memory the user
    thinks they have and does not.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"The local summarisation model is not available ({detail}). "
            "Document summaries and memory extraction are unavailable until it is installed."
        )
        self.detail = detail


@dataclass(frozen=True, slots=True)
class DocumentProfile:
    """Spec section 28: what HawkVance understands about a document without resending it."""

    summary: str
    category: str
    key_facts: tuple[str, ...]
    used_model: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "category": self.category,
            "keyFacts": list(self.key_facts),
            "usedModel": self.used_model,
        }


class ExtractiveSummariser:
    """Sentence-ranking fallback that needs no model at all.

    It is genuinely useful, not a stub: it picks the sentences carrying placeholders, dates and
    numbers, which is most of what matters in a contract. It exists so a 4 GB machine, or one where
    the model has not downloaded yet, still gets summaries and memory candidates rather than an
    error and an empty screen.
    """

    _SENTENCE = re.compile(r"(?<=[.!?])\s+")
    _PLACEHOLDER = re.compile(r"\[[A-Z][A-Z0-9_]*\]")
    _DATE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
    _MODAL = re.compile(
        r"(?i)\b(?:shall|must|will|agrees?|liable|indemnif|terminat|payment|obligat|warrant)\w*\b"
    )

    @classmethod
    def score(cls, sentence: str) -> float:
        value = 0.0
        value += 2.0 * len(cls._PLACEHOLDER.findall(sentence))
        value += 1.5 if cls._DATE.search(sentence) else 0.0
        value += 1.5 if cls._MODAL.search(sentence) else 0.0
        value += 0.5 if any(character.isdigit() for character in sentence) else 0.0
        if len(sentence) < 30:
            value -= 1.5
        if len(sentence) > 400:
            value -= 0.5
        return value

    @classmethod
    def summarise(cls, text: str, sentences: int = 3) -> str:
        parts = [part.strip() for part in cls._SENTENCE.split(text) if part.strip()]
        if not parts:
            return ""
        ranked = sorted(enumerate(parts), key=lambda pair: cls.score(pair[1]), reverse=True)
        kept = sorted(ranked[:sentences], key=lambda pair: pair[0])
        return " ".join(sentence for _, sentence in kept)

    @classmethod
    def key_facts(cls, text: str, limit: int = 6) -> tuple[str, ...]:
        parts = [part.strip() for part in cls._SENTENCE.split(text) if len(part.strip()) > 40]
        ranked = sorted(parts, key=cls.score, reverse=True)
        return tuple(ranked[:limit])

    @staticmethod
    def classify(text: str) -> str:
        lowered = text.lower()
        signals = {
            "legal": ("agreement", "clause", "indemnit", "liabilit", "party", "hereby", "terminat"),
            "financial": ("invoice", "payment", "amount due", "balance", "tax", "revenue"),
            "technical": ("function", "class ", "api", "endpoint", "database", "deploy"),
            "medical": ("patient", "diagnos", "prescrib", "dosage", "clinical"),
            "correspondence": ("dear ", "regards", "sincerely", "subject:"),
            "research": ("abstract", "methodology", "hypothes", "findings", "et al"),
        }
        best, score = "other", 0
        for category, markers in signals.items():
            hits = sum(1 for marker in markers if marker in lowered)
            if hits > score:
                best, score = category, hits
        return best


class LocalSummariser:
    """llama.cpp behind a narrow, task-specific interface.

    Falls back to `ExtractiveSummariser` whenever the model cannot be loaded, so the pipeline never
    stops because a download has not finished. The caller is told which path ran via
    `DocumentProfile.used_model`, because a user deserves to know whether a summary came from a
    model or from sentence ranking.
    """

    name = "summary"

    def __init__(self, model_path: str | None = None, context_size: int = 4096) -> None:
        self._model_path = model_path
        self._context_size = context_size
        self._model: Any | None = None
        self._unavailable: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @staticmethod
    def runtime_available() -> bool:
        try:
            import llama_cpp  # noqa: F401
        except Exception:
            return False
        return True

    def resolved_path(self) -> Path | None:
        """Looks where the installer and the model download both place GGUF files."""
        if self._model_path is not None:
            candidate = Path(self._model_path)
            return candidate if candidate.exists() else None

        import os

        roots = [
            Path(os.environ.get("HAWKVANCE_MODEL_DIR", "")),
            Path(os.environ.get("LOCALAPPDATA", "")) / "HawkVance" / "models",
            Path.home() / ".hawkvance" / "models",
            Path("models"),
        ]
        for root in roots:
            if not root or not root.exists():
                continue
            for found in sorted(root.glob("*.gguf")):
                return found
        return None

    def load(self) -> None:
        if self._model is not None:
            return
        if not self.runtime_available():
            raise SummariserUnavailable("llama-cpp-python is not installed")

        path = self.resolved_path()
        if path is None:
            raise SummariserUnavailable("no GGUF model file was found")

        from llama_cpp import Llama

        self._model = Llama(
            model_path=str(path),
            n_ctx=self._context_size,
            n_threads=None,
            verbose=False,
        )

    def release(self) -> None:
        self._model = None

    def estimated_memory_bytes(self) -> int:
        return 1_400 * 1024 * 1024

    def _complete(self, prompt: str, max_tokens: int) -> str:
        """Goes through the chat API so the model's own template is applied.

        Raw completion against an instruct-tuned model produces malformed, rambling output; the
        template is what makes a 1.5B model follow a format instruction at all.
        """
        self.load()
        model = self._model
        if model is None:  # pragma: no cover - load() raises first
            raise SummariserUnavailable("model did not initialise")

        result = model.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise extraction function. Follow the output format "
                    "exactly. Never add commentary.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return str(result["choices"][0]["message"]["content"]).strip()

    def profile(self, text: str, sentences: int = 3) -> DocumentProfile:
        """The whole of what the local model is used for on a document."""
        trimmed = text[:6000]
        if not trimmed.strip():
            return DocumentProfile("", "other", (), used_model=False)

        try:
            summary = self._complete(
                _SUMMARY_PROMPT.format(sentences=sentences, text=trimmed), max_tokens=320
            )
            category = self._complete(_CLASSIFY_PROMPT.format(text=trimmed[:2000]), max_tokens=8)
            facts_raw = self._complete(
                _FACTS_PROMPT.format(limit=6, text=trimmed), max_tokens=400
            )
            facts = self._parse_facts(facts_raw)
            if not facts:
                # The model answered but not usefully. Sentence ranking is better than nothing,
                # and better than presenting its malformed output as facts.
                facts = ExtractiveSummariser.key_facts(trimmed)

            return DocumentProfile(
                summary=summary if summary else ExtractiveSummariser.summarise(trimmed, sentences),
                category=self._clean_category(category),
                key_facts=facts,
                used_model=True,
            )
        except (SummariserUnavailable, Exception) as cause:
            # Degrading is correct here. Refusing to summarise because a model is missing would
            # block the memory pipeline entirely, and the extractive path is genuinely useful.
            if isinstance(cause, SummariserUnavailable):
                self._unavailable = cause.detail
            return DocumentProfile(
                summary=ExtractiveSummariser.summarise(trimmed, sentences),
                category=ExtractiveSummariser.classify(trimmed),
                key_facts=ExtractiveSummariser.key_facts(trimmed),
                used_model=False,
            )

    @staticmethod
    def _clean_category(raw: str) -> str:
        word = re.sub(r"[^a-z]", "", raw.lower().split()[0]) if raw.split() else "other"
        return word if word in _CATEGORIES else "other"

    @staticmethod
    def _looks_like_a_fact(candidate: str) -> bool:
        """A fact is a sentence, not a fragment of the model failing to follow instructions.

        The subtlety here: a redaction placeholder like `[ORG_001]` is bracketed, so a naive
        "starts with [" rejection throws away exactly the facts that name the entities the user
        cares about. Placeholders are recognised and allowed; JSON structure is not.
        """
        text = candidate.strip()
        if len(text) < 25 or len(text) > 400:
            return False
        if text.startswith(("{", "JSON", "json")) or text.lower().count("null") > 0:
            return False
        # A leading bracket is fine if it is a placeholder, not the start of a JSON array.
        if text.startswith("[") and _PLACEHOLDER_AT_START.match(text) is None:
            return False
        # Quote-heavy text is a serialised structure, not prose.
        if text.count('"') > 4:
            return False
        return len(re.findall(r"[A-Za-z]{3,}", text)) >= 5

    @classmethod
    def _parse_facts(cls, raw: str) -> tuple[str, ...]:
        """Returns only what genuinely looks like extracted facts.

        Returning an empty tuple is a correct answer here. The caller falls back to extractive
        ranking, which is far better than presenting the model's malformed output as findings the
        user might rely on.
        """
        candidates: list[str] = []

        # Greedy, from the first bracket to the last, so a placeholder inside a fact cannot be
        # mistaken for the array itself. Non-greedy matching here silently ate every real answer.
        opening = raw.find("[")
        closing = raw.rfind("]")
        if opening != -1 and closing > opening:
            try:
                parsed = json.loads(raw[opening : closing + 1])
                if isinstance(parsed, list):
                    candidates = [item for item in parsed if isinstance(item, str)]
            except json.JSONDecodeError:
                candidates = []

        if not candidates:
            # A model that ignored the format still produced usable lines. Strip list markers, but
            # not the brackets of a placeholder that opens the sentence.
            candidates = [line.strip().lstrip("-*•").lstrip() for line in raw.splitlines()]
            candidates = [re.sub(r"^\d+[.)]\s*", "", line) for line in candidates]

        return tuple(item.strip() for item in candidates if cls._looks_like_a_fact(item))[:6]

    def memory_candidates(
        self,
        text: str,
        source: str,
        workspace_id: str | None = None,
        document_id: str | None = None,
    ) -> list[MemoryCandidate]:
        """Turns a document into candidate memories, per spec sections 24 and 39.

        Confidence is lower for a model-free extraction, honestly: sentence ranking finds important
        sentences, it does not understand them, and the difference should reach the user rather than
        being hidden behind a uniform score.
        """
        profile = self.profile(text)
        confidence = 0.82 if profile.used_model else 0.62
        scope = MemoryScope.FILE if document_id is not None else MemoryScope.WORKSPACE

        candidates: list[MemoryCandidate] = []
        if profile.summary:
            candidates.append(
                MemoryCandidate(
                    content=profile.summary,
                    scope=scope,
                    confidence=confidence,
                    source=source,
                    workspace_id=workspace_id,
                    document_id=document_id,
                )
            )
        for fact in profile.key_facts:
            candidates.append(
                MemoryCandidate(
                    content=fact,
                    scope=scope,
                    confidence=confidence - 0.05,
                    source=source,
                    workspace_id=workspace_id,
                    document_id=document_id,
                )
            )
        return candidates

    def snapshot(self) -> dict[str, object]:
        path = self.resolved_path()
        return {
            "runtimeAvailable": self.runtime_available(),
            "modelPath": str(path) if path else None,
            "loaded": self.is_loaded,
            "unavailableReason": self._unavailable,
        }
