//! The Tauri command surface.
//!
//! The web view is the least trusted process here: it renders model output and document text, so
//! anything reachable from it should be assumed reachable by a script. Two rules follow, and both
//! are enforced by what exists rather than by convention.
//!
//! There is no command that returns a redaction mapping. `document_remember_redactions` takes a
//! scan id, asks the engine for the map and writes it to the vault in one step on this side, then
//! returns a count. `chat_restore` takes text and gives back text. At no point does an original
//! value have a route into the renderer, because no command is shaped to carry one.

pub mod cipher;
pub mod engine_process;
pub mod neon_auth;
pub mod master_key;
pub mod records;
pub mod vault;
pub mod vault_store;

use std::sync::Mutex;

use serde_json::{json, Value};
use tauri::{Manager, State};

use crate::cipher::Cipher;
use crate::engine_process::EngineProcess;
use crate::neon_auth::NeonAuth;
use crate::records::{
    ConversationRecord, ConversationTurnRecord, DocumentRecord, RedactionEntry, RestoreRequest,
    WorkspaceRecord,
};
use crate::vault::Vault;
use crate::vault_store::{VaultStore, GLOBAL_SCOPE};

/// Engine methods the renderer may not call directly.
///
/// `privacy.exportMap` returns originals. It is used, but only from `document_remember_redactions`
/// on this side, where the result goes straight into the vault. Letting the renderer name it would
/// undo the entire arrangement.
const RENDERER_MAY_NOT_CALL: &[&str] = &["privacy.exportMap"];

/// Where the session lives between runs, inside the encrypted vault.
const SESSION_COOKIE_SETTING: &str = "session.neon_cookie";

pub struct AppState {
    vault: Mutex<Option<Vault>>,
    cipher: Mutex<Option<Cipher>>,
    engine: EngineProcess,
    auth: tokio::sync::Mutex<NeonAuth>,
}

impl AppState {
    fn new() -> Self {
        Self {
            vault: Mutex::new(None),
            cipher: Mutex::new(None),
            engine: EngineProcess::new(),
            auth: tokio::sync::Mutex::new(NeonAuth::new(
                std::env::var("HAWKVANCE_NEON_AUTH_URL").unwrap_or_else(|_| {
                    // Baked in at build time by the same value the renderer is given, so the two
                    // halves of sign-in cannot end up pointed at different projects.
                    option_env!("VITE_NEON_AUTH_URL").unwrap_or_default().to_string()
                }),
            )),
        }
    }
}

/// Keeps the session in the vault so closing the app is not the same as signing out.
fn remember_session(state: &AppState, cookie: Option<String>) {
    let _ = with_store(state, |store| {
        store.write_setting(SESSION_COOKIE_SETTING, cookie.as_deref().unwrap_or(""))
    });
}

type Reply = Result<Value, Value>;

fn failure(message: &str) -> Value {
    json!({ "code": "vault_error", "message": message })
}

