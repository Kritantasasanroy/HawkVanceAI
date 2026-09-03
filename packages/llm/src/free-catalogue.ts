import type { ModelEntry } from './model-router.js';

/// Every zero-cost chat model OpenRouter exposed when this catalogue was captured.
///
/// Verified live against a real key: 13 of these answered immediately, the rest returned HTTP 429
/// from OpenRouter's shared free pool or 403 for gated access. That is the normal state of the free
/// tier, not a fault, and it is why the router is built to walk this list rather than trust any one
/// entry. Breadth here is the availability strategy.
///
/// Prices are all zero, so `CostEstimate` yields zero and the quota ledger records real token counts
/// against a zero spend. That is deliberate: usage still needs accounting even when it is free.
export const freeCatalogue: ReadonlyArray<ModelEntry> = [
  // --- economy: small, fast, cheap to retry -----------------------------------------------
  {
    id: 'liquid/lfm-2.5-2.6b:free',
    provider: 'openrouter',
    tier: 'economy',
    contextWindow: 65_536,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Liquid LFM 2.5 2.6B (free)',
  },
  {
    id: 'nvidia/nemotron-3.5-lightning:free',
    provider: 'openrouter',
    tier: 'economy',
    contextWindow: 1_000_000,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Nemotron 3.5 Lightning (free)',
  },
  {
    id: 'cohere/north-mini-code:free',
    provider: 'openrouter',
    tier: 'economy',
    contextWindow: 256_000,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Cohere North Mini Code (free)',
  },
  {
    id: 'poolside/laguna-xs-2.1:free',
    provider: 'openrouter',
    tier: 'economy',
    contextWindow: 262_144,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Poolside Laguna XS 2.1 (free)',
  },
  {
    id: 'openrouter/free',
    provider: 'openrouter',
    tier: 'economy',
    contextWindow: 200_000,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'OpenRouter Free (auto)',
  },

  // --- standard: general work -------------------------------------------------------------
  {
    id: 'z-ai/glm-5.2:free',
    provider: 'openrouter',
    tier: 'standard',
    contextWindow: 256_000,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'GLM 5.2 (free)',
  },
  {
    id: 'google/gemma-4-26b-a4b-it:free',
    provider: 'openrouter',
    tier: 'standard',
    contextWindow: 262_144,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Gemma 4 26B (free)',
  },
  {
    id: 'minimax/minimax-m2.7:free',
    provider: 'openrouter',
    tier: 'standard',
    contextWindow: 196_608,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'MiniMax M2.7 (free)',
  },
  {
    id: 'inclusionai/ling-3.0-flash-fin:free',
    provider: 'openrouter',
    tier: 'standard',
    contextWindow: 262_144,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Ling 3.0 Flash (free)',
  },
  {
    id: 'poolside/laguna-s-2.1:free',
    provider: 'openrouter',
    tier: 'standard',
    contextWindow: 262_144,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Poolside Laguna S 2.1 (free)',
  },
  {
    id: 'dots-studio/dots-3-note-preview:free',
    provider: 'openrouter',
    tier: 'standard',
    contextWindow: 512_000,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Dots 3 Note (free)',
  },
  {
    id: 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free',
    provider: 'openrouter',
    tier: 'standard',
    contextWindow: 256_000,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Nemotron 3 Nano Omni 30B (free)',
  },

  // --- premium: large models, still free ---------------------------------------------------
  {
    id: 'nvidia/nemotron-3-super-120b-a12b:free',
    provider: 'openrouter',
    tier: 'premium',
    contextWindow: 262_144,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Nemotron 3 Super 120B (free)',
  },
  {
    id: 'nvidia/nemotron-3-ultra-550b-a55b:free',
    provider: 'openrouter',
    tier: 'premium',
    contextWindow: 1_000_000,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Nemotron 3 Ultra 550B (free)',
  },
  {
    id: 'minimax/minimax-m3:free',
    provider: 'openrouter',
    tier: 'premium',
    contextWindow: 1_048_576,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'MiniMax M3 (free)',
  },
  {
    id: 'google/gemma-4-31b-it:free',
    provider: 'openrouter',
    tier: 'premium',
    contextWindow: 262_144,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Gemma 4 31B (free)',
  },
  {
    id: 'thinkingmachines/inkling:free',
    provider: 'openrouter',
    tier: 'premium',
    contextWindow: 1_048_576,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Inkling (free, gated)',
  },
  {
    id: 'thinkingmachines/inkling-small:free',
    provider: 'openrouter',
    tier: 'premium',
    contextWindow: 1_048_576,
    inputMicrosPerMillion: 0,
    outputMicrosPerMillion: 0,
    enabled: true,
    label: 'Inkling Small (free, gated)',
  },
];

/// Refreshes the free catalogue from OpenRouter at runtime.
///
/// The static list above is a working default that needs no network. This exists because the free
/// tier changes weekly: models appear, disappear, and change context windows, and a hard-coded list
/// silently rots. An administrator can refresh; a failure falls back to the static list rather than
/// leaving the product with no models at all.
export class FreeCatalogueRefresh {
  private static readonly endpoint = 'https://openrouter.ai/api/v1/models';

  static tierFor(contextWindow: number, id: string): ModelEntry['tier'] {
    if (/(?:ultra|550b|120b|m3:|31b|inkling)/i.test(id)) {
      return 'premium';
    }
    if (contextWindow <= 70_000 || /(?:lightning|mini|xs|2\.6b)/i.test(id)) {
      return 'economy';
    }
    return 'standard';
  }

  static async fetch(): Promise<ReadonlyArray<ModelEntry>> {
    const response = await fetch(FreeCatalogueRefresh.endpoint);
    if (!response.ok) {
      return freeCatalogue;
    }

    const payload = (await response.json()) as {
      data?: Array<{
        id: string;
        name?: string;
        context_length?: number;
        pricing?: { prompt?: string; completion?: string };
        architecture?: { output_modalities?: string[] };
      }>;
    };

    const zero = (value: string | undefined): boolean => Number(value ?? '0') === 0;

    const discovered = (payload.data ?? [])
      .filter(
        (model) =>
          zero(model.pricing?.prompt) &&
          zero(model.pricing?.completion) &&
          // A model that only emits audio cannot answer a question about a contract.
          (model.architecture?.output_modalities ?? ['text']).includes('text') &&
          !(model.architecture?.output_modalities ?? []).includes('audio'),
      )
      .map<ModelEntry>((model) => ({
        id: model.id,
        provider: 'openrouter',
        tier: FreeCatalogueRefresh.tierFor(model.context_length ?? 0, model.id),
        contextWindow: model.context_length ?? 8_192,
        inputMicrosPerMillion: 0,
        outputMicrosPerMillion: 0,
        enabled: true,
        label: `${model.name ?? model.id} (free)`,
      }));

    return discovered.length > 0 ? discovered : freeCatalogue;
  }
}
