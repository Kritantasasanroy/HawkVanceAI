"""Summariser tests.

The model itself is slow and optional, so most of these exercise the parts that decide *what the
user is shown*: the extractive fallback, and the validation that stops malformed model output from
being presented as findings.
"""

from __future__ import annotations

import pytest

from hawkvance_engine.memory.model import MemoryScope
from hawkvance_engine.summariser import (
    DocumentProfile,
    ExtractiveSummariser,
    LocalSummariser,
)

CONTRACT = (
    "MASTER SERVICES AGREEMENT between [ORG_001] and [ORG_002]. "
    "Primary contact [PERSON_001], reachable at [EMAIL_001]. "
    "Clause 4: [ORG_002] shall indemnify [ORG_001] against all third-party claims. "
    "Clause 8: Either party may terminate on 12/03/2026 with thirty days notice. "
    "Lunch is at noon. "
    "Clause 14: Liability is capped at [AMOUNT_001] in aggregate."
)


# ---------------------------------------------------------------------------
# The fallback, which must be genuinely useful rather than a stub
# ---------------------------------------------------------------------------


def test_extractive_summary_prefers_sentences_carrying_obligations():
    summary = ExtractiveSummariser.summarise(CONTRACT, sentences=3)

    assert "indemnify" in summary or "terminate" in summary
    assert "Lunch is at noon" not in summary


def test_extractive_summary_keeps_reading_order():
    summary = ExtractiveSummariser.summarise(CONTRACT, sentences=3)
    positions = [summary.find(marker) for marker in ("Clause 4", "Clause 8", "Clause 14")]
    present = [position for position in positions if position >= 0]
    assert present == sorted(present)


def test_extractive_summary_preserves_placeholders():
    assert "[ORG_" in ExtractiveSummariser.summarise(CONTRACT, sentences=3)


def test_empty_text_summarises_to_nothing_rather_than_failing():
    assert ExtractiveSummariser.summarise("", sentences=3) == ""
    assert ExtractiveSummariser.key_facts("") == ()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("This agreement and its liability clause shall terminate", "legal"),
        ("Invoice total, payment due, tax and revenue for the period", "financial"),
        ("The api endpoint calls a function and writes to the database", "technical"),
        ("The patient diagnosis and prescribed dosage were clinical", "medical"),
        ("Dear Sir, kind regards, sincerely yours", "correspondence"),
        ("nothing in particular here at all", "other"),
    ],
)
def test_extractive_classification(text, expected):
    assert ExtractiveSummariser.classify(text) == expected


# ---------------------------------------------------------------------------
# Fact validation: the guard that stops malformed output reaching the user
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rubbish",
    [
        '{"1": null, "2": null, "3": null}',
        "JSON: {}",
        "[]",
        "null",
        "ok",
        '"a", "b", "c", "d", "e"',
    ],
)
def test_malformed_model_output_is_rejected_rather_than_shown(rubbish):
    assert LocalSummariser._parse_facts(rubbish) == ()


def test_a_proper_json_array_of_facts_is_accepted():
    raw = (
        '["[ORG_002] shall indemnify [ORG_001] against third-party claims.", '
        '"Either party may terminate on 12/03/2026 with thirty days notice."]'
    )
    facts = LocalSummariser._parse_facts(raw)

    assert len(facts) == 2
    assert all("[ORG_" in fact or "terminate" in fact for fact in facts)


def test_a_numbered_list_is_accepted_when_the_model_ignores_json():
    raw = (
        "1. [ORG_002] shall indemnify [ORG_001] against all third-party claims.\n"
        "2. Either party may terminate on 12/03/2026 with thirty days notice.\n"
        "3. ok"
    )
    facts = LocalSummariser._parse_facts(raw)

    assert len(facts) == 2, "the two real sentences survive, the fragment does not"


def test_the_fact_guard_rejects_fragments_and_key_value_dumps():
    assert not LocalSummariser._looks_like_a_fact("ok")
    assert not LocalSummariser._looks_like_a_fact('{"a": 1}')
    assert not LocalSummariser._looks_like_a_fact("x" * 500)
    assert LocalSummariser._looks_like_a_fact(
        "Clause 4 requires the supplier to indemnify the customer against claims."
    )


def test_a_category_the_model_invented_falls_back_to_other():
    assert LocalSummariser._clean_category("Legal") == "legal"
    assert LocalSummariser._clean_category("banana") == "other"
    assert LocalSummariser._clean_category("") == "other"


# ---------------------------------------------------------------------------
# Degradation: no model must never mean no pipeline
# ---------------------------------------------------------------------------


def test_a_profile_is_produced_even_with_no_model_available():
    summariser = LocalSummariser(model_path="does-not-exist.gguf")
    profile = summariser.profile(CONTRACT, sentences=2)

    assert isinstance(profile, DocumentProfile)
    assert profile.used_model is False, "it must be honest about which path ran"
    assert profile.summary != ""
    assert profile.category == "legal"
    assert len(profile.key_facts) > 0


def test_memory_candidates_are_less_confident_without_a_model():
    without = LocalSummariser(model_path="does-not-exist.gguf")
    candidates = without.memory_candidates(
        CONTRACT, source="Contract.pdf", workspace_id="ws-1", document_id="doc-1"
    )

    assert len(candidates) > 0
    assert all(candidate.confidence < 0.8 for candidate in candidates), (
        "sentence ranking finds important sentences, it does not understand them, and the "
        "confidence should say so"
    )
    assert all(candidate.scope is MemoryScope.FILE for candidate in candidates)
    assert all(candidate.document_id == "doc-1" for candidate in candidates)


def test_candidates_carry_the_document_and_workspace_they_came_from():
    summariser = LocalSummariser(model_path="does-not-exist.gguf")
    candidates = summariser.memory_candidates(
        CONTRACT, source="Contract.pdf", workspace_id="ws-9", document_id=None
    )
    assert all(candidate.workspace_id == "ws-9" for candidate in candidates)
    assert all(candidate.scope is MemoryScope.WORKSPACE for candidate in candidates)


def test_the_snapshot_reports_what_is_actually_available():
    snapshot = LocalSummariser(model_path="does-not-exist.gguf").snapshot()

    assert snapshot["modelPath"] is None
    assert snapshot["loaded"] is False
    assert isinstance(snapshot["runtimeAvailable"], bool)


def test_nothing_here_accepts_a_free_form_user_prompt():
    """Spec section 18: the local model is not a chatbot.

    Every public method takes document text and a shape parameter. If a method ever appears here
    that takes a prompt, this test is the thing that should stop it.
    """
    import inspect

    for name in ("profile", "memory_candidates", "summarise"):
        target = getattr(LocalSummariser, name, None) or getattr(ExtractiveSummariser, name)
        parameters = set(inspect.signature(target).parameters)
        assert "prompt" not in parameters
        assert "system" not in parameters
        assert "messages" not in parameters
