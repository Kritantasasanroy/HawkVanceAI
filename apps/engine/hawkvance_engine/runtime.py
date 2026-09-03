"""Hardware detection, resource management and processing modes.

Spec sections 19, 20, 36, 42 and 44. The rule these serve: never crash because a model cannot fit
into memory. HawkVance degrades, it does not fail.
"""

from __future__ import annotations

import os
import platform
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

GIB = 1024 * 1024 * 1024


class SystemClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProcessingMode(str, Enum):
    LOW_RESOURCE = "lowResource"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    host_name: str
    os_version: str
    cpu_name: str
    physical_cores: int
    logical_cores: int
    total_memory_bytes: int
    available_memory_bytes: int
    free_disk_bytes: int
    gpu_name: str | None
    vram_bytes: int | None

    @property
    def system_class(self) -> SystemClass:
        """Chosen on total RAM, because that is what decides whether a quantised model fits
        alongside the rest of the user's work, not how fast the CPU is."""
        if self.total_memory_bytes < 8 * GIB or self.logical_cores < 4:
            return SystemClass.LOW
        if self.total_memory_bytes < 16 * GIB:
            return SystemClass.MEDIUM
        return SystemClass.HIGH

    @property
    def recommended_mode(self) -> ProcessingMode:
        return {
            SystemClass.LOW: ProcessingMode.LOW_RESOURCE,
            SystemClass.MEDIUM: ProcessingMode.BALANCED,
            SystemClass.HIGH: ProcessingMode.PERFORMANCE,
        }[self.system_class]

    @property
    def recommended_workers(self) -> int:
        """Spec section 36. Never overload a low-spec machine."""
        if self.system_class is SystemClass.LOW:
            return 1
        if self.system_class is SystemClass.MEDIUM:
            return 2
        return min(4, max(2, self.logical_cores // 2))

    @property
    def can_run_contextual_ner(self) -> bool:
        """GLiNER needs roughly 700 MB resident. Below 8 GB total it is not worth the swapping."""
        return self.total_memory_bytes >= 8 * GIB

    @property
    def has_gpu(self) -> bool:
        return self.gpu_name is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "hostName": self.host_name,
            "osVersion": self.os_version,
            "cpuName": self.cpu_name,
            "physicalCores": self.physical_cores,
            "logicalCores": self.logical_cores,
            "totalMemoryBytes": self.total_memory_bytes,
            "availableMemoryBytes": self.available_memory_bytes,
            "freeDiskBytes": self.free_disk_bytes,
            "gpuName": self.gpu_name,
            "vramBytes": self.vram_bytes,
            "systemClass": self.system_class.value,
            "recommendedMode": self.recommended_mode.value,
            "recommendedWorkers": self.recommended_workers,
            "canRunContextualNer": self.can_run_contextual_ner,
            "hasGpu": self.has_gpu,
        }


class HardwareDetector:
    """Reads the machine once, on demand. Never a hard dependency on CUDA."""

    @staticmethod
    def detect() -> HardwareProfile:
        import psutil

        memory = psutil.virtual_memory()
        gpu_name, vram = HardwareDetector._gpu()

        return HardwareProfile(
            host_name=platform.node() or "This PC",
            os_version=f"{platform.system()} {platform.release()}",
            cpu_name=platform.processor() or "Unknown CPU",
            physical_cores=psutil.cpu_count(logical=False) or os.cpu_count() or 1,
            logical_cores=psutil.cpu_count(logical=True) or os.cpu_count() or 1,
            total_memory_bytes=memory.total,
            available_memory_bytes=memory.available,
            free_disk_bytes=shutil.disk_usage(os.path.expanduser("~")).free,
            gpu_name=gpu_name,
            vram_bytes=vram,
        )

    @staticmethod
    def _gpu() -> tuple[str | None, int | None]:
        """GPU is an optional accelerator, never a requirement.

        Detection failing for any reason means "no GPU", which is a correct and safe answer, so this
        is one of the few places a broad exception is the right behaviour rather than a hidden bug.
        """
        try:
            import torch
        except Exception:
            return None, None

        try:
            if torch.cuda.is_available():
                properties = torch.cuda.get_device_properties(0)
                return properties.name, properties.total_memory
        except Exception:
            return None, None
        return None, None


class ResourceManager:
    """Watches memory and decides whether another model may be loaded.

    Spec section 42: if RAM becomes critically low, stop new model loads, reduce workers, unload
    inactive models, pause background work.
    """

    WARNING_AVAILABLE_RATIO = 0.20
    CRITICAL_AVAILABLE_RATIO = 0.10
    HEADROOM_BYTES = 512 * 1024 * 1024

    def __init__(
        self,
        profile: HardwareProfile | None = None,
        read_available: Callable[[], int] | None = None,
    ) -> None:
        """`read_available` is the seam that makes pressure testable.

        Production reads live memory, because a profile captured at start-up says nothing about
        what is free thirty minutes later. Tests supply a fixed reading so a low-memory refusal can
        be exercised without actually exhausting the machine.
        """
        self._profile = profile or HardwareDetector.detect()
        self._read_available = read_available or self._read_live

    @property
    def profile(self) -> HardwareProfile:
        return self._profile

    @staticmethod
    def _read_live() -> int:
        import psutil

        return psutil.virtual_memory().available

    def available_bytes(self) -> int:
        return self._read_available()

    @property
    def available_ratio(self) -> float:
        total = self._profile.total_memory_bytes
        return self.available_bytes() / total if total else 0.0

    @property
    def is_under_pressure(self) -> bool:
        return self.available_ratio < self.WARNING_AVAILABLE_RATIO

    @property
    def is_critical(self) -> bool:
        return self.available_ratio < self.CRITICAL_AVAILABLE_RATIO

    def can_load(self, estimated_bytes: int) -> bool:
        """Refuses a load that would leave the machine with no headroom.

        Returning False here is what turns "HawkVance crashed" into "HawkVance ran the cheaper
        detector", which is the whole point of the low-resource requirement.
        """
        if self.is_critical:
            return False
        return self.available_bytes() - estimated_bytes > self.HEADROOM_BYTES

    def worker_count(self, mode: ProcessingMode | None = None) -> int:
        chosen = mode or self._profile.recommended_mode
        if chosen is ProcessingMode.LOW_RESOURCE:
            return 1
        if chosen is ProcessingMode.BALANCED:
            return min(2, self._profile.recommended_workers)
        return self._profile.recommended_workers

    def snapshot(self) -> dict[str, object]:
        """Privacy-safe by construction: numbers about the machine, nothing about the user."""
        return {
            "availableMemoryBytes": self.available_bytes(),
            "totalMemoryBytes": self._profile.total_memory_bytes,
            "availableRatio": round(self.available_ratio, 4),
            "underPressure": self.is_under_pressure,
            "critical": self.is_critical,
            "systemClass": self._profile.system_class.value,
        }
