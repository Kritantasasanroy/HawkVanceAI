# Design — Privacy & Redaction Pipeline

Status: accepted
Scope: spec sections 7, 8 and 34. Implemented in Phase 3 of the build; modelled now because the
decisions here constrain the document pipeline and the context builder that come before it.

## The four product decisions

Given by the product owner, binding on the implementation:

- **P1 — Numbered pseudonyms.** `[PERSON_1]`, `[ORG_1]`, `[EMAIL_1]`. One real value maps to one tag
  for the whole lifetime of a ContextPack, so coreference survives redaction and the model can still
  reason about who did what with whom.
- **P2 — Auto-restore, strictly local.** The response is un-redacted before the user reads it, and
  the mapping that makes that possible never leaves the device. See the invariant below.
- **P3 — All categories on by default, with a pre-redaction confirmation.** Every detector is
  enabled out of the box, and the user sees the category list with checkboxes before redaction runs.
- **P4 — Balanced threshold.** Above 85% confidence redacts silently. 50% to 85% is surfaced amber
  in the Privacy Gate, pre-selected to redact, one click to keep. Below 50% is not surfaced.

## The one invariant that outranks everything else

> The mapping from placeholder to original value is written only to the local encrypted vault. It is
> never placed in an outbound request body, never written to any log, never included in telemetry,
> never synced to the backend, and never reaches any LLM. Restoration runs on-device, against the
> response text only.

This is not a preference to be traded against convenience later. Every other feature in the product
gives way to it. A code path that could carry the mapping off-device is treated as a CAPITAL-class
defect, not a bug to schedule.

Two structural consequences, so the invariant is enforced by shape rather than by discipline:

1. `RedactionMap` lives in the desktop process only. It has no serialiser targeting the wire, no
   representation in the shared contracts package, and no field on any request type. The backend
   literally has no type that could receive it.
2. The type sent outward is `SanitisedText`, which is constructible only as the output of applying a
   `RedactionMap` and which carries no reference back to the map it came from. Once text is
   sanitised, the original is not reachable from it.

## Durable-noun pass

The feature arrives as "detect and hide sensitive data." Detection is a verb and sensitivity is a
judgement, so neither is the concept. The nouns:

| Candidate | Verdict |
|---|---|
| Redaction | concept. A replacement of a text region with a placeholder is a durable record. |
| RedactionMap | concept. The set of redactions over one text, holding the non-overlap invariant. |
| PiiCategory | enum. What kind of sensitive thing this is. |
| Detector | concept. A named source of detections with its own precision characteristics. |
| SanitisedText | value type. Text that has provably been through the pipeline. |
| PrivacyLedger | concept, append-only. What the Privacy Dashboard in section 34 counts. |
| PiiFinding | rejected. "Finding" is a padding word (L26); strip it and it is a Redaction. |
| RedactionEngine | rejected. Suffix hiding the map's own behaviour (L26/L27). |
| SensitiveSpan | rejected. Adjective bolted on a noun; sensitivity is a category, not a kind. |

## Concepts

### Redaction — concept, ours

One replacement of one text region.

| Field | Type | Notes |
|---|---|---|
| start | int | character offset, inclusive |
| end | int | character offset, exclusive |
| category | PiiCategory | |
| placeholder | Placeholder | e.g. `PERSON_1` |
| confidence | Confidence | 0.0 to 1.0 |
| detector | DetectorKind | `regex`, `checksum`, `entropy`, `ner`, `customRule` |
| originalHash | string | SHA-256 of the original value. The original itself is never on this type. |

Behaviour on the entity, not in a free function (L27): `overlaps(other)`, `contains(other)`,
`length`, `outranks(other)`.

Offsets are character offsets into the normalised text, and they are the reason normalisation must
happen exactly once, before detection. A redaction computed against one normalisation and applied
against another silently corrupts the document.

`originalHash` exists so the Privacy Dashboard can count distinct values detected without storing
any of them, and so a repeat detection of the same value can be recognised across documents. The
original value itself lives only in `RedactionMap`, never on the `Redaction`.

### RedactionMap — concept, ours

The complete, conflict-resolved set of redactions over one text, plus the local-only reverse
mapping.

Invariants it exists to hold, which is what earns it a type rather than being a plain array:

1. No two redactions overlap. This is spec section 7's stage 4, and it is enforced at construction,
   not checked later.
2. Redactions are ordered by start offset.
3. One original value has exactly one placeholder, so `[PERSON_1]` means the same person everywhere
   in the text. This is P1, and it is a property of the map, not of any individual redaction.
4. Placeholder numbering is stable within the map and restarts per category.

Conflict resolution, spec section 7 stage 4, is `merge()` on this type. When detectors disagree
about overlapping regions the rule is: higher confidence wins; on a tie the more specific category
wins (an API key beats a generic secret); on a further tie the longer span wins, because a partially
redacted secret is a leaked secret.

