"""Deterministic detectors: the layer that needs no model at all.

Spec section 35: use the smallest component capable of the task. Finding an email address must
never load a language model, so everything here is pure pattern and arithmetic, runs first, and
runs in every privacy mode including FAST.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .detection import Confidence, Detection, DetectorGroup, DetectorKind, PiiCategory


@dataclass(frozen=True, slots=True)
class DetectorSelection:
    """Which groups the user left ticked in the confirmation step. All default to on."""

    secrets_and_credentials: bool = True
    direct_identifiers: bool = True
    names_orgs_and_places: bool = True
    dates_addresses_and_money: bool = True
    custom_rules: bool = True

    def includes(self, group: DetectorGroup) -> bool:
        return {
            DetectorGroup.SECRETS_AND_CREDENTIALS: self.secrets_and_credentials,
            DetectorGroup.DIRECT_IDENTIFIERS: self.direct_identifiers,
            DetectorGroup.NAMES_ORGS_AND_PLACES: self.names_orgs_and_places,
            DetectorGroup.DATES_ADDRESSES_AND_MONEY: self.dates_addresses_and_money,
            DetectorGroup.CUSTOM_RULES: self.custom_rules,
        }[group]

    @property
    def nothing_enabled(self) -> bool:
        return not any(
            (
                self.secrets_and_credentials,
                self.direct_identifiers,
                self.names_orgs_and_places,
                self.dates_addresses_and_money,
                self.custom_rules,
            )
        )


@dataclass(frozen=True, slots=True)
class _Pattern:
    category: PiiCategory
    confidence: float
    expression: re.Pattern[str]
    detector: DetectorKind


class SecretDetector:
    """Dedicated credential detection, per spec section 8.

    Generic PII detection does not find an OpenAI key or a Postgres URL, and a leaked credential is
    unrecoverable in a way a leaked name is not. This runs separately and at the highest priority.
    """

    _DEFINITIONS: tuple[tuple[PiiCategory, float, str], ...] = (
        (PiiCategory.PRIVATE_KEY, 0.99, r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        (PiiCategory.API_KEY, 0.99, r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_\-]{16,}"),
        (PiiCategory.API_KEY, 0.99, r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        (PiiCategory.API_KEY, 0.99, r"\bAKIA[0-9A-Z]{16}\b"),
        (PiiCategory.API_KEY, 0.98, r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        (PiiCategory.API_KEY, 0.97, r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
        (PiiCategory.API_KEY, 0.97, r"\bsk-ant-[A-Za-z0-9_\-]{16,}"),
        (PiiCategory.ACCESS_TOKEN, 0.98, r"\bey[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
        (PiiCategory.ACCESS_TOKEN, 0.96, r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"),
        (
            PiiCategory.CONNECTION_STRING,
            0.98,
            r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)://\S+",
        ),
        (PiiCategory.CREDENTIAL_IN_URL, 0.98, r"(?i)\bhttps?://[^\s/:@]+:[^\s/@]+@\S+"),
        (
            PiiCategory.PASSWORD,
            0.93,
            r"""(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token)\s*[:=]\s*["']?([^\s"',;]{6,})""",
        ),
    )

    def __init__(self) -> None:
        self._patterns = tuple(
            _Pattern(category, confidence, re.compile(source), DetectorKind.REGEX)
            for category, confidence, source in self._DEFINITIONS
        )

    def detect(self, text: str) -> list[Detection]:
        found: list[Detection] = []
        for pattern in self._patterns:
            for match in pattern.expression.finditer(text):
                found.append(
                    Detection(
                        start=match.start(),
                        end=match.end(),
                        category=pattern.category,
                        confidence=Confidence(pattern.confidence),
                        detector=pattern.detector,
                        original=match.group(0),
                    )
                )
        found.extend(HighEntropyDetector().detect(text))
        return found


class HighEntropyDetector:
    """Catches the credential no pattern anticipated.

    A long token whose characters are near-uniformly distributed is almost never prose. Deliberately
    scored into the needs-review band: entropy is a strong hint, never a certainty, so the user
    decides rather than the heuristic.
    """

    MIN_LENGTH = 24
    MIN_BITS_PER_CHARACTER = 4.0

    _CANDIDATE = re.compile(r"[A-Za-z0-9+/=_\-]{24,}")

    @staticmethod
    def shannon_bits_per_character(token: str) -> float:
        if not token:
            return 0.0
        counts = Counter(token)
        length = len(token)
        return -sum((count / length) * math.log2(count / length) for count in counts.values())

    @classmethod
    def looks_like_a_secret(cls, token: str) -> bool:
        has_digit = any(character.isdigit() for character in token)
        has_alpha = any(character.isalpha() for character in token)
        return (
            has_digit
            and has_alpha
            and cls.shannon_bits_per_character(token) >= cls.MIN_BITS_PER_CHARACTER
        )

    def detect(self, text: str) -> list[Detection]:
        return [
            Detection(
                start=match.start(),
                end=match.end(),
                category=PiiCategory.ACCESS_TOKEN,
                confidence=Confidence(0.72),
                detector=DetectorKind.ENTROPY,
                original=match.group(0),
            )
            for match in self._CANDIDATE.finditer(text)
            if self.looks_like_a_secret(match.group(0))
        ]


