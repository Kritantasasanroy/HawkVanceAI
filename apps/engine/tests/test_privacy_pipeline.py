"""Privacy pipeline tests, including the two cases the specification states verbatim."""

from __future__ import annotations

import pytest

from hawkvance_engine.privacy.detection import (
    Confidence,
    ConfidenceOutOfRange,
    Detection,
    DetectorKind,
    PiiCategory,
    RedactionDisposition,
)
from hawkvance_engine.privacy.detectors import (
    AadhaarDetector,
    CardNumberDetector,
    DetectorSelection,
    HighEntropyDetector,
    RegexDetector,
    SecretDetector,
)
from hawkvance_engine.privacy.redaction import (
    ConflictResolver,
    RedactionMap,
    RedactionStyle,
)
from hawkvance_engine.privacy.router import PrivacyMode, PrivacyPolicy, PrivacyTaskRouter
from hawkvance_engine.privacy.verification import PrivacyVerificationGate, VerificationOutcome


def deterministic(text: str, selection: DetectorSelection | None = None) -> list[Detection]:
    chosen = selection or DetectorSelection()
    return [*SecretDetector().detect(text), *RegexDetector().detect(text, chosen)]


def sanitise(text: str) -> tuple[RedactionMap, str]:
    redaction_map = RedactionMap.resolve(deterministic(text))
    return redaction_map, redaction_map.apply(text)


def detection(start: int, end: int, category: PiiCategory, score: float, original: str,
              detector: DetectorKind = DetectorKind.REGEX) -> Detection:
    return Detection(start, end, category, Confidence(score), detector, original)


# ---------------------------------------------------------------------------
# Spec section 46: the stated privacy test case
# ---------------------------------------------------------------------------


def test_spec_section_46_redacts_every_stated_value():
    text = (
        "John Doe from Acme Corp can be reached at john@example.com.\n"
        "The production API key is sk-example-secret-abcdefghijklmno."
    )
    _, sanitised = sanitise(text)

    assert "john@example.com" not in sanitised
    assert "sk-example-secret" not in sanitised
    assert "[EMAIL_001]" in sanitised
    assert "[API_KEY_001]" in sanitised


def test_no_original_value_survives_into_the_outbound_text():
    text = "Contact jane.doe@acme.co.uk, card 4539148803436467, key sk-live-abcdefghijklmnop."
    _, sanitised = sanitise(text)

    for secret in ("jane.doe@acme.co.uk", "4539148803436467", "sk-live-abcdefghijklmnop"):
        assert secret not in sanitised, f"{secret} leaked into the outbound text"


# ---------------------------------------------------------------------------
# Spec section 47: pseudonymisation keeps the mapping local
# ---------------------------------------------------------------------------


def test_spec_section_47_pseudonymisation_round_trip():
    text = "John discussed the contract with Acme Corp."
    redaction_map = RedactionMap.resolve(
        [
            detection(0, 4, PiiCategory.PERSON, 0.94, "John"),
            detection(33, 42, PiiCategory.ORGANIZATION, 0.91, "Acme Corp"),
        ]
    )

    sanitised = redaction_map.apply(text)
    assert sanitised == "[PERSON_001] discussed the contract with [ORG_001]."

    restored = redaction_map.restore("[PERSON_001] signed with [ORG_001] on Tuesday.")
    assert restored == "John signed with Acme Corp on Tuesday."


def test_the_mapping_is_not_reachable_from_any_serialised_form():
    redaction_map = RedactionMap.resolve(
        [detection(0, 13, PiiCategory.EMAIL, 0.98, "jane@acme.com")]
    )
    serialised = str([redaction.as_dict() for redaction in redaction_map.redactions])

    assert "jane@acme.com" not in serialised
    assert "jane" not in serialised
    assert len(redaction_map.redactions[0].original_hash) == 64


def test_a_placeholder_is_stable_for_one_value_and_distinct_between_values():
    redaction_map = RedactionMap.resolve(
        [
            detection(0, 8, PiiCategory.PERSON, 0.94, "John Doe"),
            detection(20, 28, PiiCategory.PERSON, 0.94, "John Doe"),
            detection(40, 48, PiiCategory.PERSON, 0.94, "Jane Roe"),
        ]
    )
    placeholders = [redaction.placeholder for redaction in redaction_map.redactions]

    assert placeholders == ["[PERSON_001]", "[PERSON_001]", "[PERSON_002]"]


