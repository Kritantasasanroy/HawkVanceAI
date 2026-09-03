import { AnthropicProvider, GeminiProvider } from './providers/anthropic-and-gemini.js';
import { OpenAiProvider, OpenRouterProvider } from './providers/openai-compatible.js';
import type { ModelProvider, ProviderName } from './provider.js';

export class UnknownProvider extends Error {
  constructor(name: string) {
    super(`HawkVance does not support the ${name} provider.`);
    this.name = 'UnknownProvider';
  }
}

/// The single place a provider name becomes a client.
///
/// Both sides use it: the backend builds one from the server-side credential for HawkVance-managed
/// inference, and the desktop builds one from the key in Windows Credential Manager for BYOK. That
/// symmetry is what lets a user's own key never reach a HawkVance server.
export class ProviderFactory {
  static create(name: ProviderName, apiKey: string): ModelProvider {
    switch (name) {
      case 'openrouter':
        return new OpenRouterProvider(apiKey);
      case 'openai':
        return new OpenAiProvider(apiKey);
      case 'anthropic':
        return new AnthropicProvider(apiKey);
      case 'gemini':
        return new GeminiProvider(apiKey);
    }
  }

  static supported(): ReadonlyArray<ProviderName> {
    return ['openrouter', 'openai', 'anthropic', 'gemini'];
  }
}
