"""The LocalTaskQueue: spec sections 36, 38 and 39.

Long local processing must never freeze the UI, must run a number of workers the machine can
actually sustain, and must be cancellable. Progress is reported per stage so the desktop can show
"PII scan 42%" rather than an indeterminate spinner.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from queue import Empty, Queue


class JobStage(str, Enum):
    EXTRACTION = "extraction"
    OCR = "ocr"
    PII_SCAN = "piiScan"
    REDACTION = "redaction"
    SUMMARY = "summary"
    MEMORY = "memory"
    EMBEDDING = "embedding"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED)


class JobCancelled(Exception):
    """Raised inside a worker when the job it is running has been cancelled.

    Distinct from a failure: a cancelled job is the user getting what they asked for, and must not
    be reported to them as an error.
    """


@dataclass(slots=True)
class JobProgress:
    stage: JobStage
    percent: int
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"stage": self.stage.value, "percent": self.percent, "note": self.note}


@dataclass(slots=True)
class Job:
    """One unit of local work. `payload` never leaves this process."""

    id: str
    kind: str
    run: Callable[["JobHandle"], object]
    state: JobState = JobState.QUEUED
    progress: JobProgress | None = None
    result: object | None = None
    failure: str | None = None
    queued_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    finished_at: float | None = None
    _cancelled: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def duration_ms(self) -> int | None:
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return int((end - self.started_at) * 1000)

    def as_dict(self) -> dict[str, object]:
        """Privacy-safe: identifiers, state and timing. Never the payload or the result."""
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state.value,
            "progress": self.progress.as_dict() if self.progress else None,
            "durationMs": self.duration_ms,
            "failure": self.failure,
        }


class JobHandle:
    """What a worker gets. Lets it report progress and check whether it should stop."""

    def __init__(self, job: Job, on_progress: Callable[[Job], None]) -> None:
        self._job = job
        self._on_progress = on_progress

    @property
    def id(self) -> str:
        return self._job.id

    def raise_if_cancelled(self) -> None:
        if self._job._cancelled.is_set():
            raise JobCancelled(self._job.id)

    def report(self, stage: JobStage, percent: int, note: str = "") -> None:
        self.raise_if_cancelled()
        self._job.progress = JobProgress(stage=stage, percent=max(0, min(100, percent)), note=note)
        self._on_progress(self._job)


class LocalTaskQueue:
    """A bounded worker pool sized by the machine, not by optimism.

    Cancellation is cooperative: a cancelled job stops at its next progress checkpoint, which is why
    every long stage reports progress rather than running opaquely to completion.
    """

    def __init__(
        self,
        workers: int = 1,
        on_progress: Callable[[Job], None] | None = None,
    ) -> None:
        self._worker_count = max(1, workers)
        self._queue: Queue[Job | None] = Queue()
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._on_progress = on_progress or (lambda _job: None)
        self._threads: list[threading.Thread] = []
        self._running = False

    @property
    def worker_count(self) -> int:
        return self._worker_count

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        for index in range(self._worker_count):
            thread = threading.Thread(
                target=self._work, name=f"hawkvance-worker-{index}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def submit(self, kind: str, run: Callable[[JobHandle], object]) -> str:
        job = Job(id=uuid.uuid4().hex, kind=kind, run=run)
        with self._lock:
            self._jobs[job.id] = job
        self._queue.put(job)
        return job.id

    def cancel(self, job_id: str) -> bool:
        """Stops queued work and signals a running job to stop at its next checkpoint."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state.is_terminal:
                return False
            job._cancelled.set()
            if job.state is JobState.QUEUED:
                job.state = JobState.CANCELLED
                job.finished_at = time.monotonic()
            return True

    def status(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.as_dict() if job else None

    def result(self, job_id: str) -> object | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.result if job and job.state is JobState.SUCCEEDED else None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            jobs: Iterable[Job] = tuple(self._jobs.values())
        pending = sum(1 for job in jobs if job.state is JobState.QUEUED)
        running = sum(1 for job in jobs if job.state is JobState.RUNNING)
        return {
            "workers": self._worker_count,
            "queued": pending,
            "running": running,
            "jobs": [job.as_dict() for job in jobs],
        }

    @property
    def is_idle(self) -> bool:
        with self._lock:
            return all(job.state.is_terminal for job in self._jobs.values())

    def drain(self, timeout_seconds: float = 30.0) -> bool:
        """Waits for the queue to empty. Used by tests and by shutdown."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.is_idle:
                return True
            time.sleep(0.01)
        return self.is_idle

    def stop(self) -> None:
        self._running = False
        for _ in self._threads:
            self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads.clear()

    def _work(self) -> None:
        while self._running:
            try:
                job = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if job is None:
                return
            self._run_one(job)

    def _run_one(self, job: Job) -> None:
        if job._cancelled.is_set():
            job.state = JobState.CANCELLED
            job.finished_at = time.monotonic()
            return

        job.state = JobState.RUNNING
        job.started_at = time.monotonic()
        try:
            job.result = job.run(JobHandle(job, self._on_progress))
            job.state = JobState.SUCCEEDED
        except JobCancelled:
            job.state = JobState.CANCELLED
        except Exception as failure:
            # The message is kept, the payload is not. A caller must be able to tell that something
            # failed, which is why this never silently swallows.
            job.state = JobState.FAILED
            job.failure = f"{type(failure).__name__}: {failure}"
        finally:
            job.finished_at = time.monotonic()
            self._on_progress(job)
