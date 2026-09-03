"""End-to-end tests over the whole local pipeline.

These follow the acceptance criteria in spec section 81, in order:

    document -> extract locally -> detect PII -> redact -> summarise -> memory
    -> retrieve -> compress -> context pack -> privacy gate -> (boundary)
    -> response -> restore locally

Nothing here is mocked. The only thing that does not run is the external model call itself, which
is the one step that is not local, and it is replaced by a canned response so the restore half of
the pipeline can be exercised.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hawkvance_engine.engine import LocalEngine
from hawkvance_engine.privacy.router import PrivacyMode

CONTRACT = """MASTER SERVICES AGREEMENT

This agreement is between Acme Corporation and Northwind Trading Limited.
The primary contact is Jane Doe, reachable at jane.doe@acme.co.uk or on 9876543210.
Billing runs through account no. 12345678901 at IFSC HDFC0001234.

Clause 4: Northwind shall indemnify Acme against all third-party claims.
Clause 8: Either party may terminate on 12/03/2026 with thirty days notice.
Clause 14: Liability is capped at Rs 25,00,000 in aggregate.

Deployment credentials for the shared environment are:
  DATABASE_URL=postgresql://svc_acme:Hunter2Hunter2@db.internal:5432/prod
  OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz012345
"""


@pytest.fixture(scope="module")
def engine() -> LocalEngine:
    built = LocalEngine()
    yield built
    built.shutdown()


@pytest.fixture()
def contract_file(tmp_path: Path) -> Path:
    path = tmp_path / "MasterAgreement.txt"
    path.write_text(CONTRACT, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The full acceptance workflow
# ---------------------------------------------------------------------------


def test_the_whole_pipeline_from_document_to_restored_answer(engine: LocalEngine, contract_file: Path):
    # 1. The document is processed entirely on this machine.
    processed = engine.process_document(str(contract_file), mode=PrivacyMode.STANDARD)
    document = processed["document"]
    scan = processed["scan"]

    assert document["characterCount"] > 0
    assert document["usedOcr"] is False, "a text file must never invoke OCR"

    # 2. Every secret is gone from what could leave.
    sanitised = scan["sanitisedText"]
    for secret in (
        "Hunter2Hunter2",
        "sk-proj-abcdefghijklmnopqrstuvwxyz012345",
        "jane.doe@acme.co.uk",
        "12345678901",
    ):
        assert secret not in sanitised, f"{secret} survived redaction"

    # 3. Placeholders took their place.
    assert "[EMAIL_001]" in sanitised
    assert "[API_KEY_001]" in sanitised or "[DB_CONNECTION_001]" in sanitised

    # 4. The document becomes memory.
    learned = engine.learn_from_document(
        sanitised, source=document["filename"], workspace_id="ws-e2e", document_id="doc-e2e"
    )
    assert len(learned["stored"]) > 0, "the document produced no memory at all"

    # 5. A question retrieves it, compressed and within budget.
    built = engine.build_context(
        "What are the indemnity and termination risks?",
        workspace_id="ws-e2e",
        token_budget=1200,
    )
    pack = built["pack"]
    assert pack["retrievedCount"] > 0
    assert pack["tokenEstimateAfter"] <= 1200

    # 6. The final gate permits it, because nothing sensitive survived.
    assert built["verification"]["mayTransmit"] is True, built["verification"]["message"]

    # 7. Nothing sensitive is in the rendered pack either.
    rendered = pack["rendered"]
    for secret in ("Hunter2Hunter2", "sk-proj-abcdefghij", "jane.doe@acme.co.uk"):
        assert secret not in rendered

    # 8. A model answers using placeholders, and restoration happens locally.
    model_response = "Under clause 4, [ORG_001] indemnifies the other party. Contact [EMAIL_001]."
    restored = engine.restore(scan["scanId"], model_response)["restoredText"]
    assert "jane.doe@acme.co.uk" in restored, "local restoration did not put the real value back"
    assert "[EMAIL_001]" not in restored


def test_a_word_the_user_protects_is_redacted_out_and_restored_back(engine: LocalEngine):
    """The whole point of letting someone mark their own words.

    "Falcon" is not a name, an email or a credential, so no detector would ever flag it. The user
    knows it matters and says so. From that moment it has to behave exactly like anything the
    detectors found by themselves: hidden on the way out, real again on the way back, and with the
    mapping never leaving this machine.
    """
    sentence = "Project Falcon slipped because Northwind pulled their funding."
    scan = engine.scan_text(sentence, protected_terms=["Falcon", "Northwind"])

    assert "Falcon" not in scan["sanitisedText"], "a protected word was about to be sent in clear"
    assert "Northwind" not in scan["sanitisedText"]

    answer = engine.restore(scan["scanId"], f"Summary: {scan['sanitisedText']}")["restoredText"]
    assert "Falcon" in answer and "Northwind" in answer, "the real words did not come back"


def test_protecting_a_word_does_not_disturb_the_detectors_own_findings(engine: LocalEngine):
    scan = engine.scan_text(
        "Email jane@acme.com about Falcon.", protected_terms=["Falcon"]
    )
    assert "jane@acme.com" not in scan["sanitisedText"]
    assert "Falcon" not in scan["sanitisedText"]


def test_a_protected_word_never_appears_in_anything_the_engine_hands_back(engine: LocalEngine):
    """Decision P2. The word is the secret; a payload that echoes it defeats the exercise."""
    scan = engine.scan_text("Project Falcon is late.", protected_terms=["Falcon"])
    rendered = json.dumps(scan)
    assert "Falcon" not in rendered, "the scan result leaked the very word it was hiding"


def test_a_credential_alone_blocks_the_outbound_gate(engine: LocalEngine):
    verdict = engine.verify_outbound(
        "Please review this: OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    )
    assert verdict["mayTransmit"] is False
    assert verdict["outcome"] == "blocked"


def test_fast_mode_processes_a_document_without_loading_any_model(
    engine: LocalEngine, contract_file: Path
):
    processed = engine.process_document(str(contract_file), mode=PrivacyMode.FAST)
    routing = processed["scan"]["routing"]

    assert routing["mode"] == "fast"
    assert routing["modelsLoaded"] == [], "FAST mode must not load a model"
    # It still has to catch the credentials, or the mode is worthless.
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz012345" not in processed["scan"]["sanitisedText"]


def test_workspace_memory_does_not_leak_between_workspaces(engine: LocalEngine):
    engine.remember(
        "Acme prefers a capped indemnity", "workspace", 0.9, source="a.pdf", workspace_id="ws-alpha"
    )
    engine.remember(
        "Zenith demands unlimited indemnity", "workspace", 0.9, source="b.pdf", workspace_id="ws-beta"
    )

    alpha = engine.recall("indemnity preference", workspace_id="ws-alpha")
    contents = [hit["memory"]["content"] for hit in alpha["hits"]]

    assert any("Acme" in item for item in contents)
    assert not any("Zenith" in item for item in contents), "workspace memory leaked"


def test_forgetting_a_workspace_removes_only_that_workspace(engine: LocalEngine):
    engine.remember("Gamma fact", "workspace", 0.9, source="c.pdf", workspace_id="ws-gamma")
    engine.remember("Delta fact", "workspace", 0.9, source="d.pdf", workspace_id="ws-delta")

    removed = engine.forget_workspace("ws-gamma")["forgotten"]
    assert removed >= 1

    remaining = engine.search_memories("Delta")["memories"]
    assert any("Delta fact" in item["content"] for item in remaining)
    assert all("Gamma fact" not in item["content"] for item in engine.search_memories("Gamma")["memories"])


def test_memories_survive_a_reload(engine: LocalEngine):
    """The vault persists; this proves the engine can be rehydrated from what it persisted."""
    engine.remember(
        "Reload survivor: the client signs on Tuesdays",
        "workspace",
        0.9,
        source="e.pdf",
        workspace_id="ws-reload",
    )
    exported = engine.export_memories()["memories"]
    assert len(exported) > 0

    fresh = LocalEngine()
    try:
        loaded = fresh.load_memories(exported)
        assert loaded["loaded"] == len(exported)

        found = fresh.search_memories("Reload survivor")["memories"]
        assert any("Reload survivor" in item["content"] for item in found)
    finally:
        fresh.shutdown()


def test_a_malformed_stored_memory_does_not_destroy_the_rest(engine: LocalEngine):
    fresh = LocalEngine()
    try:
        result = fresh.load_memories(
            [
                {"id": "1", "content": "good one", "scope": "global", "createdAt": "2026-01-01T00:00:00+00:00",
                 "lastAccessedAt": "2026-01-01T00:00:00+00:00", "lastUpdatedAt": "2026-01-01T00:00:00+00:00"},
                {"id": "2", "scope": "nonsense"},
                {"id": "3", "content": "another good one", "scope": "global", "createdAt": "2026-01-01T00:00:00+00:00",
                 "lastAccessedAt": "2026-01-01T00:00:00+00:00", "lastUpdatedAt": "2026-01-01T00:00:00+00:00"},
            ]
        )
        assert result["loaded"] == 2, "one bad row must not cost the user every memory"
    finally:
        fresh.shutdown()


# ---------------------------------------------------------------------------
# The stdio protocol, exercised as a real subprocess
# ---------------------------------------------------------------------------


def run_protocol(requests: list[dict]) -> list[dict]:
    """Drives the engine exactly as the Rust supervisor does: a child process over pipes."""
    payload = "\n".join(json.dumps(request) for request in requests) + "\n"
    completed = subprocess.run(
        [sys.executable, "-m", "hawkvance_engine"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def test_the_stdio_protocol_answers_every_request_it_is_given():
    replies = run_protocol(
        [
            {"id": 1, "method": "ping"},
            {"id": 2, "method": "hardware.detect"},
            {
                "id": 3,
                "method": "privacy.scanText",
                "params": {"text": "Mail jane@acme.com, key sk-live-abcdefghijklmnop", "mode": "fast"},
            },
            {
                "id": 4,
                "method": "privacy.verifyOutbound",
                "params": {"text": "key sk-live-abcdefghijklmnopqrst"},
            },
        ]
    )

    assert len(replies) == 4
    assert all(reply["ok"] for reply in replies), replies

    by_id = {reply["id"]: reply["result"] for reply in replies}
    assert by_id[1]["pong"] is True
    assert by_id[2]["systemClass"] in ("low", "medium", "high")
    assert "jane@acme.com" not in by_id[3]["sanitisedText"]
    assert by_id[3]["routing"]["modelsLoaded"] == []
    assert by_id[4]["mayTransmit"] is False


def test_the_protocol_reports_an_unknown_method_rather_than_dying():
    replies = run_protocol([{"id": 1, "method": "does.not.exist"}, {"id": 2, "method": "ping"}])

    assert replies[0]["ok"] is False
    assert "Unknown method" in replies[0]["error"]["message"]
    assert replies[1]["ok"] is True, "one bad request must not take the engine down"


def test_the_protocol_never_returns_a_redaction_mapping():
    """The single most important property in the product, checked at the boundary that matters."""
    replies = run_protocol(
        [
            {
                "id": 1,
                "method": "privacy.scanText",
                "params": {"text": "John Doe at john@example.com", "mode": "fast"},
            }
        ]
    )
    serialised = json.dumps(replies)

    assert "john@example.com" not in serialised, "the original value crossed the process boundary"
    assert "originals" not in serialised
    assert "[EMAIL_001]" in serialised


def test_a_document_map_outlives_its_scan_and_restores_later(engine: LocalEngine):
    """The bug that made every document answer unreadable.

    A document is scanned once, at upload. Only the sanitised text is kept, so before this the
    mapping died with the scan and [ORG_001] could never be turned back into a company name. This
    is the whole reason exporting the map exists, so it is tested the way it actually happens: scan,
    throw the scan away, and try to restore from a completely different one.
    """
    original = "Northwind Traders signed with jane@acme.co.uk on the Falcon project."
    # Protected terms rather than relying on the detectors: whether a given name is recognised as an
    # organisation varies with the model, and a test of persistence should not also be a test of
    # detection.
    first = engine.scan_text(original, protected_terms=["Northwind Traders"])
    exported = engine.export_map(first["scanId"])["entries"]
    assert exported, "a scan with detections exported no mapping at all"

    sanitised = first["sanitisedText"]
    engine.close_scan(first["scanId"])

    # A later conversation, scanning the already-sanitised text. This scan has never seen the
    # originals, which is exactly the situation chat is in.
    second = engine.scan_text(sanitised)
    assert "Northwind" not in engine.restore(second["scanId"], sanitised)["restoredText"], (
        "the second scan restored a value it was never given, so this test proves nothing"
    )

    engine.load_map(second["scanId"], exported)
    restored = engine.restore(second["scanId"], sanitised)["restoredText"]

    assert "Northwind Traders" in restored, "the stored mapping did not restore the company"
    assert "jane@acme.co.uk" in restored, "the stored mapping did not restore the address"


def test_an_exported_map_covers_every_placeholder_in_the_sanitised_text(engine: LocalEngine):
    """A partial map is worse than none: the reader cannot tell which names are real."""
    import re as _re

    scan = engine.scan_text("Contact John Smith at john@acme.com about Northwind Traders.")
    placeholders = set(_re.findall(r"\[[A-Z][A-Z0-9_]*\]", scan["sanitisedText"]))
    exported = {entry["placeholder"] for entry in engine.export_map(scan["scanId"])["entries"]}

    assert placeholders <= exported, f"no mapping for {placeholders - exported}"


def test_loading_a_map_never_overwrites_what_this_scan_resolved(engine: LocalEngine):
    """A stored entry may belong to an older version of the same document. The live scan matches the
    text actually in front of us, so it wins."""
    scan = engine.scan_text("Email jane@acme.com today.")
    placeholder = engine.export_map(scan["scanId"])["entries"][0]["placeholder"]

    engine.load_map(scan["scanId"], [{"placeholder": placeholder, "original": "stale@old.example"}])
    restored = engine.restore(scan["scanId"], scan["sanitisedText"])["restoredText"]

    assert "jane@acme.com" in restored
    assert "stale@old.example" not in restored


def test_an_exported_map_is_not_carried_inside_any_scan_result(engine: LocalEngine):
    """P2. Exporting is a deliberate call the Rust core makes; it must never ride along in the
    ordinary scan payload the web view already receives."""
    scan = engine.scan_text("Northwind Traders signed today.", protected_terms=["Northwind Traders"])
    assert "Northwind" not in json.dumps(scan), "a scan result carried an original value"
    # The mapping is reachable, but only by asking for it deliberately.
    assert any(
        entry["original"] == "Northwind Traders"
        for entry in engine.export_map(scan["scanId"])["entries"]
    )