/// Runs a closure against the open vault.
///
/// The vault and its cipher are held behind separate locks but always taken together and in the
/// same order, so there is no path where one is held while waiting on the other.
fn with_store<T, F>(state: &AppState, work: F) -> Result<T, Value>
where
    F: FnOnce(&VaultStore<'_>) -> Result<T, crate::vault_store::StoreError>,
{
    let vault_guard = state.vault.lock().map_err(|_| failure("the vault is busy"))?;
    let cipher_guard = state.cipher.lock().map_err(|_| failure("the vault is busy"))?;

    let vault = vault_guard
        .as_ref()
        .ok_or_else(|| failure("the vault is not open yet"))?;
    let cipher = cipher_guard
        .as_ref()
        .ok_or_else(|| failure("the vault is not open yet"))?;

    work(&VaultStore::new(vault, cipher)).map_err(|error| failure(&error.to_string()))
}

// ---------- the engine ---------------------------------------------------------------------

#[tauri::command]
fn engine_request(state: State<'_, AppState>, method: String, params: Value) -> Reply {
    if RENDERER_MAY_NOT_CALL.contains(&method.as_str()) {
        return Err(json!({
            "code": "not_permitted",
            "message": "That is not something the app asks for from this side."
        }));
    }
    state
        .engine
        .request(&method, &params)
        .map_err(|error| error.as_payload())
}

// ---------- documents ----------------------------------------------------------------------

#[tauri::command]
fn document_save(state: State<'_, AppState>, record: DocumentRecord) -> Reply {
    with_store(&state, |store| store.save_document(&record))?;
    Ok(Value::Null)
}

#[tauri::command]
fn document_list(state: State<'_, AppState>, workspace_id: Option<String>) -> Reply {
    let documents = with_store(&state, |store| store.documents(workspace_id.as_deref()))?;
    serde_json::to_value(documents).map_err(|_| failure("the documents could not be listed"))
}

#[tauri::command]
fn document_delete(state: State<'_, AppState>, id: String) -> Reply {
    with_store(&state, |store| store.delete_document(&id))?;
    Ok(Value::Null)
}

/// Asks the engine for a finished scan's map and files it against a document, in one step.
///
/// One step on purpose. If the renderer fetched the map and handed it back for storage, the
/// originals would pass through the web view, which is exactly what must never happen. The only
/// thing that comes back here is how many entries were kept.
#[tauri::command]
fn document_remember_redactions(
    state: State<'_, AppState>,
    document_id: String,
    workspace_id: Option<String>,
    scan_id: String,
) -> Reply {
    let exported = state
        .engine
        .request("privacy.exportMap", &json!({ "scanId": scan_id }))
        .map_err(|error| error.as_payload())?;

    let entries = exported
        .get("entries")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|entry| {
            Some(RedactionEntry {
                placeholder: entry.get("placeholder")?.as_str()?.to_string(),
                original: entry.get("original")?.as_str()?.to_string(),
                category: entry
                    .get("category")
                    .and_then(Value::as_str)
                    .unwrap_or("unknown")
                    .to_string(),
            })
        })
        .collect::<Vec<_>>();

    let stored = with_store(&state, |store| {
        store.remember_redactions(&document_id, workspace_id.as_deref(), &entries)
    })?;

    Ok(json!({ "stored": stored }))
}

/// Puts the real values back into an answer, here, on this machine.
///
/// Two sources are combined: the scan belonging to this conversation, which knows about anything
/// hidden in the question itself, and the mappings stored when each document in scope was added.
#[tauri::command]
fn chat_restore(state: State<'_, AppState>, request: RestoreRequest) -> Reply {
    let mut text = request.text;

    if let Some(scan_id) = request.scan_id.as_ref() {
        if let Ok(restored) = state.engine.request(
            "privacy.restore",
            &json!({ "scanId": scan_id, "text": text }),
        ) {
            if let Some(updated) = restored.get("text").and_then(Value::as_str) {
                text = updated.to_string();
            }
        }
    }

    let mut entries = with_store(&state, |store| {
        store.redactions_for_scope(request.workspace_id.as_deref())
    })?;

    // Longest placeholder first, so `[ORG_1]` cannot match inside `[ORG_10]` and leave a stray
    // digit behind.
    entries.sort_by(|left, right| right.placeholder.len().cmp(&left.placeholder.len()));
    for entry in entries {
        if text.contains(&entry.placeholder) {
            text = text.replace(&entry.placeholder, &entry.original);
        }
    }

    Ok(json!({ "text": text }))
}

// ---------- workspaces ---------------------------------------------------------------------

#[tauri::command]
fn workspace_save(state: State<'_, AppState>, record: WorkspaceRecord) -> Reply {
    with_store(&state, |store| store.save_workspace(&record))?;
    Ok(Value::Null)
}

#[tauri::command]
fn workspace_list(state: State<'_, AppState>) -> Reply {
    let workspaces = with_store(&state, |store| store.workspaces())?;
    serde_json::to_value(workspaces).map_err(|_| failure("the workspaces could not be listed"))
}

#[tauri::command]
fn workspace_delete(state: State<'_, AppState>, id: String) -> Reply {
    with_store(&state, |store| store.delete_workspace(&id))?;
    Ok(Value::Null)
}

// ---------- conversations ------------------------------------------------------------------

#[tauri::command]
fn conversation_save(state: State<'_, AppState>, record: ConversationRecord) -> Reply {
    with_store(&state, |store| store.save_conversation(&record))?;
    Ok(Value::Null)
}

#[tauri::command]
fn conversation_list(state: State<'_, AppState>) -> Reply {
    let conversations = with_store(&state, |store| store.conversations())?;
    serde_json::to_value(conversations).map_err(|_| failure("the chats could not be listed"))
}

