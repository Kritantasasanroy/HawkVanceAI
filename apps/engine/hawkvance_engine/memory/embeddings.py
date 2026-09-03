"""Embeddings, with a fallback that means retrieval works before any model is downloaded.

Spec section 35 says not to generate embeddings until semantic retrieval is required, and section 19
says never to crash because a model will not fit. Both point at the same design: the real encoder is
optional and lazily loaded, and something useful runs without it.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any, Protocol

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenise(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return round(dot / (left_norm * right_norm), 6)


class Encoder(Protocol):
    name: str
    dimensions: int

    def encode(self, text: str) -> tuple[float, ...]: ...


class HashingEncoder:
    """Deterministic bag-of-words hashing into a fixed vector.

    This is not a semantic model and does not pretend to be: it captures lexical overlap only, so
    "car" and "automobile" score zero against each other. It exists so that memory search, the
    consolidation job and the whole retrieval path are exercisable and useful on a fresh install
    with nothing downloaded, and so a 4 GB machine has a path that always works.
    """

    name = "hashing"
    dimensions = 384

    def encode(self, text: str) -> tuple[float, ...]:
        tokens = tokenise(text)
        if not tokens:
            return tuple([0.0] * self.dimensions)

        counts = Counter(tokens)
        vector = [0.0] * self.dimensions
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            # Sub-linear term weighting, so one repeated word cannot dominate the vector.
            vector[index] += sign * (1.0 + math.log(count))

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0.0:
            return tuple(vector)
        return tuple(round(value / magnitude, 6) for value in vector)


class OnnxEncoder:
    """A real sentence encoder, loaded only when semantic retrieval is actually asked for.

    Falls back rather than failing: if the model is not present and cannot be fetched, the caller
    gets the hashing encoder and a note saying retrieval is lexical for now.
    """

    name = "bge-small-en-v1.5"
    dimensions = 384

    def __init__(self, model_id: str = "BAAI/bge-small-en-v1.5") -> None:
        self._model_id = model_id
        self._session: Any | None = None
        self._tokeniser: Any | None = None

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    @staticmethod
    def is_available() -> bool:
        try:
            import onnxruntime  # noqa: F401
            import tokenizers  # noqa: F401
        except Exception:
            return False
        return True

    def load(self) -> None:
        if self._session is not None:
            return

        import onnxruntime
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        model_path = hf_hub_download(self._model_id, "onnx/model.onnx")
        tokeniser_path = hf_hub_download(self._model_id, "tokenizer.json")

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

        self._session = onnxruntime.InferenceSession(
            model_path, options, providers=["CPUExecutionProvider"]
        )
        self._tokeniser = Tokenizer.from_file(tokeniser_path)
        self._tokeniser.enable_truncation(max_length=512)

    def release(self) -> None:
        self._session = None
        self._tokeniser = None

    def encode(self, text: str) -> tuple[float, ...]:
        self.load()
        session = self._session
        tokeniser = self._tokeniser
        if session is None or tokeniser is None:  # pragma: no cover - load() raises first
            raise RuntimeError("the encoder did not initialise")

        encoded = tokeniser.encode(text)
        inputs = {
            "input_ids": [encoded.ids],
            "attention_mask": [encoded.attention_mask],
        }
        if any(node.name == "token_type_ids" for node in session.get_inputs()):
            inputs["token_type_ids"] = [encoded.type_ids]

        import numpy

        outputs = session.run(
            None, {name: numpy.array(value, dtype=numpy.int64) for name, value in inputs.items()}
        )
        # CLS pooling, then L2 normalisation, which is what this model family expects.
        vector = outputs[0][0][0]
        magnitude = float(numpy.linalg.norm(vector))
        if magnitude == 0.0:
            return tuple(float(value) for value in vector)
        return tuple(round(float(value) / magnitude, 6) for value in vector)


class EmbeddingProvider:
    """Chooses an encoder and remembers which one produced a vector.

    Mixing vectors from two encoders in one index produces silently meaningless similarity scores,
    so the encoder name is stored alongside every vector and a mismatch forces a re-encode rather
    than a wrong answer.
    """

    def __init__(self, prefer_semantic: bool = True) -> None:
        self._fallback = HashingEncoder()
        self._semantic = OnnxEncoder() if prefer_semantic and OnnxEncoder.is_available() else None
        self._active: Encoder = self._fallback
        self._degraded: str | None = None

    @property
    def name(self) -> str:
        return self._active.name

    @property
    def is_semantic(self) -> bool:
        return self._active is not self._fallback

    @property
    def degraded_reason(self) -> str | None:
        return self._degraded

    def prepare(self) -> None:
        """Promotes to the semantic encoder if it can actually be loaded.

        Called the first time semantic retrieval is needed, never at start-up.
        """
        if self._semantic is None or self.is_semantic:
            return
        try:
            self._semantic.load()
            self._active = self._semantic
            self._degraded = None
        except Exception as cause:
            self._degraded = (
                "Semantic search is using lexical matching for now: the embedding model is not "
                f"available ({type(cause).__name__})."
            )

    def encode(self, text: str) -> tuple[float, ...]:
        return self._active.encode(text)

    def release(self) -> list[str]:
        released: list[str] = []
        if self._semantic is not None and self._semantic.is_loaded:
            self._semantic.release()
            released.append("embedding")
        self._active = self._fallback
        return released

    def snapshot(self) -> dict[str, object]:
        return {
            "encoder": self.name,
            "semantic": self.is_semantic,
            "dimensions": self._active.dimensions,
            "degraded": self._degraded,
        }