def test_numbering_restarts_per_category():
    redaction_map = RedactionMap.resolve(
        [
            detection(0, 8, PiiCategory.PERSON, 0.94, "John Doe"),
            detection(20, 24, PiiCategory.ORGANIZATION, 0.9, "Acme"),
        ]
    )
    assert [r.placeholder for r in redaction_map.redactions] == ["[PERSON_001]", "[ORG_001]"]


def test_restore_does_not_confuse_placeholder_one_with_placeholder_ten():
    redaction_map = RedactionMap.resolve(
        [detection(offset, offset + 4, PiiCategory.PERSON, 0.94, f"Name{index:02d}")
         for index, offset in enumerate(range(0, 55, 5))]
    )
    restored = redaction_map.restore("[PERSON_001] and [PERSON_010] met.")

    assert "Name00" in restored and "Name09" in restored
    assert "[PERSON_" not in restored


def test_mask_style_emits_no_recoverable_mapping():
    redaction_map = RedactionMap.resolve(
        [detection(0, 13, PiiCategory.EMAIL, 0.98, "jane@acme.com")],
        style=RedactionStyle.MASK,
    )
    assert redaction_map.placeholder_count == 0
    assert redaction_map.restore("****") == "****"


# ---------------------------------------------------------------------------
# Secret detection, spec section 8
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("key sk-live-abcdefghijklmnopqrst here", PiiCategory.API_KEY),
        ("AKIAIOSFODNN7EXAMPLE", PiiCategory.API_KEY),
        ("AIzaSyA1234567890abcdefghijklmnopqrstuv", PiiCategory.API_KEY),
        ("-----BEGIN RSA PRIVATE KEY-----", PiiCategory.PRIVATE_KEY),
        ("postgresql://app:s3cret@db.internal:5432/prod", PiiCategory.CONNECTION_STRING),
        ("https://deploy:hunter2@git.internal/repo.git", PiiCategory.CREDENTIAL_IN_URL),
        ("password = correcthorsebattery", PiiCategory.PASSWORD),
        ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345", PiiCategory.ACCESS_TOKEN),
    ],
)
def test_secret_detector_finds_each_credential_class(text, expected):
    found = SecretDetector().detect(text)
    assert any(item.category is expected for item in found), f"missed {expected} in {text!r}"


def test_a_jwt_is_detected_as_an_access_token():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    found = SecretDetector().detect(f"token {jwt}")
    assert any(item.category is PiiCategory.ACCESS_TOKEN for item in found)


def test_entropy_finds_an_unknown_vendor_key():
    found = HighEntropyDetector().detect("token GkZ3mQ7xR2vB8nL4pW9tY6cA1sD5fH0j done")
    assert found and found[0].detector is DetectorKind.ENTROPY


def test_entropy_stays_quiet_on_prose():
    assert HighEntropyDetector().detect(
        "The quick brown fox jumps over the lazy dog repeatedly today"
    ) == []


def test_entropy_lands_in_the_review_band_rather_than_auto_redacting():
    found = HighEntropyDetector().detect("GkZ3mQ7xR2vB8nL4pW9tY6cA1sD5fH0j")
    assert found[0].confidence.disposition is RedactionDisposition.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# Checksums beat patterns
# ---------------------------------------------------------------------------


def test_a_luhn_valid_card_is_detected():
    assert CardNumberDetector().detect("Card 4539 1488 0343 6467 on file.")


def test_a_luhn_invalid_run_is_not_a_card():
    assert CardNumberDetector().detect("Invoice 4539 1488 0343 6460 is overdue.") == []


def test_aadhaar_requires_the_verhoeff_check_digit():
    assert AadhaarDetector().passes_verhoeff("234567890124") is True
    assert AadhaarDetector().passes_verhoeff("234567890123") is False


def test_aadhaar_rejects_numbers_starting_zero_or_one():
    assert AadhaarDetector().detect("ID 0234 5678 9012 here") == []


def test_indian_pan_is_detected():
    found = RegexDetector().detect("PAN ABCDE1234F on the form.", DetectorSelection())
    assert any(item.category is PiiCategory.NATIONAL_ID for item in found)


def test_indian_mobile_and_ifsc_are_detected():
    found = RegexDetector().detect("Call 9876543210, IFSC HDFC0001234.", DetectorSelection())
    categories = {item.category for item in found}
    assert PiiCategory.PHONE in categories
    assert PiiCategory.BANK_ACCOUNT in categories


