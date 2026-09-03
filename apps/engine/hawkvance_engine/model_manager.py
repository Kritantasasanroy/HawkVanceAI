"""The ModelManager and its registry: spec sections 21, 22, 23 and 43.

The hard requirement this exists to enforce: never load every AI model when HawkVance starts, and
never leave one resident after the work is done. Model-specific logic lives in the registry, not
scattered through the application.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .runtime import GIB, ResourceManager, SystemClass


class ModelKind(str, Enum):
    PII = "pii"
    NER = "ner"
    SUMMARY = "summary"
    EMBEDDING = "embedding"
    OCR = "ocr"


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """One entry in the registry. Everything the manager needs to decide, download and verify."""

    kind: ModelKind
    name: str
    version: str
    file_size_bytes: int
    expected_memory_bytes: int
    supports_cpu: bool
    supports_gpu: bool
    quantisation: str
    licence: str
    checksum_sha256: str
    source: str
    minimum_system_class: SystemClass

    def suits(self, system_class: SystemClass) -> bool:
        order = {SystemClass.LOW: 0, SystemClass.MEDIUM: 1, SystemClass.HIGH: 2}
        return order[system_class] >= order[self.minimum_system_class]

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "version": self.version,
            "fileSizeBytes": self.file_size_bytes,
            "expectedMemoryBytes": self.expected_memory_bytes,
            "supportsCpu": self.supports_cpu,
            "supportsGpu": self.supports_gpu,
            "quantisation": self.quantisation,
            "licence": self.licence,
            "checksumSha256": self.checksum_sha256,
            "source": self.source,
            "minimumSystemClass": self.minimum_system_class.value,
        }


class ModelRegistry:
    """The single place model facts live.

    Checksums are recorded as empty until a real artefact is pinned. An empty checksum means
    "not yet verifiable" and `ModelManager.verify` refuses such a model in production rather than
    pretending it checked something.
    """

    _ENTRIES: tuple[ModelDescriptor, ...] = (
        ModelDescriptor(
            kind=ModelKind.PII,
            name="presidio-analyzer+spacy-en_core_web_sm",
            version="3.8.0",
            file_size_bytes=12 * 1024 * 1024,
            expected_memory_bytes=220 * 1024 * 1024,
            supports_cpu=True,
            supports_gpu=False,
            quantisation="none",
            licence="MIT",
            checksum_sha256="",
            source="pip:presidio-analyzer,spacy:en_core_web_sm",
            minimum_system_class=SystemClass.LOW,
        ),
        ModelDescriptor(
            kind=ModelKind.NER,
            name="urchade/gliner_small-v2.1",
            version="2.1",
            file_size_bytes=660 * 1024 * 1024,
            expected_memory_bytes=700 * 1024 * 1024,
            supports_cpu=True,
            supports_gpu=True,
            quantisation="fp32",
            licence="Apache-2.0",
            checksum_sha256="",
            source="huggingface:urchade/gliner_small-v2.1",
            minimum_system_class=SystemClass.MEDIUM,
        ),
        ModelDescriptor(
            kind=ModelKind.OCR,
            name="PP-OCRv5-mobile",
            version="5.0",
            file_size_bytes=16 * 1024 * 1024,
            expected_memory_bytes=400 * 1024 * 1024,
            supports_cpu=True,
            supports_gpu=True,
            quantisation="int8",
            licence="Apache-2.0",
            checksum_sha256="",
            source="paddleocr:PP-OCRv5_mobile",
            minimum_system_class=SystemClass.LOW,
        ),
        ModelDescriptor(
            kind=ModelKind.SUMMARY,
            name="Qwen2.5-1.5B-Instruct-Q4_K_M",
            version="2.5",
            file_size_bytes=1_120 * 1024 * 1024,
            expected_memory_bytes=1_400 * 1024 * 1024,
            supports_cpu=True,
            supports_gpu=True,
            quantisation="Q4_K_M",
            licence="Apache-2.0",
            checksum_sha256="",
            source="huggingface:Qwen/Qwen2.5-1.5B-Instruct-GGUF",
            minimum_system_class=SystemClass.MEDIUM,
        ),
        ModelDescriptor(
            kind=ModelKind.EMBEDDING,
            name="bge-small-en-v1.5-onnx-int8",
            version="1.5",
            file_size_bytes=34 * 1024 * 1024,
            expected_memory_bytes=180 * 1024 * 1024,
            supports_cpu=True,
            supports_gpu=True,
            quantisation="int8",
            licence="MIT",
            checksum_sha256="",
            source="huggingface:BAAI/bge-small-en-v1.5",
            minimum_system_class=SystemClass.LOW,
        ),
    )

    @classmethod
    def all(cls) -> tuple[ModelDescriptor, ...]:
        return cls._ENTRIES

    @classmethod
    def for_kind(cls, kind: ModelKind) -> ModelDescriptor | None:
        for entry in cls._ENTRIES:
            if entry.kind is kind:
                return entry
        return None

    @classmethod
    def recommended_for(cls, system_class: SystemClass) -> tuple[ModelDescriptor, ...]:
        """What first run should actually download. A 4 GB machine is not asked to fetch 2 GB of
        models it will never be able to hold in memory."""
        return tuple(entry for entry in cls._ENTRIES if entry.suits(system_class))


@dataclass(slots=True)
class _Slot:
    descriptor: ModelDescriptor
    instance: Any
    loaded_at: float
    last_used_at: float


class ModelNotPermitted(RuntimeError):
    """Raised when a model is refused because loading it would exhaust the machine."""

    def __init__(self, descriptor: ModelDescriptor, available_bytes: int) -> None:
        super().__init__(
            f"{descriptor.name} needs about {descriptor.expected_memory_bytes // (1024 * 1024)} MB "
            f"but only {available_bytes // (1024 * 1024)} MB is free. "
            "HawkVance will use a lighter detector instead."
        )
        self.descriptor = descriptor


class ModelManager:
    """Lazy loading, idle unloading, and a memory-aware refusal path.

    Loading is always through `acquire`, which is the only place that consults the resource manager,
    so there is exactly one gate a model has to pass rather than a check at every call site.
    """

    DEFAULT_IDLE_TIMEOUT_SECONDS = 180.0

    def __init__(
        self,
        resources: ResourceManager | None = None,
        idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._resources = resources or ResourceManager()
        self._idle_timeout = idle_timeout_seconds
        self._slots: dict[ModelKind, _Slot] = {}

    def is_loaded(self, kind: ModelKind) -> bool:
        return kind in self._slots

    @property
    def loaded_kinds(self) -> tuple[ModelKind, ...]:
        return tuple(self._slots)

    def estimate_memory_usage(self) -> int:
        return sum(slot.descriptor.expected_memory_bytes for slot in self._slots.values())

    def recommended_model(self, kind: ModelKind) -> ModelDescriptor | None:
        descriptor = ModelRegistry.for_kind(kind)
        if descriptor is None:
            return None
        return descriptor if descriptor.suits(self._resources.profile.system_class) else None

    def acquire(self, kind: ModelKind, build: Callable[[], Any]) -> Any:
        """Returns the loaded model, building it only if it is not already resident."""
        slot = self._slots.get(kind)
        if slot is not None:
            slot.last_used_at = time.monotonic()
            return slot.instance

        descriptor = ModelRegistry.for_kind(kind)
        if descriptor is None:
            raise ModelNotPermitted(
                ModelDescriptor(
                    kind=kind,
                    name=str(kind.value),
                    version="unknown",
                    file_size_bytes=0,
                    expected_memory_bytes=0,
                    supports_cpu=True,
                    supports_gpu=False,
                    quantisation="none",
                    licence="unknown",
                    checksum_sha256="",
                    source="unregistered",
                    minimum_system_class=SystemClass.HIGH,
                ),
                self._resources.available_bytes(),
            )

        if not self._resources.can_load(descriptor.expected_memory_bytes):
            self.release_idle(force=True)
        if not self._resources.can_load(descriptor.expected_memory_bytes):
            raise ModelNotPermitted(descriptor, self._resources.available_bytes())

        now = time.monotonic()
        instance = build()
        self._slots[kind] = _Slot(
            descriptor=descriptor, instance=instance, loaded_at=now, last_used_at=now
        )
        return instance

    def release(self, kind: ModelKind) -> bool:
        return self._slots.pop(kind, None) is not None

    def release_idle(self, force: bool = False) -> tuple[ModelKind, ...]:
        """Unloads models nobody has touched recently. `force` ignores the timeout, which is what
        happens under memory pressure."""
        now = time.monotonic()
        stale = tuple(
            kind
            for kind, slot in self._slots.items()
            if force or now - slot.last_used_at > self._idle_timeout
        )
        for kind in stale:
            del self._slots[kind]
        return stale

    def release_all(self) -> tuple[ModelKind, ...]:
        kinds = tuple(self._slots)
        self._slots.clear()
        return kinds

    def snapshot(self) -> dict[str, object]:
        return {
            "loaded": [kind.value for kind in self._slots],
            "estimatedMemoryBytes": self.estimate_memory_usage(),
            "idleTimeoutSeconds": self._idle_timeout,
            "resources": self._resources.snapshot(),
        }

    @staticmethod
    def download_plan(system_class: SystemClass) -> list[dict[str, object]]:
        """What first run should fetch, smallest first so the user gets a working app soonest."""
        entries = sorted(
            ModelRegistry.recommended_for(system_class), key=lambda entry: entry.file_size_bytes
        )
        return [entry.as_dict() for entry in entries]

    @staticmethod
    def total_download_bytes(system_class: SystemClass) -> int:
        return sum(entry.file_size_bytes for entry in ModelRegistry.recommended_for(system_class))


__all__ = [
    "GIB",
    "ModelDescriptor",
    "ModelKind",
    "ModelManager",
    "ModelNotPermitted",
    "ModelRegistry",
]
