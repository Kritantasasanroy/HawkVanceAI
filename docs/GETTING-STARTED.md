# HawkVance AI — running it and using it

Two halves: getting the thing running on a developer machine, and using the app once it is.

---

## Part 1 — Start the project

### What you need once

| Requirement | Why | Check it |
|---|---|---|
| Node 20+ and pnpm | Backend, desktop shell, shared packages | `node -v && pnpm -v` |
| Rust toolchain | The desktop core is Rust | `cargo --version` |
| Python 3.12 | The local privacy and memory engine | `python --version` |
| WebView2 | The app window (already on Windows 11) | Preinstalled |
| Strawberry Perl | Only needed to build OpenSSL from source | `perl -v` |

### First time setup

```bash
pnpm install
pnpm --filter @hawkvance/contracts build
pnpm --filter @hawkvance/llm build
```

Then the Python engine, which is a separate virtual environment:

```bash
cd apps/engine
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[documents,ner,ocr]"
.venv/Scripts/python.exe -m spacy download en_core_web_sm
cd ../..
```

### Configuration

Copy `.env.example` to `.env` and fill it in. Four values are required and the backend refuses to
start without them, by design:

- `DATABASE_URL` — your Postgres connection string
- `ENCRYPTION_KEY` — any long random string
- `NEON_AUTH_URL` — the auth endpoint, ending in `/neondb/auth`
- `NEON_JWKS_URL` — the same host plus `/.well-known/jwks.json`

**`CORS_ALLOWED_ORIGINS` must include the desktop app.** It is easy to assume a native app needs no
browser origin. Its window is a web view, so it has one. Leave it out and sign-in appears to work
and is then silently refused, with nothing in the server log:

```
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174,http://tauri.localhost,https://tauri.localhost,tauri://localhost
```

Apply the database schema once:

```bash
pnpm --filter @hawkvance/backend db:migrate
```

### Running it day to day

Two processes. The backend, from `apps/backend`:

```bash
node --env-file=../../.env --import tsx src/main.ts
```

Check it with `curl http://127.0.0.1:8080/health` — you want `"database":true`.

Then the desktop app, from `apps/desktop`:

```bash
pnpm app:dev
```

`pnpm app:dev` gives you hot reload against the Vite dev server. To test what a user actually
installs, build the real thing instead:

```bash
npx tauri build --bundles nsis
```

The installer lands in `apps/desktop/src-tauri/target/release/bundle/nsis/`.

> Build the real app before believing sign-in works. The dev server runs on a different origin from
> the packaged app, so CORS behaves differently between them. That difference hid a bug for a long
> time.

### Tests

```bash
pnpm -r typecheck
pnpm --filter @hawkvance/contracts test          # 19
pnpm --filter @hawkvance/backend test            # 62
cd apps/engine && .venv/Scripts/python.exe -m pytest -q   # 194
cd apps/desktop/src-tauri && cargo test          # 34
```

Two extras that do reach the network, so they are off by default:

```bash
HAWKVANCE_LIVE_AUTH=1 cargo test        # signs in against the real auth service
node scripts/e2e-live.mjs               # end to end against the live backend
```

---

## Part 2 — Use the app

### Sign in

Enter your email, get a six-digit code, type it in. There is no separate sign-up: the same code
creates your account the first time. No password is ever chosen or stored.

The session lives in the app's Rust core and is deliberately never written to disk, so **closing the
app signs you out**. That is the trade for never leaving a long-lived credential on the machine.

### 1. Make a workspace

**Workspaces → Create.** A workspace keeps one project's documents and memory apart from another's.
Work documents and personal ones should not share a memory, and this is the boundary that stops it.

### 2. Add a document

**Documents → Add a document.** Four named steps, and nothing is stored until the last one:

1. **Choose a file** — PDF, Word, spreadsheet, image, or code.
2. **Set what to hide** — four groups, all on by default, plus how carefully to look.
   *Quick* matches patterns like emails and card numbers. *Normal* also reads sentences to find
   names and places. *Thorough* adds a second opinion for anything unusual.
3. **Read and check** — extraction, image reading and detection, all on this computer.
4. **Review and save** — what was found, and a preview of exactly what would be sent.

Press **Save** to keep it, or **Discard** to leave no trace. Discarding really does keep nothing.

### 3. Hide your own words

The detectors find emails, names and card numbers. They cannot know that "Falcon" is your unreleased
product, because nothing about that word looks sensitive.

In the review step, **click any word in the preview to hide it**, or type it into *Words you always
hide*. Then press **Update preview** to see the result.

From that point, in that workspace, the word behaves exactly like anything the detectors found:

- Replaced with a label such as `[REDACTED_001]` in anything sent out
- Hidden in questions too, not only documents
- **Put back automatically in the answer, on this computer**

So you can ask about Falcon and read an answer about Falcon, while the model that answered only ever
saw `[REDACTED_001]`. The list mapping labels back to real words never leaves this machine — there is
no code path that transmits it.

Remove a word by clicking its chip.

### 4. Ask a question

**Chat.** Pick which model answers from the dropdown, type your question, then **Review and send**.

Before anything leaves, the privacy gate shows you the exact text that would be sent and what has
been hidden. Approve it, or cancel. If something high-risk survives, the send is blocked rather than
sent.

The answer comes back with hidden values restored locally, and tells you how many were put back.

### 5. The rest

- **Memory** — what HawkVance has learned. Pin what matters, edit what is wrong, forget anything.
- **Privacy** — a running count of what has been redacted and what was processed here.
- **AI models** — free models, or add your own provider key. Keys are stored in Windows Credential
  Manager and shown only as a fingerprint, never displayed back.
- **Settings** — machine details and processing speed.

---

## When something breaks

| What you see | What it means |
|---|---|
| "You have been signed out" | Expected after restarting the app. Sign in again. |
| Sign-in gets stuck | Press **Show connection details**. It only checks reachability and sends no code. |
| "Local engine not installed" | The Python engine is missing. Redo the `apps/engine` setup above. |
| Chat says models could not load | The backend is not running, or its CORS list is missing the app's origin. |
| Backend exits at startup | One of the four required values is absent from `.env`. It says which. |

**Rotate your credentials** if a database URL or API key has ever been pasted into a chat, an issue,
or a screenshot.
