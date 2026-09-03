import { useCallback, useState } from 'react';
import { NeonAuthClient } from '../session/neon-auth.js';
import { useSessionState } from '../session/session-context.js';
import { HawkMark } from './HawkMark.js';

/// Signing in, in two steps, with no password to remember.
///
/// There is one path here, not two. An earlier version offered a choice between signing in and
/// creating an account, which reads as two different buttons for what is, to the person, one act:
/// type your email. The same code does both, so asking which one they wanted was asking them to
/// answer a question the system had already answered.

type Stage =
  | { readonly name: 'email' }
  | { readonly name: 'code'; readonly email: string };

export function SignIn(): JSX.Element {
  const { adoptIdentityToken } = useSessionState();
  const [stage, setStage] = useState<Stage>({ name: 'email' });
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const submitEmail = useCallback(
    async (event: React.FormEvent): Promise<void> => {
      event.preventDefault();
      const address = email.trim();
      if (address.length === 0) {
        return;
      }
      setBusy(true);
      setProblem(null);
      try {
        await NeonAuthClient.sendCode(address);
        setStage({ name: 'code', email: address });
      } catch (cause) {
        setProblem(cause instanceof Error ? cause.message : 'That did not work. Please try again.');
      } finally {
        setBusy(false);
      }
    },
    [email],
  );

  const submitCode = useCallback(
    async (event: React.FormEvent): Promise<void> => {
      event.preventDefault();
      if (stage.name !== 'code' || code.trim().length === 0) {
        return;
      }
      setBusy(true);
      setProblem(null);
      try {
        const token = await NeonAuthClient.verifyCode(stage.email, code.trim());
        await adoptIdentityToken(token);
      } catch (cause) {
        setProblem(cause instanceof Error ? cause.message : 'That code did not work.');
      } finally {
        setBusy(false);
      }
    },
    [adoptIdentityToken, code, stage],
  );

  return (
    <div className="signin">
      <aside className="signin__brandside">
        <div className="signin__wordmark">
          <HawkMark size={26} />
          HawkVance
        </div>

        <div>
          <p className="signin__promise">Give AI memory without giving away your data.</p>
          <div className="signin__pillars">
            <div className="signin__pillar">
              <span>
                <strong>Read on this computer</strong>
                Your files never leave the machine they are on.
              </span>
            </div>
            <div className="signin__pillar">
              <span>
                <strong>You see what is sent</strong>
                Every question can be shown to you in full before it goes.
              </span>
            </div>
            <div className="signin__pillar">
              <span>
                <strong>Hidden values come back here</strong>
                The list that turns a label back into the real value never leaves.
              </span>
            </div>
          </div>
        </div>

        <span className="tiny" style={{ color: '#9c9382' }}>
          No password to remember
        </span>
      </aside>

      <main className="signin__formside">
        {stage.name === 'email' ? (
          <form className="signin__form" onSubmit={(event) => void submitEmail(event)}>
            <div>
              <h1>Sign in or create your account</h1>
              <p className="muted" style={{ margin: '6px 0 0' }}>
                Enter your email and we send a six-digit code. If you have not used HawkVance
                before, that same code creates your account.
              </p>
            </div>

            <div className="field">
              <label htmlFor="email">Your email</label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>

            {problem !== null && <div className="notice notice--error">{problem}</div>}

            <button
              type="submit"
              className="btn btn--primary btn--wide"
              disabled={busy || email.trim().length === 0}
            >
              {busy ? <span className="spinner" /> : null}
              {busy ? 'Sending' : 'Send my code'}
            </button>
          </form>
        ) : (
          <form className="signin__form" onSubmit={(event) => void submitCode(event)}>
            <div>
              <h1>Check your email</h1>
              <p className="muted" style={{ margin: '6px 0 0' }}>
                We sent a six-digit code to <strong>{stage.email}</strong>. It is good for a few
                minutes.
              </p>
            </div>

            <div className="field">
              <label htmlFor="code">Your code</label>
              <input
                id="code"
                className="input input--code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
              />
            </div>

            {problem !== null && <div className="notice notice--error">{problem}</div>}

            <button
              type="submit"
              className="btn btn--primary btn--wide"
              disabled={busy || code.trim().length < 6}
            >
              {busy ? <span className="spinner" /> : null}
              {busy ? 'Checking' : 'Sign in'}
            </button>

            <button
              type="button"
              className="btn btn--quiet"
              onClick={() => {
                setStage({ name: 'email' });
                setCode('');
                setProblem(null);
              }}
            >
              Use a different email
            </button>
          </form>
        )}
      </main>
    </div>
  );
}
