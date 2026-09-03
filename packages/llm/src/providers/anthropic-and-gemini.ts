import { z } from 'zod';
import {
  HttpModelProvider,
  ProviderFailure,
  type ChatMessage,
  type Generation,
  type GenerationRequest,
  type ProviderHealth,
  type ProviderName,
} from '../provider.js';

const anthropicSchema = z.object({
  content: z.array(z.object({ type: z.string(), text: z.string().optional() })),
  model: z.string().optional(),
  stop_reason: z.string().nullish(),
  usage: z
    .object({
      input_tokens: z.number().int().nonnegative().optional(),
      output_tokens: z.number().int().nonnegative().optional(),
    })
    .optional(),
});

/// Anthropic's Messages API takes the system prompt as a top-level field rather than a message,
/// which is the one structural difference from the OpenAI dialect.
export class AnthropicProvider extends HttpModelProvider {
  readonly name: ProviderName = 'anthropic';
  private readonly version: string;

  constructor(apiKey: string, baseUrl = 'https://api.anthropic.com/v1', version = '2023-06-01') {
    super(apiKey, baseUrl);
    this.version = version;
  }

  async generate(request: GenerationRequest): Promise<Generation> {
    const system = request.messages
      .filter((message) => message.role === 'system')
      .map((message) => message.content)
      .join('\n\n');
    const conversation = request.messages.filter((message) => message.role !== 'system');

    const result = (await this.post(
      '/messages',
      {
        model: request.model,
        max_tokens: request.maxOutputTokens,
        temperature: request.temperature,
        ...(system.length > 0 ? { system } : {}),
        messages: conversation.map((message) => ({
          role: message.role,
          content: message.content,
        })),
      },
      { 'x-api-key': this.apiKey, 'anthropic-version': this.version },
    )) as { payload: unknown; latencyMs: number };

    const parsed = anthropicSchema.safeParse(result.payload);
    if (!parsed.success) {
      throw new ProviderFailure(this.name, 502, 'Anthropic returned an unreadable response.', true);
    }

    const text = parsed.data.content
      .filter((block) => block.type === 'text')
      .map((block) => block.text ?? '')
      .join('');

    return {
      text,
      model: parsed.data.model ?? request.model,
      provider: this.name,
      usage: {
        inputTokens: parsed.data.usage?.input_tokens ?? this.countTokens(request.messages),
        outputTokens: parsed.data.usage?.output_tokens ?? Math.ceil(text.length / 4),
      },
      latencyMs: result.latencyMs,
      finishReason: parsed.data.stop_reason ?? 'stop',
    };
  }

  async healthCheck(): Promise<ProviderHealth> {
    const startedAt = Date.now();
    try {
      const response = await fetch(`${this.baseUrl}/models`, {
        headers: { 'x-api-key': this.apiKey, 'anthropic-version': this.version },
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

const geminiSchema = z.object({
  candidates: z
    .array(
      z.object({
        content: z.object({ parts: z.array(z.object({ text: z.string().optional() })) }).optional(),
        finishReason: z.string().nullish(),
      }),
    )
    .optional(),
  usageMetadata: z
    .object({
      promptTokenCount: z.number().int().nonnegative().optional(),
      candidatesTokenCount: z.number().int().nonnegative().optional(),
    })
    .optional(),
});

/// Gemini differs most: the key goes in the URL, roles are `user`/`model`, and the system prompt is
/// `systemInstruction`. Mapping it here keeps that strangeness out of the gateway.
export class GeminiProvider extends HttpModelProvider {
  readonly name: ProviderName = 'gemini';

  constructor(apiKey: string, baseUrl = 'https://generativelanguage.googleapis.com/v1beta') {
    super(apiKey, baseUrl);
  }

  private static roleOf(message: ChatMessage): 'user' | 'model' {
    return message.role === 'assistant' ? 'model' : 'user';
  }

  async generate(request: GenerationRequest): Promise<Generation> {
    const system = request.messages
      .filter((message) => message.role === 'system')
      .map((message) => message.content)
      .join('\n\n');
    const conversation = request.messages.filter((message) => message.role !== 'system');

    const result = (await this.post(
      `/models/${request.model}:generateContent?key=${encodeURIComponent(this.apiKey)}`,
      {
        ...(system.length > 0 ? { systemInstruction: { parts: [{ text: system }] } } : {}),
        contents: conversation.map((message) => ({
          role: GeminiProvider.roleOf(message),
          parts: [{ text: message.content }],
        })),
        generationConfig: {
          maxOutputTokens: request.maxOutputTokens,
          temperature: request.temperature,
        },
      },
      {},
    )) as { payload: unknown; latencyMs: number };

    const parsed = geminiSchema.safeParse(result.payload);
    if (!parsed.success) {
      throw new ProviderFailure(this.name, 502, 'Gemini returned an unreadable response.', true);
    }

    const candidate = parsed.data.candidates?.[0];
    const text = (candidate?.content?.parts ?? []).map((part) => part.text ?? '').join('');

    return {
      text,
      model: request.model,
      provider: this.name,
      usage: {
        inputTokens: parsed.data.usageMetadata?.promptTokenCount ?? this.countTokens(request.messages),
        outputTokens: parsed.data.usageMetadata?.candidatesTokenCount ?? Math.ceil(text.length / 4),
      },
      latencyMs: result.latencyMs,
      finishReason: candidate?.finishReason ?? 'stop',
    };
  }

  async healthCheck(): Promise<ProviderHealth> {
    const startedAt = Date.now();
    try {
      const response = await fetch(
        `${this.baseUrl}/models?key=${encodeURIComponent(this.apiKey)}`,
      );
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
