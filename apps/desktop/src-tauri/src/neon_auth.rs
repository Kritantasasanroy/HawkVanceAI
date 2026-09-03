//! Sign-in against Neon Auth, over email codes.
//!
//! The session itself never reaches the web view. It lives here and in the vault, and the renderer
//! is only ever handed a short-lived identity token to put in an Authorization header. A session
//! that a script in the web view could read is a session that page content could steal.
//!
//! Three things about this exchange are not obvious and each one cost a working sign-in to learn:
//!
//! 1. The sign-in POSTs must not carry a cookie. Better Auth treats a request that arrives with a
//!    session cookie but no browser Origin as a cross-site forgery attempt and rejects it before
//!    it ever looks at the code, which surfaces as a 403 that says nothing about the code.
//! 2. The bearer plugin is not enabled on this project, so there is no token in a response header.
//!    The session arrives as a `Set-Cookie` and has to be captured from there.
//! 3. That captured cookie is replayed on exactly one request, the `GET /token` that mints the
//!    identity JWT, and nowhere else.

use serde_json::{json, Value};

const SESSION_COOKIE: &str = "__Secure-neon-auth.session_token";

#[derive(Debug, thiserror::Error)]
pub enum SignInFailure {
    #[error("We could not reach HawkVance just now. Check your internet connection and try again.")]
    Unreachable,
    #[error("That code is not right. Check it and type it again.")]
    WrongCode,
    #[error("That code has run out. Ask for a new one.")]
    Expired,
    #[error("That does not look like an email address.")]
    BadEmail,
    #[error("Too many tries just now. Wait a minute and try again.")]
    TooMany,
    #[error("Something went wrong at our end. Please try again in a moment.")]
    Server,
}

impl SignInFailure {
    /// Turns a response into something a person can act on.
    ///
    /// Deliberately never surfaces the status code or the body. A sign-in screen that prints a
    /// JSON fragment tells the person nothing they can use and makes a working product look broken.
    fn from_response(status: u16, body: &str) -> Self {
        let lowered = body.to_lowercase();
        match status {
            400 if lowered.contains("email") => SignInFailure::BadEmail,
            400 | 401 if lowered.contains("expired") => SignInFailure::Expired,
            400 | 401 => SignInFailure::WrongCode,
            403 => SignInFailure::Server,
            429 => SignInFailure::TooMany,
            _ => SignInFailure::Server,
        }
    }
}

pub struct NeonAuth {
    base_url: String,
    client: reqwest::Client,
    session_cookie: Option<String>,
}

