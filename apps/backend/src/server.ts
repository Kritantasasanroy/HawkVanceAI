import cors from '@fastify/cors';
import helmet from '@fastify/helmet';
import rateLimit from '@fastify/rate-limit';
import Fastify, { type FastifyInstance } from 'fastify';
import type { Configuration } from './config.js';
import type { Database } from './db/client.js';
import { ModelRouter, OpenRouterProvider, freeCatalogue } from '@hawkvance/llm';
import { AiGateway } from './gateway/ai-gateway.js';
import { QuotaLedger } from './gateway/quota-ledger.js';
import { AdminRoutes } from './http/admin-routes.js';
import { AuthRoutes } from './http/auth-routes.js';
import { GatewayRoutes } from './http/gateway-routes.js';
import { AccountRepository } from './identity/account-repository.js';
import { AccountWriter } from './identity/account-writer.js';
import type { NeonIdentityVerifier } from './identity/neon-identity-token.js';
import { PlanLimitsRepository } from './identity/plan-limits-repository.js';

export class HawkVanceServer {
  readonly fastify: FastifyInstance;
  private readonly database: Database;

  private constructor(fastify: FastifyInstance, database: Database) {
    this.fastify = fastify;
    this.database = database;
  }

  static async assemble(
    configuration: Configuration,
    database: Database,
    verifier: NeonIdentityVerifier,
  ): Promise<HawkVanceServer> {
    const fastify = Fastify({
      logger: {
        level: configuration.environment.NODE_ENV === 'test' ? 'silent' : configuration.isProduction ? 'info' : 'debug',
        redact: {
          paths: [
            'req.headers.authorization',
            'req.headers.cookie',
            'req.body.otp',
            'req.body.token',
          ],
          censor: '[redacted]',
        },
      },
      trustProxy: true,
      bodyLimit: 1_048_576,
    });

    await fastify.register(helmet, { contentSecurityPolicy: false });
    await fastify.register(cors, {
      origin: configuration.environment.CORS_ALLOWED_ORIGINS.length === 0
        ? false
        : configuration.environment.CORS_ALLOWED_ORIGINS,
      credentials: true,
    });
    await fastify.register(rateLimit, {
      max: 60,
      timeWindow: '1 minute',
      keyGenerator: (request) => request.ip,
    });

    const accounts = new AccountRepository(database);
    const accountWriter = new AccountWriter(accounts);
    const planLimits = new PlanLimitsRepository(database);

    new AuthRoutes({ verifier, accounts, accountWriter, planLimits }).register(fastify);

    const gateway = new AiGateway(
      configuration.hasManagedInference
        ? new OpenRouterProvider(configuration.environment.OPENROUTER_API_KEY)
        : null,
      new ModelRouter(freeCatalogue),
      new QuotaLedger(database),
    );
    new GatewayRoutes({ verifier, accounts, accountWriter, planLimits, gateway }).register(fastify);
    new AdminRoutes({ verifier, accounts, accountWriter, database }).register(fastify);

    fastify.get('/health', async () => ({
      status: 'ok',
      database: await database.isReachable(),
      managedInference: configuration.hasManagedInference,
      version: process.env.npm_package_version ?? '0.1.0',
    }));

    return new HawkVanceServer(fastify, database);
  }

  async listen(host: string, port: number): Promise<string> {
    return this.fastify.listen({ host, port });
  }

  async shutdown(): Promise<void> {
    await this.fastify.close();
    await this.database.close();
  }
}
