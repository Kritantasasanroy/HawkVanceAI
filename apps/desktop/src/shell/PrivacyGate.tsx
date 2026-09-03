import { useState } from 'react';
import type { ContextPack, Redaction, VerificationVerdict } from '../engine/engine-bridge.js';

/// The last screen before anything leaves this computer.
///
/// Its whole job is to show the exact text that would be sent, not a summary of it. A person
/// cannot consent to something they have not been shown, and a product that claims to hide things
/// has to be checkable rather than merely trusted.

const categoryLabels: Record<string, string> = {
  apiKey: 'API key',
  accessToken: 'Access token',
  password: 'Password',
  privateKey: 'Private key',
  connectionString: 'Database address',
  credentialInUrl: 'Login inside a link',
  email: 'Email address',
  phone: 'Phone number',
  creditCard: 'Card number',
  bankAccount: 'Bank details',
  iban: 'Bank code',
  nationalId: 'ID number',
  ipAddress: 'Device address',
  url: 'Web link',
  person: 'Person',
  organization: 'Company',
  location: 'Place',
  gpe: 'Place',
  streetAddress: 'Address',
  date: 'Date',
  dateOfBirth: 'Date of birth',
  monetaryAmount: 'Amount',
  customRule: 'A word you chose',
};

const label = (category: string): string => categoryLabels[category] ?? category;

export type PrivacyGateProps = {
  readonly pack: ContextPack;
  readonly verification: VerificationVerdict;
  readonly automatic: ReadonlyArray<Redaction>;
  readonly needsReview: ReadonlyArray<Redaction>;
  readonly busy: boolean;
  readonly onApprove: (keepInClear: string[]) => void;
  readonly onCancel: () => void;
};

export function PrivacyGate({
  pack,
  verification,
  automatic,
  needsReview,
  busy,
  onApprove,
  onCancel,
}: PrivacyGateProps): JSX.Element {
  /// Anything uncertain stays hidden unless the person says otherwise. The safe answer is the
  /// default, so a hurried click never reveals something by accident.
  const [reveal, setReveal] = useState<Set<string>>(new Set());

  const toggle = (placeholder: string): void => {
    setReveal((current) => {
      const next = new Set(current);
      if (next.has(placeholder)) {
        next.delete(placeholder);
      } else {
        next.add(placeholder);
      }
      return next;
    });
  };

  return (
    <section className="gate">
      <div className="gate__head">
        <div>
          <h2>Check what is about to be sent</h2>
          <p className="tiny muted" style={{ margin: '4px 0 0' }}>
            This is the exact text that leaves your computer. Nothing else goes with it.
          </p>
        </div>
        <span className={`pill ${verification.mayTransmit ? 'pill--ok' : 'pill--warn'}`}>
          <span className="dot" /> {verification.mayTransmit ? 'Ready to send' : 'Needs a look'}
        </span>
      </div>

      {automatic.length > 0 && (
        <div className="gate__group">
          <div className="card__label">Hidden for you · {automatic.length}</div>
          <ul className="gate__list">
            {automatic.map((item) => (
              <li key={item.placeholder} className="gate__row gate__row--locked">
                <span className="gate__tick" aria-hidden>
                  ✓
                </span>
                <span className="gate__placeholder">{item.placeholder}</span>
                <span className="gate__category">{label(item.category)}</span>
                <span className="gate__confidence">{Math.round(item.confidence * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {needsReview.length > 0 && (
        <div className="gate__group">
          <div className="card__label">Not sure about these · {needsReview.length}</div>
          <p className="tiny muted" style={{ marginTop: -4 }}>
            These stay hidden unless you tick them. Tick one only if it is safe for it to leave.
          </p>
          <ul className="gate__list">
            {needsReview.map((item) => (
              <li key={item.placeholder} className="gate__row gate__row--amber">
                <input
                  type="checkbox"
                  checked={reveal.has(item.placeholder)}
                  onChange={() => toggle(item.placeholder)}
                  aria-label={`Send ${label(item.category)} as it is`}
                />
                <span className="gate__placeholder">{item.placeholder}</span>
                <span className="gate__category">{label(item.category)}</span>
                <span className="gate__confidence">{Math.round(item.confidence * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card__label">The exact text</div>
      <pre className="gate__payload">{pack.rendered}</pre>

      {!verification.mayTransmit && (
        <div className="notice notice--warn" style={{ marginTop: 12 }}>
          {verification.message}
        </div>
      )}

      <div className="gate__actions">
        <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => onApprove([...reveal])}
          disabled={busy}
        >
          {busy ? <span className="spinner" /> : null}
          {busy ? 'Sending' : 'Send this'}
        </button>
      </div>
    </section>
  );
}