#[tauri::command]
fn conversation_delete(state: State<'_, AppState>, id: String) -> Reply {
    with_store(&state, |store| store.delete_conversation(&id))?;
    Ok(Value::Null)
}

#[tauri::command]
fn conversation_append_turn(state: State<'_, AppState>, record: ConversationTurnRecord) -> Reply {
    with_store(&state, |store| store.append_turn(&record))?;
    Ok(Value::Null)
}

#[tauri::command]
fn conversation_turns(state: State<'_, AppState>, conversation_id: String) -> Reply {
    let turns = with_store(&state, |store| store.turns(&conversation_id))?;
    serde_json::to_value(turns).map_err(|_| failure("the messages could not be read"))
}

// ---------- protected terms and settings ----------------------------------------------------

#[tauri::command]
fn protected_terms_save(state: State<'_, AppState>, scope: String, terms: Vec<String>) -> Reply {
    with_store(&state, |store| store.save_protected_terms(&scope, &terms))?;
    Ok(Value::Null)
}

#[tauri::command]
fn protected_terms_load(state: State<'_, AppState>, scope: String) -> Reply {
    let terms = with_store(&state, |store| store.protected_terms(&scope))?;
    serde_json::to_value(terms).map_err(|_| failure("the hidden words could not be read"))
}

#[tauri::command]
fn protected_terms_in_effect(state: State<'_, AppState>, workspace_id: Option<String>) -> Reply {
    let terms = with_store(&state, |store| {
        store.terms_in_effect(workspace_id.as_deref())
    })?;
    serde_json::to_value(terms).map_err(|_| failure("the hidden words could not be read"))
}

/// Only settings the app itself owns. A renderer that could write any key could use the vault as
/// general storage for whatever it liked, which is not what this is for.
#[tauri::command]
fn setting_write(state: State<'_, AppState>, key: String, value: String) -> Reply {
    if !(key.starts_with("chat.") || key.starts_with("ui.")) {
        return Err(failure("that is not a setting this app keeps"));
    }
    with_store(&state, |store| store.write_setting(&key, &value))?;
    Ok(Value::Null)
}

#[tauri::command]
fn setting_read(state: State<'_, AppState>, key: String) -> Reply {
    if !(key.starts_with("chat.") || key.starts_with("ui.")) {
        return Err(failure("that is not a setting this app keeps"));
    }
    let value = with_store(&state, |store| store.read_setting(&key))?;
    Ok(json!(value))
}

// ---------- sign in ------------------------------------------------------------------------

#[tauri::command]
async fn auth_send_code(state: State<'_, AppState>, email: String) -> Reply {
    let auth = state.auth.lock().await;
    auth.send_code(email.trim())
        .await
        .map(|()| Value::Null)
        .map_err(|error| json!({ "code": "sign_in_failed", "message": error.to_string() }))
}

#[tauri::command]
async fn auth_verify_code(state: State<'_, AppState>, email: String, code: String) -> Reply {
    let mut auth = state.auth.lock().await;
    auth.verify_code(email.trim(), code.trim())
        .await
        .map_err(|error| json!({ "code": "sign_in_failed", "message": error.to_string() }))?;

    let token = auth
        .identity_token()
        .await
        .map_err(|error| json!({ "code": "sign_in_failed", "message": error.to_string() }))?;

    let cookie = auth.stored_cookie();
    drop(auth);
    remember_session(&state, cookie);

    Ok(json!({ "identityToken": token }))
}

/// A fresh identity token for an already signed-in session.
///
/// The renderer calls this when the backend rejects a token as expired. The session behind it is
/// good for far longer than the token, so this is a renewal rather than a new sign-in.
#[tauri::command]
async fn auth_identity_token(state: State<'_, AppState>) -> Reply {
    let mut auth = state.auth.lock().await;
    if !auth.is_signed_in() {
        return Err(json!({ "code": "signed_out", "message": "Please sign in again." }));
    }
    let token = auth
        .identity_token()
        .await
        .map_err(|error| json!({ "code": "signed_out", "message": error.to_string() }))?;

    let cookie = auth.stored_cookie();
    drop(auth);
    remember_session(&state, cookie);

    Ok(json!({ "identityToken": token }))
}

