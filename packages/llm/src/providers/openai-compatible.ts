import { z } from 'zod';
import {
  HttpModelProvider,
  ProviderFailure,
  type Generation,
  type GenerationRequest,
  type ProviderHealth,
  type ProviderName,
} from '../provider.js';

const completionSchema = z.object({
  choices: z
    .array(
      z.object({
        message: z.object({ content: z.string().nullable() }),
        finish_reason: z.string().nullish(),
      }),
    )
    .nonempty(),
  model: z.string().optional(),
  usage: z
    .object({
      prompt_tokens: z.number().int().nonnegative().optional(),
      completion_tokens: z.number().int().nonnegative().optional(),
    })
    .optional(),
});

/// OpenRouter and OpenAI speak the same chat-completions dialect, so one implementation serves
/// both. That is the whole reason OpenRouter is the aggregation layer: adding a model behind it
/// costs a registry entry, not a new client.
export abstract class OpenAiCompatibleProvider extends HttpModelProvider {
  protected extraHeaders(): Record<string, string> {
    return {};
  }

  async generate(request: GenerationRequest): Promise<Generation> {
    const result = (await this.post(
      '/chat/completions',
      {
        model: request.model,
        messages: request.messages,
        max_tokens: request.maxOutputTokens,
        temperature: request.temperature,
      },
      { authorization: `Bearer ${this.apiKey}`, ...this.extraHeaders() },
    )) as { payload: unknown; latencyMs: number };

    const parsed = completionSchema.safeParse(result.payload);
    if (!parsed.success) {
      throw new ProviderFailure(
        this.name,
        502,
        `${this.name} returned a response HawkVance could not read.`,
        true,
      );
    }

    const choice = parsed.data.choices[0];
    const estimated = this.countTokens(request.messages);

    return {
      text: choice.message.content ?? '',
      model: parsed.data.model ?? request.model,
      provider: this.name,
      usage: {
        inputTokens: parsed.data.usage?.prompt_tokens ?? estimated,
        outputTokens:
          parsed.data.usage?.completion_tokens ??
          Math.ceil((choice.message.content ?? '').length / 4),
      },
      latencyMs: result.latencyMs,
      finishReason: choice.finish_reason ?? 'stop',
    };
  }

  async healthCheck(): Promise<ProviderHealth> {
    const startedAt = Date.now();
    try {
      const response = await fetch(`${this.baseUrl}/models`, {
        headers: { authorization: `Bearer ${this.apiKey}`, ...this.extraHeaders() },
      });
      return {
        provider: this.name,
        reachable: response.ok,
        latencyMs: Date.now() - startedAt,
        detail: response.ok ? 'reachable' : `returned ${response.status}`,
      };
    } catch (cause) {
      return {
        provider: this.name,
        reachable: false,
        latencyMs: Date.now() - startedAt,
        detail: cause instanceof Error ? cause.message : 'unreachable',
      };
    }
  }
}

export class OpenRouterProvider extends OpenAiCompatibleProvider {
  readonly name: ProviderName = 'openrouter';

  constructor(apiKey: string, baseUrl = 'https://openrouter.ai/api/v1') {
    super(apiKey, baseUrl);
  }

  /// OpenRouter attributes traffic by these headers. They identify the application, never the user.
  protected override extraHeaders(): Record<string, string> {
    return {
      'HTTP-Referer': 'https://hawkvance.ai',
      'X-Title': 'HawkVance AI',
    };
  }
}

export class OpenAiProvider extends OpenAiCompatibleProvider {
  readonly name: ProviderName = 'openai';

  constructor(apiKey: string, baseUrl = 'https://api.openai.com/v1') {
    super(apiKey, baseUrl);
  }
}
