"""Privacy-safe logging: spec section 41.

Logs record what happened, never what it was about. There is deliberately no way to pass free text
through this module: every field is a named, typed, non-content value. If you find yourself wanting
to log a document's text to debug something, that is the module working as intended.
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import TextIO

# Anything matching these must never appear in a log line. The scrubber is a backstop, not the
# primary defence: the primary defence is that no logging call accepts content in the first place.
_FORBIDDEN = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bey[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://\S+"),
    re.compile(r"\b(?:\d[ \-]?){12,18}\d\b"),
)


class LogStream(str, Enum):
    """Separate streams, per spec section 55."""

    APPLICATION = "application"
    SECURITY = "security"
    PRIVACY = "privacy"
    AI_USAGE = "aiUsage"
    ERROR = "error"


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PrivacyLogger:
    """Structured, scrubbed, and pointed at stderr so stdout stays a clean protocol channel."""

    stream: LogStream
    destination: TextIO = sys.stderr

    @staticmethod
    def scrub(value: str) -> str:
        scrubbed = value
        for pattern in _FORBIDDEN:
            scrubbed = pattern.sub("[redacted]", scrubbed)
        return scrubbed

    def write(self, level: LogLevel, event: str, **fields: object) -> None:
        record: dict[str, object] = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "stream": self.stream.value,
            "level": level.value,
            "event": event,
        }
        for key, value in fields.items():
            record[key] = self.scrub(value) if isinstance(value, str) else value

        self.destination.write(json.dumps(record, default=str) + "\n")
        self.destination.flush()

    def info(self, event: str, **fields: object) -> None:
        self.write(LogLevel.INFO, event, **fields)

    def warn(self, event: str, **fields: object) -> None:
        self.write(LogLevel.WARN, event, **fields)

    def error(self, event: str, **fields: object) -> None:
        self.write(LogLevel.ERROR, event, **fields)

    def document_processed(
        self,
        *,
        document_hash: str,
        operation: str,
        duration_ms: int,
        detector: str,
        entities_detected: int,
        model: str,
        succeeded: bool,
    ) -> None:
        """The exact field list spec section 41 permits, and nothing else.

        Note what is not a parameter: filename, text, entity values, placeholder mappings.
        """
        self.write(
            LogLevel.INFO if succeeded else LogLevel.ERROR,
            "document.processed",
            documentHash=document_hash[:16],
            operation=operation,
            durationMs=duration_ms,
            detector=detector,
            entitiesDetected=entities_detected,
            model=model,
            succeeded=succeeded,
        )
