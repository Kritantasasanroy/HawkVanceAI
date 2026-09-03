//! Reading and writing the vault.
//!
//! Every method that touches something a person would call their own content seals it on the way
//! in and unseals it on the way out, so the only place a value exists in the clear is in memory
//! while it is being used.

use rusqlite::{params, OptionalExtension};

use crate::cipher::Cipher;
use crate::records::{
    ConversationRecord, ConversationTurnRecord, DocumentRecord, RedactionEntry, WorkspaceRecord,
};
use crate::vault::Vault;

/// The scope key used for words that apply everywhere rather than to one project.
pub const GLOBAL_SCOPE: &str = "global";

#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error("the vault could not be read or written")]
    Database,
    #[error("a stored value could not be unsealed")]
    Unseal,
}

impl From<rusqlite::Error> for StoreError {
    fn from(_: rusqlite::Error) -> Self {
        StoreError::Database
    }
}

impl From<crate::cipher::CipherError> for StoreError {
    fn from(_: crate::cipher::CipherError) -> Self {
        StoreError::Unseal
    }
}

fn now() -> String {
    chrono::Utc::now().to_rfc3339()
}

pub struct VaultStore<'a> {
    vault: &'a Vault,
    cipher: &'a Cipher,
}

impl<'a> VaultStore<'a> {
    pub fn new(vault: &'a Vault, cipher: &'a Cipher) -> Self {
        Self { vault, cipher }
    }

    // ---------- workspaces ----------------------------------------------------------------

    pub fn save_workspace(&self, record: &WorkspaceRecord) -> Result<(), StoreError> {
        self.vault.connection().execute(
            "insert into workspaces (id, name, description, created_at, updated_at)
             values (?1, ?2, ?3, ?4, ?5)
             on conflict (id) do update set name = ?2, description = ?3, updated_at = ?5",
            params![
                record.id,
                record.name,
                record.description,
                record.created_at,
                now()
            ],
        )?;
        Ok(())
    }

    pub fn workspaces(&self) -> Result<Vec<WorkspaceRecord>, StoreError> {
        let connection = self.vault.connection();
        let mut statement = connection.prepare(
            "select id, name, description, created_at, updated_at from workspaces order by name",
        )?;
        let rows = statement.query_map([], |row| {
            Ok(WorkspaceRecord {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                created_at: row.get(3)?,
                updated_at: row.get(4)?,
            })
        })?;
        Ok(rows.collect::<Result<Vec<_>, _>>()?)
    }

    pub fn delete_workspace(&self, id: &str) -> Result<(), StoreError> {
        self.vault
            .connection()
            .execute("delete from workspaces where id = ?1", params![id])?;
        Ok(())
    }

    // ---------- documents -----------------------------------------------------------------

    pub fn save_document(&self, record: &DocumentRecord) -> Result<(), StoreError> {
        let sealed = self.cipher.seal(&record.sanitised_text)?;
        self.vault.connection().execute(
            "insert into documents
               (id, workspace_id, filename, sha256, size_bytes, character_count, used_ocr,
                sanitised_text, created_at)
             values (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                record.id,
                record.workspace_id,
                record.filename,
                record.sha256,
                record.size_bytes,
                record.character_count,
                record.used_ocr as i32,
                sealed,
                record.created_at
            ],
        )?;
        Ok(())
    }

