/// The one place this app talks to a network.
///
/// Every call goes through `send`, which is not tidiness for its own sake. Renewal of an expired
/// identity token keys off catching an `ApiRejected` with status 401, and only `send` produces
/// one. A screen that called `fetch` directly threw a plain Error instead, so nothing renewed and
/// every request after about fifteen minutes failed in a way that read as being signed out.

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080';

export class ApiUnavailable extends Error {
  constructor(cause: unknown) {
    super('HawkVance could not be reached. Check your internet connection and try again.');
    this.name = 'ApiUnavailable';
    this.cause = cause;
  }
}

export class ApiRejected extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiRejected';
    this.status = status;
    this.code = code;
  }
}

export type AvailableModel = {
  readonly id: string;
  readonly label: string;
  readonly tier: 'economy' | 'standard' | 'premium';
  readonly provider: string;
  readonly contextWindow: number;
};

export type ModelCatalogue = {
  readonly hawkvanceConfigured: boolean;
  readonly byokAllowed: boolean;
  readonly models: ReadonlyArray<AvailableModel>;
  readonly creditCosts: Record<string, number>;
};

export type PlanLimits = {
  readonly monthlyCredits: number;
  readonly allowedModelTiers: ReadonlyArray<string>;
  readonly byokAllowed: boolean;
};

export type Account = {
  readonly id: string;
  readonly email: string;
  readonly displayName: string;
  readonly occupation: string | null;
  readonly status: string;
  readonly role: string;
  readonly plan: 'free' | 'beta' | 'pro' | 'enterprise';
};

export type AccountResponse = {
  readonly account: Account;
  readonly limits: PlanLimits;
};

export type UsageReport = {
  readonly usage: { readonly creditsRemaining: number; readonly creditsSpent: number };
  readonly limits: { readonly monthlyCredits: number };
};

export type CompletionRequest = {
  readonly messages: ReadonlyArray<{ role: 'user' | 'assistant'; content: string }>;
  readonly maxOutputTokens?: number;
  readonly workspaceId?: string;
  readonly preferredModelId?: string;
  readonly globalMemory?: boolean;
};

export type CompletionResult = {
  readonly text: string;
  readonly model: string;
  readonly modelLabel: string;
  readonly creditsSpent: number;
  readonly attemptedFallback: boolean;
};

export class HawkVanceApi {
  private readonly baseUrl: string;

  constructor(baseUrl: string = apiBaseUrl) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  async currentAccount(identityToken: string): Promise<AccountResponse> {
    return (await this.send('GET', '/auth/me', identityToken)) as AccountResponse;
  }

  async updateProfile(
    identityToken: string,
    fields: { displayName?: string; occupation?: string | null },
  ): Promise<AccountResponse> {
    return (await this.send('PATCH', '/auth/me', identityToken, fields)) as AccountResponse;
  }

  async models(identityToken: string): Promise<ModelCatalogue> {
    return (await this.send('GET', '/ai/models', identityToken)) as ModelCatalogue;
  }

  async usage(identityToken: string): Promise<UsageReport> {
    return (await this.send('GET', '/ai/usage', identityToken)) as UsageReport;
  }

  async complete(identityToken: string, request: CompletionRequest): Promise<CompletionResult> {
    return (await this.send('POST', '/ai/complete', identityToken, request)) as CompletionResult;
  }

  private async send(
    method: string,
    path: string,
    identityToken: string,
    body?: unknown,
  ): Promise<unknown> {
    const headers: Record<string, string> = {
      accept: 'application/json',
      authorization: `Bearer ${identityToken}`,
    };
    if (body !== undefined) {
      headers['content-type'] = 'application/json';
    }

    const init: RequestInit =
      body === undefined ? { method, headers } : { method, headers, body: JSON.stringify(body) };

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, init);
    } catch (cause) {
      // A refused connection is not a rejection, and must not be mistaken for one: renewing a
      // token would not help, and telling somebody they are signed out would be wrong.
      throw new ApiUnavailable(cause);
    }

    const payload = response.status === 204 ? null : await response.json().catch(() => null);

    if (!response.ok) {
      const problem = payload as { data?: { error?: { code?: string; message?: string } } } | null;
      const error = problem?.data?.error;
      throw error?.code !== undefined && error.message !== undefined
        ? new ApiRejected(response.status, error.code, error.message)
        : new ApiRejected(response.status, 'unexpected_error', 'That request did not succeed.');
    }

    return payload;
  }
}
