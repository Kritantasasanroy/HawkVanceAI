import { randomUUID } from 'node:crypto';
import { and, desc, eq } from 'drizzle-orm';
import type {
  AccountId,
  AccountRole,
  AccountStatus,
  DeviceId,
  DeviceRegistration,
  EmailAddress,
  PlanTier,
} from '@hawkvance/contracts';
import type { Database } from '../db/client.js';
import { accounts, devices } from '../db/schema.js';
import { Account } from './account.js';

export class AccountRepository {
  private readonly database: Database;

  constructor(database: Database) {
    this.database = database;
  }

  async findByEmail(email: EmailAddress): Promise<Account | null> {
    const [row] = await this.database.drizzle
      .select()
      .from(accounts)
      .where(eq(accounts.email, email.canonical))
      .limit(1);
    return row === undefined ? null : AccountRepository.hydrate(row);
  }

  async findByNeonUserId(neonUserId: string): Promise<Account | null> {
    const [row] = await this.database.drizzle
      .select()
      .from(accounts)
      .where(eq(accounts.neonUserId, neonUserId))
      .limit(1);
    return row === undefined ? null : AccountRepository.hydrate(row);
  }

  async linkNeonUser(id: AccountId, neonUserId: string): Promise<void> {
    await this.database.drizzle.update(accounts).set({ neonUserId }).where(eq(accounts.id, id));
  }

  async findById(id: AccountId): Promise<Account | null> {
    const [row] = await this.database.drizzle.select().from(accounts).where(eq(accounts.id, id)).limit(1);
    return row === undefined ? null : AccountRepository.hydrate(row);
  }

  async insert(account: Account): Promise<void> {
    const fields = account.snapshot;
    await this.database.drizzle.insert(accounts).values({
      id: fields.id,
      neonUserId: fields.neonUserId,
      email: fields.email,
      emailDomain: fields.emailDomain,
      displayName: fields.displayName,
      occupation: fields.occupation,
      onboardedAt: fields.onboardedAt,
      status: fields.status,
      role: fields.role,
      plan: fields.plan,
      suspendedReason: fields.suspendedReason,
      createdAt: fields.createdAt,
      lastSeenAt: fields.lastSeenAt,
    });
  }

  async save(account: Account): Promise<void> {
    const fields = account.snapshot;
    await this.database.drizzle
      .update(accounts)
      .set({
        displayName: fields.displayName,
        occupation: fields.occupation,
        onboardedAt: fields.onboardedAt,
        status: fields.status,
        role: fields.role,
        plan: fields.plan,
        suspendedReason: fields.suspendedReason,
        lastSeenAt: fields.lastSeenAt,
      })
      .where(eq(accounts.id, fields.id));
  }

  async registerDevice(
    accountId: AccountId,
    registration: DeviceRegistration,
    moment: Date,
  ): Promise<DeviceId> {
    const [existing] = await this.database.drizzle
      .select({ id: devices.id })
      .from(devices)
      .where(
        and(
          eq(devices.accountId, accountId),
          eq(devices.name, registration.name),
          eq(devices.platform, registration.platform),
        ),
      )
      .limit(1);

    if (existing !== undefined) {
      await this.database.drizzle
        .update(devices)
        .set({ appVersion: registration.appVersion, lastSeenAt: moment })
        .where(eq(devices.id, existing.id));
      return existing.id as DeviceId;
    }

    const id = randomUUID() as DeviceId;
    await this.database.drizzle.insert(devices).values({
      id,
      accountId,
      name: registration.name,
      platform: registration.platform,
      appVersion: registration.appVersion,
      firstSeenAt: moment,
      lastSeenAt: moment,
    });
    return id;
  }

  async listDevices(accountId: AccountId): Promise<ReadonlyArray<typeof devices.$inferSelect>> {
    return this.database.drizzle
      .select()
      .from(devices)
      .where(eq(devices.accountId, accountId))
      .orderBy(desc(devices.lastSeenAt));
  }

  async removeDevice(accountId: AccountId, deviceId: DeviceId): Promise<boolean> {
    const removed = await this.database.drizzle
      .delete(devices)
      .where(and(eq(devices.id, deviceId), eq(devices.accountId, accountId)))
      .returning({ id: devices.id });
    return removed.length === 1;
  }

  private static hydrate(row: typeof accounts.$inferSelect): Account {
    return new Account({
      id: row.id as AccountId,
      neonUserId: row.neonUserId,
      email: row.email,
      emailDomain: row.emailDomain,
      displayName: row.displayName,
      occupation: row.occupation,
      onboardedAt: row.onboardedAt,
      status: row.status as AccountStatus,
      role: row.role as AccountRole,
      plan: row.plan as PlanTier,
      suspendedReason: row.suspendedReason,
      createdAt: row.createdAt,
      lastSeenAt: row.lastSeenAt,
    });
  }
}
