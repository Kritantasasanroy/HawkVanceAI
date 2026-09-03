import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { LocalEngine } from '../engine/engine-bridge.js';
import type { ConversationRecord, ConversationTurnRecord } from './vault-store.js';
import { VaultStore } from './vault-store.js';

export type Turn = {
  readonly id: string;
  readonly role: 'user' | 'assistant';
  readonly content: string;
  readonly model: string | null;
  readonly occurredAt: string;
};

export type Conversation = {
  readonly id: string;
  readonly workspaceId: string | null;
  readonly title: string;
  readonly startedAt: string;
};

/// How many replies pass before the conversation is condensed into memory.
///
/// Five is a compromise. Summarising every turn spends local model time on exchanges that are
/// still in the visible history anyway; waiting much longer risks losing the thread of a long
/// conversation when older turns drop out of the context window.
const summariseEvery = 5;

type ChatContextValue = {
  readonly conversations: ReadonlyArray<Conversation>;
  readonly activeId: string | null;
  readonly turns: ReadonlyArray<Turn>;
  readonly loading: boolean;
  readonly select: (id: string | null) => void;
  readonly startNew: (workspaceId: string | null) => Promise<string>;
  readonly remove: (id: string) => Promise<void>;
  readonly rename: (id: string, title: string) => Promise<void>;
  readonly append: (conversationId: string, turn: Omit<Turn, 'id' | 'occurredAt'>) => Promise<void>;
};

const ChatContext = createContext<ChatContextValue | null>(null);

function toConversation(record: ConversationRecord): Conversation {
  return {
    id: record.id,
    workspaceId: record.workspaceId,
    title: record.title,
    startedAt: record.startedAt,
  };
}

function toRecord(conversation: Conversation): ConversationRecord {
  return {
    id: conversation.id,
    workspaceId: conversation.workspaceId,
    title: conversation.title,
    startedAt: conversation.startedAt,
  };
}

function toTurn(record: ConversationTurnRecord): Turn {
  return {
    id: record.id,
    role: record.role,
    content: record.content,
    model: record.model,
    occurredAt: record.occurredAt,
  };
}

/// Holds every conversation for the life of the app, not the life of the Chat screen.
///
/// This lived inside the Chat component once, which meant navigating to Documents and back threw
/// the conversation away. State somebody expects to outlive a click cannot be owned by the thing
/// they clicked away from.
export function ChatProvider({ children }: { children: ReactNode }): JSX.Element {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);
  const [sinceSummary, setSinceSummary] = useState<Record<string, number>>({});

  /// Mirrors of the two pieces of state that callbacks read after an await. React state is a
  /// snapshot per render, and a conversation created moments ago is not in it yet.
  const activeIdRef = useRef<string | null>(null);
  const turnsRef = useRef<Turn[]>([]);

  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  useEffect(() => {
    let cancelled = false;
    void VaultStore.conversations()
      .then((found) => {
        if (!cancelled) {
          setConversations(found.map(toConversation));
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Messages are loaded per thread rather than all at once. A year of chat history is a lot to
  // hold in memory in order to show one conversation.
  useEffect(() => {
    if (activeId === null) {
      setTurns([]);
      return;
    }
    let cancelled = false;
    void VaultStore.turns(activeId)
      .then((found) => {
        if (!cancelled) {
          setTurns(found.map(toTurn));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTurns([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const select = useCallback((id: string | null): void => {
    activeIdRef.current = id;
    setActiveId(id);
  }, []);

  const startNew = useCallback(async (workspaceId: string | null): Promise<string> => {
    const conversation: Conversation = {
      id: crypto.randomUUID(),
      workspaceId,
      title: '',
      startedAt: new Date().toISOString(),
    };
    await VaultStore.saveConversation(toRecord(conversation)).catch(() => undefined);
    // The refs are set before the state, so a message sent in this same tick finds the thread.
    activeIdRef.current = conversation.id;
    turnsRef.current = [];
    setConversations((current) => [conversation, ...current]);
    setActiveId(conversation.id);
    setTurns([]);
    return conversation.id;
  }, []);

  const remove = useCallback(
    async (id: string): Promise<void> => {
      await VaultStore.deleteConversation(id).catch(() => undefined);
      setConversations((current) => current.filter((item) => item.id !== id));
      if (activeIdRef.current === id) {
        activeIdRef.current = null;
        setActiveId(null);
        setTurns([]);
      }
    },
    [],
  );

  const rename = useCallback(async (id: string, title: string): Promise<void> => {
    setConversations((current) => {
      const next = current.map((item) => (item.id === id ? { ...item, title } : item));
      const renamed = next.find((item) => item.id === id);
      if (renamed !== undefined) {
        void VaultStore.saveConversation(toRecord(renamed)).catch(() => undefined);
      }
      return next;
    });
  }, []);

  /// Folds the recent exchange into memory, on the local model, at no cost.
  const condense = useCallback(
    async (recent: ReadonlyArray<Turn>, workspaceId: string | null): Promise<void> => {
      const transcript = recent
        .map((turn) => `${turn.role === 'user' ? 'Asked' : 'Answered'}: ${turn.content}`)
        .join('\n');
      const summary = await LocalEngine.summarise(transcript, 3);
      if (summary.trim().length > 0) {
        await LocalEngine.remember(summary, workspaceId, 'chat');
      }
    },
    [],
  );

  /// Adds a message to a named thread, and every so often folds the exchange into memory.
  ///
  /// The thread is a parameter rather than whatever is currently selected, because the first
  /// message of a conversation is sent in the same tick that creates it, when React state still
  /// says there is no thread. Reading it from state there silently dropped the message, after the
  /// answer had already been fetched and charged for.
  ///
  /// The summary costs nothing and runs locally, but it must never delay or break the reply
  /// somebody is waiting on, so a failure there is swallowed rather than surfaced.
  const append = useCallback(
    async (id: string, turn: Omit<Turn, 'id' | 'occurredAt'>): Promise<void> => {
      const complete: Turn = {
        ...turn,
        id: crypto.randomUUID(),
        occurredAt: new Date().toISOString(),
      };

      // The visible transcript only changes when the message belongs to the thread on screen.
      setTurns((current) => (id === activeIdRef.current ? [...current, complete] : current));
      await VaultStore.appendTurn({ ...complete, conversationId: id }).catch(() => undefined);

      const conversation = conversations.find((item) => item.id === id);
      if (conversation !== undefined && conversation.title.trim() === '' && turn.role === 'user') {
        // The first thing asked becomes the thread's name, so the list is readable without
        // anybody having to name anything.
        const title = turn.content.trim().slice(0, 60);
        void rename(id, title);
      }

      if (turn.role !== 'assistant') {
        return;
      }

      const count = (sinceSummary[id] ?? 0) + 1;
      setSinceSummary((current) => ({ ...current, [id]: count % summariseEvery }));
      if (count % summariseEvery !== 0) {
        return;
      }

      const recent = [...turnsRef.current, complete].slice(-(summariseEvery * 2));
      void condense(recent, conversation?.workspaceId ?? null).catch(() => undefined);
    },
    [condense, conversations, rename, sinceSummary],
  );

  const value = useMemo(
    () => ({ conversations, activeId, turns, loading, select, startNew, remove, rename, append }),
    [conversations, activeId, turns, loading, select, startNew, remove, rename, append],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatContextValue {
  const context = useContext(ChatContext);
  if (context === null) {
    throw new Error('useChat was called outside the chat provider');
  }
  return context;
}