impl NeonAuth {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into().trim_end_matches('/').to_string(),
            // No cookie jar, by leaving reqwest's `cookies` feature off entirely rather than by
            // switching one off here. See the note at the top of this file: a cookie sent on the
            // sign-in POSTs is what makes them fail, and a jar would attach one automatically the
            // moment the sign-in response set it. Not having the feature makes that impossible
            // rather than merely switched off.
            client: reqwest::Client::builder().build().unwrap_or_default(),
            session_cookie: None,
        }
    }

    fn origin(&self) -> String {
        // Better Auth wants an Origin it recognises. Sending the auth host's own origin is what
        // makes it treat the call as first-party rather than as a forgery.
        reqwest::Url::parse(&self.base_url)
            .ok()
            .map(|url| url.origin().ascii_serialization())
            .unwrap_or_else(|| self.base_url.clone())
    }

    /// Sends a six-digit code to an email address, creating the account if it is new.
    pub async fn send_code(&self, email: &str) -> Result<(), SignInFailure> {
        let response = self
            .client
            .post(format!("{}/api/v1/auth/otp/send-sign-in-code", self.base_url))
            .header("origin", self.origin())
            .json(&json!({ "email": email }))
            .send()
            .await
            .map_err(|_| SignInFailure::Unreachable)?;

        let status = response.status().as_u16();
        if (200..300).contains(&status) {
            return Ok(());
        }
        let body = response.text().await.unwrap_or_default();
        Err(SignInFailure::from_response(status, &body))
    }

    /// Exchanges a code for a session, and keeps the session here.
    pub async fn verify_code(&mut self, email: &str, code: &str) -> Result<(), SignInFailure> {
        let response = self
            .client
            .post(format!("{}/api/v1/auth/otp/sign-in", self.base_url))
            .header("origin", self.origin())
            .json(&json!({ "email": email, "otp": code }))
            .send()
            .await
            .map_err(|_| SignInFailure::Unreachable)?;

        let status = response.status().as_u16();
        if !(200..300).contains(&status) {
            let body = response.text().await.unwrap_or_default();
            return Err(SignInFailure::from_response(status, &body));
        }

        self.capture_cookie(response.headers());
        if self.session_cookie.is_none() {
            return Err(SignInFailure::Server);
        }
        Ok(())
    }

    fn capture_cookie(&mut self, headers: &reqwest::header::HeaderMap) {
        for value in headers.get_all(reqwest::header::SET_COOKIE) {
            let Ok(text) = value.to_str() else { continue };
            if let Some(pair) = text.split(';').next() {
                if pair.trim_start().starts_with(SESSION_COOKIE) {
                    self.session_cookie = Some(pair.trim().to_string());
                    return;
                }
            }
        }
    }

    /// Mints a fresh identity token, which is the only thing the renderer ever sees.
    ///
    /// Takes `&mut self` because the response may carry a refreshed cookie, and keeping it is what
    /// gives the session a rolling window rather than a hard expiry a few minutes after sign-in.
    pub async fn identity_token(&mut self) -> Result<String, SignInFailure> {
        let cookie = self
            .session_cookie
            .clone()
            .ok_or(SignInFailure::Server)?;

        let response = self
            .client
            .get(format!("{}/api/v1/auth/token", self.base_url))
            .header("origin", self.origin())
            .header(reqwest::header::COOKIE, cookie)
            .send()
            .await
            .map_err(|_| SignInFailure::Unreachable)?;

        let status = response.status().as_u16();
        if !(200..300).contains(&status) {
            return Err(SignInFailure::from_response(status, ""));
        }

        self.capture_cookie(response.headers());

        let body: Value = response.json().await.map_err(|_| SignInFailure::Server)?;
        body.get("token")
            .or_else(|| body.get("accessToken"))
            .and_then(Value::as_str)
            .map(str::to_string)
            .ok_or(SignInFailure::Server)
    }

    pub fn stored_cookie(&self) -> Option<String> {
        self.session_cookie.clone()
    }

    /// Puts back a session kept in the vault from a previous run, so closing the app does not sign
    /// somebody out.
    pub fn restore_cookie(&mut self, cookie: String) {
        if !cookie.trim().is_empty() {
            self.session_cookie = Some(cookie);
        }
    }

    pub fn sign_out(&mut self) {
        self.session_cookie = None;
    }

    pub fn is_signed_in(&self) -> bool {
        self.session_cookie.is_some()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn failures_are_written_for_a_person_not_a_developer() {
        // No status codes, no field names, no JSON. Every one of these is something the reader can
        // actually do something about.
        for failure in [
            SignInFailure::Unreachable,
            SignInFailure::WrongCode,
            SignInFailure::Expired,
            SignInFailure::BadEmail,
            SignInFailure::TooMany,
            SignInFailure::Server,
        ] {
            let message = failure.to_string();
            assert!(!message.contains("40"), "a status code leaked into: {message}");
            assert!(!message.contains('{'), "a payload leaked into: {message}");
            assert!(
                message.chars().next().is_some_and(char::is_uppercase),
                "not a sentence: {message}"
            );
        }
    }

    #[test]
    fn a_wrong_code_says_so_rather_than_blaming_the_server() {
        assert!(matches!(
            SignInFailure::from_response(401, "invalid otp"),
            SignInFailure::WrongCode
        ));
    }

    #[test]
    fn an_expired_code_is_told_apart_from_a_wrong_one() {
        // These need different advice: retype it, versus ask for a new one.
        assert!(matches!(
            SignInFailure::from_response(400, "the code has expired"),
            SignInFailure::Expired
        ));
    }

    #[test]
    fn rate_limiting_asks_the_person_to_wait() {
        assert!(matches!(
            SignInFailure::from_response(429, ""),
            SignInFailure::TooMany
        ));
    }

    #[test]
    fn a_restored_session_counts_as_signed_in() {
        let mut auth = NeonAuth::new("https://example.neonauth.test/neondb/auth");
        assert!(!auth.is_signed_in());
        auth.restore_cookie(format!("{SESSION_COOKIE}=abc123"));
        assert!(auth.is_signed_in());
    }

    #[test]
    fn an_empty_restored_cookie_is_ignored() {
        // An empty setting in the vault must not look like a live session, or the app shows the
        // signed-in shell and then fails on the first request.
        let mut auth = NeonAuth::new("https://example.neonauth.test/neondb/auth");
        auth.restore_cookie(String::new());
        assert!(!auth.is_signed_in());
    }

    #[test]
    fn signing_out_forgets_the_session() {
        let mut auth = NeonAuth::new("https://example.neonauth.test/neondb/auth");
        auth.restore_cookie(format!("{SESSION_COOKIE}=abc123"));
        auth.sign_out();
        assert!(!auth.is_signed_in());
        assert_eq!(auth.stored_cookie(), None);
    }

    #[test]
    fn the_origin_is_the_auth_hosts_own() {
        let auth = NeonAuth::new("https://example.neonauth.test/neondb/auth");
        assert_eq!(auth.origin(), "https://example.neonauth.test");
    }

    #[test]
    fn a_token_cannot_be_minted_without_a_session() {
        let auth = NeonAuth::new("https://example.neonauth.test/neondb/auth");
        assert!(auth.stored_cookie().is_none());
    }
}
