"""Value types shared by every detector.

Offsets are character offsets into text that was normalised exactly once. A detection computed
against one normalisation and applied against another silently corrupts the document, which is why
`TextNormaliser` runs before the router and never again.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DetectorGroup(str, Enum):
    """The four toggles the user confirms before anything runs."""

    SECRETS_AND_CREDENTIALS = "secretsAndCredentials"
    DIRECT_IDENTIFIERS = "directIdentifiers"
    NAMES_ORGS_AND_PLACES = "namesOrgsAndPlaces"
    DATES_ADDRESSES_AND_MONEY = "datesAddressesAndMoney"
    CUSTOM_RULES = "customRules"


class PiiCategory(str, Enum):
    API_KEY = "apiKey"
    ACCESS_TOKEN = "accessToken"
    PASSWORD = "password"
    PRIVATE_KEY = "privateKey"
    CONNECTION_STRING = "connectionString"
    CREDENTIAL_IN_URL = "credentialInUrl"

    EMAIL = "email"
    PHONE = "phone"
    CREDIT_CARD = "creditCard"
    BANK_ACCOUNT = "bankAccount"
    IBAN = "iban"
    NATIONAL_ID = "nationalId"
    IP_ADDRESS = "ipAddress"
    URL = "url"

    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    GPE = "gpe"

    STREET_ADDRESS = "streetAddress"
    # A plain date and a date of birth are not the same fact. Treating every date as a birth date
    # labelled contract dates, invoice dates and meeting dates as [DATE_OF_BIRTH_001], which is
    # both wrong on the face of it and misleading to the model reading the placeholder.
    DATE = "date"
    DATE_OF_BIRTH = "dateOfBirth"
    MONETARY_AMOUNT = "monetaryAmount"

    PROJECT = "project"
    CLIENT = "client"
    CASE = "case"
    EMPLOYEE_ID = "employeeId"
    CUSTOMER_ID = "customerId"
    CUSTOM_RULE = "customRule"

    @property
    def group(self) -> DetectorGroup:
        return _CATEGORY_GROUPS[self]

    @property
    def placeholder_stem(self) -> str:
        return _PLACEHOLDER_STEMS[self]

    @property
    def specificity(self) -> int:
        """Breaks a confidence tie between overlapping detections.

        A specific category beats a general one: `[API_KEY_001]` tells the model more than
        `[PASSWORD_001]` and leaks no more.
        """
        return _SPECIFICITY.get(self, 1)

    @property
    def is_high_risk(self) -> bool:
        """High-risk categories block outbound transmission if they survive to the final gate."""
        return self in _HIGH_RISK


_CATEGORY_GROUPS: dict[PiiCategory, DetectorGroup] = {
    **{
        category: DetectorGroup.SECRETS_AND_CREDENTIALS
        for category in (
            PiiCategory.API_KEY,
            PiiCategory.ACCESS_TOKEN,
            PiiCategory.PASSWORD,
            PiiCategory.PRIVATE_KEY,
            PiiCategory.CONNECTION_STRING,
            PiiCategory.CREDENTIAL_IN_URL,
        )
    },
    **{
        category: DetectorGroup.DIRECT_IDENTIFIERS
        for category in (
            PiiCategory.EMAIL,
            PiiCategory.PHONE,
            PiiCategory.CREDIT_CARD,
            PiiCategory.BANK_ACCOUNT,
            PiiCategory.IBAN,
            PiiCategory.NATIONAL_ID,
            PiiCategory.IP_ADDRESS,
            PiiCategory.URL,
        )
    },
    **{
        category: DetectorGroup.NAMES_ORGS_AND_PLACES
        for category in (
            PiiCategory.PERSON,
            PiiCategory.ORGANIZATION,
            PiiCategory.LOCATION,
            PiiCategory.GPE,
        )
    },
    **{
        category: DetectorGroup.DATES_ADDRESSES_AND_MONEY
        for category in (
            PiiCategory.STREET_ADDRESS,
            PiiCategory.DATE,
            PiiCategory.DATE_OF_BIRTH,
            PiiCategory.MONETARY_AMOUNT,
        )
    },
    **{
        category: DetectorGroup.CUSTOM_RULES
        for category in (
            PiiCategory.PROJECT,
            PiiCategory.CLIENT,
            PiiCategory.CASE,
            PiiCategory.EMPLOYEE_ID,
            PiiCategory.CUSTOMER_ID,
            PiiCategory.CUSTOM_RULE,
        )
    },
}

_PLACEHOLDER_STEMS: dict[PiiCategory, str] = {
    PiiCategory.API_KEY: "API_KEY",
    PiiCategory.ACCESS_TOKEN: "AUTH_TOKEN",
    PiiCategory.PASSWORD: "PASSWORD",
    PiiCategory.PRIVATE_KEY: "PRIVATE_KEY",
    PiiCategory.CONNECTION_STRING: "DB_CONNECTION",
    PiiCategory.CREDENTIAL_IN_URL: "CREDENTIAL_URL",
    PiiCategory.EMAIL: "EMAIL",
    PiiCategory.PHONE: "PHONE",
    PiiCategory.CREDIT_CARD: "CREDIT_CARD",
    PiiCategory.BANK_ACCOUNT: "BANK_ACCOUNT",
    PiiCategory.IBAN: "IBAN",
    PiiCategory.NATIONAL_ID: "NATIONAL_ID",
    PiiCategory.IP_ADDRESS: "IP_ADDRESS",
    PiiCategory.URL: "URL",
    PiiCategory.PERSON: "PERSON",
    PiiCategory.ORGANIZATION: "ORG",
    PiiCategory.LOCATION: "LOCATION",
    PiiCategory.GPE: "GPE",
    PiiCategory.STREET_ADDRESS: "ADDRESS",
    PiiCategory.DATE: "DATE",
    PiiCategory.DATE_OF_BIRTH: "DATE_OF_BIRTH",
    PiiCategory.MONETARY_AMOUNT: "AMOUNT",
    PiiCategory.PROJECT: "PROJECT",
    PiiCategory.CLIENT: "CLIENT",
    PiiCategory.CASE: "CASE",
    PiiCategory.EMPLOYEE_ID: "EMPLOYEE_ID",
    PiiCategory.CUSTOMER_ID: "CUSTOMER_ID",
    PiiCategory.CUSTOM_RULE: "REDACTED",
}

_SPECIFICITY: dict[PiiCategory, int] = {
    PiiCategory.PRIVATE_KEY: 6,
    PiiCategory.API_KEY: 6,
    PiiCategory.CONNECTION_STRING: 6,
    PiiCategory.CREDENTIAL_IN_URL: 6,
    PiiCategory.ACCESS_TOKEN: 5,
    PiiCategory.CREDIT_CARD: 5,
    PiiCategory.IBAN: 5,
    PiiCategory.NATIONAL_ID: 5,
    PiiCategory.EMAIL: 4,
    PiiCategory.PHONE: 4,
    PiiCategory.BANK_ACCOUNT: 4,
    PiiCategory.PASSWORD: 3,
    PiiCategory.IP_ADDRESS: 3,
    PiiCategory.DATE_OF_BIRTH: 3,
    PiiCategory.URL: 2,
    PiiCategory.DATE: 1,
}

_HIGH_RISK: frozenset[PiiCategory] = frozenset(
    {
        PiiCategory.API_KEY,
        PiiCategory.ACCESS_TOKEN,
        PiiCategory.PASSWORD,
        PiiCategory.PRIVATE_KEY,
        PiiCategory.CONNECTION_STRING,
        PiiCategory.CREDENTIAL_IN_URL,
        PiiCategory.CREDIT_CARD,
        PiiCategory.IBAN,
        PiiCategory.BANK_ACCOUNT,
        PiiCategory.NATIONAL_ID,
    }
)


class DetectorKind(str, Enum):
    REGEX = "regex"
    CHECKSUM = "checksum"
    ENTROPY = "entropy"
    PRESIDIO = "presidio"
    GLINER = "gliner"
    CUSTOM_RULE = "customRule"


class RedactionDisposition(str, Enum):
    AUTO_REDACT = "autoRedact"
    NEEDS_REVIEW = "needsReview"
    IGNORED = "ignored"


class ConfidenceOutOfRange(ValueError):
    def __init__(self, attempted: float) -> None:
        super().__init__(f"Confidence must be between 0 and 1, received {attempted}.")
        self.attempted = attempted


@dataclass(frozen=True, slots=True, order=True)
class Confidence:
    """A value between 0 and 1, with the threshold rule attached.

    A bare float invites comparison against the wrong scale, so the disposition boundaries live
    here rather than at every call site.
    """

    value: float

    AUTO_REDACT_ABOVE = 0.85
    REVIEW_ABOVE = 0.50

    def __post_init__(self) -> None:
        if not isinstance(self.value, (int, float)) or self.value != self.value:
            raise ConfidenceOutOfRange(self.value)
        if not 0.0 <= self.value <= 1.0:
            raise ConfidenceOutOfRange(self.value)

    @property
    def disposition(self) -> RedactionDisposition:
        if self.value > Confidence.AUTO_REDACT_ABOVE:
            return RedactionDisposition.AUTO_REDACT
        if self.value >= Confidence.REVIEW_ABOVE:
            return RedactionDisposition.NEEDS_REVIEW
        return RedactionDisposition.IGNORED

    @property
    def percent(self) -> int:
        return round(self.value * 100)


@dataclass(slots=True)
class Detection:
    """One detector's observation that a span holds a category of sensitive value.

    `original` is the matched text. Nothing outside the privacy package reads it: it is consumed by
    `RedactionMap`, which keeps it in the local-only reverse table, and it is never serialised.
    """

    start: int
    end: int
    category: PiiCategory
    confidence: Confidence
    detector: DetectorKind
    original: str

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)

    def overlaps(self, other: "Detection") -> bool:
        return self.start < other.end and other.start < self.end

    def outranks(self, other: "Detection") -> bool:
        """Priority per spec section 11: explicit rules, then enterprise rules, then secrets, then
        validated deterministic patterns, then contextual NER."""
        if self.detector_priority != other.detector_priority:
            return self.detector_priority > other.detector_priority
        if self.confidence.value != other.confidence.value:
            return self.confidence.value > other.confidence.value
        if self.category.specificity != other.category.specificity:
            return self.category.specificity > other.category.specificity
        return self.length > other.length

    @property
    def detector_priority(self) -> int:
        return _DETECTOR_PRIORITY[self.detector]


_DETECTOR_PRIORITY: dict[DetectorKind, int] = {
    DetectorKind.CUSTOM_RULE: 5,
    DetectorKind.CHECKSUM: 4,
    DetectorKind.REGEX: 3,
    DetectorKind.ENTROPY: 2,
    DetectorKind.PRESIDIO: 2,
    DetectorKind.GLINER: 1,
}
