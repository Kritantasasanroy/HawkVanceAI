import type { DeviceId, DeviceRegistration } from '@hawkvance/contracts';
import { EmailAddress } from '@hawkvance/contracts';
import { Account, AccountNotSignInEligible } from './account.js';
import type { AccountRepository } from './account-repository.js';
import type { NeonIdentityToken } from './neon-identity-token.js';

/// Turns a verified Neon identity into a HawkVance account. This is the seam between "who Neon says
/// you are" and "what you are to HawkVance": Neon owns authentication, this owns entitlement.
///
/// The decision spans Account and Device, which is why it lives on a writer rather than on either
/// entity (see docs/designs/auth-and-identity.md).
export class AccountWriter {
  private readonly accounts: AccountRepository;

  constructor(accounts: AccountRepository) {
    this.accounts = accounts;
  }

  /// Finds the account behind a verified token, provisioning one on first sign-in. Registration is
  /// nothing more than Neon vouching for an address, so there is no separate sign-up step.
  async fromIdentity(token: NeonIdentityToken, moment: Date): Promise<Account> {
    const existing = await this.accounts.findByNeonUserId(token.neonUserId);
    if (existing !== null) {
      return this.admit(existing, moment);
    }

    const email = EmailAddress.parse(token.email);

    /// An account may already exist for this address from an earlier identity, for instance if the
    /// Neon user was recreated. Adopt it rather than colliding on the unique email index.
    const byEmail = await this.accounts.findByEmail(email);
    if (byEmail !== null) {
      await this.accounts.linkNeonUser(byEmail.id, token.neonUserId);
      return this.admit(byEmail, moment);
    }

    const registered = Account.register({
      email,
      registeredAt: moment,
      neonUserId: token.neonUserId,
      displayName: token.displayName,
    });
    await this.accounts.insert(registered);
    return this.admit(registered, moment);
  }

  private async admit(account: Account, moment: Date): Promise<Account> {
    if (!account.canSignIn) {
      throw new AccountNotSignInEligible(account.status);
    }
    account.activate(moment);
    await this.accounts.save(account);
    return account;
  }

  async registerDevice(
    account: Account,
    registration: DeviceRegistration,
    moment: Date,
  ): Promise<DeviceId> {
    return this.accounts.registerDevice(account.id, registration, moment);
  }
}
