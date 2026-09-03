import { z } from 'zod';

/// Every provider implements exactly this, per spec section 19. The gateway and the desktop's BYOK
/// path both program against it, so adding a provider never touches the router or the UI.

export const providerNameSchema = z.enum(['openrouter', 'openai', 'anthropic', 'gemini']);
export type ProviderName = z.infer<typeof providerNameSchema>;

export const modelTierSchema = z.enum(['economy', 'standard', 'premium']);
export type ModelTier = z.infer<typeof modelTierSchema>;

export const taskComplexitySchema = z.enum(['simple', 'moderate', 'complex']);
export type TaskComplexity = z.infer<typeof taskComplexitySchema>;

export const chatRoleSchema = z.enum(['system', 'user', 'assistant']);
export type ChatRole = z.infer<typeof chatRoleSchema>;

/// Preserved through every layer rather than degraded to a plain array. A generation request with
/// no messages is not a runtime error to handle, it is a state the type system can rule out.
export type NonEmptyArray<TItem> = readonly [TItem, ...TItem[]];

export const chatMessageSchema = z.object({
  role: chatRoleSchema,
  content: z.string(),
});
export type ChatMessage = z.infer<typeof chatMessageSchema>;

/// Validation shape for an untrusted boundary.
export const generationRequestSchema = z.object({
  model: z.string().min(1),
  messages: z.array(chatMessageSchema).nonempty(),
  maxOutputTokens: z.number().int().positive().max(32_000).default(2_048),
  temperature: z.number().min(0).max(2).default(0.3),
});

/// The type the interface is written in, declared rather than inferred from the parser. A schema
/// describes what arrives from outside; it should not dictate the shape internal callers hold.
export type GenerationRequest = {
  readonly model: string;
  readonly messages: NonEmptyArray<ChatMessage>;
  readonly maxOutputTokens: number;
  readonly temperature: number;
};

export const tokenUsageSchema = z.object({
  inputTokens: z.number().int().nonnegative(),
  outputTokens: z.number().int().nonnegative(),
});
export type TokenUsage = z.infer<typeof tokenUsageSchema>;

export const generationSchema = z.object({
  text: z.string(),
  model: z.string(),
  provider: providerNameSchema,
  usage: tokenUsageSchema,
  latencyMs: z.number().int().nonnegative(),
  finishReason: z.string(),
});
export type Generation = z.infer<typeof generationSchema>;

export type ProviderHealth = {
  readonly provider: ProviderName;
  readonly reachable: boolean;
  readonly latencyMs: number;
  readonly detail: string;
};

/// Thrown for every provider failure, so callers switch on one type rather than four SDKs'
/// error shapes. `retryable` is what the gateway uses to decide whether a fallback is worth trying.
export class ProviderFailure extends Error {
  readonly provider: ProviderName;
  readonly status: number;
  readonly retryable: boolean;

  constructor(provider: ProviderName, status: number, message: string, retryable: boolean) {
    super(message);
    this.name = 'ProviderFailure';
    this.provider = provider;
    this.status = status;
    this.retryable = retryable;
  }

  static fromStatus(provider: ProviderName, status: number, detail: string): ProviderFailure {
    if (status === 401 || status === 403) {
      return new ProviderFailure(
        provider,
        status,
        `The ${provider} credential was rejected. Check the key and try again.`,
        false,
      );
    }
    if (status === 429) {
      return new ProviderFailure(
        provider,
        status,
        `${provider} is rate limiting this key. Wait a moment or switch model.`,
        true,
      );
    }
    if (status >= 500) {
      return new ProviderFailure(provider, status, `${provider} is having trouble right now.`, true);
    }
    return new ProviderFailure(provider, status, detail, false);
  }
}

export interface ModelProvider {
  readonly name: ProviderName;
  generate(request: GenerationRequest): Promise<Generation>;
  stream(request: GenerationRequest, onChunk: (delta: string) => void): Promise<Generation>;
  countTokens(messages: ReadonlyArray<ChatMessage>): number;
  healthCheck(): Promise<ProviderHealth>;
}

/// Shared HTTP behaviour. Providers differ in their payload shape, not in how they fail.
export abstract class HttpModelProvider implements ModelProvider {
  abstract readonly name: ProviderName;
  protected readonly apiKey: string;
  protected readonly baseUrl: string;

  protected constructor(apiKey: string, baseUrl: string) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  abstract generate(request: GenerationRequest): Promise<Generation>;
  abstract healthCheck(): Promise<ProviderHealth>;

  /// Default streaming is a single chunk. A provider that supports real token streaming overrides
  /// this; one that does not still satisfies the interface without pretending to stream.
  async stream(
    request: GenerationRequest,
    onChunk: (delta: string) => void,
  ): Promise<Generation> {
    const generated = await this.generate(request);
    onChunk(generated.text);
    return generated;
  }

  /// A deliberate estimate, not a tokeniser.
  ///
  /// Shipping a real BPE tokeniser for four providers costs megabytes and still disagrees with
  /// each of them. This exists for pre-flight budget checks; the authoritative counts come back
  /// from the provider in `usage` and are what gets billed and recorded.
  countTokens(messages: ReadonlyArray<ChatMessage>): number {
    const characters = messages.reduce(
      (total, message) => total + message.content.length + message.role.length + 4,
      0,
    );
    return Math.max(1, Math.ceil(characters / 4));
  }

  protected async post(path: string, body: unknown, headers: Record<string, string>): Promise<unknown> {
    const startedAt = Date.now();
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...headers },
        body: JSON.stringify(body),
      });
    } catch (cause) {
      throw new ProviderFailure(
        this.name,
        0,
        `Could not reach ${this.name}. Check the connection.`,
        true,
      );
    }

    const payload: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      const detail =
        typeof payload === 'object' && payload !== null && 'error' in payload
          ? JSON.stringify((payload as { error: unknown }).error).slice(0, 300)
          : `${this.name} returned ${response.status}`;
      throw ProviderFailure.fromStatus(this.name, response.status, detail);
    }

    return { payload, latencyMs: Date.now() - startedAt };
  }
}
