import { invoke } from '@tauri-apps/api/core';

/// Sign-in, as far as this process is concerned.
///
/// Every call here is a Tauri command. The session itself lives in Rust and in the encrypted
/// vault; what comes back is a short-lived identity token to put in a header. Nothing in this file
/// can read or keep the session, which is deliberate: this process renders model output and
/// document text, so anything it can reach should be assumed reachable by page content.

export class SignInFailed extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SignInFailed';
  }
}

function readable(cause: unknown): SignInFailed {
  if (typeof cause === 'object' && cause !== null && 'message' in cause) {
    return new SignInFailed(String((cause as { message: unknown }).message));
  }
  return new SignInFailed('That did not work just now. Please try again.');
}

export class NeonAuthClient {
  /// Sends a six-digit code. The same code creates the account if it is a new address.
  static async sendCode(email: string): Promise<void> {
    try {
      await invoke('auth_send_code', { email });
    } catch (cause) {
      throw readable(cause);
    }
  }

  static async verifyCode(email: string, code: string): Promise<string> {
    try {
      const result = await invoke<{ identityToken: string }>('auth_verify_code', { email, code });
      return result.identityToken;
    } catch (cause) {
      throw readable(cause);
    }
  }

  /// A fresh identity token for a session that is still good.
  static async identityToken(): Promise<string> {
    const result = await invoke<{ identityToken: string }>('auth_identity_token');
    return result.identityToken;
  }

  /// Picks up a session kept from a previous run, so closing the app is not signing out.
  static async restore(): Promise<string | null> {
    try {
      const result = await invoke<{ signedIn: boolean; identityToken?: string }>('auth_restore');
      return result.signedIn ? result.identityToken ?? null : null;
    } catch {
      return null;
    }
  }

  static async signOut(): Promise<void> {
    await invoke('auth_sign_out').catch(() => undefined);
  }
}
