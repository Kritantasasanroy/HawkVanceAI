//! Opening the encrypted vault file.
//!
//! SQLCipher wants the key before anything else happens on the connection, so `PRAGMA key` is the
//! very first statement issued. If it is not, SQLite reads the header, finds no recognisable
//! database, and reports file corruption rather than a wrong key, which sends anyone debugging it
//! in entirely the wrong direction.

use std::path::{Path, PathBuf};

use rusqlite::Connection;

#[derive(Debug, thiserror::Error)]
pub enum VaultError {
    #[error("the vault could not be opened on this computer")]
    Open,
    #[error("the vault is there but the key does not fit it")]
    WrongKey,
    #[error("the vault could not be prepared: {0}")]
    Schema(String),
}

pub struct Vault {
    connection: Connection,
}

impl Vault {
    /// Opens, keys and prepares the vault, creating it on first run.
    pub fn open(path: &Path, key: &[u8; 32]) -> Result<Self, VaultError> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|_| VaultError::Open)?;
        }

        let connection = Connection::open(path).map_err(|_| VaultError::Open)?;

        // Before anything else, including any read.
        connection
            .pragma_update(None, "key", format!("x'{}'", hex::encode(key)))
            .map_err(|_| VaultError::Open)?;

        // Proves the key fits. Without a real read, a wrong key is not discovered until some
        // unrelated query fails much later with a confusing message.
        connection
            .query_row("select count(*) from sqlite_master", [], |row| {
                row.get::<_, i64>(0)
            })
            .map_err(|_| VaultError::WrongKey)?;

        connection
            .pragma_update(None, "foreign_keys", "ON")
            .map_err(|_| VaultError::Open)?;
        // Survives an abrupt shutdown without the rollback journal being lost.
        connection
            .pragma_update(None, "journal_mode", "WAL")
            .map_err(|_| VaultError::Open)?;

        let vault = Self { connection };
        vault.prepare()?;
        Ok(vault)
    }

    fn prepare(&self) -> Result<(), VaultError> {
        self.connection
            .execute_batch(include_str!("vault_schema.sql"))
            .map_err(|error| VaultError::Schema(error.to_string()))
    }

    pub fn connection(&self) -> &Connection {
        &self.connection
    }

    /// Where the vault lives for a given app data directory.
    pub fn path_within(data_directory: &Path) -> PathBuf {
        data_directory.join("hawkvance.vault")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary() -> PathBuf {
        std::env::temp_dir().join(format!("hawkvance-test-{}.vault", uuid::Uuid::new_v4()))
    }

    #[test]
    fn a_new_vault_opens_and_has_its_tables() {
        let path = temporary();
        let vault = Vault::open(&path, &[3u8; 32]).expect("opens");
        let tables: i64 = vault
            .connection()
            .query_row(
                "select count(*) from sqlite_master where type = 'table'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert!(tables >= 7, "expected the schema to be created, saw {tables} tables");
        drop(vault);
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn reopening_with_the_same_key_keeps_the_contents() {
        let path = temporary();
        {
            let vault = Vault::open(&path, &[5u8; 32]).unwrap();
            vault
                .connection()
                .execute(
                    "insert into workspaces (id, name, description, created_at, updated_at)
                     values ('w1', 'Test', '', '2026-01-01', '2026-01-01')",
                    [],
                )
                .unwrap();
        }
        let vault = Vault::open(&path, &[5u8; 32]).unwrap();
        let name: String = vault
            .connection()
            .query_row("select name from workspaces where id = 'w1'", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(name, "Test");
        drop(vault);
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn the_wrong_key_is_refused_rather_than_reading_rubbish() {
        let path = temporary();
        {
            Vault::open(&path, &[1u8; 32]).unwrap();
        }
        let opened = Vault::open(&path, &[2u8; 32]);
        assert!(matches!(opened, Err(VaultError::WrongKey)));
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn the_file_on_disk_is_not_readable_as_plain_sqlite() {
        // The whole point of SQLCipher: an unencrypted SQLite file begins with this string, and a
        // vault must not.
        let path = temporary();
        {
            let vault = Vault::open(&path, &[8u8; 32]).unwrap();
            vault
                .connection()
                .execute(
                    "insert into workspaces (id, name, description, created_at, updated_at)
                     values ('w1', 'Falcon Retail', '', '2026-01-01', '2026-01-01')",
                    [],
                )
                .unwrap();
        }
        let bytes = std::fs::read(&path).unwrap();
        assert!(!bytes.starts_with(b"SQLite format 3"));
        let needle = b"Falcon Retail";
        assert!(
            !bytes.windows(needle.len()).any(|window| window == needle),
            "a value written to the vault was found in clear text on disk"
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn preparing_twice_is_harmless() {
        let path = temporary();
        let vault = Vault::open(&path, &[4u8; 32]).unwrap();
        vault.prepare().expect("the schema is written with create table if not exists");
        drop(vault);
        let _ = std::fs::remove_file(path);
    }
}
