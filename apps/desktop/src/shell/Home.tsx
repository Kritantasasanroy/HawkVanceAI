import { useEffect, useState } from 'react';
import { LocalEngine, type Hardware } from '../engine/engine-bridge.js';
import { useSession } from '../session/session-context.js';
import { VaultStore } from '../session/vault-store.js';
import type { Destination } from './navigation.js';

const modeExplanation: Record<string, string> = {
  fast: 'Finds set patterns like emails, cards and keys.',
  balanced: 'Finds set patterns and names, on this computer.',
  thorough: 'Set to full speed, because this machine has memory to spare.',
};

function greeting(now: Date): string {
  const hour = now.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function Home({ onNavigate }: { readonly onNavigate: (to: Destination) => void }): JSX.Element {
  const { account, limits } = useSession();
  const [counts, setCounts] = useState<{ documents: number; workspaces: number } | null>(null);
  const [hardware, setHardware] = useState<Hardware | null>(null);

  useEffect(() => {
    let cancelled = false;
    const read = async (): Promise<void> => {
      const workspaces = await VaultStore.workspaces().catch(() => []);
      const perPlace = await Promise.all(
        [null, ...workspaces.map((item) => item.id)].map((id) =>
          VaultStore.documents(id).catch(() => []),
        ),
      );
      const detected = await LocalEngine.hardware().catch(() => null);
      if (!cancelled) {
        setCounts({
          documents: perPlace.reduce((total, list) => total + list.length, 0),
          workspaces: workspaces.length,
        });
        setHardware(detected);
      }
    };
    void read();
    return () => {
      cancelled = true;
    };
  }, []);

  const firstRun = counts !== null && counts.workspaces === 0;

  return (
    <>
      <div className="main__head">
        <div>
          <h1>
            {greeting(new Date())}, {account.displayName}
          </h1>
          <p className="muted" style={{ margin: '4px 0 0' }}>
            Everything you add is processed on this computer.
          </p>
        </div>
        <span className="pill pill--ok">
          <span className="dot" /> Private mode on
        </span>
      </div>

      {firstRun ? (
        <section className="card empty">
          <h2 className="empty__title">Let us set up your first workspace</h2>
          <p className="empty__body">
            A workspace keeps one project separate from the rest, so what HawkVance remembers about
            work does not mix with anything else. Make one, add a document, then ask about it.
          </p>
          <button type="button" className="btn btn--primary" onClick={() => onNavigate('workspaces')}>
            Create a workspace
          </button>
        </section>
      ) : (
        <div className="nextsteps">
          <button type="button" className="nextstep" onClick={() => onNavigate('documents')}>
            <span className="nextstep__title">Add a document</span>
            <span className="nextstep__body">
              Read a PDF, Word file or image here on your computer, and choose what stays hidden.
            </span>
          </button>
          <button type="button" className="nextstep" onClick={() => onNavigate('chat')}>
            <span className="nextstep__title">Ask a question</span>
            <span className="nextstep__body">
              Get an answer that uses your own documents, with anything sensitive hidden first.
            </span>
          </button>
          <button type="button" className="nextstep" onClick={() => onNavigate('workspaces')}>
            <span className="nextstep__title">Switch project</span>
            <span className="nextstep__body">
              Keep separate pieces of work apart, each with its own memory and documents.
            </span>
          </button>
        </div>
      )}

      <div className="grid grid--3" style={{ marginTop: 16 }}>
        <section className="card">
          <div className="card__label">Your work</div>
          <div className="stat">{counts === null ? '—' : counts.documents}</div>
          <p className="tiny muted" style={{ margin: '6px 0 0' }}>
            {counts === null
              ? 'Checking…'
              : `${counts.documents === 1 ? 'document' : 'documents'} across ${counts.workspaces} ${
                  counts.workspaces === 1 ? 'workspace' : 'workspaces'
                }`}
          </p>
        </section>

        <section className="card">
          <div className="card__label">Included this month</div>
          <div className="stat">{limits.monthlyCredits.toLocaleString()}</div>
          <p className="tiny muted" style={{ margin: '6px 0 0' }}>
            credits on your {account.plan} plan. A question costs 1, reading a document costs 1 to 3.
          </p>
        </section>

        <section className="card">
          <div className="card__label">Speed setting</div>
          <div className="stat" style={{ textTransform: 'capitalize' }}>
            {hardware?.recommendedMode ?? '—'}
          </div>
          <p className="tiny muted" style={{ margin: '6px 0 0' }}>
            {hardware === null
              ? 'Checking this computer…'
              : modeExplanation[hardware.recommendedMode] ?? ''}
          </p>
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card__label">Why this is private</div>
        <ul className="reasons">
          <li>
            <strong>Your files never leave.</strong> Reading, image recognition and the search for
            sensitive details all happen on this computer.
          </li>
          <li>
            <strong>You see what is sent.</strong> Before any question goes out, HawkVance can show
            you the exact text and what it has hidden.
          </li>
          <li>
            <strong>Hidden values come back here.</strong> The list that turns a label back into the
            real value is kept on this computer and is never sent anywhere.
          </li>
          <li>
            <strong>Stored locked.</strong> What you keep is encrypted on this computer, with the
            key held by Windows.
          </li>
        </ul>
      </section>
    </>
  );
}
