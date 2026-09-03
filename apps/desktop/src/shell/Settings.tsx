import { useCallback, useEffect, useState } from 'react';
import type { Hardware } from '../engine/engine-bridge.js';
import { LocalEngine } from '../engine/engine-bridge.js';
import { useSession } from '../session/session-context.js';

/// Your details, and what this computer can do.
///
/// The hardware section is read-only on purpose. It is here to answer "why is it slow" rather than
/// to be tuned: the engine already picks a level from what it finds, and inviting somebody to
/// override that mostly produces a slower app and a worse result.

export function Settings(): JSX.Element {
  const { account, limits, updateProfile } = useSession();
  const [displayName, setDisplayName] = useState(account.displayName);
  const [occupation, setOccupation] = useState(account.occupation ?? '');
  const [hardware, setHardware] = useState<Hardware | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void LocalEngine.hardware()
      .then((found) => !cancelled && setHardware(found))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const save = useCallback(async (): Promise<void> => {
    setBusy(true);
    setProblem(null);
    setSaved(false);
    try {
      await updateProfile({
        displayName: displayName.trim(),
        occupation: occupation.trim().length === 0 ? null : occupation.trim(),
      });
      setSaved(true);
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'That could not be saved just now.');
    } finally {
      setBusy(false);
    }
  }, [displayName, occupation, updateProfile]);

  const readableMemory = (bytes: number): string => `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;

  return (
    <>
      <div className="main__head">
        <div>
          <h1>Settings</h1>
          <p className="muted" style={{ margin: '4px 0 0' }}>
            Your details, your plan, and what this computer can handle.
          </p>
        </div>
      </div>

      <section className="card">
        <div className="card__label">About you</div>
        <p className="tiny muted" style={{ marginTop: -4 }}>
          Used to greet you and to shape answers towards the kind of work you do.
        </p>

        <div className="profileform">
          <label className="field">
            <span>Name</span>
            <input
              className="input"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Occupation</span>
            <input
              className="input"
              value={occupation}
              placeholder="Leave blank if you would rather not say"
              onChange={(event) => setOccupation(event.target.value)}
            />
          </label>
        </div>

        {problem !== null && (
          <div className="notice notice--error" style={{ marginTop: 12 }}>
            {problem}
          </div>
        )}
        {saved && (
          <div className="notice notice--ok" style={{ marginTop: 12 }}>
            Saved.
          </div>
        )}

        <div className="actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void save()}
            disabled={busy || displayName.trim().length === 0}
          >
            {busy ? <span className="spinner" /> : null}
            {busy ? 'Saving' : 'Save changes'}
          </button>
        </div>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card__label">Your account</div>
        <div className="kv">
          <span>Email</span>
          <span className="kv__value">{account.email}</span>
        </div>
        <div className="kv">
          <span>Plan</span>
          <span className="kv__value" style={{ textTransform: 'capitalize' }}>
            {account.plan}
          </span>
        </div>
        <div className="kv">
          <span>Included each month</span>
          <span className="kv__value">{limits.monthlyCredits.toLocaleString()} credits</span>
        </div>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card__label">This computer</div>
        <p className="tiny muted" style={{ marginTop: -4 }}>
          Reading and checking happen here, so how fast that is depends on this machine rather than
          on us.
        </p>
        {hardware === null ? (
          <p className="muted">Checking…</p>
        ) : (
          <>
            <div className="kv">
              <span>Memory</span>
              <span className="kv__value">{readableMemory(hardware.totalMemoryBytes)}</span>
            </div>
            <div className="kv">
              <span>Graphics acceleration</span>
              <span className="kv__value">{hardware.hasGpu ? 'Available' : 'Not available'}</span>
            </div>
            <div className="kv">
              <span>Checking level chosen for you</span>
              <span className="kv__value" style={{ textTransform: 'capitalize' }}>
                {hardware.recommendedMode}
              </span>
            </div>
          </>
        )}
      </section>
    </>
  );
}
