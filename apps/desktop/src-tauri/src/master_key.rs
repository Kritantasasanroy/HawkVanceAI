//! Where the vault's key lives when the app is not running.
//!
//! Not beside the vault, and not derived from anything guessable. On Windows it goes into
//! Credential Manager, which ties it to the signed-in user account: another user on the same
//! machine cannot read it, and it does not sit in a file that a backup tool or a sync client will
//! quietly copy somewhere else.
//!
//! The key is generated once on first run and then only ever read back. There is deliberately no
//! way to export it through the renderer, because a value that can be requested from the web view
//! is a value that any script running there can obtain.

use rand::RngCore;

const TARGET: &str = "HawkVance/vault-master-key";

#[derive(Debug, thiserror::Error)]
pub enum MasterKeyError {
    #[error("the stored key could not be read back from this computer")]
    Read,
    #[error("the key could not be saved on this computer")]
    Write,
    #[error("the stored key is not the right size, so the vault cannot be opened with it")]
    Corrupt,
}

/// Returns the machine's vault key, creating it on first use.
pub fn load_or_create() -> Result<[u8; 32], MasterKeyError> {
    if let Some(existing) = read()? {
        return Ok(existing);
    }
    let mut fresh = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut fresh);
    write(&fresh)?;
    Ok(fresh)
}

#[cfg(windows)]
fn read() -> Result<Option<[u8; 32]>, MasterKeyError> {
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::ERROR_NOT_FOUND;
    use windows::Win32::Security::Credentials::{
        CredFree, CredReadW, CREDENTIALW, CRED_TYPE_GENERIC,
    };

    let target = wide(TARGET);
    let mut credential: *mut CREDENTIALW = std::ptr::null_mut();

    // Safety: the target string outlives the call, and the returned pointer is freed below on
    // every path that reaches it.
    unsafe {
        match CredReadW(
            PCWSTR(target.as_ptr()),
            CRED_TYPE_GENERIC,
            0,
            &mut credential,
        ) {
            Ok(()) => {}
            Err(error) if error.code() == ERROR_NOT_FOUND.to_hresult() => return Ok(None),
            Err(_) => return Err(MasterKeyError::Read),
        }

        let blob = std::slice::from_raw_parts(
            (*credential).CredentialBlob,
            (*credential).CredentialBlobSize as usize,
        );
        let copied = blob.to_vec();
        CredFree(credential as *const _);

        let key: [u8; 32] = copied.try_into().map_err(|_| MasterKeyError::Corrupt)?;
        Ok(Some(key))
    }
}

#[cfg(windows)]
fn write(key: &[u8; 32]) -> Result<(), MasterKeyError> {
    use windows::core::PWSTR;
    use windows::Win32::Security::Credentials::{
        CredWriteW, CREDENTIALW, CRED_PERSIST_LOCAL_MACHINE, CRED_TYPE_GENERIC,
    };

    let mut target = wide(TARGET);
    let mut blob = key.to_vec();

    let credential = CREDENTIALW {
        Type: CRED_TYPE_GENERIC,
        TargetName: PWSTR(target.as_mut_ptr()),
        CredentialBlobSize: blob.len() as u32,
        CredentialBlob: blob.as_mut_ptr(),
        Persist: CRED_PERSIST_LOCAL_MACHINE,
        ..Default::default()
    };

    // Safety: both buffers outlive the call.
    unsafe { CredWriteW(&credential, 0).map_err(|_| MasterKeyError::Write) }
}

#[cfg(windows)]
fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}

/// Elsewhere there is no Credential Manager, so the key goes in a file that only the owner can
/// read. Kept so the crate builds and tests on other platforms; Windows is the shipping target.
#[cfg(not(windows))]
fn key_path() -> std::path::PathBuf {
    let base = std::env::var("XDG_DATA_HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| {
            std::path::PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| ".".into()))
                .join(".local/share")
        });
    base.join("hawkvance").join("vault.key")
}

#[cfg(not(windows))]
fn read() -> Result<Option<[u8; 32]>, MasterKeyError> {
    let path = key_path();
    match std::fs::read(&path) {
        Ok(bytes) => {
            let key: [u8; 32] = bytes.try_into().map_err(|_| MasterKeyError::Corrupt)?;
            Ok(Some(key))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(_) => Err(MasterKeyError::Read),
    }
}

#[cfg(not(windows))]
fn write(key: &[u8; 32]) -> Result<(), MasterKeyError> {
    let path = key_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|_| MasterKeyError::Write)?;
    }
    std::fs::write(&path, key).map_err(|_| MasterKeyError::Write)?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))
            .map_err(|_| MasterKeyError::Write)?;
    }
    Ok(())
}
