import { invoke } from '@tauri-apps/api/core';

/// The encrypted store on this computer, reached through Rust.
///
/// Note what is absent: there is no method that returns a redaction mapping. `rememberRedactions`
/// hands Rust a scan id and gets back a count, and `restoreAnswer` hands it text and gets back
/// text. The originals behind placeholders have no route into this process at all, which is a
/// property of the command surface rather than a rule this file is trusted to follow.

export type WorkspaceRecord = {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly createdAt: string;
  readonly updatedAt: string;
};

export type DocumentRecord = {
  readonly id: string;
  /// Null means Global memory: a file not tied to any one project.
  readonly workspaceId: string | null;
  readonly filename: string;
  readonly sha256: string;
  readonly sizeBytes: number;
  readonly characterCount: number;
  readonly usedOcr: boolean;
  readonly sanitisedText: string;
  readonly createdAt: string;
};

export type ConversationRecord = {
  readonly id: string;
  readonly workspaceId: string | null;
  readonly title: string;
  readonly startedAt: string;
};

export type ConversationTurnRecord = {
  readonly id: string;
  readonly conversationId: string;
  readonly role: 'user' | 'assistant';
  readonly content: string;
  readonly model: string | null;
  readonly occurredAt: string;
};

export class VaultStore {
  // ---------- workspaces ------------------------------------------------------------------

  static async workspaces(): Promise<ReadonlyArray<WorkspaceRecord>> {
    return invoke<WorkspaceRecord[]>('workspace_list');
  }

  static async saveWorkspace(record: WorkspaceRecord): Promise<void> {
    await invoke('workspace_save', { record });
  }

  static async deleteWorkspace(id: string): Promise<void> {
    await invoke('workspace_delete', { id });
  }

  // ---------- documents -------------------------------------------------------------------

  /// The files in one workspace, or the ones in Global memory when given null.
  static async documents(workspaceId: string | null): Promise<ReadonlyArray<DocumentRecord>> {
    return invoke<DocumentRecord[]>('document_list', { workspaceId });
  }

  static async saveDocument(record: DocumentRecord): Promise<void> {
    await invoke('document_save', { record });
  }

  static async deleteDocument(id: string): Promise<void> {
    await invoke('document_delete', { id });
  }

  /// Files what a scan found against a document, so answers can be restored later.
  ///
  /// Only a count comes back. The mapping itself goes from the engine into the vault without ever
  /// passing through this process.
  static async rememberRedactions(request: {
    readonly documentId: string;
    readonly workspaceId: string | null;
    readonly scanId: string;
  }): Promise<number> {
    const result = await invoke<{ stored: number }>('document_remember_redactions', request);
    return result.stored;
  }

  /// Puts the real values back into an answer, on this computer.
  static async restoreAnswer(request: {
    readonly scanId: string | null;
    readonly workspaceId: string | null;
    readonly text: string;
  }): Promise<string> {
    const result = await invoke<{ text: string }>('chat_restore', { request });
    return result.text;
  }

  // ---------- conversations ---------------------------------------------------------------

  static async conversations(): Promise<ReadonlyArray<ConversationRecord>> {
    return invoke<ConversationRecord[]>('conversation_list');
  }

  static async saveConversation(record: ConversationRecord): Promise<void> {
    await invoke('conversation_save', { record });
  }

  static async deleteConversation(id: string): Promise<void> {
    await invoke('conversation_delete', { id });
  }

  static async appendTurn(record: ConversationTurnRecord): Promise<void> {
    await invoke('conversation_append_turn', { record });
  }

  static async turns(conversationId: string): Promise<ReadonlyArray<ConversationTurnRecord>> {
    return invoke<ConversationTurnRecord[]>('conversation_turns', { conversationId });
  }

  // ---------- hidden words and settings ---------------------------------------------------

  static async saveProtectedTerms(scope: string, terms: ReadonlyArray<string>): Promise<void> {
    await invoke('protected_terms_save', { scope, terms: [...terms] });
  }

  static async protectedTerms(scope: string): Promise<ReadonlyArray<string>> {
    return invoke<string[]>('protected_terms_load', { scope });
  }

  /// The union of the words chosen here and the ones chosen to apply everywhere.
  static async termsInEffect(workspaceId: string | null): Promise<string[]> {
    return invoke<string[]>('protected_terms_in_effect', { workspaceId });
  }

  static async writeSetting(key: string, value: string): Promise<void> {
    await invoke('setting_write', { key, value });
  }

  static async readSetting(key: string): Promise<string | null> {
    return invoke<string | null>('setting_read', { key });
  }
}
