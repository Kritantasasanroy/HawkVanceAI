import { randomUUID } from 'node:crypto';
import type {
  Account as AccountResource,
  AccountId,
  AccountRole,
  AccountStatus,
  EmailAddress,
  PlanTier,
} from '@hawkvance/contracts';

export class AccountNotSignInEligible extends Error {
  readonly status: AccountStatus;

  constructor(status: AccountStatus) {
    super(
      status === 'suspended'
        ? 'This account is suspended. Contact support@hawkvance.ai to restore access.'
        : 'This account is no longer active. Create a new account or contact support.',
    );
    this.name = 'AccountNotSignInEligible';
    this.status = status;
  }
}

export type AccountFields = {
  readonly id: AccountId;
  neonUserId: string;
  readonly email: string;
  readonly emailDomain: string;
  displayName: string;
  occupation: string | null;
  onboardedAt: Date | null;
  status: AccountStatus;
  role: AccountRole;
  plan: PlanTier;
  suspendedReason: string | null;
  readonly createdAt: Date;
  lastSeenAt: Date;
};

export class Account {
  private readonly fields: AccountFields;

  constructor(fields: AccountFields) {
    this.fields = fields;
  }

  static register(request: {
    email: EmailAddress;
    registeredAt: Date;
    neonUserId: string;
    displayName: string;
  }): Account {
    return new Account({
      id: randomUUID() as AccountId,
      neonUserId: request.neonUserId,
      email: request.email.canonical,
      emailDomain: request.email.domain,
      displayName: request.displayName,
      occupation: null,
      onboardedAt: null,
      status: 'active',
      role: 'member',
      plan: 'beta',
      suspendedReason: null,
      createdAt: request.registeredAt,
      lastSeenAt: request.registeredAt,
    });
  }

  get id(): AccountId {
    return this.fields.id;
  }

  get email(): string {
    return this.fields.email;
  }

  get neonUserId(): string {
    return this.fields.neonUserId;
  }

  adoptNeonUser(neonUserId: string): void {
    this.fields.neonUserId = neonUserId;
  }

  get status(): AccountStatus {
    return this.fields.status;
  }

  get role(): AccountRole {
    return this.fields.role;
  }

  get plan(): PlanTier {
    return this.fields.plan;
  }

  get snapshot(): AccountFields {
    return this.fields;
  }

  get canSignIn(): boolean {
    return this.fields.status === 'pending' || this.fields.status === 'active';
  }

  activate(moment: Date): void {
    if (!this.canSignIn) {
      throw new AccountNotSignInEligible(this.fields.status);
    }
    this.fields.status = 'active';
    this.fields.lastSeenAt = moment;
  }

  suspend(reason: string, moment: Date): void {
    this.fields.status = 'suspended';
    this.fields.suspendedReason = reason;
    this.fields.lastSeenAt = moment;
  }

  reactivate(moment: Date): void {
    this.fields.status = 'active';
    this.fields.suspendedReason = null;
    this.fields.lastSeenAt = moment;
  }

  softDelete(moment: Date): void {
    this.fields.status = 'deleted';
    this.fields.lastSeenAt = moment;
  }

  changePlan(plan: PlanTier): void {
    this.fields.plan = plan;
  }

  changeRole(role: AccountRole): void {
    this.fields.role = role;
  }

  rename(displayName: string): void {
    this.fields.displayName = displayName;
  }

  describeOccupation(occupation: string | null): void {
    const trimmed = occupation?.trim() ?? '';
    this.fields.occupation = trimmed.length === 0 ? null : trimmed;
  }

  get isOnboarded(): boolean {
    return this.fields.onboardedAt !== null;
  }

  /// Recorded once, the first time the person is asked for their name and occupation.
  ///
  /// Stamped whether or not they filled anything in, because it records that they were asked. Left
  /// unstamped on a skip, the same question would greet them on every launch.
  markOnboarded(moment: Date): void {
    this.fields.onboardedAt ??= moment;
  }

  toResource(): AccountResource {
    return {
      id: this.fields.id,
      email: this.fields.email,
      displayName: this.fields.displayName,
      occupation: this.fields.occupation,
      onboardedAt: this.fields.onboardedAt?.toISOString() ?? null,
      status: this.fields.status,
      role: this.fields.role,
      plan: this.fields.plan,
      createdAt: this.fields.createdAt.toISOString(),
      lastSeenAt: this.fields.lastSeenAt.toISOString(),
    };
  }
}