class CardNumberDetector:
    """A run of 13 to 19 digits is a card number only if it passes Luhn.

    Without the checksum this fires on invoice numbers, order ids and part numbers, which is exactly
    the false-positive class that makes users switch redaction off.
    """

    _CANDIDATE = re.compile(r"\b(?:\d[ \-]?){12,18}\d\b")

    @staticmethod
    def passes_luhn(digits: str) -> bool:
        total = 0
        double = False
        for character in reversed(digits):
            if not character.isdigit():
                return False
            value = int(character)
            if double:
                value *= 2
                if value > 9:
                    value -= 9
            total += value
            double = not double
        return total % 10 == 0

    def detect(self, text: str) -> list[Detection]:
        found: list[Detection] = []
        for match in self._CANDIDATE.finditer(text):
            digits = "".join(character for character in match.group(0) if character.isdigit())
            if 13 <= len(digits) <= 19 and self.passes_luhn(digits):
                found.append(
                    Detection(
                        start=match.start(),
                        end=match.end(),
                        category=PiiCategory.CREDIT_CARD,
                        confidence=Confidence(0.97),
                        detector=DetectorKind.CHECKSUM,
                        original=match.group(0),
                    )
                )
        return found


class AadhaarDetector:
    """Aadhaar is 12 digits with a Verhoeff check digit.

    Pattern alone collides with phone numbers and order ids across Indian documents, so the checksum
    is what makes this usable rather than noisy.
    """

    _CANDIDATE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")

    _D = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
        (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
        (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
        (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
        (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
        (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
        (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
        (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
        (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
    )
    _P = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
        (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
        (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
        (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
        (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
        (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
        (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
    )

    @classmethod
    def passes_verhoeff(cls, digits: str) -> bool:
        check = 0
        for position, character in enumerate(reversed(digits)):
            if not character.isdigit():
                return False
            check = cls._D[check][cls._P[position % 8][int(character)]]
        return check == 0

    def detect(self, text: str) -> list[Detection]:
        found: list[Detection] = []
        for match in self._CANDIDATE.finditer(text):
            digits = match.group(0).replace(" ", "")
            if digits[0] in "01":
                continue
            if self.passes_verhoeff(digits):
                found.append(
                    Detection(
                        start=match.start(),
                        end=match.end(),
                        category=PiiCategory.NATIONAL_ID,
                        confidence=Confidence(0.96),
                        detector=DetectorKind.CHECKSUM,
                        original=match.group(0),
                    )
                )
        return found


class RegexDetector:
    """Deterministic identifiers, including the Indian formats spec section 7 calls for."""

    _DEFINITIONS: tuple[tuple[PiiCategory, float, str], ...] = (
        (PiiCategory.EMAIL, 0.98, r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        (PiiCategory.IBAN, 0.95, r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
        # Indian PAN: five letters, four digits, one letter.
        (PiiCategory.NATIONAL_ID, 0.96, r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        # US SSN and UK national insurance number.
        (PiiCategory.NATIONAL_ID, 0.93, r"\b\d{3}-\d{2}-\d{4}\b"),
        (PiiCategory.NATIONAL_ID, 0.92, r"\b[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]\b"),
        (PiiCategory.BANK_ACCOUNT, 0.94, r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
        (
            PiiCategory.BANK_ACCOUNT,
            0.90,
            r"(?i)\b(?:sort\s*code|routing(?:\s*number)?|ifsc|swift|bic)\s*[:=]?\s*[A-Z0-9]{6,11}\b",
        ),
        (
            PiiCategory.BANK_ACCOUNT,
            0.88,
            r"(?i)\b(?:a/c|acct|account)\s*(?:no\.?|number|#)?\s*[:=]?\s*\d{8,18}\b",
        ),
        # Indian mobile: optional +91, then 6-9 followed by nine digits.
        (PiiCategory.PHONE, 0.94, r"(?:\+91[\s\-]?)?\b[6-9]\d{9}\b"),
        (PiiCategory.PHONE, 0.88, r"\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b"),
        (
            PiiCategory.IP_ADDRESS,
            0.92,
            r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b",
        ),
        (PiiCategory.MONETARY_AMOUNT, 0.90, r"(?:[$£€]|₹|\bRs\.?|\bINR)\s?\d[\d,]*(?:\.\d{2})?\b"),
        # A date that announces itself as a birth date, where only the date is replaced: swallowing
        # the words "Date of birth" along with it would remove the very thing that makes the
        # placeholder readable.
        (
            PiiCategory.DATE_OF_BIRTH,
            0.92,
            # The abbreviation carries no trailing word boundary: "D.O.B." ends in a full stop, and
            # a full stop followed by a space is not a boundary, so anchoring it there never matches.
            r"(?i)(?:\b(?:date\s+of\s+birth|birth\s+date|born(?:\s+on)?)\b|\bd\.?\s?o\.?\s?b\.?)"
            r"\s*[:\-]?\s*(?P<value>"
            r"(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}"
            r"|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s+(?:19|20)\d{2}"
            r"|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(?:19|20)\d{2}"
            r")",
        ),
        # Every other date. It is still worth hiding, but calling a contract date a date of birth
        # is simply wrong, and tells the model something untrue about the document.
        (
            PiiCategory.DATE,
            0.80,
            r"\b(?:0?[1-9]|[12]\d|3[01])[/\-](?:0?[1-9]|1[0-2])[/\-](?:19|20)\d{2}\b",
        ),
        (
            PiiCategory.STREET_ADDRESS,
            0.78,
            r"(?i)\b\d{1,5}\s+[A-Za-z][A-Za-z\s]{2,30}\s"
            r"(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|marg|nagar)\b\.?",
        ),
    )

    def __init__(self) -> None:
        self._patterns = tuple(
            _Pattern(category, confidence, re.compile(source), DetectorKind.REGEX)
            for category, confidence, source in self._DEFINITIONS
        )
        self._custom: list[_Pattern] = []
        self._card = CardNumberDetector()
        self._aadhaar = AadhaarDetector()

    def with_custom_rule(
        self,
        expression: str,
        category: PiiCategory = PiiCategory.CUSTOM_RULE,
        confidence: float = 0.99,
    ) -> "RegexDetector":
        """Enterprise rules from spec section 7 stage 3, e.g. ACME-INTERNAL, CLIENT-\\d{4}.

        An invalid expression raises rather than being silently skipped: a rule the administrator
        believes is protecting them but is not is worse than no rule.
        """
        self._custom.append(
            _Pattern(category, confidence, re.compile(expression), DetectorKind.CUSTOM_RULE)
        )
        return self

    def with_protected_term(
        self,
        term: str,
        category: PiiCategory = PiiCategory.CUSTOM_RULE,
        confidence: float = 0.99,
    ) -> "RegexDetector":
        """A word or phrase the user chose to protect, matched literally.

        Separate from `with_custom_rule` because the input is different in kind. A rule is written
        by an administrator who knows regex; a term is typed by someone protecting their client's
        name. "Smith & Co. (Pvt)" is a perfectly ordinary company name and a broken expression, so
        it is escaped rather than compiled, and matched without regard to case because a document
        that says ACME and one that says Acme are protecting the same thing.

        Word boundaries are only applied where the term itself ends in a word character. Anchoring
        "Acme Corp." with \\b would never match, since the boundary falls after the full stop.
        """
        cleaned = term.strip()
        if not cleaned:
            return self

        prefix = r"\b" if cleaned[0].isalnum() or cleaned[0] == "_" else ""
        suffix = r"\b" if cleaned[-1].isalnum() or cleaned[-1] == "_" else ""
        # Runs of whitespace in the term match runs of whitespace in the text, so a name broken
        # across a line in a PDF still matches.
        body = r"\s+".join(re.escape(part) for part in cleaned.split())

        self._custom.append(
            _Pattern(
                category,
                confidence,
                re.compile(f"(?i){prefix}{body}{suffix}"),
                DetectorKind.CUSTOM_RULE,
            )
        )
        return self

    def detect(self, text: str, selection: DetectorSelection) -> list[Detection]:
        found: list[Detection] = []
        for pattern in (*self._patterns, *self._custom):
            if not selection.includes(pattern.category.group):
                continue
            # A pattern may name the part that is actually sensitive with a group called `value`,
            # so the surrounding words that identify it are matched but left in place.
            group: str | int = "value" if "value" in pattern.expression.groupindex else 0
            for match in pattern.expression.finditer(text):
                start, end = match.span(group)
                if start < 0:
                    continue
                found.append(
                    Detection(
                        start=start,
                        end=end,
                        category=pattern.category,
                        confidence=Confidence(pattern.confidence),
                        detector=pattern.detector,
                        original=match.group(group),
                    )
                )

        if selection.direct_identifiers:
            found.extend(self._card.detect(text))
            found.extend(self._aadhaar.detect(text))

        return found
