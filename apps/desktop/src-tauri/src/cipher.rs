//! Per-value sealing, on top of the vault's whole-file encryption.
//!
//! The database file is already encrypted by SQLCipher, so this is a second layer rather than the
//! only one. It exists because the two protect against different things: SQLCipher protects the
//! file at rest, and this protects individual values from anything that manages to get a readable
//! handle on the database while it is open, including a bug in this program.
//!
//! AES-256-GCM is used with a fresh random nonce per value. The nonce is stored in front of the
//! ciphertext rather than derived from the plaintext, because a nonce that repeats under the same
//! key destroys the security of GCM entirely, and the only safe way to never repeat one is to draw
//! it at random from a large enough space each time.

use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes256Gcm, Key, Nonce};
use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine as _;
use rand::RngCore;

/// GCM's standard nonce width. Twelve bytes is what the construction is defined for; other lengths
/// go through an extra derivation step and buy nothing here.
const NONCE_BYTES: usize = 12;

#[derive(Debug, thiserror::Error)]
pub enum CipherError {
    #[error("the master key is not 32 bytes long")]
    KeyLength,
    #[error("this value could not be unsealed, so it is not what it claims to be")]
    Unseal,
    #[error("this value is not valid sealed text")]
    Malformed,
}

#[derive(Clone)]
pub struct Cipher {
    key: [u8; 32],
}

impl Cipher {
    pub fn new(key: &[u8]) -> Result<Self, CipherError> {
        let key: [u8; 32] = key.try_into().map_err(|_| CipherError::KeyLength)?;
        Ok(Self { key })
    }

    fn aead(&self) -> Aes256Gcm {
        Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(&self.key))
    }

    /// Seals a value, producing `base64(nonce || ciphertext)`.
    ///
    /// The nonce travels with the ciphertext because the reader needs it and it is not a secret.
    /// What it must never be is reused, which is why it is drawn fresh here rather than stored
    /// once and shared.
    pub fn seal(&self, plaintext: &str) -> Result<String, CipherError> {
        let mut nonce_bytes = [0u8; NONCE_BYTES];
        rand::thread_rng().fill_bytes(&mut nonce_bytes);
        let nonce = Nonce::from_slice(&nonce_bytes);

        let ciphertext = self
            .aead()
            .encrypt(nonce, plaintext.as_bytes())
            .map_err(|_| CipherError::Unseal)?;

        let mut joined = Vec::with_capacity(NONCE_BYTES + ciphertext.len());
        joined.extend_from_slice(&nonce_bytes);
        joined.extend_from_slice(&ciphertext);
        Ok(BASE64.encode(joined))
    }

    pub fn unseal(&self, sealed: &str) -> Result<String, CipherError> {
        let joined = BASE64.decode(sealed).map_err(|_| CipherError::Malformed)?;
        if joined.len() <= NONCE_BYTES {
            return Err(CipherError::Malformed);
        }

        let (nonce_bytes, ciphertext) = joined.split_at(NONCE_BYTES);
        let plaintext = self
            .aead()
            .decrypt(Nonce::from_slice(nonce_bytes), ciphertext)
            .map_err(|_| CipherError::Unseal)?;

        String::from_utf8(plaintext).map_err(|_| CipherError::Unseal)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cipher() -> Cipher {
        Cipher::new(&[7u8; 32]).expect("a 32 byte key is valid")
    }

    #[test]
    fn a_sealed_value_comes_back_unchanged() {
        let sealed = cipher().seal("the real company name").unwrap();
        assert_eq!(cipher().unseal(&sealed).unwrap(), "the real company name");
    }

    #[test]
    fn sealing_the_same_text_twice_gives_different_ciphertext() {
        // If these matched, an observer could tell that two rows hold the same value without
        // being able to read either, which is a leak in itself.
        let once = cipher().seal("Falcon Retail").unwrap();
        let twice = cipher().seal("Falcon Retail").unwrap();
        assert_ne!(once, twice);
    }

    #[test]
    fn the_plaintext_never_appears_in_the_sealed_form() {
        let sealed = cipher().seal("Narayan Dutt").unwrap();
        assert!(!sealed.contains("Narayan"));
    }

    #[test]
    fn another_key_cannot_unseal_it() {
        let sealed = cipher().seal("private").unwrap();
        let stranger = Cipher::new(&[9u8; 32]).unwrap();
        assert!(stranger.unseal(&sealed).is_err());
    }

    #[test]
    fn a_tampered_value_is_refused_rather_than_returned_wrong() {
        // GCM authenticates as well as encrypts, so a flipped bit has to be caught, not decoded
        // into plausible-looking rubbish.
        let sealed = cipher().seal("balance: 100").unwrap();
        let mut raw = BASE64.decode(&sealed).unwrap();
        let last = raw.len() - 1;
        raw[last] ^= 0x01;
        assert!(cipher().unseal(&BASE64.encode(raw)).is_err());
    }

    #[test]
    fn a_short_key_is_rejected() {
        assert!(matches!(Cipher::new(&[0u8; 16]), Err(CipherError::KeyLength)));
    }

    #[test]
    fn nonsense_input_is_malformed_not_a_panic() {
        assert!(matches!(cipher().unseal("not base64 at all!!"), Err(CipherError::Malformed)));
        assert!(matches!(cipher().unseal(""), Err(CipherError::Malformed)));
    }

    #[test]
    fn an_empty_string_round_trips() {
        let sealed = cipher().seal("").unwrap();
        assert_eq!(cipher().unseal(&sealed).unwrap(), "");
    }

    #[test]
    fn text_outside_ascii_survives() {
        let sealed = cipher().seal("कोलकाता ७०० ००१").unwrap();
        assert_eq!(cipher().unseal(&sealed).unwrap(), "कोलकाता ७०० ००१");
    }
}
