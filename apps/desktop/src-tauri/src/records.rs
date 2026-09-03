//! The shapes that cross between Rust and the web view.
//!
//! Deliberately narrow. Nothing here carries an original value from the redaction map: the closest
//! it comes is a count, because the one rule the whole product rests on is that the mapping from a
//! placeholder back to the real text never leaves this machine, and the web view is the least
//! trusted process in it.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkspaceRecord {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub description: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DocumentRecord {
    pub id: String,
    /// Null means Global memory.
    pub workspace_id: Option<String>,
    pub filename: String,
    pub sha256: String,
    pub size_bytes: i64,
    pub character_count: i64,
    pub used_ocr: bool,
    pub sanitised_text: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ConversationRecord {
    pub id: String,
    pub workspace_id: Option<String>,
    pub title: String,
    pub started_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ConversationTurnRecord {
    pub id: String,
    pub conversation_id: String,
    pub role: String,
    pub content: String,
    pub model: Option<String>,
    pub occurred_at: String,
}

/// One placeholder and what it stands for.
///
/// This type exists only inside the Rust process. It has no command that returns it and no
/// TypeScript counterpart, which is the mechanical reason a mapping cannot be asked for from the
/// renderer rather than merely a rule saying it should not be.
#[derive(Debug, Clone)]
pub struct RedactionEntry {
    pub placeholder: String,
    pub original: String,
    pub category: String,
}

/// What a restore request carries. The text is an answer that came back from a model, so it is
/// already public; what makes it sensitive is what this call is about to put back into it.
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RestoreRequest {
    pub scan_id: Option<String>,
    pub workspace_id: Option<String>,
    pub text: String,
}
