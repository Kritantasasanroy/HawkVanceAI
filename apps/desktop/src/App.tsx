import { useState } from 'react';
import { useSessionState } from './session/session-context.js';
import { AppShell } from './shell/AppShell.js';
import { Onboarding } from './shell/Onboarding.js';
import { SignIn } from './shell/SignIn.js';

/// Decides which of the three states the app is in.
///
/// Restoring is its own state rather than being folded into signed-out, because showing the
/// sign-in screen for a moment to somebody who is already signed in looks like being logged out
/// and is the sort of thing that makes people stop trusting an app with their documents.
export function App(): JSX.Element {
  const { state } = useSessionState();
  const [skippedOnboarding, setSkippedOnboarding] = useState(false);

  if (state.kind === 'restoring') {
    return <div className="centered">Opening your vault…</div>;
  }

  if (state.kind === 'signedOut') {
    return <SignIn />;
  }

  // Occupation is null until it has been asked for, which is what tells us this is a first run
  // rather than somebody who chose to leave it blank.
  const needsOnboarding = state.account.occupation === null && !skippedOnboarding;
  if (needsOnboarding) {
    return <Onboarding onDone={() => setSkippedOnboarding(true)} />;
  }

  return <AppShell />;
}
