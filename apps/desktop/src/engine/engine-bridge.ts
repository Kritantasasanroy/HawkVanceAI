import { invoke } from '@tauri-apps/api/core';

/// The local engine, reached through Rust rather than spoken to directly.
///
/// Everything here runs on this computer. Nothing in this file makes a network request, and that
/// is the point: reading a document, finding what is sensitive in it and putting real values back
/// into an answer all happen before or after anything leaves the machine, never as part of it.

export type Redaction = {
  readonly start: number;
  readonly end: number;
  readonly category: string;
  readonly placeholder: string;
  readonly confidence: number;
  readonly detector: string;
  readonly disposition: 'autoRedact' | 'needsReview' | 'keepInClear';
};

export type ScanResult = {
  readonly scanId: string;
  readonly sanitisedText: string;
  readonly redactions: ReadonlyArray<Redaction>;
  readonly needsReview: ReadonlyArray<Redaction>;
  readonly countsByCategory: Record<string, number>;
  readonly routing: { readonly mode: string; readonly detectorsUsed: ReadonlyArray<string> };
  readonly degraded: ReadonlyArray<string>;
};

export type ExtractedDocument = {
  readonly filename: string;
  readonly format: string;
  readonly sha256: string;
  readonly sizeBytes: number;
  readonly characterCount: number;
  readonly usedOcr: boolean;
  readonly pageCount: number | null;
  readonly degraded: ReadonlyArray<string>;
};

export type ProcessedDocument = {
  readonly document: ExtractedDocument;
  readonly scan: ScanResult;
};

export type ContextPack = {
  readonly rendered: string;
  readonly tokenEstimate?: number;
};

export type VerificationVerdict = {
  readonly outcome: 'allowed' | 'needsReview' | 'blocked';
  readonly mayTransmit: boolean;
  readonly message: string;
};

export type BuiltContext = {
  readonly pack: ContextPack;
  readonly verification: VerificationVerdict;
};

export type Memory = {
  readonly id: string;
  readonly content: string;
  readonly workspaceId: string | null;
  readonly pinned: boolean;
  readonly observationCount: number;
  readonly source: string;
};

export type Hardware = {
  readonly systemClass: string;
  readonly recommendedMode: 'fast' | 'balanced' | 'thorough';
  readonly totalMemoryBytes: number;
  readonly hasGpu: boolean;
};

/// A failure from the engine, in a shape the screens can act on.
export class EngineFailure extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'EngineFailure';
    this.code = code;
  }

  /// True when the engine is simply not installed, which the app presents as a setup step rather
  /// than as an error the person caused.
  get isNotInstalled(): boolean {
    return this.code === 'engine_not_installed';
  }

  static from(cause: unknown): EngineFailure {
    if (typeof cause === 'object' && cause !== null && 'code' in cause && 'message' in cause) {
      return new EngineFailure(String(cause.code), String(cause.message));
    }
    return new EngineFailure(
      'engine_unavailable',
      'The local processing engine did not respond. Restart HawkVance and try again.',
    );
  }
}

export class LocalEngine {
  private static async call<TResult>(method: string, params: unknown = {}): Promise<TResult> {
    try {
      return await invoke<TResult>('engine_request', { method, params });
    } catch (cause) {
      throw EngineFailure.from(cause);
    }
  }

  static async ping(): Promise<boolean> {
    const result = await this.call<{ pong: boolean }>('ping');
    return result.pong;
  }

  static async hardware(): Promise<Hardware> {
    return this.call<Hardware>('hardware.detect');
  }

  /// Looks over a piece of text for anything sensitive.
  ///
  /// `protectedTerms` are the words the person marked themselves. They are always applied; the
  /// mode only governs how hard the detectors look for everything else.
  static async scanText(
    text: string,
    mode?: 'fast' | 'balanced' | 'thorough',
    style?: string,
    protectedTerms?: ReadonlyArray<string>,
  ): Promise<ScanResult> {
    return this.call<ScanResult>('privacy.scanText', {
      text,
      ...(mode === undefined ? {} : { mode }),
      ...(style === undefined ? {} : { style }),
      ...(protectedTerms === undefined || protectedTerms.length === 0
        ? {}
        : { protectedTerms: [...protectedTerms] }),
    });
  }

  static async keepInClear(scanId: string, placeholders: ReadonlyArray<string>): Promise<void> {
    await this.call('privacy.keepInClear', { scanId, placeholders: [...placeholders] });
  }

  static async verifyOutbound(text: string): Promise<VerificationVerdict> {
    return this.call<VerificationVerdict>('privacy.verifyOutbound', { text });
  }

  static async closeScan(scanId: string): Promise<void> {
    await this.call('privacy.closeScan', { scanId }).catch(() => undefined);
  }

  static async processDocument(
    path: string,
    mode?: 'fast' | 'balanced' | 'thorough',
    allowOcr = true,
    protectedTerms?: ReadonlyArray<string>,
  ): Promise<ProcessedDocument> {
    return this.call<ProcessedDocument>('document.process', {
      path,
      ...(mode === undefined ? {} : { mode }),
      allowOcr,
      ...(protectedTerms === undefined || protectedTerms.length === 0
        ? {}
        : { protectedTerms: [...protectedTerms] }),
    });
  }

  static async buildContext(request: {
    readonly query: string;
    readonly workspaceId: string | null;
    readonly documentContext?: ReadonlyArray<string>;
  }): Promise<BuiltContext> {
    return this.call<BuiltContext>('context.build', {
      query: request.query,
      workspaceId: request.workspaceId,
      ...(request.documentContext === undefined
        ? {}
        : { documentContext: [...request.documentContext] }),
    });
  }

  // ---------- memory ----------------------------------------------------------------------

  static async remember(
    content: string,
    workspaceId: string | null,
    source: string,
  ): Promise<void> {
    await this.call('memory.remember', { content, workspaceId, source });
  }

  static async searchMemories(text = '', limit = 50): Promise<ReadonlyArray<Memory>> {
    const result = await this.call<{ memories: ReadonlyArray<Memory> }>('memory.search', {
      text,
      limit,
    });
    return result.memories ?? [];
  }

  static async pinMemory(memoryId: string, pinned: boolean): Promise<void> {
    await this.call('memory.pin', { memoryId, pinned });
  }

  static async editMemory(memoryId: string, content: string): Promise<void> {
    await this.call('memory.edit', { memoryId, content });
  }

  static async forget(memoryId: string): Promise<void> {
    await this.call('memory.forget', { memoryId });
  }

  static async forgetWorkspace(workspaceId: string): Promise<void> {
    await this.call('memory.forgetWorkspace', { workspaceId });
  }

  /// Condenses recent conversation into memory using the local model, at no cost and without a
  /// network call.
  static async summarise(text: string, sentences = 3): Promise<string> {
    const result = await this.call<{ summary: string }>('summary.text', { text, sentences });
    return result.summary ?? '';
  }
}