`apply(text)` produces `SanitisedText`. `restore(text)` is the P2 reverse direction and is the only
method that can see original values.

### PiiCategory — enum, general

Grouped into the four toggles the user confirms before redaction (P3):

- **Secrets and credentials**: `apiKey`, `accessToken`, `password`, `privateKey`, `connectionString`,
  `credentialInUrl`. Detected by regex plus Shannon-entropy scoring.
- **Direct identifiers**: `email`, `phone`, `creditCard`, `bankAccount`, `iban`, `nationalId`,
  `ipAddress`. Regex plus checksum validation, so a Luhn-failing 16-digit number is not a card.
- **Names, organisations and places**: `person`, `organization`, `location`, `gpe`. Local ONNX NER.
  This is the group carrying real false-positive risk on technical and legal text.
- **Dates, addresses and money**: `streetAddress`, `dateOfBirth`, `monetaryAmount`.

Plus `customRule` for the enterprise patterns in spec section 7 stage 3.

The secrets group is on by default like the others, but its default is argued differently: a leaked
credential is unrecoverable in a way a leaked name is not, and its detectors are near-zero
false-positive. The UI presents it checked with a note explaining why unchecking it is a bad idea.
The user may still uncheck it; P3 says the choice is theirs.

### Confidence and the threshold

`Confidence` is a value type over 0.0 to 1.0, not a bare float, because a bare float invites
comparison against the wrong scale.

`RedactionDisposition` is the P4 decision, derived rather than stored: `autoRedact` above 0.85,
`needsReview` from 0.50 to 0.85, `ignored` below 0.50. It is a computed property so the thresholds
can move in configuration without a migration, and so the disposition can never disagree with the
confidence it came from.

`needsReview` is exactly what the Privacy Gate in spec section 8 renders amber, pre-selected. The
user is the tiebreaker, never the model.

### PrivacyLedger — concept, ours, append-only

What spec section 34's dashboard counts. One row per privacy-relevant event:
`occurredAt`, `eventKind`, `documentId or absent`, `categoryCounts`, `contextPackId or absent`.

`eventKind` covers `documentProcessedLocally`, `piiDetected`, `contextPackBuilt`,
`contextPackApproved`, `contextPackSent`.

Append-only, and it stores counts, never values. The claim the dashboard makes, "raw document
transmission: 0", has to be backed by a record that could in principle have shown otherwise;
otherwise it is decoration. The count of `contextPackSent` events with a non-sanitised payload is
structurally always zero because `SanitisedText` is the only type the gateway accepts.

## Pipeline shape

```
raw text
   |
   v
normalise once            <- offsets are meaningless without this
   |
   v
category confirmation     <- P3, user checks/unchecks before anything runs
   |
   v
detectors in parallel     <- regex | checksum | entropy | NER | custom rules
   |                         only the enabled categories load their models (spec section 4)
   v
RedactionMap.merge()      <- spec section 7 stage 4, conflict resolution
   |
   v
disposition split         <- P4: auto | needsReview | ignored
   |
   v
Privacy Gate              <- spec section 8, user approves or edits
   |
   v
map.apply() -> SanitisedText
   |
   v
[ leaves the device ]
   |
   v
LLM response
   |
   v
map.restore()             <- P2, local only, map never left the device
   |
   v
user reads real values
```

## Where the mapping lives, and why that changed

Originally the `RedactionMap` existed only inside the engine process, for the life of one scan. That
was the strongest possible position and it made the product's central feature impossible.

A document is scanned once, when it is added. Only the sanitised text is stored. So the mapping died
with that scan, and from then on every placeholder in that document was unresolvable: an answer
about it could only ever read `[ORG_003]`. Restoration for documents was not broken, it had never
been able to work.

The mapping is now also written to the local vault, in `redaction_map_entries`, one row per
placeholder, each value sealed with the same per-value cipher as document text on top of the
whole-file encryption. Rust reads it from the engine and writes it in a single command; it is not
relayed through the web view, which is the least trusted process in the app. `privacy.exportMap` is
on a deny-list for the engine passthrough, so the renderer cannot ask for it.

The invariant in rule 1 below is unchanged, and so are the two structural consequences that enforce
it: there is still no wire serialiser, no type in the shared contracts package, and no field on any
request the backend could receive. What changed is that the mapping now survives on this device
instead of being destroyed, which is what the rule always allowed.

## Rules that must always hold

1. The placeholder-to-original mapping never leaves the device, by any path, in any form.
2. Text is normalised exactly once, before detection, and every offset refers to that normalisation.
3. No two redactions in a map overlap.
4. One original value has one placeholder per map.
5. On a confidence tie between overlapping detections, the longer span wins. A partially redacted
   secret is a leaked secret.
6. Only `SanitisedText` can be handed to the gateway. There is no overload accepting a raw string.
7. The privacy ledger stores counts and categories, never values.
8. A detector model is loaded only when its category is enabled and a document needs it, and is
   released afterwards (spec section 4's lazy loading).