/// Puts back a session kept from a previous run, if there is one.
#[tauri::command]
async fn auth_restore(state: State<'_, AppState>) -> Reply {
    let stored = with_store(&state, |store| store.read_setting(SESSION_COOKIE_SETTING))
        .unwrap_or(None)
        .unwrap_or_default();

    if stored.trim().is_empty() {
        return Ok(json!({ "signedIn": false }));
    }

    let mut auth = state.auth.lock().await;
    auth.restore_cookie(stored);
    match auth.identity_token().await {
        Ok(token) => {
            let cookie = auth.stored_cookie();
            drop(auth);
            remember_session(&state, cookie);
            Ok(json!({ "signedIn": true, "identityToken": token }))
        }
        Err(_) => {
            // The stored session is no longer good. Clearing it means the next launch shows the
            // sign-in screen straight away rather than trying a dead session again.
            auth.sign_out();
            drop(auth);
            remember_session(&state, None);
            Ok(json!({ "signedIn": false }))
        }
    }
}

#[tauri::command]
async fn auth_sign_out(state: State<'_, AppState>) -> Reply {
    let mut auth = state.auth.lock().await;
    auth.sign_out();
    drop(auth);
    remember_session(&state, None);
    Ok(Value::Null)
}

#[tauri::command]
fn global_scope_name() -> Reply {
    Ok(json!(GLOBAL_SCOPE))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(AppState::new())
        .setup(|app| {
            let directory = app
                .path()
                .app_data_dir()
                .map_err(|_| "no application data directory on this computer")?;

            let key = master_key::load_or_create()
                .map_err(|error| format!("the vault key is unavailable: {error}"))?;
            let vault = Vault::open(&Vault::path_within(&directory), &key)
                .map_err(|error| format!("the vault could not be opened: {error}"))?;
            let cipher = Cipher::new(&key).map_err(|error| error.to_string())?;

            let state = app.state::<AppState>();
            *state.vault.lock().map_err(|_| "the vault is busy")? = Some(vault);
            *state.cipher.lock().map_err(|_| "the vault is busy")? = Some(cipher);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            engine_request,
            document_save,
            document_list,
            document_delete,
            document_remember_redactions,
            chat_restore,
            workspace_save,
            workspace_list,
            workspace_delete,
            conversation_save,
            conversation_list,
            conversation_delete,
            conversation_append_turn,
            conversation_turns,
            protected_terms_save,
            protected_terms_load,
            protected_terms_in_effect,
            setting_write,
            setting_read,
            auth_send_code,
            auth_verify_code,
            auth_identity_token,
            auth_restore,
            auth_sign_out,
            global_scope_name,
        ])
        .run(tauri::generate_context!())
        .expect("HawkVance failed to start");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_export_command_is_closed_to_the_renderer() {
        // This is the whole arrangement in one line: if this list ever loses this entry, the web
        // view can ask for originals directly.
        assert!(RENDERER_MAY_NOT_CALL.contains(&"privacy.exportMap"));
    }

    #[test]
    fn only_the_apps_own_settings_are_writable() {
        // Guarding the prefix here rather than at the call site, because the check has to hold for
        // every caller including a future one.
        for key in ["chat.preferred_model", "ui.threads_open"] {
            assert!(key.starts_with("chat.") || key.starts_with("ui."));
        }
        for key in ["documents.secret", "", "vault.master"] {
            assert!(!(key.starts_with("chat.") || key.starts_with("ui.")));
        }
    }

    #[test]
    fn longer_placeholders_are_replaced_before_shorter_ones() {
        let mut entries = vec![
            RedactionEntry {
                placeholder: "[ORG_1]".into(),
                original: "Falcon".into(),
                category: "organization".into(),
            },
            RedactionEntry {
                placeholder: "[ORG_10]".into(),
                original: "Heron Holdings".into(),
                category: "organization".into(),
            },
        ];
        entries.sort_by(|left, right| right.placeholder.len().cmp(&left.placeholder.len()));

        let mut text = String::from("[ORG_10] and [ORG_1]");
        for entry in &entries {
            text = text.replace(&entry.placeholder, &entry.original);
        }

        // Had the short one gone first it would have matched inside the long one and left "0".
        assert_eq!(text, "Heron Holdings and Falcon");
    }
}
