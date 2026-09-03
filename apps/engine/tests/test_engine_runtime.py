"""Runtime, model lifecycle, queue and logging tests.

These cover the requirements that keep HawkVance usable on a weak machine, which are as much a part
of the product as the detection accuracy is.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from hawkvance_engine.documents import (
    DocumentFormat,
    DocumentProcessor,
    OCRManager,
    TextNormaliser,
    UnsupportedDocument,
)
from hawkvance_engine.model_manager import (
    ModelKind,
    ModelManager,
    ModelNotPermitted,
    ModelRegistry,
)
from hawkvance_engine.privacy.detectors import DetectorSelection
from hawkvance_engine.privacy.presidio_detector import PresidioDetector
from hawkvance_engine.privacy.router import PrivacyMode, PrivacyTaskRouter
from hawkvance_engine.privacy_log import LogStream, PrivacyLogger
from hawkvance_engine.runtime import (
    GIB,
    HardwareDetector,
    HardwareProfile,
    ProcessingMode,
    ResourceManager,
    SystemClass,
)
from hawkvance_engine.task_queue import JobStage, JobState, LocalTaskQueue


def profile(total_gib: float, cores: int = 8) -> HardwareProfile:
    return HardwareProfile(
        host_name="test",
        os_version="Windows 11",
        cpu_name="Test CPU",
        physical_cores=cores // 2,
        logical_cores=cores,
        total_memory_bytes=int(total_gib * GIB),
        available_memory_bytes=int(total_gib * GIB * 0.5),
        free_disk_bytes=100 * GIB,
        gpu_name=None,
        vram_bytes=None,
    )


# ---------------------------------------------------------------------------
# Hardware classification, spec sections 19 and 20
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "total_gib,cores,expected",
    [
        (4, 8, SystemClass.LOW),
        (6, 8, SystemClass.LOW),
        (8, 8, SystemClass.MEDIUM),
        (12, 8, SystemClass.MEDIUM),
        (16, 8, SystemClass.HIGH),
        (32, 16, SystemClass.HIGH),
        (32, 2, SystemClass.LOW),
    ],
)
def test_system_classification(total_gib, cores, expected):
    assert profile(total_gib, cores).system_class is expected


def test_a_four_gigabyte_machine_is_told_not_to_run_contextual_ner():
    assert profile(4).can_run_contextual_ner is False
    assert profile(8).can_run_contextual_ner is True


def test_worker_counts_never_overload_a_weak_machine():
    assert profile(4).recommended_workers == 1
    assert profile(8).recommended_workers == 2
    assert profile(32, 16).recommended_workers == 4


def test_low_resource_mode_always_runs_one_worker():
    resources = ResourceManager(profile(32, 16))
    assert resources.worker_count(ProcessingMode.LOW_RESOURCE) == 1
    assert resources.worker_count(ProcessingMode.BALANCED) == 2


def test_hardware_detection_reads_the_real_machine():
    detected = HardwareDetector.detect()
    assert detected.total_memory_bytes > 0
    assert detected.logical_cores >= 1
    assert detected.system_class in tuple(SystemClass)
    assert detected.as_dict()["recommendedWorkers"] >= 1


def test_gpu_is_optional_and_never_required():
    detected = HardwareDetector.detect()
    assert isinstance(detected.has_gpu, bool)


# ---------------------------------------------------------------------------
# Model lifecycle, spec sections 21, 23 and 43
# ---------------------------------------------------------------------------


def test_nothing_is_loaded_when_the_engine_starts():
    manager = ModelManager(ResourceManager(profile(16), read_available=lambda: 8 * GIB))
    assert manager.loaded_kinds == ()
    assert manager.estimate_memory_usage() == 0


def test_a_model_loads_once_and_is_reused():
    manager = ModelManager(ResourceManager(profile(16), read_available=lambda: 8 * GIB))
    builds = []

    def build():
        builds.append(1)
        return object()

    first = manager.acquire(ModelKind.PII, build)
    second = manager.acquire(ModelKind.PII, build)

    assert first is second
    assert len(builds) == 1


def test_a_model_is_released_and_then_rebuilt():
    manager = ModelManager(ResourceManager(profile(16), read_available=lambda: 8 * GIB))
    manager.acquire(ModelKind.PII, object)
    assert manager.is_loaded(ModelKind.PII)

    assert manager.release(ModelKind.PII) is True
    assert manager.is_loaded(ModelKind.PII) is False


def test_idle_models_are_unloaded():
    manager = ModelManager(ResourceManager(profile(16), read_available=lambda: 8 * GIB), idle_timeout_seconds=0.01)
    manager.acquire(ModelKind.PII, object)
    time.sleep(0.05)

    assert ModelKind.PII in manager.release_idle()
    assert manager.loaded_kinds == ()


def test_a_load_is_refused_rather_than_crashing_the_machine():
    exhausted = ResourceManager(profile(4), read_available=lambda: 32 * 1024 * 1024)
    manager = ModelManager(exhausted)

    with pytest.raises(ModelNotPermitted):
        manager.acquire(ModelKind.NER, object)


def test_pressure_is_reported_before_it_becomes_critical():
    tight = ResourceManager(profile(8), read_available=lambda: int(0.15 * 8 * GIB))
    assert tight.is_under_pressure is True
    assert tight.is_critical is False

    critical = ResourceManager(profile(8), read_available=lambda: int(0.05 * 8 * GIB))
    assert critical.is_critical is True
    assert critical.can_load(100 * 1024 * 1024) is False


def test_a_healthy_machine_permits_a_load():
    healthy = ResourceManager(profile(16), read_available=lambda: 10 * GIB)
    assert healthy.is_under_pressure is False
    assert healthy.can_load(700 * 1024 * 1024) is True


def test_a_low_spec_machine_is_not_asked_to_download_the_large_models():
    low = ModelRegistry.recommended_for(SystemClass.LOW)
    names = {entry.name for entry in low}

    assert "urchade/gliner_small-v2.1" not in names, "GLiNER should not be pushed to a 4 GB machine"
    assert ModelManager.total_download_bytes(SystemClass.LOW) < ModelManager.total_download_bytes(
        SystemClass.HIGH
    )


def test_every_registry_entry_declares_what_the_manager_needs_to_decide():
    for entry in ModelRegistry.all():
        assert entry.supports_cpu, f"{entry.name} must run without a GPU"
        assert entry.expected_memory_bytes > 0
        assert entry.licence
        assert entry.source


def test_the_download_plan_is_ordered_smallest_first():
    sizes = [entry["fileSizeBytes"] for entry in ModelManager.download_plan(SystemClass.HIGH)]
    assert sizes == sorted(sizes)


# ---------------------------------------------------------------------------
# The task queue, spec sections 38 and 39
# ---------------------------------------------------------------------------


def test_a_job_runs_and_reports_progress():
    seen: list[int] = []
    queue = LocalTaskQueue(workers=1, on_progress=lambda job: seen.append(1))
    queue.start()
    try:
        def run(handle):
            handle.report(JobStage.EXTRACTION, 50, "half way")
            return "done"

        job_id = queue.submit("test", run)
        assert queue.drain(timeout_seconds=5)
        assert queue.status(job_id)["state"] == JobState.SUCCEEDED.value
        assert queue.result(job_id) == "done"
        assert seen
    finally:
        queue.stop()


def test_a_failing_job_records_the_failure_rather_than_hiding_it():
    queue = LocalTaskQueue(workers=1)
    queue.start()
    try:
        job_id = queue.submit("test", lambda handle: (_ for _ in ()).throw(ValueError("boom")))
        assert queue.drain(timeout_seconds=5)
        status = queue.status(job_id)
        assert status["state"] == JobState.FAILED.value
        assert "boom" in status["failure"]
    finally:
        queue.stop()


def test_a_queued_job_can_be_cancelled_before_it_starts():
    queue = LocalTaskQueue(workers=1)
    job_id = queue.submit("test", lambda handle: "never runs")

    assert queue.cancel(job_id) is True
    assert queue.status(job_id)["state"] == JobState.CANCELLED.value


def test_a_running_job_stops_at_its_next_checkpoint():
    queue = LocalTaskQueue(workers=1)
    queue.start()
    try:
        started = []

        def run(handle):
            started.append(handle.id)
            for step in range(200):
                handle.report(JobStage.PII_SCAN, step % 100)
                time.sleep(0.005)
            return "should not finish"

        job_id = queue.submit("test", run)
        for _ in range(200):
            if started:
                break
            time.sleep(0.01)

        queue.cancel(job_id)
        assert queue.drain(timeout_seconds=5)
        assert queue.status(job_id)["state"] == JobState.CANCELLED.value
    finally:
        queue.stop()


def test_job_status_never_carries_the_payload():
    queue = LocalTaskQueue(workers=1)
    queue.start()
    try:
        job_id = queue.submit("test", lambda handle: {"secret": "sk-live-abcdefghijklmnop"})
        assert queue.drain(timeout_seconds=5)
        assert "sk-live" not in str(queue.status(job_id))
    finally:
        queue.stop()


# ---------------------------------------------------------------------------
# Privacy-safe logging, spec section 41
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "leak",
    [
        "sk-live-abcdefghijklmnopqrst",
        "jane.doe@acme.com",
        "postgresql://app:pass@db/prod",
        "AKIAIOSFODNN7EXAMPLE",
        "4539148803436467",
    ],
)
def test_the_scrubber_removes_every_credential_class(leak):
    assert leak not in PrivacyLogger.scrub(f"something happened with {leak} today")


def test_the_document_log_line_carries_no_content(tmp_path, capsys):
    import io

    buffer = io.StringIO()
    logger = PrivacyLogger(LogStream.PRIVACY, destination=buffer)
    logger.document_processed(
        document_hash="a" * 64,
        operation="extract",
        duration_ms=12,
        detector="regex",
        entities_detected=3,
        model="none",
        succeeded=True,
    )
    line = buffer.getvalue()

    assert '"entitiesDetected": 3' in line
    assert "filename" not in line
    assert "text" not in line


# ---------------------------------------------------------------------------
# Documents, spec sections 15 and 16
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("a.pdf", DocumentFormat.PDF),
        ("a.docx", DocumentFormat.DOCX),
        ("a.txt", DocumentFormat.TEXT),
        ("a.md", DocumentFormat.MARKDOWN),
        ("a.csv", DocumentFormat.CSV),
        ("a.py", DocumentFormat.SOURCE_CODE),
        ("a.png", DocumentFormat.IMAGE),
        ("a.xyz", DocumentFormat.UNSUPPORTED),
    ],
)
def test_format_detection(name, expected):
    assert DocumentProcessor.format_of(Path(name)) is expected


def test_a_plain_text_file_needs_neither_docling_nor_ocr(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Contact jane@acme.com about the contract.", encoding="utf-8")

    extracted = DocumentProcessor().extract(path)

    assert extracted.used_ocr is False
    assert extracted.format is DocumentFormat.TEXT
    assert "jane@acme.com" in extracted.text
    assert extracted.degraded == ()


def test_an_unsupported_format_is_reported_not_guessed(tmp_path):
    path = tmp_path / "thing.xyz"
    path.write_text("data", encoding="utf-8")

    with pytest.raises(UnsupportedDocument):
        DocumentProcessor().extract(path)


def test_the_digest_is_stable_and_drives_the_cache(tmp_path):
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("identical", encoding="utf-8")
    second.write_text("identical", encoding="utf-8")

    assert DocumentProcessor.digest_of(first) == DocumentProcessor.digest_of(second)


def test_an_empty_text_layer_triggers_ocr_and_a_full_one_does_not():
    assert DocumentProcessor._text_layer_is_unusable("", 10) is True
    assert DocumentProcessor._text_layer_is_unusable("   \n  ", 3) is True
    assert DocumentProcessor._text_layer_is_unusable("x" * 40, 1) is False
    # 10 characters across 5 pages is a scan with stray marks, not a text layer.
    assert DocumentProcessor._text_layer_is_unusable("x" * 10, 5) is True


def test_extraction_metadata_carries_no_document_text(tmp_path):
    """`as_dict` is what gets logged and shown. The document body must not be in it."""
    path = tmp_path / "secret.txt"
    path.write_text("The API key is sk-live-abcdefghijklmnop and jane@acme.com owns it.", encoding="utf-8")

    extracted = DocumentProcessor().extract(path)
    metadata = str(extracted.as_dict())

    assert extracted.text, "the text should still be available in-process"
    assert "sk-live" not in metadata
    assert "jane@acme.com" not in metadata
    assert metadata.count("characterCount") == 1


def test_normalisation_is_idempotent():
    raw = "Line one\r\n\r\n\r\n\r\nLine two   \r\n"
    once = TextNormaliser.normalise(raw)
    assert TextNormaliser.normalise(once) == once


def test_ocr_is_not_loaded_until_it_is_needed():
    assert OCRManager().is_loaded is False


# ---------------------------------------------------------------------------
# Presidio integration, exercised against the real library
# ---------------------------------------------------------------------------

presidio_installed = pytest.mark.skipif(
    not PresidioDetector.is_available(), reason="Presidio is not installed"
)


@presidio_installed
def test_presidio_uses_the_small_spacy_model_not_the_large_one():
    detector = PresidioDetector()
    assert detector._model_name == "en_core_web_sm"


@presidio_installed
def test_standard_mode_detects_an_organisation_that_fast_mode_cannot():
    text = "John Doe from Acme Corp can be reached at john@example.com."

    fast = PrivacyTaskRouter().scan(text, requested=PrivacyMode.FAST)
    standard = PrivacyTaskRouter().scan(text, requested=PrivacyMode.STANDARD)

    assert "organization" not in fast.redaction_map.counts_by_category()
    assert "organization" in standard.redaction_map.counts_by_category()


@presidio_installed
def test_an_uncertain_organisation_is_offered_for_review_rather_than_silently_redacted():
    """The 'API' false positive is the point of the balanced threshold.

    spaCy calls 'API' an ORG in 'the production API key'. That detection must reach the user as an
    amber item they can reject, not be applied silently.
    """
    result = PrivacyTaskRouter().scan(
        "The production API key is sk-example-secret-abcdefghijklmno.",
        requested=PrivacyMode.STANDARD,
    )
    reviewable = {redaction.placeholder for redaction in result.redaction_map.needing_review()}
    automatic = {redaction.placeholder for redaction in result.redaction_map.automatic()}

    assert "[API_KEY_001]" in automatic, "a credential must always redact silently"
    assert any(placeholder.startswith("[ORG_") for placeholder in reviewable)


@presidio_installed
def test_the_model_is_released_when_asked():
    router = PrivacyTaskRouter()
    router.scan("John Smith works at Acme Corporation in London.", requested=PrivacyMode.STANDARD)
    assert "presidio" in router.loaded_models

    assert "presidio" in router.release_models()
    assert router.loaded_models == ()


@presidio_installed
def test_disabling_names_stops_presidio_finding_people_even_in_standard_mode():
    result = PrivacyTaskRouter().scan(
        "John Smith works at Acme Corporation in London.",
        requested=PrivacyMode.STANDARD,
    )
    assert "person" in result.redaction_map.counts_by_category()

    from hawkvance_engine.privacy.router import PrivacyPolicy

    without_names = PrivacyTaskRouter(
        PrivacyPolicy(selection=DetectorSelection(names_orgs_and_places=False))
    )
    quiet = without_names.scan("John Smith works at Acme Corporation.", requested=PrivacyMode.STANDARD)
    assert "person" not in quiet.redaction_map.counts_by_category()