def test_rupee_amounts_are_detected():
    found = RegexDetector().detect("Fee is ₹1,25,000 payable now.", DetectorSelection())
    assert any(item.category is PiiCategory.MONETARY_AMOUNT for item in found)


# ---------------------------------------------------------------------------
# Conflict resolution, spec section 11
# ---------------------------------------------------------------------------


def test_overlapping_detections_never_both_survive():
    resolved = ConflictResolver.resolve(
        [
            detection(10, 30, PiiCategory.PERSON, 0.72, "x" * 20, DetectorKind.GLINER),
            detection(10, 24, PiiCategory.PERSON, 0.88, "x" * 14, DetectorKind.PRESIDIO),
        ]
    )
    assert len(resolved) == 1


def test_a_secret_outranks_contextual_ner_over_the_same_span():
    resolved = ConflictResolver.resolve(
        [
            detection(0, 20, PiiCategory.PERSON, 0.99, "sk-abcdefghijklmnop", DetectorKind.GLINER),
            detection(0, 20, PiiCategory.API_KEY, 0.80, "sk-abcdefghijklmnop", DetectorKind.REGEX),
        ]
    )
    assert len(resolved) == 1
    assert resolved[0].category is PiiCategory.API_KEY


def test_an_explicit_custom_rule_outranks_everything():
    resolved = ConflictResolver.resolve(
        [
            detection(0, 12, PiiCategory.PERSON, 0.99, "PROJECT-X123", DetectorKind.PRESIDIO),
            detection(0, 12, PiiCategory.CUSTOM_RULE, 0.60, "PROJECT-X123", DetectorKind.CUSTOM_RULE),
        ]
    )
    assert resolved[0].detector is DetectorKind.CUSTOM_RULE


def test_adjacent_detections_both_survive_and_come_back_ordered():
    resolved = ConflictResolver.resolve(
        [
            detection(30, 40, PiiCategory.PHONE, 0.9, "0123456789"),
            detection(0, 10, PiiCategory.EMAIL, 0.98, "a@b.com"),
        ]
    )
    assert [item.start for item in resolved] == [0, 30]


def test_ignored_confidence_never_reaches_the_map():
    redaction_map = RedactionMap.resolve([detection(0, 5, PiiCategory.PERSON, 0.3, "Alice")])
    assert redaction_map.is_empty


# ---------------------------------------------------------------------------
# Thresholds, decision P4
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.99, RedactionDisposition.AUTO_REDACT),
        (0.86, RedactionDisposition.AUTO_REDACT),
        (0.85, RedactionDisposition.NEEDS_REVIEW),
        (0.50, RedactionDisposition.NEEDS_REVIEW),
        (0.49, RedactionDisposition.IGNORED),
    ],
)
def test_disposition_boundaries(score, expected):
    assert Confidence(score).disposition is expected


def test_confidence_rejects_impossible_values():
    for bad in (1.01, -0.01, float("nan")):
        with pytest.raises(ConfidenceOutOfRange):
            Confidence(bad)


def test_only_the_uncertain_band_is_offered_for_review():
    redaction_map = RedactionMap.resolve(
        [
            detection(0, 10, PiiCategory.API_KEY, 0.99, "sk-abcdefg"),
            detection(20, 29, PiiCategory.ORGANIZATION, 0.71, "Northwind"),
        ]
    )
    assert [r.placeholder for r in redaction_map.needing_review()] == ["[ORG_001]"]
    assert [r.placeholder for r in redaction_map.automatic()] == ["[API_KEY_001]"]


def test_keeping_a_value_in_the_clear_drops_it_from_the_reverse_table():
    text = "Northwind signed with sk-abcdefghijklmnop today."
    redaction_map = RedactionMap.resolve(
        [
            detection(0, 9, PiiCategory.ORGANIZATION, 0.71, "Northwind"),
            detection(22, 41, PiiCategory.API_KEY, 0.99, "sk-abcdefghijklmnop"),
        ]
    )
    redaction_map.keep_in_clear(["[ORG_001]"])

    assert "Northwind" in redaction_map.apply(text)
    assert redaction_map.restore("[ORG_001]") == "[ORG_001]"


# ---------------------------------------------------------------------------
# Category confirmation, decision P3
# ---------------------------------------------------------------------------


def test_unticking_a_group_stops_that_group_running():
    text = "Email jane@acme.com with key sk-live-abcdefghijklmnop"
    found = RegexDetector().detect(text, DetectorSelection(direct_identifiers=False))
    assert not any(item.category is PiiCategory.EMAIL for item in found)


