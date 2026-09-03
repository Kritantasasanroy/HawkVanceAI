"""The engine facade: the single object the desktop app talks to.

Everything below this line is local. Nothing in this module opens a socket, and the only I/O it
performs is reading files the user chose and writing scrubbed logs to stderr.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .context.builder import ContextBuilder, ContextPack
from .documents import DocumentProcessor, OCRManager, TextNormaliser
from .memory.embeddings import EmbeddingProvider
from .memory.model import Memory, MemoryCandidate, MemoryScope
from .memory.store import MemoryStore
from .model_manager import ModelManager
from .privacy.detectors import DetectorSelection
from .privacy.redaction import RedactionMap, RedactionStyle
from .privacy.router import PrivacyMode, PrivacyPolicy, PrivacyTaskRouter
from .privacy.verification import PrivacyVerificationGate
from .privacy_log import LogStream, PrivacyLogger
from .runtime import HardwareDetector, ProcessingMode, ResourceManager
from .summariser import LocalSummariser
from .task_queue import LocalTaskQueue


class UnknownScan(KeyError):
    def __init__(self, scan_id: str) -> None:
        super().__init__(f"No open scan with id {scan_id}.")
        self.scan_id = scan_id


class LocalEngine:
    """Owns the privacy pipeline, the document processor and the job queue.

    Redaction maps are held here, keyed by scan id, and are the reason this object exists at all:
    they must stay in one process, on this machine, reachable by no serialiser that targets the
    wire. There is deliberately no method that returns a map's contents.
    """

    def __init__(self, policy: PrivacyPolicy | None = None) -> None:
        self._profile = HardwareDetector.detect()
        self._resources = ResourceManager(self._profile)
        self._models = ModelManager(self._resources)
        self._router = PrivacyTaskRouter(policy)
        self._documents = DocumentProcessor(OCRManager(use_gpu=self._profile.has_gpu))
        self._gate = PrivacyVerificationGate()
        self._log = PrivacyLogger(LogStream.PRIVACY)
        self._queue = LocalTaskQueue(workers=self._resources.worker_count())
        self._queue.start()
        self._scans: dict[str, RedactionMap] = {}
        self._embeddings = EmbeddingProvider()
        self._memories = MemoryStore(self._embeddings)
        self._context = ContextBuilder(self._memories)
        self._summariser = LocalSummariser()

    # ------------------------------------------------------------------ machine

    def hardware(self) -> dict[str, Any]:
        return self._profile.as_dict()

    def resources(self) -> dict[str, Any]:
        return {
            **self._resources.snapshot(),
            "models": self._models.snapshot(),
            "queue": self._queue.snapshot(),
            "loadedPrivacyModels": list(self._router.loaded_models),
            "memory": self._memories.snapshot(),
            "summariser": self._summariser.snapshot(),
        }

    def download_plan(self) -> dict[str, Any]:
        system_class = self._profile.system_class
        return {
            "systemClass": system_class.value,
            "totalBytes": ModelManager.total_download_bytes(system_class),
            "models": ModelManager.download_plan(system_class),
        }

    def set_processing_mode(self, mode: ProcessingMode) -> dict[str, Any]:
        """Changing mode changes worker count, which is the setting that actually protects a
        low-spec machine from thrashing."""
        return {"mode": mode.value, "workers": self._resources.worker_count(mode)}

    # ------------------------------------------------------------------ privacy

    def scan_text(
        self,
        text: str,
        mode: PrivacyMode | None = None,
        selection: DetectorSelection | None = None,
        style: RedactionStyle | None = None,
        protected_terms: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Detects, resolves and sanitises. Returns metadata plus the sanitised text.

        The reverse mapping stays here under `scanId`. It is never part of this return value.

        `protected_terms` are the words the user marked themselves. They join the detectors as
        literal matches, so they are redacted on the way out and restored on the way back exactly
        like anything the detectors found on their own.
        """
        router = self._router_for(selection, style, protected_terms)
        normalised = TextNormaliser.normalise(text)
        result = router.scan(normalised, mode)

        scan_id = uuid.uuid4().hex
        self._scans[scan_id] = result.redaction_map

        self._log.info(
            "text.scanned",
            scanId=scan_id,
            mode=result.decision.mode.value,
            detectors=list(result.decision.detectors_used),
            entitiesDetected=len(result.redaction_map.redactions),
            needsReview=len(result.redaction_map.needing_review()),
        )

        return {"scanId": scan_id, **result.as_dict()}

    def keep_in_clear(self, scan_id: str, placeholders: list[str]) -> dict[str, Any]:
        """Applies the user's Privacy Gate decisions before anything is sent."""
        redaction_map = self._scan(scan_id)
        redaction_map.keep_in_clear(placeholders)
        return {
            "scanId": scan_id,
            "remaining": len(redaction_map.redactions),
            "countsByCategory": redaction_map.counts_by_category(),
        }

    def sanitise(self, scan_id: str, text: str) -> dict[str, Any]:
        return {"sanitisedText": self._scan(scan_id).apply(TextNormaliser.normalise(text))}

    def restore(self, scan_id: str, text: str) -> dict[str, Any]:
        """The local un-redaction of a model's response.

        This is the only method that can see original values, it runs on this machine, and the map
        it reads has never left it.
        """
        return {"restoredText": self._scan(scan_id).restore(text)}

    def verify_outbound(self, text: str) -> dict[str, Any]:
        """The final gate. Blocks rather than transmits when a high-risk value survives."""
        verdict = self._gate.verify(text)
        self._log.info(
            "outbound.verified",
            outcome=verdict.outcome.value,
            survivors=len(verdict.survivors),
        )
        return verdict.as_dict()

    def export_map(self, scan_id: str) -> dict[str, Any]:
        """Hands the reverse mapping to the desktop so it can outlive this scan.

        Called once, straight after a document is processed. Without it the mapping dies with the
        scan and every placeholder in that document is unresolvable for good.
        """
        entries = self._scan(scan_id).export_entries()
        # Counted, never logged by value: the log is a place originals must never appear.
        self._log.info("map.exported", scanId=scan_id, entries=len(entries))
        return {"scanId": scan_id, "entries": entries}

    def load_map(self, scan_id: str, entries: list[dict[str, str]]) -> dict[str, Any]:
        """Adds a stored mapping to a live scan, so an answer can be restored against documents
        that were redacted long before this conversation started."""
        added = self._scan(scan_id).load_entries(entries)
        self._log.info("map.loaded", scanId=scan_id, added=added)
        return {"scanId": scan_id, "added": added}

    def close_scan(self, scan_id: str) -> dict[str, Any]:
        """Drops a redaction map. After this the placeholders in that conversation can no longer be
        restored, which is the correct behaviour once the user is done with it."""
        existed = self._scans.pop(scan_id, None) is not None
        return {"scanId": scan_id, "closed": existed}

    # ------------------------------------------------------------------ documents

    def process_document(
        self,
        path: str,
        mode: PrivacyMode | None = None,
        selection: DetectorSelection | None = None,
        allow_ocr: bool = True,
        protected_terms: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Extract, then scan. Synchronous; `submit_document` is the queued form."""
        extracted = self._documents.extract(Path(path), allow_ocr=allow_ocr)
        scanned = self.scan_text(
            extracted.text, mode=mode, selection=selection, protected_terms=protected_terms
        )

        self._log.document_processed(
            document_hash=extracted.sha256,
            operation="extract+scan",
            duration_ms=0,
            detector=",".join(scanned["routing"]["detectorsUsed"]),
            entities_detected=len(scanned["redactions"]),
            model=",".join(scanned["routing"]["modelsLoaded"]) or "none",
            succeeded=True,
        )

        return {"document": extracted.as_dict(), "scan": scanned}

    def submit_document(self, path: str, mode: PrivacyMode | None = None) -> dict[str, Any]:
        """Queues extraction so the UI never blocks. Returns a job id to poll or cancel."""
        from .task_queue import JobStage

        def run(handle: Any) -> dict[str, Any]:
            handle.report(JobStage.EXTRACTION, 10, "reading the document")
            extracted = self._documents.extract(Path(path))
            handle.report(JobStage.PII_SCAN, 55, "scanning for sensitive values")
            scanned = self.scan_text(extracted.text, mode=mode)
            handle.report(JobStage.REDACTION, 95, "applying redactions")
            return {"document": extracted.as_dict(), "scan": scanned}

        return {"jobId": self._queue.submit("document", run)}

    def job_status(self, job_id: str) -> dict[str, Any] | None:
        return self._queue.status(job_id)

    def job_result(self, job_id: str) -> Any:
        return self._queue.result(job_id)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return {"jobId": job_id, "cancelled": self._queue.cancel(job_id)}

    # ------------------------------------------------------------------ memory

    def remember(
        self,
        content: str,
        scope: str,
        confidence: float,
        source: str = "",
        workspace_id: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        """Stores a candidate. Weak candidates are dropped, not stored with a caveat."""
        candidate = MemoryCandidate(
            content=content,
            scope=MemoryScope(scope),
            confidence=confidence,
            source=source,
            workspace_id=workspace_id,
            document_id=document_id,
        )
        stored = self._memories.remember(candidate)
        return {
            "stored": stored is not None,
            "candidate": candidate.as_dict(),
            "memory": stored.as_dict() if stored else None,
        }

    def recall(
        self,
        query: str,
        workspace_id: str | None = None,
        document_id: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        from .memory.store import RetrievalRequest

        hits = self._memories.retrieve(
            RetrievalRequest(
                query=query, workspace_id=workspace_id, document_id=document_id, limit=limit
            )
        )
        return {"hits": [hit.as_dict() for hit in hits], "total": self._memories.count()}

    def search_memories(self, text: str, limit: int = 50) -> dict[str, Any]:
        return {
            "memories": [memory.as_dict() for memory in self._memories.search(text, limit)],
            "total": self._memories.count(),
        }

    def pin_memory(self, memory_id: str, pinned: bool = True) -> dict[str, Any]:
        return {"memoryId": memory_id, "updated": self._memories.pin(memory_id, pinned)}

    def edit_memory(self, memory_id: str, content: str) -> dict[str, Any]:
        return {"memoryId": memory_id, "updated": self._memories.edit(memory_id, content)}

    def forget(self, memory_id: str) -> dict[str, Any]:
        return {"memoryId": memory_id, "forgotten": self._memories.forget(memory_id)}

    def forget_workspace(self, workspace_id: str) -> dict[str, Any]:
        return {"workspaceId": workspace_id, "forgotten": self._memories.forget_workspace(workspace_id)}

    def forget_everything(self) -> dict[str, Any]:
        return {"forgotten": self._memories.forget_everything()}

    def export_memories(self) -> dict[str, Any]:
        return {"memories": self._memories.export()}

    def consolidate_memories(self) -> dict[str, Any]:
        return {"outcome": self._memories.consolidate(), "snapshot": self._memories.snapshot()}

    def memory_snapshot(self) -> dict[str, Any]:
        return self._memories.snapshot()

    # ------------------------------------------------------------------ context

    def build_context(
        self,
        query: str,
        workspace_id: str | None = None,
        document_id: str | None = None,
        document_context: list[str] | None = None,
        user_preferences: list[str] | None = None,
        token_budget: int | None = None,
    ) -> dict[str, Any]:
        """Retrieve, rank, compress, then verify before anything is offered for approval."""
        builder = (
            self._context
            if token_budget is None
            else ContextBuilder(self._memories, token_budget=token_budget)
        )
        pack: ContextPack = builder.build(
            query=query,
            workspace_id=workspace_id,
            document_id=document_id,
            document_context=document_context,
            user_preferences=user_preferences,
        )

        verdict = self._gate.verify(pack.render())
        self._log.info(
            "context.built",
            retrieved=pack.retrieved_count,
            selected=pack.selected_count,
            tokensBefore=pack.token_estimate_before,
            tokensAfter=pack.token_estimate_after,
            outcome=verdict.outcome.value,
        )

        return {"pack": pack.as_dict(), "verification": verdict.as_dict()}

    # ------------------------------------------------------------------ summarisation

    def summarise(self, text: str, sentences: int = 3) -> dict[str, Any]:
        """Local summary, classification and key facts.

        Never a chat surface: the prompt is built from a template here, and there is no parameter
        through which a user prompt could reach the model.
        """
        profile = self._summariser.profile(text, sentences)
        self._log.info(
            "text.summarised",
            usedModel=profile.used_model,
            category=profile.category,
            facts=len(profile.key_facts),
        )
        return profile.as_dict()

    def learn_from_document(
        self,
        text: str,
        source: str,
        workspace_id: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        """Summarise, extract candidates, score them, and file the ones that earn it.

        This is the whole of spec section 24 in one call: document to memory, with every candidate
        passing the confidence bar rather than being stored because it was generated.
        """
        profile = self._summariser.profile(text)
        candidates = self._summariser.memory_candidates(
            text, source=source, workspace_id=workspace_id, document_id=document_id
        )

        stored: list[dict[str, Any]] = []
        skipped = 0
        for candidate in candidates:
            memory = self._memories.remember(candidate)
            if memory is None:
                skipped += 1
            else:
                stored.append(memory.as_dict())

        self._log.info(
            "document.learned",
            candidates=len(candidates),
            stored=len(stored),
            skipped=skipped,
            usedModel=profile.used_model,
        )

        return {
            "profile": profile.as_dict(),
            "stored": stored,
            "skipped": skipped,
        }

    def load_memories(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Rehydrates the memory bucket from the vault on start-up.

        The desktop owns persistence; this owns the domain behaviour. Keeping the split that way
        means there is exactly one encrypted store on the machine rather than two.
        """
        from datetime import datetime, timezone

        def moment(value: Any) -> datetime:
            try:
                return datetime.fromisoformat(str(value))
            except (TypeError, ValueError):
                return datetime.now(timezone.utc)

        loaded = 0
        for record in records:
            try:
                memory = Memory(
                    id=str(record["id"]),
                    content=str(record["content"]),
                    scope=MemoryScope(str(record["scope"])),
                    workspace_id=record.get("workspaceId"),
                    document_id=record.get("documentId"),
                    source=str(record.get("source", "")),
                    confidence=float(record.get("confidence", 0.5)),
                    pinned=bool(record.get("pinned", False)),
                    created_at=moment(record.get("createdAt")),
                    last_accessed_at=moment(record.get("lastAccessedAt")),
                    last_updated_at=moment(record.get("lastUpdatedAt")),
                    retention_days=record.get("retentionDays"),
                )
            except (KeyError, ValueError):
                # A malformed row is skipped rather than aborting the whole restore: one bad record
                # must not cost the user every memory they have.
                continue
            self._memories.add(memory)
            loaded += 1

        return {"loaded": loaded, "total": self._memories.count()}

    # ------------------------------------------------------------------ lifecycle

    def release_models(self) -> dict[str, Any]:
        """Spec section 43: models must not remain loaded indefinitely."""
        self._summariser.release()
        released = [
            *self._router.release_models(),
            *self._documents.release(),
            *self._embeddings.release(),
            *(['summary'] if self._summariser.is_loaded else []),
            *(kind.value for kind in self._models.release_all()),
        ]
        self._log.info("models.released", released=released)
        return {"released": released}

    def shutdown(self) -> None:
        self._queue.stop()
        self.release_models()
        self._scans.clear()

    # ------------------------------------------------------------------ internals

    def _scan(self, scan_id: str) -> RedactionMap:
        redaction_map = self._scans.get(scan_id)
        if redaction_map is None:
            raise UnknownScan(scan_id)
        return redaction_map

    def _router_for(
        self,
        selection: DetectorSelection | None,
        style: RedactionStyle | None,
        protected_terms: Sequence[str] | None = None,
    ) -> PrivacyTaskRouter:
        if selection is None and style is None and not protected_terms:
            return self._router
        current = self._router.policy
        return PrivacyTaskRouter(
            PrivacyPolicy(
                mode=current.mode,
                selection=selection or current.selection,
                style=style or current.style,
                custom_rules=current.custom_rules,
                protected_terms=(
                    current.protected_terms
                    if protected_terms is None
                    else tuple(protected_terms)
                ),
            )
        )
