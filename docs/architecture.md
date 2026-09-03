# Architecture

## The principle everything else serves

The LLM is the reasoning engine. HawkVance owns the user's private context, memory and
personalisation layer. Every design decision below follows from that split:

```
LOCAL AI  = privacy + processing + memory
CLOUD LLM = reasoning
```

The local model is deliberately **not** exposed as a chatbot. It exists to do PII detection, entity
recognition, classification, summarisation, memory extraction and importance scoring. If a user ever
gets a general-purpose answer, it came from a cloud model that received sanitised context.

## System shape

```
                        HAWKVANCE DESKTOP  (Tauri v2)
                                  |
              +-------------------+-------------------+
              |                                       |
        React renderer                          Rust core
        (no filesystem, no                (vault, master key, model
         direct DB access)                 runtime, hardware profile)
              |                                       |
              +------------- Tauri IPC ---------------+
                                  |
                                  v
                        ENCRYPTED LOCAL VAULT
                     AES-256-GCM per value, key in
                       Windows Credential Manager
                                  |
        +-------------------------+------------------------+
        |             |              |            |         |
   documents      redactions      memories   conversations  privacy
                +redaction map                              ledger
                (never leaves)
                                  |
                                  v
                         CONTEXT BUILDER
                  retrieve -> rank -> compress -> sanitise
                                  |
                                  v
                          PRIVACY GATE  (user approves)
                                  |
                              SanitisedText
                                  |
                                HTTPS
                                  |
                                  v
                        HAWKVANCE BACKEND  (Fastify)
                    auth · quotas · usage · admin · gateway
                                  |
                                  v
                            MODEL ROUTER
                                  |
              +-------------------+-------------------+
              |                                       |
        HawkVance AI                                BYOK
     (our OpenRouter key,                    (user's own provider
      server-side only)                       credential)
```

## Why Tauri

The spec prioritises performance, low RAM, startup time, native OS integration and secure local
storage, and targets machines with as little as 4 GB. Tauri renders through the WebView2 runtime
that Windows 11 already ships, so nothing bundles a browser: roughly a 10 MB installer and 80 MB
idle against Electron's ~180 MB and ~250 MB. On a 4 GB machine that difference is most of what a
quantised local model needs to fit alongside the user's real work.

The legacy prototype was Python and tkinter. Preserving it was considered and rejected: tkinter
cannot deliver the required UI, an NSIS/MSI installer, auto-update, or OS credential storage.

## The two databases, and why they are shaped alike

| | Local (desktop) | Cloud (backend) |
|---|---|---|
| Engine | SQLite, AES-256-GCM per value | PostgreSQL |
| Vectors | embedding blobs, `sqlite-vec` when memory lands | pgvector |
| Holds | documents, extracted text, redactions, **redaction map**, memories, conversations, privacy ledger, settings | accounts, OTP challenges, sessions, devices, plan limits, usage records, activity events, admin audit |
| Never holds | account credentials | document content, extracted text, redaction maps, chat content |

The split is the product. Content lives locally; operational metadata lives in the cloud. The
backend has no table that could accept a document body, which is a stronger guarantee than a policy
saying it will not.

## Module boundaries

Backend modules are reached through their public service or repository, never by importing
internals. `identity/` owns Account, OtpChallenge, Session, Device and PlanLimits. Decisions that
span concepts live on a writer (`SessionWriter.openFromOtp`, `OtpChallengeWriter.issueAndSend`);
routes orchestrate and never decide.

Four transaction units: Account (with its Devices), OtpChallenge, Session, UsageRecord. Units
reference each other by id, never by held object.

## Resource-aware local AI

A large model is never held resident. Each capability is loaded on demand and released:

```
Model runtime
  ├── PII regex + checksum + entropy   (no model at all)
  ├── NER                              ONNX, loaded only if that category is enabled
  ├── Summariser                       llama.cpp GGUF, loaded per job
  ├── Classifier                       ONNX
  ├── Embeddings                       ONNX
  └── OCR                              Tesseract, loaded per image
```

Detecting an email address must never load a general-purpose model. `HardwareProfile` picks the
mode on first run: low under 6 GB RAM, balanced under 12 GB or fewer than 4 logical cores,
performance above that.

## Memory hierarchy

```
GLOBAL MEMORY
     |
     +---------------------------+
     |                           |
WORKSPACE MEMORY           PERSONAL MEMORY
     |
     +--------------+
     |              |
FILE MEMORY   CONVERSATION MEMORY
```

Retrieval ranks current document, then current workspace, then related documents, then conversation
memory, then global preferences. Relevance always beats volume: workspace memory does not leak into
unrelated workspaces, and global memory is injected only when it earns its tokens.

Tiers age by access and importance, not by date alone: HOT 0-15 days, WARM 15-180, COLD 180+.
Pinned memories are never automatically compressed or deleted.

## Context compression

```
500,000 tokens of history
   -> retrieval        25,000
   -> relevance rank   10,000
   -> compression       4,000
   -> Context Pack -> privacy gate -> LLM
```

The whole memory bucket is never sent. The Context Builder optimises for relevance, completeness,
low token usage, privacy and redundancy removal, in that order.

## Prompt injection boundary

Document content is data, never instruction. The context pack keeps four channels separate and
labelled, and nothing in the document or memory channel can alter system instructions, privacy
controls or tool permissions:

```
SYSTEM INSTRUCTIONS   trusted, ours
USER INSTRUCTIONS     trusted, the person at the keyboard
DOCUMENT CONTENT      untrusted data
MEMORY                untrusted-ish, machine-derived
```

## Request flow, end to end

1. User drops a file. Rust hashes it, stores it locally, and queues it. The file never uploads.
2. Extraction runs locally, OCR only if needed. Text is normalised **once**; every later offset
   refers to that normalisation.
3. The user confirms which detector categories to run.
4. Detectors run in parallel. Findings merge into a `RedactionMap` with a no-overlap invariant.
5. Above 85% confidence redacts silently; 50-85% surfaces amber in the gate; below 50% is dropped.
6. The user reviews and approves the Context Pack.
7. `SanitisedText` goes to the backend. The gateway has no overload that accepts a raw string.
8. The response returns; the local `RedactionMap` restores real values before display.
9. The conversation is summarised locally into a candidate memory, scored, and filed by tier.

Steps 1 through 6 and step 9 never touch the network.
