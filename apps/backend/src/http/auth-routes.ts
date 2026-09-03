import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { DeviceId } from '@hawkvance/contracts';
import { deviceIdSchema, deviceRegistrationSchema, profileUpdateSchema } from '@hawkvance/contracts';
import type { AccountRepository } from '../identity/account-repository.js';
import type { AccountWriter } from '../identity/account-writer.js';
import type { Account } from '../identity/account.js';
import { BearerHeader, type NeonIdentityVerifier } from '../identity/neon-identity-token.js';
import type { PlanLimitsRepository } from '../identity/plan-limits-repository.js';
import { HttpProblem } from './errors.js';

export type AuthDependencies = {
  readonly verifier: NeonIdentityVerifier;
  readonly accounts: AccountRepository;
  readonly accountWriter: AccountWriter;
  readonly planLimits: PlanLimitsRepository;
};

/// Every route here is behind a Neon Auth identity token. HawkVance issues no tokens of its own and
/// never sees a password or an OTP code: the desktop app talks to Neon Auth directly for that, then
/// presents the resulting JWT here.
export class AuthRoutes {
  private readonly dependencies: AuthDependencies;

  constructor(dependencies: AuthDependencies) {
    this.dependencies = dependencies;
  }

  register(server: FastifyInstance): void {
    server.get('/auth/me', async (request, reply) => this.currentAccount(request, reply));
    server.patch('/auth/me', async (request, reply) => this.updateProfile(request, reply));
    server.post('/auth/devices', async (request, reply) => this.registerDevice(request, reply));
    server.get('/auth/devices', async (request, reply) => this.listDevices(request, reply));
    server.delete('/auth/devices/:id', async (request, reply) => this.revokeDevice(request, reply));
  }

  /// Also the provisioning endpoint. The first time a Neon identity appears, the HawkVance account
  /// behind it is created here, so there is no separate sign-up call for the client to forget.
  private async currentAccount(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const limits = await this.dependencies.planLimits.forTier(account.plan);
      return reply.code(200).send({ account: account.toResource(), limits });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  /// The person's own name and occupation.
  ///
  /// Scoped to the caller's own account by construction: the account comes from the verified token,
  /// never from the request body, so there is no id a caller could substitute for someone else's.
  /// `profileUpdateSchema` also admits only these two fields, so a profile edit cannot become a
  /// route to changing a plan, role or status.
  private async updateProfile(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const fields = profileUpdateSchema.parse(request.body);

      if (fields.displayName !== undefined) {
        account.rename(fields.displayName.trim());
      }
      if (fields.occupation !== undefined) {
        account.describeOccupation(fields.occupation);
      }
      // Stamped whether or not anything was filled in: it records that they were asked, so a person
      // who skips is not asked again on every launch.
      account.markOnboarded(new Date());

      await this.dependencies.accounts.save(account);
      const limits = await this.dependencies.planLimits.forTier(account.plan);
      return reply.code(200).send({ account: account.toResource(), limits });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async registerDevice(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const registration = deviceRegistrationSchema.parse(request.body);
      const deviceId = await this.dependencies.accountWriter.registerDevice(
        account,
        registration,
        new Date(),
      );
      return reply.code(200).send({ deviceId });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async listDevices(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const rows = await this.dependencies.accounts.listDevices(account.id);
      return reply.code(200).send({
        devices: rows.map((row) => ({
          id: row.id,
          name: row.name,
          platform: row.platform,
          appVersion: row.appVersion,
          firstSeenAt: row.firstSeenAt.toISOString(),
          lastSeenAt: row.lastSeenAt.toISOString(),
        })),
      });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async revokeDevice(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const targetId = deviceIdSchema.parse((request.params as { id: string }).id) as DeviceId;
      const removed = await this.dependencies.accounts.removeDevice(account.id, targetId);
      if (!removed) {
        return reply.code(404).send({
          error: { code: 'device_not_found', message: 'That device is not registered to this account.' },
        });
      }
      return reply.code(204).send();
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async authenticate(request: FastifyRequest): Promise<Account> {
    const token = await this.dependencies.verifier.verify(
      BearerHeader.tokenFrom(request.headers.authorization),
    );
    return this.dependencies.accountWriter.fromIdentity(token, new Date());
  }
}
