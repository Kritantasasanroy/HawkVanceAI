"""Stdio JSON-lines server.

Deliberately not an HTTP server. A local port is an attack surface and something a firewall has to
be told about; a pipe to the parent process is neither. One JSON object per line in, one out.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from .engine import LocalEngine, UnknownScan
from .privacy.detectors import DetectorSelection
from .privacy.redaction import RedactionStyle
from .privacy.router import PrivacyMode
from .privacy_log import LogStream, PrivacyLogger
from .runtime import ProcessingMode


class StdioServer:
    """Reads requests from stdin, writes replies to stdout, logs to stderr.

    Keeping logs off stdout is what lets the protocol stay parseable no matter what any dependency
    decides to print.
    """

    def __init__(self) -> None:
        self._engine = LocalEngine()
        self._log = PrivacyLogger(LogStream.APPLICATION)

    def run(self) -> None:
        self._log.info("engine.ready", version="0.1.0")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            self._respond(line)
        self._engine.shutdown()

    def _respond(self, line: str) -> None:
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            result = self._dispatch(str(request.get("method", "")), request.get("params") or {})
            self._write({"id": request_id, "ok": True, "result": result})
        except UnknownScan as unknown:
            self._write({"id": request_id, "ok": False, "error": {
                "code": "unknown_scan", "message": str(unknown)}})
        except Exception as failure:
            self._log.error("request.failed", kind=type(failure).__name__)
            self._write({"id": request_id, "ok": False, "error": {
                "code": "engine_error",
                "message": f"{type(failure).__name__}: {failure}",
                "trace": traceback.format_exc(limit=3),
            }})

    def _write(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload, default=str) + "\n")
        sys.stdout.flush()

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        engine = self._engine

        if method == "ping":
            return {"pong": True}
        if method == "hardware.detect":
            return engine.hardware()
        if method == "resources.snapshot":
            return engine.resources()
        if method == "models.downloadPlan":
            return engine.download_plan()
        if method == "models.release":
            return engine.release_models()
        if method == "processing.setMode":
            return engine.set_processing_mode(ProcessingMode(params["mode"]))

        if method == "privacy.scanText":
            return engine.scan_text(
                params["text"],
                mode=PrivacyMode(params["mode"]) if params.get("mode") else None,
                selection=_selection(params.get("selection")),
                style=RedactionStyle(params["style"]) if params.get("style") else None,
                protected_terms=_terms(params.get("protectedTerms")),
            )
        if method == "privacy.keepInClear":
            return engine.keep_in_clear(params["scanId"], list(params.get("placeholders", [])))
        if method == "privacy.sanitise":
            return engine.sanitise(params["scanId"], params["text"])
        if method == "privacy.restore":
            return engine.restore(params["scanId"], params["text"])
        if method == "privacy.verifyOutbound":
            return engine.verify_outbound(params["text"])
        if method == "privacy.exportMap":
            return engine.export_map(params["scanId"])
        if method == "privacy.loadMap":
            return engine.load_map(params["scanId"], list(params.get("entries", [])))
        if method == "privacy.closeScan":
            return engine.close_scan(params["scanId"])

        if method == "document.process":
            return engine.process_document(
                params["path"],
                mode=PrivacyMode(params["mode"]) if params.get("mode") else None,
                selection=_selection(params.get("selection")),
                allow_ocr=bool(params.get("allowOcr", True)),
                protected_terms=_terms(params.get("protectedTerms")),
            )
        if method == "document.submit":
            return engine.submit_document(params["path"])
        if method == "job.status":
            return engine.job_status(params["jobId"])
        if method == "job.result":
            return engine.job_result(params["jobId"])
        if method == "job.cancel":
            return engine.cancel_job(params["jobId"])

        if method == "memory.remember":
            return engine.remember(
                params["content"],
                params["scope"],
                float(params.get("confidence", 0.6)),
                source=params.get("source", ""),
                workspace_id=params.get("workspaceId"),
                document_id=params.get("documentId"),
            )
        if method == "memory.recall":
            return engine.recall(
                params["query"],
                workspace_id=params.get("workspaceId"),
                document_id=params.get("documentId"),
                limit=int(params.get("limit", 12)),
            )
        if method == "memory.search":
            return engine.search_memories(params.get("text", ""), int(params.get("limit", 50)))
        if method == "memory.pin":
            return engine.pin_memory(params["memoryId"], bool(params.get("pinned", True)))
        if method == "memory.edit":
            return engine.edit_memory(params["memoryId"], params["content"])
        if method == "memory.forget":
            return engine.forget(params["memoryId"])
        if method == "memory.forgetWorkspace":
            return engine.forget_workspace(params["workspaceId"])
        if method == "memory.forgetEverything":
            return engine.forget_everything()
        if method == "memory.export":
            return engine.export_memories()
        if method == "memory.consolidate":
            return engine.consolidate_memories()
        if method == "memory.snapshot":
            return engine.memory_snapshot()

        if method == "summary.text":
            return engine.summarise(params["text"], int(params.get("sentences", 3)))
        if method == "summary.learnFromDocument":
            return engine.learn_from_document(
                params["text"],
                params.get("source", ""),
                workspace_id=params.get("workspaceId"),
                document_id=params.get("documentId"),
            )
        if method == "memory.load":
            return engine.load_memories(list(params.get("memories", [])))

        if method == "context.build":
            return engine.build_context(
                params["query"],
                workspace_id=params.get("workspaceId"),
                document_id=params.get("documentId"),
                document_context=params.get("documentContext"),
                user_preferences=params.get("userPreferences"),
                token_budget=params.get("tokenBudget"),
            )

        raise ValueError(f"Unknown method: {method}")


def _selection(raw: dict[str, Any] | None) -> DetectorSelection | None:
    if raw is None:
        return None
    return DetectorSelection(
        secrets_and_credentials=bool(raw.get("secretsAndCredentials", True)),
        direct_identifiers=bool(raw.get("directIdentifiers", True)),
        names_orgs_and_places=bool(raw.get("namesOrgsAndPlaces", True)),
        dates_addresses_and_money=bool(raw.get("datesAddressesAndMoney", True)),
        custom_rules=bool(raw.get("customRules", True)),
    )


def _terms(raw: Any) -> list[str] | None:
    """Words the user marked, taken as text and nothing else.

    Anything that is not a non-empty string is dropped rather than coerced: a stray null turning
    into the string "None" would silently redact that word everywhere it appeared.
    """
    if not isinstance(raw, list):
        return None
    cleaned = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    return cleaned or None


def main() -> None:
    StdioServer().run()


if __name__ == "__main__":
    main()
