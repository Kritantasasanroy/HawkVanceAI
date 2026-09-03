import { useCallback, useEffect, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import type { ProcessedDocument, ScanResult } from '../engine/engine-bridge.js';
import { EngineFailure, LocalEngine } from '../engine/engine-bridge.js';
import type { DocumentRecord, WorkspaceRecord } from '../session/vault-store.js';
import { VaultStore } from '../session/vault-store.js';
import { EngineMissing } from './EngineMissing.js';
import { Stepper, type Step } from './Stepper.js';
import { WordPicker } from './WordPicker.js';

const steps: ReadonlyArray<Step> = [
  { id: 'choose', label: 'Choose a file', detail: 'Stays on this machine' },
  { id: 'confirm', label: 'Set what to hide', detail: 'You decide before anything runs' },
  { id: 'read', label: 'Read and check', detail: 'Locally, no upload' },
  { id: 'review', label: 'Review and save', detail: 'Nothing is kept until you save' },
];

const categoryLabels: Record<string, string> = {
  apiKey: 'API keys',
  accessToken: 'Access tokens',
  password: 'Passwords',
  privateKey: 'Private keys',
  connectionString: 'Database addresses',
  credentialInUrl: 'Logins inside links',
  email: 'Email addresses',
  phone: 'Phone numbers',
  creditCard: 'Card numbers',
  bankAccount: 'Bank details',
  iban: 'Bank codes',
  nationalId: 'ID numbers',
  ipAddress: 'Device addresses',
  url: 'Web links',
  person: 'People',
  organization: 'Companies',
  location: 'Places',
  gpe: 'Places',
  streetAddress: 'Street addresses',
  date: 'Dates',
  dateOfBirth: 'Dates of birth',
  monetaryAmount: 'Amounts of money',
  customRule: 'Words you chose',
};

const readableCategory = (raw: string): string => categoryLabels[raw] ?? raw;

const modes = [
  {
    value: 'fast' as const,
    title: 'Quick',
    detail: 'Finds set patterns like emails, cards and keys.',
    cost: 'Fastest, uses least memory',
  },
  {
    value: 'balanced' as const,
    title: 'Balanced',
    detail: 'Also finds names, places and companies.',
    cost: 'Recommended for most files',
  },
  {
    value: 'thorough' as const,
    title: 'Thorough',
    detail: 'Looks hardest, including unusual wording.',
    cost: 'Slowest, uses most memory',
  },
];

const readableSize = (bytes: number): string =>
  bytes < 1024
    ? `${bytes} B`
    : bytes < 1024 * 1024
      ? `${Math.round(bytes / 1024)} KB`
      : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

/// Where a file can be filed. Null means Global memory: anything not tied to one project.
type Destination = string | null;

type Stage =
  | { readonly name: 'idle' }
  | { readonly name: 'confirming'; readonly path: string; readonly filename: string }
  | { readonly name: 'processing'; readonly filename: string }
  | {
      readonly name: 'review';
      readonly document: ProcessedDocument['document'];
      readonly scan: ScanResult;
      readonly saved: boolean;
    };

export function Documents({
  workspaces,
  workspace,
  onActivate,
}: {
  readonly workspaces: ReadonlyArray<WorkspaceRecord>;
  readonly workspace: WorkspaceRecord | null;
  readonly onActivate: (workspace: WorkspaceRecord | null) => void;
}): JSX.Element {
  /// Which place the screen is showing, independent of the app-wide workspace, so somebody can
  /// look at Global memory without changing what Chat is pointed at.
  const [viewing, setViewing] = useState<Destination>(workspace?.id ?? null);
  /// Where the file being added will be filed. Asked before the scan, because moving a document
  /// afterwards would mean reading it again.
  const [destination, setDestination] = useState<Destination>(workspace?.id ?? null);

  const [stage, setStage] = useState<Stage>({ name: 'idle' });
  const [mode, setMode] = useState<'fast' | 'balanced' | 'thorough'>('balanced');
  const [stored, setStored] = useState<ReadonlyArray<DocumentRecord>>([]);
  const [terms, setTerms] = useState<ReadonlyArray<string>>([]);
  const [termDraft, setTermDraft] = useState('');
  const [rescanning, setRescanning] = useState(false);
  const [problem, setProblem] = useState<EngineFailure | null>(null);

  const scopeKey = viewing ?? 'global';
  const placeName = (id: Destination): string =>
    id === null ? 'Global memory' : workspaces.find((item) => item.id === id)?.name ?? 'Workspace';

  const refresh = useCallback(async (): Promise<void> => {
    const [documents, inEffect] = await Promise.all([
      VaultStore.documents(viewing).catch(() => []),
      VaultStore.termsInEffect(viewing).catch(() => []),
    ]);
    setStored(documents);
    setTerms(inEffect);
  }, [viewing]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const currentStep =
    stage.name === 'idle'
      ? 'choose'
      : stage.name === 'confirming'
        ? 'confirm'
        : stage.name === 'processing'
          ? 'read'
          : 'review';

  const choose = useCallback(async (): Promise<void> => {
    const picked = await open({
      multiple: false,
      filters: [
        {
          name: 'Documents',
          extensions: ['pdf', 'docx', 'txt', 'md', 'csv', 'png', 'jpg', 'jpeg', 'py', 'ts', 'js'],
        },
      ],
    });
    if (typeof picked !== 'string') {
      return;
    }
    setProblem(null);
    setDestination(viewing);
    setStage({
      name: 'confirming',
      path: picked,
      filename: picked.split(/[\\/]/).pop() ?? picked,
    });
  }, [viewing]);

  const runScan = useCallback(
    async (path: string, filename: string): Promise<void> => {
      setStage({ name: 'processing', filename });
      setProblem(null);
      try {
        const result = await LocalEngine.processDocument(path, mode, true, terms);
        setStage({ name: 'review', document: result.document, scan: result.scan, saved: false });
      } catch (cause) {
        setProblem(EngineFailure.from(cause));
        setStage({ name: 'idle' });
      }
    },
    [mode, terms],
  );

  /// Keeps the document, and the mapping that makes its placeholders reversible.
  ///
  /// Nothing is written until this runs, which is what the fourth step promises. The mapping is
  /// stored through Rust in one call, so the originals never pass through this screen.
  const save = useCallback(async (): Promise<void> => {
    if (stage.name !== 'review') {
      return;
    }
    const id = crypto.randomUUID();
    await VaultStore.saveDocument({
      id,
      workspaceId: destination,
      filename: stage.document.filename,
      sha256: stage.document.sha256,
      sizeBytes: stage.document.sizeBytes,
      characterCount: stage.document.characterCount,
      usedOcr: stage.document.usedOcr,
      sanitisedText: stage.scan.sanitisedText,
      createdAt: new Date().toISOString(),
    });

    await VaultStore.rememberRedactions({
      documentId: id,
      workspaceId: destination,
      scanId: stage.scan.scanId,
    }).catch(() => 0);

    setStage({ ...stage, saved: true });
    await refresh();
  }, [destination, refresh, stage]);

  const discard = useCallback((): void => {
    if (stage.name === 'review') {
      void LocalEngine.closeScan(stage.scan.scanId);
    }
    setStage({ name: 'idle' });
  }, [stage]);

  const toggleTerm = useCallback(
    async (word: string): Promise<void> => {
      // The fallback is typed, because an untyped empty array infers as never[] and then unions
      // with the real result into something nothing can be compared against.
      const existing = await VaultStore.protectedTerms(scopeKey).catch(
        (): ReadonlyArray<string> => [],
      );
      const next = existing.includes(word)
        ? existing.filter((term) => term !== word)
        : [...existing, word];
      await VaultStore.saveProtectedTerms(scopeKey, next);
      await refresh();
    },
    [refresh, scopeKey],
  );

  /// Reads the file again with the newly marked words applied.
  ///
  /// A rescan rather than a text substitution, because a word marked now may appear in forms the
  /// detectors handle better than a plain find and replace would.
  const applyWords = useCallback(async (): Promise<void> => {
    if (stage.name !== 'review') {
      return;
    }
    setRescanning(true);
    try {
      const rescanned = await LocalEngine.scanText(
        stage.scan.sanitisedText,
        mode,
        undefined,
        terms,
      );
      setStage({ ...stage, scan: rescanned });
    } catch (cause) {
      setProblem(EngineFailure.from(cause));
    } finally {
      setRescanning(false);
    }
  }, [mode, stage, terms]);

  if (problem?.isNotInstalled === true) {
    return <EngineMissing />;
  }

  const hiddenCount = stage.name === 'review' ? stage.scan.redactions.length : 0;

  return (
    <>
      <div className="main__head">
        <div>
          <h1>Documents</h1>
          <p className="muted" style={{ margin: '4px 0 0' }}>
            Your file is read and checked on this computer. It is never uploaded.
          </p>
        </div>
        {stage.name === 'idle' && (
          <label className="modelpick">
            <span className="tiny muted">Showing</span>
            <select
              className="input"
              value={viewing ?? 'global'}
              onChange={(event) => {
                const chosen = event.target.value === 'global' ? null : event.target.value;
                setViewing(chosen);
                setDestination(chosen);
                onActivate(workspaces.find((item) => item.id === chosen) ?? null);
              }}
            >
              <option value="global">Global memory</option>
              {workspaces.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <Stepper steps={steps} currentId={currentStep} />

      {problem !== null && (
        <div className="notice notice--error" style={{ marginBottom: 16 }}>
          {problem.message}
        </div>
      )}

      {stage.name === 'idle' && (
        <>
          {stored.length === 0 ? (
            <section className="card empty">
              <h2 className="empty__title">No documents yet</h2>
              <p className="empty__body">
                Add a PDF, Word file, spreadsheet, image or code file to{' '}
                <strong>{placeName(viewing)}</strong>. HawkVance reads it here, shows you exactly
                what it found, and keeps nothing until you press save.
              </p>
              <button type="button" className="btn btn--primary" onClick={() => void choose()}>
                Add your first document
              </button>
            </section>
          ) : (
            <section className="card">
              <div className="card__label">
                In {placeName(viewing)} · {stored.length}
              </div>
              {stored.map((item) => (
                <div className="kv" key={item.id}>
                  <span>{item.filename}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span className="kv__value">
                      {item.characterCount.toLocaleString()} characters
                    </span>
                    <button
                      type="button"
                      className="btn btn--quiet btn--danger"
                      onClick={() => {
                        void VaultStore.deleteDocument(item.id).then(refresh);
                      }}
                    >
                      Remove
                    </button>
                  </span>
                </div>
              ))}
              <div className="actions">
                <button type="button" className="btn btn--primary" onClick={() => void choose()}>
                  Add another document
                </button>
              </div>
            </section>
          )}

          {terms.length > 0 && (
            <section className="card" style={{ marginTop: 16 }}>
              <div className="card__label">Words you always hide · {terms.length}</div>
              <p className="tiny muted" style={{ marginTop: -4 }}>
                These are hidden in every document and every question here, and put back
                automatically in the answers you get.
              </p>
              <div className="chips">
                {terms.map((term) => (
                  <button
                    key={term}
                    type="button"
                    className="chip chip--removable"
                    onClick={() => void toggleTerm(term)}
                    title={`Stop hiding ${term}`}
                  >
                    {term} <span aria-hidden>×</span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {stage.name === 'confirming' && (
        <section className="card">
          <div className="card__label">Step 2 of 4 · {stage.filename}</div>
          <h2 style={{ margin: '2px 0 4px', fontSize: 17 }}>Where should this go?</h2>
          <p className="tiny muted" style={{ marginTop: 0 }}>
            A workspace keeps this file with one project, and only chats in that workspace can read
            it. Global memory is for anything not tied to a project.
          </p>
          <div className="modes" style={{ marginBottom: 18 }}>
            <button
              type="button"
              className={`modes__option${destination === null ? ' modes__option--active' : ''}`}
              onClick={() => setDestination(null)}
              aria-pressed={destination === null}
            >
              <strong>Global memory</strong>
              <span className="tiny muted">Not tied to a project</span>
            </button>
            {workspaces.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`modes__option${destination === item.id ? ' modes__option--active' : ''}`}
                onClick={() => setDestination(item.id)}
                aria-pressed={destination === item.id}
              >
                <strong>{item.name}</strong>
                <span className="tiny muted">Workspace</span>
              </button>
            ))}
          </div>

          <div className="card__label" style={{ marginTop: 20 }}>
            How carefully should it look?
          </div>
          <div className="modes">
            {modes.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`modes__option${mode === option.value ? ' modes__option--active' : ''}`}
                onClick={() => setMode(option.value)}
                aria-pressed={mode === option.value}
              >
                <strong>{option.title}</strong>
                <span className="tiny muted">{option.detail}</span>
                <span className="tiny modes__cost">{option.cost}</span>
              </button>
            ))}
          </div>

          <div className="actions">
            <button type="button" className="btn btn--ghost" onClick={discard}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void runScan(stage.path, stage.filename)}
            >
              Read and check the file
            </button>
          </div>
        </section>
      )}

      {stage.name === 'processing' && (
        <section className="card">
          <div className="card__label">Step 3 of 4</div>
          <h2 style={{ margin: '2px 0 10px', fontSize: 17 }}>Reading {stage.filename}</h2>
          <p className="muted" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="spinner" />
            Opening the file, then checking it for anything sensitive. Nothing is being uploaded.
          </p>
          <p className="tiny muted">
            A long or scanned document can take a minute the first time, because the tools it needs
            are being started.
          </p>
        </section>
      )}

      {stage.name === 'review' && (
        <>
          <section className="card">
            <div className="card__label">Step 4 of 4 · {stage.document.filename}</div>
            <h2 style={{ margin: '2px 0 4px', fontSize: 17 }}>
              {hiddenCount === 0
                ? 'Nothing sensitive was found'
                : `${hiddenCount} thing${hiddenCount === 1 ? '' : 's'} will be hidden`}
            </h2>
            <p className="tiny muted" style={{ marginTop: 0 }}>
              {stage.saved
                ? `Saved to ${placeName(destination)}. You can close this now.`
                : 'Nothing has been kept yet. Read the preview below, hide anything else you want, then save.'}
            </p>

            <div className="summarybar">
              <span>
                <strong>{readableSize(stage.document.sizeBytes)}</strong>
                <span className="tiny muted">Size</span>
              </span>
              <span>
                <strong>{stage.document.characterCount.toLocaleString()}</strong>
                <span className="tiny muted">Characters read</span>
              </span>
              <span>
                <strong>{stage.document.usedOcr ? 'Yes' : 'No'}</strong>
                <span className="tiny muted">Needed image reading</span>
              </span>
              <span>
                <strong>
                  {modes.find((item) => item.value === stage.scan.routing.mode)?.title ??
                    stage.scan.routing.mode}
                </strong>
                <span className="tiny muted">Check level</span>
              </span>
            </div>

            {stage.document.degraded.length > 0 && (
              <div className="notice notice--warn" style={{ marginTop: 12 }}>
                {stage.document.degraded.join(' ')}
              </div>
            )}
          </section>

          <div
            className="grid"
            style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.35fr)', marginTop: 16 }}
          >
            <section className="card">
              <div className="card__label">What was found</div>
              {Object.keys(stage.scan.countsByCategory).length === 0 ? (
                <p className="tiny muted">
                  Nothing matched. You can still hide your own words in the preview.
                </p>
              ) : (
                Object.entries(stage.scan.countsByCategory).map(([category, count]) => (
                  <div className="kv" key={category}>
                    <span>{readableCategory(category)}</span>
                    <span className="kv__value">{count}</span>
                  </div>
                ))
              )}

              {stage.scan.needsReview.length > 0 && (
                <div className="notice notice--warn" style={{ marginTop: 12 }}>
                  {stage.scan.needsReview.length} item
                  {stage.scan.needsReview.length === 1 ? ' is' : 's are'} uncertain. You will be
                  asked about {stage.scan.needsReview.length === 1 ? 'it' : 'them'} before anything
                  is sent.
                </div>
              )}

              <div className="card__label" style={{ marginTop: 18 }}>
                Words you always hide · {terms.length}
              </div>
              <form
                className="termadd"
                onSubmit={(event) => {
                  event.preventDefault();
                  const word = termDraft.trim();
                  if (word.length === 0) {
                    return;
                  }
                  void toggleTerm(word);
                  setTermDraft('');
                }}
              >
                <input
                  className="input"
                  placeholder="Type a word or name"
                  value={termDraft}
                  onChange={(event) => setTermDraft(event.target.value)}
                />
                <button
                  type="submit"
                  className="btn btn--ghost"
                  disabled={termDraft.trim().length === 0}
                >
                  Add
                </button>
              </form>
              {terms.length > 0 && (
                <div className="chips" style={{ marginTop: 10 }}>
                  {terms.map((term) => (
                    <button
                      key={term}
                      type="button"
                      className="chip chip--removable"
                      onClick={() => void toggleTerm(term)}
                      title={`Stop hiding ${term}`}
                    >
                      {term} <span aria-hidden>×</span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section className="card">
              <div className="card__label">Preview of what would be sent</div>
              <WordPicker
                text={stage.scan.sanitisedText}
                protectedTerms={terms}
                onToggle={(word) => void toggleTerm(word)}
              />
              <div className="actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => void applyWords()}
                  disabled={rescanning}
                >
                  {rescanning ? <span className="spinner" /> : null}
                  {rescanning ? 'Updating' : 'Update preview'}
                </button>
              </div>
            </section>
          </div>

          <div className="savebar">
            <span className="tiny muted">
              {stage.saved
                ? 'This document is saved.'
                : 'Nothing is kept until you press save.'}
            </span>
            <span style={{ display: 'flex', gap: 10 }}>
              <button type="button" className="btn btn--ghost" onClick={discard}>
                {stage.saved ? 'Done' : 'Discard'}
              </button>
              {!stage.saved && (
                <button type="button" className="btn btn--primary" onClick={() => void save()}>
                  Save to {placeName(destination)}
                </button>
              )}
            </span>
          </div>
        </>
      )}
    </>
  );
}
