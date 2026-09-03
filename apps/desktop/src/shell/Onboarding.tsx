import { useCallback, useState } from 'react';
import { useSession } from '../session/session-context.js';
import { HawkMark } from './HawkMark.js';

/// Asked once, after the first sign-in.
///
/// Two questions, both of which change the answers rather than filling a database. The name is
/// used to greet somebody, and the occupation tells the assistant what kind of work it is looking
/// at, which is the difference between an answer written for a lawyer and one written for an
/// engineer. Both can be changed later in Settings, and both can be skipped.

export function Onboarding({ onDone }: { readonly onDone: () => void }): JSX.Element {
  const { account, updateProfile } = useSession();
  const [displayName, setDisplayName] = useState(account.displayName);
  const [occupation, setOccupation] = useState(account.occupation ?? '');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const save = useCallback(async (): Promise<void> => {
    setBusy(true);
    setProblem(null);
    try {
      await updateProfile({
        displayName: displayName.trim(),
        occupation: occupation.trim().length === 0 ? null : occupation.trim(),
      });
      onDone();
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'That could not be saved just now.');
    } finally {
      setBusy(false);
    }
  }, [displayName, occupation, onDone, updateProfile]);

  return (
    <div className="onboarding">
      <section className="onboarding__panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <HawkMark size={24} />
          <strong>HawkVance</strong>
        </div>

        <div>
          <h1>Two quick things</h1>
          <p className="muted" style={{ margin: '6px 0 0' }}>
            Both are only used to make answers fit you better, and both stay on your account. You
            can change or clear them at any time.
          </p>
        </div>

        <div className="onboarding__form">
          <label className="field">
            <span>What should we call you?</span>
            <input
              className="input"
              value={displayName}
              placeholder="Your name"
              onChange={(event) => setDisplayName(event.target.value)}
            />
          </label>

          <label className="field">
            <span>What kind of work do you do?</span>
            <input
              className="input"
              value={occupation}
              placeholder="Such as accountant, lawyer, founder, student"
              onChange={(event) => setOccupation(event.target.value)}
            />
            <span className="tiny muted">
              This tells HawkVance what sort of answer is useful to you. Leave it blank if you
              would rather not say.
            </span>
          </label>

          {problem !== null && <div className="notice notice--error">{problem}</div>}

          <div className="actions">
            <button type="button" className="btn btn--quiet" onClick={onDone} disabled={busy}>
              Skip for now
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void save()}
              disabled={busy || displayName.trim().length === 0}
            >
              {busy ? <span className="spinner" /> : null}
              {busy ? 'Saving' : 'Continue'}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
