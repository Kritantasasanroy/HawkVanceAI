import { z } from 'zod';
import type { ChatMessage, ModelTier, TaskComplexity } from './provider.js';

/// One model HawkVance is willing to route to. Prices are micros per million tokens, held as
/// integers because money in a float is a rounding complaint waiting to happen.
export const modelEntrySchema = z.object({
  id: z.string().min(1),
  provider: z.enum(['openrouter', 'openai', 'anthropic', 'gemini']),
  tier: z.enum(['economy', 'standard', 'premium']),
  contextWindow: z.number().int().positive(),
  inputMicrosPerMillion: z.number().int().nonnegative(),
  outputMicrosPerMillion: z.number().int().nonnegative(),
  enabled: z.boolean().default(true),
  label: z.string().min(1),
});
export type ModelEntry = z.infer<typeof modelEntrySchema>;

/// The default catalogue. Admin-configurable at runtime, per spec section 45, so this is a seed
/// rather than a hard-coded routing table.
export const defaultCatalogue: ReadonlyArray<ModelEntry> = [
  {
    id: 'z-ai/glm-4-32b',
    provider: 'openrouter',
    tier: 'economy',
    contextWindow: 128_000,
    inputMicrosPerMillion: 100_000,
    outputMicrosPerMillion: 100_000,
    enabled: true,
    label: 'GLM 4 32B',
  },
  {
    id: 'deepseek/deepseek-chat',
    provider: 'openrouter',
    tier: 'standard',
    contextWindow: 128_000,
    inputMicrosPerMillion: 270_000,
    outputMicrosPerMillion: 1_100_000,
    enabled: true,
    label: 'DeepSeek Chat',
  },
  {
    id: 'anthropic/claude-sonnet-4.5',
    provider: 'openrouter',
    tier: 'premium',
    contextWindow: 200_000,
    inputMicrosPerMillion: 3_000_000,
    outputMicrosPerMillion: 15_000_000,
    enabled: true,
    label: 'Claude Sonnet 4.5',
  },
];

export class TaskClassifier {
  /// Spec section 23. Cheap heuristics on purpose: paying a model to decide which model to pay is
  /// the kind of cost spiral this router exists to prevent.
  private static readonly SIMPLE = /\b(rewrite|rephrase|shorten|translate|tidy|fix typo|summar(?:ise|ize) briefly)\b/i;
  private static readonly COMPLEX = /\b(compare|across|reconcile|debug|trace|derive|prove|audit|contradict|implications?)\b/i;

  static classify(messages: ReadonlyArray<ChatMessage>, contextTokens: number): TaskComplexity {
    const prompt = messages
      .filter((message) => message.role === 'user')
      .map((message) => message.content)
      .join('\n');

    // A large context is complex regardless of wording: multi-document reasoning is the expensive
    // case whether or not the user phrased it as a question about several things.
    if (contextTokens > 12_000 || TaskClassifier.COMPLEX.test(prompt)) {
      return 'complex';
    }
    if (prompt.length < 240 && TaskClassifier.SIMPLE.test(prompt)) {
      return 'simple';
    }
    return 'moderate';
  }

  static tierFor(complexity: TaskComplexity): ModelTier {
    return { simple: 'economy', moderate: 'standard', complex: 'premium' }[complexity] as ModelTier;
  }
}

export class NoModelAvailable extends Error {
  constructor(tier: ModelTier, reason: string) {
    super(`No ${tier} model is available right now. ${reason}`);
    this.name = 'NoModelAvailable';
  }
}

export type RoutingChoice = {
  readonly model: ModelEntry;
  readonly complexity: TaskComplexity;
  readonly requestedTier: ModelTier;
  readonly downgraded: boolean;
  readonly reason: string;
};

export class ModelRouter {
  private readonly catalogue: ReadonlyArray<ModelEntry>;

  constructor(catalogue: ReadonlyArray<ModelEntry> = defaultCatalogue) {
    this.catalogue = catalogue;
  }

  /// Picks the cheapest model that satisfies the task, the plan and the context size.
  ///
  /// A plan that does not allow premium is not an error: the request is served by the best tier the
  /// plan does allow, and the caller is told it was downgraded rather than silently getting a worse
  /// answer with no explanation.
  route(request: {
    messages: ReadonlyArray<ChatMessage>;
    contextTokens: number;
    allowedTiers: ReadonlyArray<ModelTier>;
    preferredModelId?: string;
  }): RoutingChoice {
    const complexity = TaskClassifier.classify(request.messages, request.contextTokens);
    const requestedTier = TaskClassifier.tierFor(complexity);

    if (request.preferredModelId !== undefined) {
      const preferred = this.catalogue.find(
        (entry) => entry.id === request.preferredModelId && entry.enabled,
      );
      if (preferred !== undefined && request.allowedTiers.includes(preferred.tier)) {
        return {
          model: preferred,
          complexity,
          requestedTier,
          downgraded: false,
          reason: 'the model you selected',
        };
      }
    }

    const ordered: ReadonlyArray<ModelTier> = ['economy', 'standard', 'premium'];
    const ceiling = ordered.indexOf(requestedTier);

    for (let index = ceiling; index >= 0; index -= 1) {
      const tier = ordered[index];
      if (tier === undefined || !request.allowedTiers.includes(tier)) {
        continue;
      }
      const candidates = this.catalogue
        .filter(
          (entry) =>
            entry.enabled && entry.tier === tier && entry.contextWindow >= request.contextTokens,
        )
        .sort((left, right) => left.outputMicrosPerMillion - right.outputMicrosPerMillion);

      const chosen = candidates[0];
      if (chosen !== undefined) {
        return {
          model: chosen,
          complexity,
          requestedTier,
          downgraded: index < ceiling,
          reason:
            index < ceiling
              ? `your plan does not include ${requestedTier} models, so a ${tier} model was used`
              : `a ${tier} model suits a ${complexity} task`,
        };
      }
    }

    throw new NoModelAvailable(
      requestedTier,
      request.allowedTiers.length === 0
        ? 'Your plan has no models enabled.'
        : 'Every model large enough for this context is disabled.',
    );
  }

  /// Ordered alternatives for when the first choice fails, cheapest first.
  fallbacksFor(choice: RoutingChoice, allowedTiers: ReadonlyArray<ModelTier>): ModelEntry[] {
    return this.catalogue
      .filter(
        (entry) =>
          entry.enabled && entry.id !== choice.model.id && allowedTiers.includes(entry.tier),
      )
      .sort((left, right) => left.outputMicrosPerMillion - right.outputMicrosPerMillion);
  }

  find(modelId: string): ModelEntry | null {
    return this.catalogue.find((entry) => entry.id === modelId) ?? null;
  }

  get enabled(): ReadonlyArray<ModelEntry> {
    return this.catalogue.filter((entry) => entry.enabled);
  }
}

export class CostEstimate {
  /// Integer micros throughout. 1_000_000 micros is one unit of currency.
  static micros(model: ModelEntry, inputTokens: number, outputTokens: number): number {
    const input = Math.ceil((inputTokens * model.inputMicrosPerMillion) / 1_000_000);
    const output = Math.ceil((outputTokens * model.outputMicrosPerMillion) / 1_000_000);
    return input + output;
  }

  static format(micros: number): string {
    return `$${(micros / 1_000_000).toFixed(4)}`;
  }
}