    /// The files in one workspace, or the ones in Global memory when given none.
    pub fn documents(&self, workspace_id: Option<&str>) -> Result<Vec<DocumentRecord>, StoreError> {
        let connection = self.vault.connection();
        let sql = "select id, workspace_id, filename, sha256, size_bytes, character_count,
                          used_ocr, sanitised_text, created_at
                   from documents
                   where workspace_id is ?1
                   order by created_at desc";
        let mut statement = connection.prepare(sql)?;
        let rows = statement.query_map(params![workspace_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<String>>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, i64>(4)?,
                row.get::<_, i64>(5)?,
                row.get::<_, i32>(6)?,
                row.get::<_, String>(7)?,
                row.get::<_, String>(8)?,
            ))
        })?;

        let mut documents = Vec::new();
        for row in rows {
            let row = row?;
            documents.push(DocumentRecord {
                id: row.0,
                workspace_id: row.1,
                filename: row.2,
                sha256: row.3,
                size_bytes: row.4,
                character_count: row.5,
                used_ocr: row.6 != 0,
                sanitised_text: self.cipher.unseal(&row.7)?,
                created_at: row.8,
            });
        }
        Ok(documents)
    }

    pub fn delete_document(&self, id: &str) -> Result<(), StoreError> {
        self.vault
            .connection()
            .execute("delete from documents where id = ?1", params![id])?;
        Ok(())
    }

    // ---------- the redaction map ---------------------------------------------------------

    /// Stores what each placeholder in a document stands for.
    ///
    /// Without this the product's central promise cannot work: the map produced when a document is
    /// scanned used to die with the scan, so by the time an answer came back mentioning
    /// `[ORG_001]` there was nothing left that knew what it meant.
    pub fn remember_redactions(
        &self,
        document_id: &str,
        workspace_id: Option<&str>,
        entries: &[RedactionEntry],
    ) -> Result<usize, StoreError> {
        let connection = self.vault.connection();
        let stamp = now();
        let mut written = 0usize;

        for entry in entries {
            let sealed = self.cipher.seal(&entry.original)?;
            connection.execute(
                "insert into redaction_map_entries
                   (document_id, workspace_id, placeholder, original, category, created_at)
                 values (?1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    document_id,
                    workspace_id,
                    entry.placeholder,
                    sealed,
                    entry.category,
                    stamp
                ],
            )?;
            written += 1;
        }
        Ok(written)
    }

    /// Every mapping a conversation in this scope is allowed to use.
    ///
    /// A workspace conversation sees that workspace's documents; a Global one sees the documents
    /// kept outside any workspace. Neither can reach the other, which is the same boundary the
    /// documents themselves observe.
    pub fn redactions_for_scope(
        &self,
        workspace_id: Option<&str>,
    ) -> Result<Vec<RedactionEntry>, StoreError> {
        let connection = self.vault.connection();
        let mut statement = connection.prepare(
            "select placeholder, original, category
             from redaction_map_entries
             where workspace_id is ?1",
        )?;
        let rows = statement.query_map(params![workspace_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?;

        let mut entries = Vec::new();
        for row in rows {
            let row = row?;
            entries.push(RedactionEntry {
                placeholder: row.0,
                original: self.cipher.unseal(&row.1)?,
                category: row.2,
            });
        }
        Ok(entries)
    }

    // ---------- conversations -------------------------------------------------------------

    pub fn save_conversation(&self, record: &ConversationRecord) -> Result<(), StoreError> {
        self.vault.connection().execute(
            "insert into conversations (id, workspace_id, title, started_at)
             values (?1, ?2, ?3, ?4)
             on conflict (id) do update set title = ?3",
            params![
                record.id,
                record.workspace_id,
                record.title,
                record.started_at
            ],
        )?;
        Ok(())
    }

    pub fn conversations(&self) -> Result<Vec<ConversationRecord>, StoreError> {
        let connection = self.vault.connection();
        let mut statement = connection.prepare(
            "select id, workspace_id, title, started_at from conversations order by started_at desc",
        )?;
        let rows = statement.query_map([], |row| {
            Ok(ConversationRecord {
                id: row.get(0)?,
                workspace_id: row.get(1)?,
                title: row.get(2)?,
                started_at: row.get(3)?,
            })
        })?;
        Ok(rows.collect::<Result<Vec<_>, _>>()?)
    }

    pub fn delete_conversation(&self, id: &str) -> Result<(), StoreError> {
        self.vault
            .connection()
            .execute("delete from conversations where id = ?1", params![id])?;
        Ok(())
    }

    pub fn append_turn(&self, record: &ConversationTurnRecord) -> Result<(), StoreError> {
        let sealed = self.cipher.seal(&record.content)?;
        self.vault.connection().execute(
            "insert into conversation_turns (id, conversation_id, role, content, model, occurred_at)
             values (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                record.id,
                record.conversation_id,
                record.role,
                sealed,
                record.model,
                record.occurred_at
            ],
        )?;
        Ok(())
    }

    pub fn turns(&self, conversation_id: &str) -> Result<Vec<ConversationTurnRecord>, StoreError> {
        let connection = self.vault.connection();
        let mut statement = connection.prepare(
            "select id, conversation_id, role, content, model, occurred_at
             from conversation_turns
             where conversation_id = ?1
             order by occurred_at",
        )?;
        let rows = statement.query_map(params![conversation_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, String>(5)?,
            ))
        })?;

        let mut turns = Vec::new();
        for row in rows {
            let row = row?;
            turns.push(ConversationTurnRecord {
                id: row.0,
                conversation_id: row.1,
                role: row.2,
                content: self.cipher.unseal(&row.3)?,
                model: row.4,
                occurred_at: row.5,
            });
        }
        Ok(turns)
    }

    // ---------- protected terms and settings ----------------------------------------------

    pub fn save_protected_terms(&self, scope: &str, terms: &[String]) -> Result<(), StoreError> {
        let connection = self.vault.connection();
        connection.execute("delete from protected_terms where scope = ?1", params![scope])?;
        let stamp = now();
        for term in terms {
            connection.execute(
                "insert or ignore into protected_terms (scope, term, created_at)
                 values (?1, ?2, ?3)",
                params![scope, term, stamp],
            )?;
        }
        Ok(())
    }

    pub fn protected_terms(&self, scope: &str) -> Result<Vec<String>, StoreError> {
        let connection = self.vault.connection();
        let mut statement =
            connection.prepare("select term from protected_terms where scope = ?1 order by term")?;
        let rows = statement.query_map(params![scope], |row| row.get::<_, String>(0))?;
        Ok(rows.collect::<Result<Vec<_>, _>>()?)
    }

    /// The union of the words chosen here and the ones chosen to apply everywhere.
    pub fn terms_in_effect(&self, workspace_id: Option<&str>) -> Result<Vec<String>, StoreError> {
        let mut terms = self.protected_terms(GLOBAL_SCOPE)?;
        if let Some(scope) = workspace_id {
            for term in self.protected_terms(scope)? {
                if !terms.iter().any(|existing| existing == &term) {
                    terms.push(term);
                }
            }
        }
        Ok(terms)
    }

    pub fn write_setting(&self, key: &str, value: &str) -> Result<(), StoreError> {
        self.vault.connection().execute(
            "insert into settings (key, value, updated_at) values (?1, ?2, ?3)
             on conflict (key) do update set value = ?2, updated_at = ?3",
            params![key, value, now()],
        )?;
        Ok(())
    }

    pub fn read_setting(&self, key: &str) -> Result<Option<String>, StoreError> {
        Ok(self
            .vault
            .connection()
            .query_row("select value from settings where key = ?1", params![key], |row| {
                row.get::<_, String>(0)
            })
            .optional()?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    struct Fixture {
        path: PathBuf,
        vault: Vault,
        cipher: Cipher,
    }

    impl Fixture {
        fn new() -> Self {
            let path =
                std::env::temp_dir().join(format!("hawkvance-store-{}.vault", uuid::Uuid::new_v4()));
            let vault = Vault::open(&path, &[6u8; 32]).expect("opens");
            let cipher = Cipher::new(&[6u8; 32]).expect("valid key");
            Self { path, vault, cipher }
        }

        fn store(&self) -> VaultStore<'_> {
            VaultStore::new(&self.vault, &self.cipher)
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.path);
        }
    }

    fn document(id: &str, workspace: Option<&str>) -> DocumentRecord {
        DocumentRecord {
            id: id.into(),
            workspace_id: workspace.map(str::to_string),
            filename: "offer.pdf".into(),
            sha256: format!("sha-{id}"),
            size_bytes: 1024,
            character_count: 500,
            used_ocr: false,
            sanitised_text: "Signed by [PERSON_001] at [ORG_001].".into(),
            created_at: "2026-09-03T00:00:00Z".into(),
        }
    }

    #[test]
    fn a_document_round_trips_through_sealing() {
        let fixture = Fixture::new();
        let store = fixture.store();
        store.save_document(&document("d1", None)).unwrap();

        let found = store.documents(None).unwrap();
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].sanitised_text, "Signed by [PERSON_001] at [ORG_001].");
    }

    #[test]
    fn document_text_is_not_stored_in_the_clear() {
        let fixture = Fixture::new();
        fixture.store().save_document(&document("d1", None)).unwrap();

        let stored: String = fixture
            .vault
            .connection()
            .query_row("select sanitised_text from documents where id = 'd1'", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert!(!stored.contains("PERSON_001"));
    }

    #[test]
    fn global_and_workspace_documents_do_not_see_each_other() {
        let fixture = Fixture::new();
        let store = fixture.store();
        store
            .save_workspace(&WorkspaceRecord {
                id: "w1".into(),
                name: "Test".into(),
                description: String::new(),
                created_at: "2026-09-03T00:00:00Z".into(),
                updated_at: "2026-09-03T00:00:00Z".into(),
            })
            .unwrap();
        store.save_document(&document("d1", None)).unwrap();
        store.save_document(&document("d2", Some("w1"))).unwrap();

        assert_eq!(store.documents(None).unwrap().len(), 1);
        assert_eq!(store.documents(Some("w1")).unwrap().len(), 1);
        assert_eq!(store.documents(Some("w1")).unwrap()[0].id, "d2");
    }

    #[test]
    fn redaction_entries_survive_a_close_and_reopen() {
        let path =
            std::env::temp_dir().join(format!("hawkvance-map-{}.vault", uuid::Uuid::new_v4()));
        let cipher = Cipher::new(&[2u8; 32]).unwrap();
        {
            let vault = Vault::open(&path, &[2u8; 32]).unwrap();
            let store = VaultStore::new(&vault, &cipher);
            store.save_document(&document("d1", None)).unwrap();
            store
                .remember_redactions(
                    "d1",
                    None,
                    &[RedactionEntry {
                        placeholder: "[ORG_001]".into(),
                        original: "Falcon Retail Limited".into(),
                        category: "organization".into(),
                    }],
                )
                .unwrap();
        }

        let vault = Vault::open(&path, &[2u8; 32]).unwrap();
        let store = VaultStore::new(&vault, &cipher);
        let entries = store.redactions_for_scope(None).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].original, "Falcon Retail Limited");
        drop(store);
        drop(vault);
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn an_original_is_never_written_to_disk_in_the_clear() {
        let path =
            std::env::temp_dir().join(format!("hawkvance-clear-{}.vault", uuid::Uuid::new_v4()));
        {
            let vault = Vault::open(&path, &[4u8; 32]).unwrap();
            let cipher = Cipher::new(&[4u8; 32]).unwrap();
            let store = VaultStore::new(&vault, &cipher);
            store.save_document(&document("d1", None)).unwrap();
            store
                .remember_redactions(
                    "d1",
                    None,
                    &[RedactionEntry {
                        placeholder: "[PERSON_001]".into(),
                        original: "Rajmani Pal".into(),
                        category: "person".into(),
                    }],
                )
                .unwrap();
        }
        let bytes = std::fs::read(&path).unwrap();
        let needle = b"Rajmani Pal";
        assert!(
            !bytes.windows(needle.len()).any(|window| window == needle),
            "the original behind a placeholder was found in clear text on disk"
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn a_workspace_map_is_not_visible_from_global() {
        let fixture = Fixture::new();
        let store = fixture.store();
        store
            .save_workspace(&WorkspaceRecord {
                id: "w1".into(),
                name: "Test".into(),
                description: String::new(),
                created_at: "2026-09-03T00:00:00Z".into(),
                updated_at: "2026-09-03T00:00:00Z".into(),
            })
            .unwrap();
        store.save_document(&document("d2", Some("w1"))).unwrap();
        store
            .remember_redactions(
                "d2",
                Some("w1"),
                &[RedactionEntry {
                    placeholder: "[ORG_001]".into(),
                    original: "Private Holdings".into(),
                    category: "organization".into(),
                }],
            )
            .unwrap();

        assert!(store.redactions_for_scope(None).unwrap().is_empty());
        assert_eq!(store.redactions_for_scope(Some("w1")).unwrap().len(), 1);
    }

    #[test]
    fn deleting_a_document_takes_its_mappings_with_it() {
        let fixture = Fixture::new();
        let store = fixture.store();
        store.save_document(&document("d1", None)).unwrap();
        store
            .remember_redactions(
                "d1",
                None,
                &[RedactionEntry {
                    placeholder: "[ORG_001]".into(),
                    original: "Falcon".into(),
                    category: "organization".into(),
                }],
            )
            .unwrap();

        store.delete_document("d1").unwrap();
        assert!(store.redactions_for_scope(None).unwrap().is_empty());
    }

    #[test]
    fn turns_come_back_in_order_and_readable() {
        let fixture = Fixture::new();
        let store = fixture.store();
        store
            .save_conversation(&ConversationRecord {
                id: "c1".into(),
                workspace_id: None,
                title: "First".into(),
                started_at: "2026-09-03T00:00:00Z".into(),
            })
            .unwrap();

        for (index, role) in ["user", "assistant"].iter().enumerate() {
            store
                .append_turn(&ConversationTurnRecord {
                    id: format!("t{index}"),
                    conversation_id: "c1".into(),
                    role: (*role).into(),
                    content: format!("message {index}"),
                    model: None,
                    occurred_at: format!("2026-09-03T00:0{index}:00Z"),
                })
                .unwrap();
        }

        let turns = store.turns("c1").unwrap();
        assert_eq!(turns.len(), 2);
        assert_eq!(turns[0].content, "message 0");
        assert_eq!(turns[1].role, "assistant");
    }

    #[test]
    fn terms_in_effect_are_the_union_without_duplicates() {
        let fixture = Fixture::new();
        let store = fixture.store();
        store
            .save_protected_terms(GLOBAL_SCOPE, &["Dutt".into(), "Narayan".into()])
            .unwrap();
        store
            .save_protected_terms("w1", &["Narayan".into(), "Pandey".into()])
            .unwrap();

        let mut terms = store.terms_in_effect(Some("w1")).unwrap();
        terms.sort();
        assert_eq!(terms, vec!["Dutt", "Narayan", "Pandey"]);
    }

    #[test]
    fn a_setting_can_be_written_read_and_replaced() {
        let fixture = Fixture::new();
        let store = fixture.store();
        assert_eq!(store.read_setting("chat.preferred_model").unwrap(), None);

        store.write_setting("chat.preferred_model", "glm").unwrap();
        assert_eq!(
            store.read_setting("chat.preferred_model").unwrap().as_deref(),
            Some("glm")
        );

        store.write_setting("chat.preferred_model", "minimax").unwrap();
        assert_eq!(
            store.read_setting("chat.preferred_model").unwrap().as_deref(),
            Some("minimax")
        );
    }

    #[test]
    fn deleting_a_workspace_takes_its_documents_with_it() {
        let fixture = Fixture::new();
        let store = fixture.store();
        store
            .save_workspace(&WorkspaceRecord {
                id: "w1".into(),
                name: "Test".into(),
                description: String::new(),
                created_at: "2026-09-03T00:00:00Z".into(),
                updated_at: "2026-09-03T00:00:00Z".into(),
            })
            .unwrap();
        store.save_document(&document("d1", Some("w1"))).unwrap();

        store.delete_workspace("w1").unwrap();
        assert!(store.documents(Some("w1")).unwrap().is_empty());
    }
}