def test_unticking_everything_detects_nothing():
    nothing = DetectorSelection(False, False, False, False, False)
    assert nothing.nothing_enabled
    assert RegexDetector().detect("jane@acme.com sk-live-abcdefghij", nothing) == []


def test_a_custom_rule_is_reported_as_a_custom_rule():
    detector = RegexDetector().with_custom_rule(r"\bCLIENT-\d{4}\b")
    found = detector.detect("Case CLIENT-7429 is open.", DetectorSelection())
    custom = [item for item in found if item.category is PiiCategory.CUSTOM_RULE]
    assert custom and custom[0].detector is DetectorKind.CUSTOM_RULE


def test_an_invalid_custom_rule_raises_rather_than_being_skipped():
    import re as _re

    with pytest.raises(_re.error):
        RegexDetector().with_custom_rule(r"[unclosed")


# ---------------------------------------------------------------------------
# Protected terms: words the user marked, matched literally
# ---------------------------------------------------------------------------


def test_a_protected_term_is_found_whatever_its_case():
    detector = RegexDetector().with_protected_term("Falcon")
    for text in ("Project Falcon ships", "project falcon ships", "PROJECT FALCON ships"):
        assert detector.detect(text, DetectorSelection()), f"missed it in: {text}"


def test_a_protected_term_containing_regex_characters_is_matched_literally():
    """A company name is not an expression. Escaping it is the difference between protecting
    "Smith & Co. (Pvt)" and crashing on it."""
    detector = RegexDetector().with_protected_term("Smith & Co. (Pvt)")
    found = detector.detect("Invoice from Smith & Co. (Pvt) attached.", DetectorSelection())
    assert found and found[0].category is PiiCategory.CUSTOM_RULE


def test_a_protected_term_ending_in_punctuation_still_matches():
    """Anchoring "Acme Corp." with a word boundary would never match, because the boundary falls
    after the full stop."""
    detector = RegexDetector().with_protected_term("Acme Corp.")
    assert detector.detect("Paid to Acme Corp. last week.", DetectorSelection())


def test_a_protected_term_does_not_match_inside_a_longer_word():
    detector = RegexDetector().with_protected_term("art")
    assert detector.detect("the art collection", DetectorSelection())
    assert detector.detect("started the cart", DetectorSelection()) == []


def test_a_protected_phrase_matches_across_a_line_break():
    """Text lifted out of a PDF breaks lines in places the author never chose."""
    detector = RegexDetector().with_protected_term("Project Falcon")
    assert detector.detect("the Project\nFalcon budget", DetectorSelection())


def test_a_blank_protected_term_is_ignored_rather_than_matching_everything():
    detector = RegexDetector().with_protected_term("   ")
    assert detector.detect("anything at all", DetectorSelection()) == []


# ---------------------------------------------------------------------------
# The router, spec sections 5 and 35
# ---------------------------------------------------------------------------


def test_short_structured_text_routes_to_fast_and_loads_no_model():
    router = PrivacyTaskRouter()
    result = router.scan("Call me at john@example.com")

    assert result.decision.mode is PrivacyMode.FAST
    assert result.decision.models_loaded == ()
    assert "[EMAIL_001]" in result.sanitised_text


def test_narrative_prose_routes_to_standard():
    router = PrivacyTaskRouter()
    mode, _ = router.mode_for("John Smith joined Microsoft Corporation in London last year.")
    assert mode is PrivacyMode.STANDARD


def test_turning_off_names_forces_fast_because_no_model_is_needed():
    router = PrivacyTaskRouter(
        PrivacyPolicy(selection=DetectorSelection(names_orgs_and_places=False))
    )
    mode, reason = router.mode_for("John Smith joined Microsoft Corporation in London last year.")
    assert mode is PrivacyMode.FAST
    assert "no language model" in reason


def test_an_explicit_mode_request_is_never_downgraded():
    router = PrivacyTaskRouter()
    mode, reason = router.mode_for("hi", requested=PrivacyMode.HIGH_SECURITY)
    assert mode is PrivacyMode.HIGH_SECURITY
    assert "explicitly" in reason


def test_fast_mode_never_reports_a_loaded_model():
    router = PrivacyTaskRouter()
    router.scan("api key sk-live-abcdefghijklmnop", requested=PrivacyMode.FAST)
    assert router.loaded_models == ()


