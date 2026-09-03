import type { FastifyReply } from 'fastify';
import { ZodError } from 'zod';
import type { ApiError } from '@hawkvance/contracts';
import { InvalidEmailAddress } from '@hawkvance/contracts';
import { AccountNotSignInEligible } from '../identity/account.js';
import { IdentityTokenRejected } from '../identity/neon-identity-token.js';
import { PlanLimitsMissing } from '../identity/plan-limits-repository.js';
import { NoModelAvailable, ProviderFailure } from '@hawkvance/llm';
import { GatewayUnconfigured, ModelBusy } from '../gateway/ai-gateway.js';
import { QuotaExceeded } from '../gateway/quota-ledger.js';
import { NotPermitted } from './admin-routes.js';

export class HttpProblem {
  readonly statusCode: number;
  readonly body: ApiError;

  private constructor(statusCode: number, code: string, message: string, retryAfterSeconds?: number) {
    this.statusCode = statusCode;
    this.body = {
      error: retryAfterSeconds === undefined ? { code, message } : { code, message, retryAfterSeconds },
    };
    Object.freeze(this);
  }

  static from(cause: unknown): HttpProblem {
    if (cause instanceof ZodError) {
      const first = cause.issues[0];
      return new HttpProblem(
        400,
        'invalid_request',
        first === undefined ? 'That request was not valid.' : `${first.path.join('.')}: ${first.message}`,
      );
    }
    if (cause instanceof InvalidEmailAddress) {
      return new HttpProblem(400, 'invalid_email', cause.message);
    }
    if (cause instanceof AccountNotSignInEligible) {
      return new HttpProblem(403, 'account_not_eligible', cause.message);
    }
    if (cause instanceof IdentityTokenRejected) {
      return new HttpProblem(401, 'identity_token_rejected', cause.message);
    }
    if (cause instanceof PlanLimitsMissing) {
      return new HttpProblem(503, 'plan_limits_missing', cause.message);
    }
    if (cause instanceof NotPermitted) {
      return new HttpProblem(403, 'not_permitted', cause.message);
    }
    if (cause instanceof QuotaExceeded) {
      return new HttpProblem(429, 'quota_exceeded', cause.message);
    }
    if (cause instanceof ModelBusy) {
      // 503 rather than 502: the model is fine, it is oversubscribed, and trying again shortly is
      // the right advice.
      return new HttpProblem(503, 'model_busy', cause.message);
    }
    if (cause instanceof GatewayUnconfigured) {
      return new HttpProblem(503, 'gateway_unconfigured', cause.message);
    }
    if (cause instanceof NoModelAvailable) {
      return new HttpProblem(409, 'no_model_available', cause.message);
    }
    if (cause instanceof ProviderFailure) {
      return new HttpProblem(cause.retryable ? 503 : 502, 'provider_failed', cause.message);
    }
    return new HttpProblem(
      500,
      'internal_error',
      'Something went wrong on our side. Try again, and contact support if it continues.',
    );
  }

  send(reply: FastifyReply): FastifyReply {
    return reply.code(this.statusCode).send(this.body);
  }
}
