import { useCallback, useEffect, useRef, useState } from 'react';
import type { ContextPack, Redaction, VerificationVerdict } from '../engine/engine-bridge.js';
import { EngineFailure, LocalEngine } from '../engine/engine-bridge.js';
import { useChat } from '../session/chat-store.js';
import type { AvailableModel } from '../session/hawkvance-api.js';
import { useSession } from '../session/session-context.js';
import type { WorkspaceRecord } from '../session/vault-store.js';
import { VaultStore } from '../session/vault-store.js';
import { EngineMissing } from './EngineMissing.js';
import { Icon } from './Icon.js';
import { Markdown } from './Markdown.js';
import { ModelPicker } from './ModelPicker.js';
import { PrivacyGate } from './PrivacyGate.js';

type Pending = {
  readonly question: string;
  readonly scanId: string;
  readonly conversationId: string;
  readonly pack: ContextPack;
  readonly verification: VerificationVerdict;
  readonly automatic: ReadonlyArray<Redaction>;
  readonly needsReview: ReadonlyArray<Redaction>;
};

/// Remembered across visits, because a choice that resets whenever you leave the screen is not one.
const MODEL_SETTING = 'chat.preferred_model';
const RAIL_SETTING = 'ui.threads_open';

export function Chat({
  workspaces,
}: {
  readonly workspaces: ReadonlyArray<WorkspaceRecord>;
}): JSX.Element {
  const { api, withIdentityToken } = useSession();
  const { conversations, activeId, turns, select, startNew, remove, append } = useChat();

  const [question, setQuestion] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [engineMissing, setEngineMissing] = useState(false);

  const [models, setModels] = useState<ReadonlyArray<AvailableModel>>([]);
  const [chosenModel, setChosenModel] = useState('');
  const [terms, setTerms] = useState<string[]>([]);
  /// Off by default. Checking a question you typed yourself is usually wasted effort, so it is
  /// offered rather than imposed. Words the person chose to protect are hidden either way.
  const [checkMyQuestion, setCheckMyQuestion] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const endOfTurns = useRef<HTMLDivElement>(null);

  const active = conversations.find((item) => item.id === activeId) ?? null;
  /// Which context the *next* message uses. A thread keeps the context it was started in, so an
  /// answer can never quietly come from a different workspace than the one above it.
  const [nextWorkspace, setNextWorkspace] = useState<string | null>(null);
  const workspaceId = active?.workspaceId ?? nextWorkspace;
  const placeName =
    workspaceId === null
      ? 'Global memory'
      : workspaces.find((item) => item.id === workspaceId)?.name ?? 'Workspace';

  // `problem` is in here because a failure is shown at the foot of the transcript, and something
  // that only appears below the fold has not been shown at all.
  useEffect(() => {
    endOfTurns.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns.length, busy, pending, problem]);

  useEffect(() => {
    let cancelled = false;
    void VaultStore.termsInEffect(workspaceId)
      .then((found) => !cancelled && setTerms(found))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  useEffect(() => {
    let cancelled = false;
    const load = async (): Promise<void> => {
      const [catalogue, remembered, rail] = await Promise.all([
        withIdentityToken(async (token) => api.models(token)).catch(() => null),
        VaultStore.readSetting(MODEL_SETTING).catch(() => null),
        VaultStore.readSetting(RAIL_SETTING).catch(() => null),
      ]);
      if (cancelled) {
        return;
      }
      setRailOpen(rail !== 'closed');
      if (catalogue === null) {
        return;
      }
      setModels(catalogue.models);
      // A remembered choice only counts if that model is still on offer; a plan change or a
      // withdrawn model would otherwise leave the picker pointing at something that cannot answer.
      const stillOffered = catalogue.models.some((entry) => entry.id === remembered);
      setChosenModel(
        stillOffered && remembered !== null ? remembered : catalogue.models[0]?.id ?? '',
      );
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [api, withIdentityToken]);

  const chooseModel = useCallback((id: string): void => {
    setChosenModel(id);
    void VaultStore.writeSetting(MODEL_SETTING, id).catch(() => undefined);
  }, []);

  const toggleRail = useCallback((): void => {
    setRailOpen((current) => {
      void VaultStore.writeSetting(RAIL_SETTING, current ? 'closed' : 'open').catch(() => undefined);
      return !current;
    });
  }, []);

  /// Everything the answer may draw on, gathered here on this computer.
  const gatherContext = useCallback(
    async (asked: string) => {
      // A workspace conversation reads that workspace's files; a Global one reads the files kept
      // outside any workspace. Neither can reach the other.
      const documents = (await VaultStore.documents(workspaceId).catch(() => []))
        .map((item) => item.sanitisedText)
        .filter((text) => text.length > 0);

      const built = await LocalEngine.buildContext({
        query: asked,
        workspaceId,
        ...(documents.length === 0 ? {} : { documentContext: documents }),
      });

      // The person's own protected words are always applied. The detector sweep over the whole
      // pack is what the checkbox controls.
      const scan = await LocalEngine.scanText(
        built.pack.rendered,
        checkMyQuestion ? undefined : 'fast',
        undefined,
        terms,
      );

      return { outbound: scan.sanitisedText, scan, built };
    },
    [checkMyQuestion, terms, workspaceId],
  );

  /// Sends, restores, and files the reply under a named thread.
  const deliver = useCallback(
    async (
      conversationId: string,
      asked: string,
      outbound: string,
      scanId: string | null,
      alreadyShown: boolean,
    ): Promise<void> => {
      if (!alreadyShown) {
        await append(conversationId, { role: 'user', content: asked, model: null });
      }

      // Through the API client, so an identity token that aged out is renewed and retried rather
      // than surfacing as a failure that looks like being signed out.
      const answer = await withIdentityToken(async (token) =>
        api.complete(token, {
          messages: [{ role: 'user', content: outbound }],
          maxOutputTokens: 1024,
          globalMemory: workspaceId === null,
          ...(workspaceId === null ? {} : { workspaceId }),
          ...(chosenModel === '' ? {} : { preferredModelId: chosenModel }),
        }),
      );

      // Hidden values become real again here, on this machine. Through Rust, because two sources
      // have to be combined: this conversation's scan, and the mappings stored when each document
      // was added.
      const restored = await VaultStore.restoreAnswer({
        scanId,
        workspaceId,
        text: answer.text,
      });

      await append(conversationId, {
        role: 'assistant',
        content: restored,
        model: answer.modelLabel,
      });
    },
    [api, append, chosenModel, withIdentityToken, workspaceId],
  );

  /// Puts a failure on screen in words, in one place.
  ///
  /// Every path that can fail has to end here. A question that comes back with nothing and no
  /// explanation is the worst outcome the chat can produce, because there is no way to tell a busy
  /// model apart from a broken app.
  const report = useCallback((cause: unknown): void => {
    const failure = EngineFailure.from(cause);
    if (failure.isNotInstalled) {
      setEngineMissing(true);
      return;
    }
    setProblem(cause instanceof Error ? cause.message : failure.message);
  }, []);

  const ask = useCallback(async (): Promise<void> => {
    const asked = question.trim();
    if (asked.length === 0) {
      return;
    }
    setBusy(true);
    setProblem(null);

    // The thread is carried explicitly from here on. Reading it back from React state in the same
    // tick it was created is what used to make the first message of a conversation vanish with no
    // error at all, after the answer had already been fetched and charged for.
    const conversationId = activeId ?? (await startNew(nextWorkspace));

    try {
      const prepared = await gatherContext(asked);

      if (checkMyQuestion) {
        // Nothing is shown or sent until the person has approved what leaves.
        setPending({
          question: asked,
          scanId: prepared.scan.scanId,
          conversationId,
          pack: prepared.built.pack,
          verification: prepared.built.verification,
          automatic: prepared.scan.redactions.filter((item) => item.disposition === 'autoRedact'),
          needsReview: prepared.scan.needsReview,
        });
        return;
      }

      // Shown and cleared before the wait, so the question sits in the conversation where the
      // person is looking rather than in the box they thought they had just emptied.
      await append(conversationId, { role: 'user', content: asked, model: null });
      setQuestion('');

      await deliver(conversationId, asked, prepared.outbound, prepared.scan.scanId, true);
    } catch (cause) {
      report(cause);
    } finally {
      setBusy(false);
    }
  }, [
    activeId,
    append,
    checkMyQuestion,
    deliver,
    gatherContext,
    nextWorkspace,
    question,
    report,
    startNew,
  ]);

  /// Sends the last question again, without adding it to the conversation a second time.
  ///
  /// The common failure here is a free model being busy, which clears on its own within a minute.
  /// Making somebody retype their question to find that out is the wrong answer.
  const retry = useCallback(async (): Promise<void> => {
    const lastAsked = [...turns].reverse().find((turn) => turn.role === 'user');
    if (lastAsked === undefined || activeId === null) {
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const prepared = await gatherContext(lastAsked.content);
      await deliver(activeId, lastAsked.content, prepared.outbound, prepared.scan.scanId, true);
    } catch (cause) {
      report(cause);
    } finally {
      setBusy(false);
    }
  }, [activeId, deliver, gatherContext, report, turns]);

  const approve = useCallback(
    async (keepInClear: string[]): Promise<void> => {
      if (pending === null) {
        return;
      }
      setBusy(true);
      try {
        if (keepInClear.length > 0) {
          await LocalEngine.keepInClear(pending.scanId, keepInClear);
        }
        const verdict = await LocalEngine.verifyOutbound(pending.pack.rendered);
        if (!verdict.mayTransmit) {
          setProblem(verdict.message);
          return;
        }
        setQuestion('');
        setPending(null);
        await deliver(
          pending.conversationId,
          pending.question,
          pending.pack.rendered,
          pending.scanId,
          false,
        );
      } catch (cause) {
        report(cause);
      } finally {
        setBusy(false);
      }
    },
    [deliver, pending, report],
  );

  if (engineMissing) {
    return <EngineMissing />;
  }

  return (
    <div className={`chat${railOpen ? '' : ' chat--narrow'}`}>
      <aside className="threads">
        <div className="threads__top">
          <button
            type="button"
            className="iconbtn"
            onClick={toggleRail}
            title={railOpen ? 'Hide your chats' : 'Show your chats'}
            aria-label={railOpen ? 'Hide your chats' : 'Show your chats'}
            aria-expanded={railOpen}
          >
            {/* One arrow, turned around. It points the way the panel will move, which reads
                without a label; a fixed glyph did not say whether pressing it opened or closed. */}
            <Icon name="arrowLeft" size={16} className={railOpen ? '' : 'flipped'} />
          </button>
          {railOpen && (
            <button
              type="button"
              className="btn btn--primary threads__new"
              // Clears the current thread rather than creating one. A thread saved on every click
              // is how the list filled with rows called "New chat" that nobody wrote in.
              onClick={() => {
                select(null);
                setQuestion('');
                setProblem(null);
              }}
            >
              <Icon name="plus" size={15} />
              New chat
            </button>
          )}
        </div>

        {railOpen && (
          <>
            <label className="threads__context">
              <span className="tiny">Answers use</span>
              <select
                className="input"
                value={workspaceId ?? 'global'}
                disabled={active !== null && turns.length > 0}
                onChange={(event) =>
                  setNextWorkspace(event.target.value === 'global' ? null : event.target.value)
                }
              >
                <option value="global">Global memory</option>
                {workspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
              <span className="tiny muted">
                {workspaceId === null
                  ? 'Your general picture, and any files kept outside a workspace.'
                  : 'Reads the documents in this workspace.'}
              </span>
            </label>

            <div className="threads__list">
              {conversations.length === 0 && (
                <p className="tiny muted" style={{ padding: '8px 4px' }}>
                  Your chats appear here and are kept between visits.
                </p>
              )}
              {conversations.map((item) => (
                <div
                  key={item.id}
                  className={`thread${item.id === activeId ? ' thread--active' : ''}`}
                >
                  <button type="button" className="thread__open" onClick={() => select(item.id)}>
                    <span className="thread__title">{item.title || 'New chat'}</span>
                    <span className="thread__tag">
                      {item.workspaceId === null
                        ? 'Global memory'
                        : workspaces.find((w) => w.id === item.workspaceId)?.name ?? 'Workspace'}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="thread__delete"
                    title="Delete this chat"
                    onClick={() => void remove(item.id)}
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </aside>

      <section className="conversation">
        <header className="conversation__head">
          <h1>{active?.title || 'Chat'}</h1>
          <p className="muted tiny" style={{ margin: '2px 0 0' }}>
            Using {placeName}. Hidden words are put back on this computer.
          </p>
        </header>

        <div className="conversation__body">
          {pending !== null ? (
            <PrivacyGate
              pack={pending.pack}
              verification={pending.verification}
              automatic={pending.automatic}
              needsReview={pending.needsReview}
              busy={busy}
              onApprove={(keep) => void approve(keep)}
              onCancel={() => {
                void LocalEngine.closeScan(pending.scanId);
                setPending(null);
              }}
            />
          ) : (
            <>
              {turns.length === 0 && !busy && (
                <section className="card empty">
                  <h2 className="empty__title">Ask about your own work</h2>
                  <p className="empty__body">
                    {workspaceId === null
                      ? 'Global memory holds a general picture of your work, and any files you keep outside a workspace. For something inside a workspace, open it and ask there.'
                      : `HawkVance reads what is in ${placeName} and answers from it. Anything sensitive is hidden before it leaves, and put back in the answer.`}
                  </p>
                  <div className="examples">
                    {(workspaceId === null
                      ? ['What am I working on lately?', 'What are my priorities?']
                      : [
                          'Summarise the documents here',
                          'What did we decide about pricing?',
                          'List the deadlines mentioned',
                        ]
                    ).map((example) => (
                      <button
                        key={example}
                        type="button"
                        className="chip"
                        onClick={() => setQuestion(example)}
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </section>
              )}

              {turns.map((turn) => (
                <article key={turn.id} className={`turn turn--${turn.role}`}>
                  {/* Only the answer is named. On the person's own message the bubble on the
                      right already says who wrote it, and a label over every single turn is
                      repetition that piles up down a long conversation. */}
                  {turn.role === 'assistant' && <div className="turn__role">HawkVance</div>}
                  {turn.role === 'assistant' ? (
                    <Markdown source={turn.content} />
                  ) : (
                    <p className="turn__text">{turn.content}</p>
                  )}
                  {turn.role === 'assistant' && turn.model !== null && (
                    <div className="turn__meta">
                      <span className="tiny muted">{turn.model}</span>
                    </div>
                  )}
                </article>
              ))}

              {busy && (
                // Shown where the answer will land, not on the button. A spinner on a control says
                // the control was pressed; this says an answer is coming.
                <article className="turn turn--assistant turn--thinking">
                  <div className="turn__role">HawkVance</div>
                  <p className="turn__text muted">
                    <span className="thinking" aria-hidden>
                      <i />
                      <i />
                      <i />
                    </span>
                    Thinking
                  </p>
                </article>
              )}

              {/* Where the answer would have been, not at the top of the transcript. Up there it
                  was scrolled out of sight the moment it appeared, so a question that failed
                  looked exactly like a question that was ignored. */}
              {problem !== null && !busy && (
                <article className="turn turn--failed">
                  <div className="notice notice--error">{problem}</div>
                  <div className="turn__meta">
                    <button type="button" className="btn btn--quiet" onClick={() => void retry()}>
                      Try again
                    </button>
                    <span className="tiny muted">or pick another model below</span>
                  </div>
                </article>
              )}
              <div ref={endOfTurns} />
            </>
          )}
        </div>

        {pending === null && (
          <footer className="composerbar">
            <form
              className="composer"
              onSubmit={(event) => {
                event.preventDefault();
                void ask();
              }}
            >
              <input
                className="input"
                placeholder={`Ask about ${placeName}`}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <button
                type="submit"
                className="btn btn--primary"
                disabled={busy || question.trim().length === 0}
              >
                <Icon name="send" size={15} />
                Send
              </button>
            </form>

            <div className="composerbar__row">
              <ModelPicker models={models} chosen={chosenModel} onChoose={chooseModel} />

              <label className="optin optin--inline">
                <input
                  type="checkbox"
                  checked={checkMyQuestion}
                  onChange={(event) => setCheckMyQuestion(event.target.checked)}
                />
                <span className="tiny">
                  Check my question first
                  {terms.length > 0 && (
                    <span className="muted">
                      {' '}
                      · your {terms.length} hidden word{terms.length === 1 ? '' : 's'} always apply
                    </span>
                  )}
                </span>
              </label>
            </div>
          </footer>
        )}
      </section>
    </div>
  );
}
