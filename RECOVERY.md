# Data loss, 3 September 2026

Files were deleted from this working tree. There was no git repository at the time,
no backup, and nothing in the Recycle Bin, so most of what was lost is not
recoverable from this machine. This file records exactly what survived and what
did not, so nobody has to rediscover it later.

The repository was created *after* the loss, from what remained. The first commit
is therefore a partial tree, not the project as it stood.

## What survived

| Area | State |
| --- | --- |
| `apps/engine/` | Intact. Python source, tests, PyInstaller spec, `pyproject.toml`. |
| `apps/backend/` | Intact. 27 source files, `package.json`, `tsconfig.json`. |
| `packages/contracts/` | Intact. |
| `packages/llm/` | Intact. |
| `docs/`, `scripts/`, `assets/` | Intact. |
| `apps/desktop/src-tauri/target/` | Compiled output only: `hawkvance.exe` and the signed installer. |

## What was lost

| Area | Detail |
| --- | --- |
| `apps/desktop/src/` | The entire React renderer. Roughly 25 files: every screen, `theme.css`, the session and vault stores, the API client. |
| `apps/desktop/src-tauri/src/` | The entire Rust core. Around 12 modules and 51 tests: the vault, SQLCipher storage, value sealing, Neon Auth client, the engine subprocess bridge, hardware detection. |
| `apps/desktop/src-tauri/` config | `Cargo.toml`, `tauri.conf.json`, `build.rs`, `icons/`. |
| `apps/desktop/` config | `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `.env`. |
| `apps/admin/` | Everything. The directory is empty. |
| Root config | `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `.gitignore`, `.env`, tsconfig files, `README.md`. |
| `.keys/` | The updater signing key, both halves. |

## Reconstructed rather than recovered

These were rewritten from knowledge of how the project was set up. They are not the
originals and should be reviewed:

- `package.json` at the root
- `pnpm-workspace.yaml`
- `.gitignore`

`pnpm-lock.yaml` was **not** reconstructed. Dependency versions in the surviving
per-package manifests are exact, but the resolved transitive tree is gone, so a
fresh `pnpm install` may not reproduce the exact versions the last build used.

## Recovery routes already tried and exhausted

- **Recycle Bin** — empty. The deletion bypassed it or it was emptied afterwards.
- **OneDrive** — the Desktop is not redirected into OneDrive. The only match found
  there is an unrelated older prototype.
- **File History** — not configured on this machine.
- **Source maps or a `dist/` build** — none present anywhere on disk.
- **The compiled binary** — Tauri compresses embedded frontend assets, so the
  renderer cannot be read back out of `hawkvance.exe` as source. Even if
  decompressed it would be minified output, not the original TypeScript.

## Not yet tried, and worth trying before rewriting anything

**Volume Shadow Copies.** Querying them requires an elevated prompt, which was not
available. From an Administrator PowerShell:

```powershell
vssadmin list shadows
```

If a snapshot predates the deletion, the whole tree may be restorable. Windows
Explorer exposes the same thing: right-click the `Hawkvance` folder, then
**Restore previous versions**. This is the single best remaining chance and is
worth doing before any decision to rewrite.

## The signing key

`.keys/hawkvance-updater.key` is gone, and its public half was inside the deleted
`tauri.conf.json`.

The already-built installer at
`apps/desktop/src-tauri/target/release/bundle/nsis/` was signed with that key. Any
copy of the app installed from it will only accept updates signed by the same key,
which no longer exists. Generating a new pair is straightforward, but every install
from the old build is then stranded on its current version permanently.

Since that installer was never distributed publicly, generating a fresh pair costs
nothing. Do it before shipping:

```
pnpm --filter @hawkvance/desktop exec tauri signer generate -w .keys/hawkvance-updater.key
```

Then put the contents of the `.pub` file into `plugins.updater.pubkey` in
`tauri.conf.json`, and keep the private half somewhere other than this laptop.
