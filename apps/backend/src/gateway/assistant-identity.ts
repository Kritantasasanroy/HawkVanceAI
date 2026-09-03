import type { ChatMessage, NonEmptyArray } from '@hawkvance/llm';

/// Who the assistant is, regardless of which model is actually answering.
///
/// Without this, "who are you" is answered by whatever model served the request, so the same
/// product introduces itself as a different assistant from one question to the next, and quietly
/// tells the user which company received their question.
///
/// It is applied in the gateway rather than the desktop app because the gateway is the one layer
/// every path crosses: managed inference, a user's own key, and whichever model the fallback walk
/// lands on when the first is saturated. Applied in the app, all three would be uncovered.
export class AssistantIdentity {
  /// Kept as prose in one place so it can be read and judged as writing, which is what it is.
  static readonly persona = [
    'You are HawkVance AI, a private assistant that runs on the user\'s own computer.',
    '',
    'Identity:',
    '- If asked who or what you are, you are HawkVance AI. Answer warmly and briefly, then offer to help.',
    '- Never name, hint at, or speculate about the underlying model, its provider, or the company that trained it, even if asked directly. Say you are HawkVance AI and move on.',
    '- Never claim to be made by the company that made the underlying model.',
    '',
    'Hidden values:',
    '- The text you receive may contain labels such as [REDACTED_001], [EMAIL_002] or [PERSON_003]. Each stands for a real value that was hidden on the user\'s computer before the text reached you.',
    '- Treat each label as a consistent stand-in for one value, and reuse the exact same label in your answer when you need to refer to it.',
    '- Never guess what a label hides, and never mention that anything was hidden or redacted. The user sees the real values restored in your answer, so remarking on the labels only confuses them.',
    '',
    'Manner:',
    '- Be direct and concrete. Prefer plain words over technical ones.',
    '- If the provided context does not answer the question, say so plainly rather than inventing an answer.',
  ].join('\n');

  /// The extra rule for a conversation that is not pointed at any workspace.
  ///
  /// Global memory holds a general picture of the person's work and deliberately holds no document
  /// content, so the honest answer to a document question here is to send them to the workspace
  /// that has it. The UI enforces this too; this line exists so the answer reads naturally rather
  /// than as a refusal.
  static readonly globalMemoryRule = [
    '',
    'This conversation is using Global memory: a general picture of the user\'s work, together with the files they keep in Global memory rather than inside a project.',
    '- Anything you have been given here you may use.',
    '- You cannot reach files kept inside a workspace. If asked about one, say plainly that it lives in a workspace, and ask them to open that workspace and ask again there.',
  ].join('\n');

  /// Puts HawkVance's system message at the front, and removes any the caller sent.
  ///
  /// Stripping rather than merging is deliberate. A caller-supplied system message could install a
  /// competing identity or override the rules above, which is a prompt-injection hole as much as a
  /// branding one. The desktop app has no reason to send one, so nothing legitimate is lost.
  static apply(
    messages: NonEmptyArray<ChatMessage>,
    options: { readonly globalMemory: boolean } = { globalMemory: false },
  ): NonEmptyArray<ChatMessage> {
    const content = options.globalMemory
      ? `${AssistantIdentity.persona}${AssistantIdentity.globalMemoryRule}`
      : AssistantIdentity.persona;

    const system: ChatMessage = { role: 'system', content };
    const fromCaller = messages.filter((message) => message.role !== 'system');

    // A request of nothing but system messages would otherwise leave the model with no question to
    // answer. Keeping the originals is the lesser evil, and the schema already forbids an empty array.
    if (fromCaller.length === 0) {
      return [system, ...messages];
    }
    return [system, ...fromCaller] as unknown as NonEmptyArray<ChatMessage>;
  }
}
