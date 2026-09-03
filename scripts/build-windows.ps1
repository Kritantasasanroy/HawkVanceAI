# Builds HawkVance for Windows, end to end.
#
#   1. shared packages
#   2. the Python engine, frozen into a sidecar folder
#   3. the Tauri app, with the engine bundled as a resource
#
# Run from the repository root in a shell that has Node, pnpm and the Rust toolchain on PATH.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "==> 1/4  Installing workspace dependencies" -ForegroundColor Cyan
Push-Location $root
pnpm install --frozen-lockfile
pnpm --filter @hawkvance/contracts build
pnpm --filter @hawkvance/llm build

Write-Host "==> 2/4  Freezing the local engine" -ForegroundColor Cyan
Push-Location "$root/apps/engine"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -e ".[documents,ner,ocr]"
    .\.venv\Scripts\python.exe -m spacy download en_core_web_sm
}
.\.venv\Scripts\python.exe -m pip install --upgrade pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller hawkvance-engine.spec --noconfirm --clean
Pop-Location

$engineOut = "$root/apps/engine/dist/hawkvance-engine"
if (-not (Test-Path $engineOut)) {
    throw "The engine build produced nothing at $engineOut"
}

Write-Host "==> 3/4  Staging the engine into the desktop resources" -ForegroundColor Cyan
$resources = "$root/apps/desktop/src-tauri/resources/engine"
if (Test-Path $resources) { Remove-Item -Recurse -Force $resources }
New-Item -ItemType Directory -Force $resources | Out-Null
Copy-Item -Recurse -Force "$engineOut/*" $resources

Write-Host "==> 4/4  Building the desktop application and installer" -ForegroundColor Cyan

# The updater signing key. Without it Tauri builds every bundle and then fails on the last step,
# because tauri.conf.json carries the public half and nothing can sign against it. The key is not
# in the repository, so a fresh clone has to be given one before it can cut a release.
$signingKey = Join-Path $root ".keys\hawkvance-updater.key"
if (-not (Test-Path $signingKey)) {
    throw @"
No updater signing key at $signingKey.

Restore the key from wherever it is kept, or generate a new pair with

    pnpm --filter @hawkvance/desktop exec tauri signer generate -w .keys/hawkvance-updater.key

and copy the contents of the .pub file into plugins.updater.pubkey in
apps/desktop/src-tauri/tauri.conf.json. A new pair invalidates updates for anyone
already running a build signed with the old one.
"@
}
$env:TAURI_SIGNING_PRIVATE_KEY = Get-Content $signingKey -Raw

# The key carries no password, and the build has to be told so. That is harder than it sounds:
# PowerShell cannot put an empty string in the environment. Assigning "" deletes the variable, and
# .NET's SetEnvironmentVariable treats empty and null as the same thing, as does cmd's `set`. With
# the variable simply absent, Tauri asks for the password on standard input, and an unattended
# build then waits at that prompt until somebody kills it. Node can pass an empty value, so the
# build is started through it.
$launcher = Join-Path $env:TEMP "hawkvance-signed-build.cjs"
Set-Content -Path $launcher -Encoding utf8 -Value @'
const { spawnSync } = require("node:child_process");
const result = spawnSync("pnpm", ["--filter", "@hawkvance/desktop", "app:build"], {
  stdio: "inherit",
  shell: true,
  env: { ...process.env, TAURI_SIGNING_PRIVATE_KEY_PASSWORD: "" },
});
process.exit(result.status ?? 1);
'@

node $launcher
if ($LASTEXITCODE -ne 0) {
    throw "The desktop build failed. See the output above."
}
Pop-Location

Write-Host ""
Write-Host "Done. Installers are under:" -ForegroundColor Green
Write-Host "  apps/desktop/src-tauri/target/release/bundle/nsis/"
Write-Host "  apps/desktop/src-tauri/target/release/bundle/msi/"