def test_disabling_everything_short_circuits_the_whole_pipeline():
    router = PrivacyTaskRouter(
        PrivacyPolicy(selection=DetectorSelection(False, False, False, False, False))
    )
    result = router.scan("jane@acme.com")
    assert result.sanitised_text == "jane@acme.com"
    assert result.decision.detectors_used == ()


# ---------------------------------------------------------------------------
# The final gate, spec sections 12 and 48
# ---------------------------------------------------------------------------


def test_the_gate_blocks_a_surviving_credential():
    verdict = PrivacyVerificationGate().verify(
        "Here is the context. The key is sk-live-abcdefghijklmnopqrst."
    )
    assert verdict.outcome is VerificationOutcome.BLOCKED
    assert verdict.may_transmit is False


def test_a_blocked_verdict_never_quotes_the_value_it_found():
    secret = "sk-live-abcdefghijklmnopqrst"
    verdict = PrivacyVerificationGate().verify(f"key {secret}")
    assert secret not in str(verdict.as_dict())


def test_the_gate_allows_fully_sanitised_text():
    verdict = PrivacyVerificationGate().verify(
        "[PERSON_001] of [ORG_001] asked about clause 4. Contact via [EMAIL_001]."
    )
    assert verdict.outcome is VerificationOutcome.ALLOWED
    assert verdict.may_transmit is True


def test_the_gate_asks_for_review_on_a_surviving_low_risk_value():
    verdict = PrivacyVerificationGate().verify("Reach the team at 10.1.2.3 tomorrow.")
    assert verdict.outcome is VerificationOutcome.NEEDS_REVIEW
    assert verdict.may_transmit is False


def test_the_pipeline_output_passes_its_own_gate():
    text = "Mail jane@acme.com, key sk-live-abcdefghijklmnop, card 4539148803436467."
    _, sanitised = sanitise(text)
    assert PrivacyVerificationGate().verify(sanitised).may_transmit is True


# ---------------------------------------------------------------------------
# Dates: a contract date is not a date of birth
# ---------------------------------------------------------------------------


def test_a_plain_date_is_labelled_as_a_date():
    """Every date used to be reported as a date of birth.

    That is wrong on the face of it, and it also misleads the model: the placeholder is the only
    description of the removed value it ever sees, so `[DATE_OF_BIRTH_001]` on an invoice date
    tells it something untrue about the document.
    """
    _, sanitised = sanitise("The agreement was signed on 04/03/2026 and runs for a year.")
    assert "[DATE_001]" in sanitised
    assert "DATE_OF_BIRTH" not in sanitised


def test_several_plain_dates_are_numbered_in_order():
    _, sanitised = sanitise("Signed 04/03/2026, delivered 18/07/2026, invoiced 02/08/2026.")
    assert "[DATE_001]" in sanitised
    assert "[DATE_002]" in sanitised
    assert "[DATE_003]" in sanitised


def test_the_same_date_twice_keeps_one_label():
    redaction_map, sanitised = sanitise("Due 04/03/2026, and again on 04/03/2026.")
    assert sanitised.count("[DATE_001]") == 2
    assert "[DATE_002]" not in sanitised


@pytest.mark.parametrize(
    "text",
    [
        "Date of birth: 04/03/1990",
        "date of birth 04/03/1990",
        "DOB: 04/03/1990",
        "D.O.B. 04/03/1990",
        "Born on 4 March 1990",
        "Birth date: March 4, 1990",
    ],
)
def test_a_date_announced_as_a_birth_date_keeps_that_label(text):
    _, sanitised = sanitise(text)
    assert "[DATE_OF_BIRTH_001]" in sanitised


def test_the_words_identifying_a_birth_date_are_left_in_place():
    """Only the date is replaced.

    Taking the label with it would leave the model reading a sentence whose subject is gone, which
    costs the answer quality the redaction was supposed to protect.
    """
    _, sanitised = sanitise("Date of birth: 04/03/1990 as stated on the form.")
    assert sanitised.startswith("Date of birth: [DATE_OF_BIRTH_001]")
    assert "1990" not in sanitised


def test_a_birth_date_and_a_plain_date_in_one_document_are_told_apart():
    _, sanitised = sanitise("Signed 04/03/2026. Date of birth: 11/09/1988.")
    assert "[DATE_001]" in sanitised
    assert "[DATE_OF_BIRTH_001]" in sanitised
