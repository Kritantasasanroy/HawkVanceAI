import { useCallback, useEffect, useState } from 'react';
import { ChatProvider } from '../session/chat-store.js';
import { useSession } from '../session/session-context.js';
import type { WorkspaceRecord } from '../session/vault-store.js';
import { VaultStore } from '../session/vault-store.js';
import { Chat } from './Chat.js';
import { Documents } from './Documents.js';
import { HawkMark } from './HawkMark.js';
import { Home } from './Home.js';
import { Icon, type IconName } from './Icon.js';
import { MemoryBrowser } from './MemoryBrowser.js';
import type { Destination } from './navigation.js';
import { Settings } from './Settings.js';
import { Workspaces } from './Workspaces.js';

type NavEntry = { readonly id: Destination; readonly label: string; readonly icon: IconName };

/// Grouped so the list reads as two ideas rather than six links: the things you do, and the things
/// you adjust.
const groups: ReadonlyArray<{ readonly heading: string | null; readonly items: ReadonlyArray<NavEntry> }> = [
  {
    heading: 'Your work',
    items: [
      { id: 'home', label: 'Home', icon: 'home' },
      { id: 'chat', label: 'Chat', icon: 'chat' },
      { id: 'documents', label: 'Documents', icon: 'document' },
      { id: 'workspaces', label: 'Workspaces', icon: 'workspace' },
    ],
  },
  {
    heading: 'Settings',
    items: [
      { id: 'memory', label: 'Memory', icon: 'memory' },
      { id: 'settings', label: 'Settings', icon: 'settings' },
    ],
  },
];

export function AppShell(): JSX.Element {
  const { account, api, signOut, withIdentityToken } = useSession();
  const [destination, setDestination] = useState<Destination>('home');
  const [workspaces, setWorkspaces] = useState<ReadonlyArray<WorkspaceRecord>>([]);
  const [workspace, setWorkspace] = useState<WorkspaceRecord | null>(null);
  const [credits, setCredits] = useState<{ remaining: number; allowance: number } | null>(null);

  const loadWorkspaces = useCallback(async (): Promise<void> => {
    const found = await VaultStore.workspaces().catch(() => []);
    setWorkspaces(found);
    setWorkspace((current) =>
      current === null ? null : found.find((item) => item.id === current.id) ?? null,
    );
  }, []);

  useEffect(() => {
    void loadWorkspaces();
  }, [loadWorkspaces]);

  const refreshCredits = useCallback(async (): Promise<void> => {
    const report = await withIdentityToken(async (token) => api.usage(token)).catch(() => null);
    if (report !== null) {
      setCredits({
        remaining: report.usage.creditsRemaining,
        allowance: report.limits.monthlyCredits,
      });
    }
  }, [api, withIdentityToken]);

  // Refreshed on every move, because a question just asked has changed the number and a stale one
  // is worse than none.
  useEffect(() => {
    void refreshCredits();
  }, [refreshCredits, destination]);

  return (
    <ChatProvider>
      <div className="shell">
        <nav className="sidebar">
          <div className="sidebar__wordmark">
            <HawkMark size={22} />
            HawkVance
          </div>

          {groups.map((group, index) => (
            <div key={group.heading ?? `group-${index}`} className="navgroup">
              {group.heading !== null && <div className="navgroup__heading">{group.heading}</div>}
              {group.items.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  className={`navitem${destination === entry.id ? ' navitem--active' : ''}`}
                  onClick={() => setDestination(entry.id)}
                  aria-current={destination === entry.id ? 'page' : undefined}
                >
                  <span className="navitem__glyph">
                    <Icon name={entry.icon} size={17} />
                  </span>
                  {entry.label}
                </button>
              ))}
            </div>
          ))}

          <div className="sidebar__footer">
            {workspace !== null && (
              <button
                type="button"
                className="sidebar__workspace sidebar__workspace--action"
                onClick={() => setDestination('workspaces')}
                title="Change workspace"
              >
                <span className="tiny">Workspace, change</span>
                <strong>{workspace.name}</strong>
              </button>
            )}
            {credits !== null && (
              <div className="credits">
                <span className="credits__label">
                  <span>Credits left</span>
                  <span>
                    {credits.remaining.toLocaleString()} of {credits.allowance.toLocaleString()}
                  </span>
                </span>
                <span className="credits__track">
                  <span
                    className={`credits__fill${
                      credits.remaining <= credits.allowance * 0.1 ? ' credits__fill--low' : ''
                    }`}
                    style={{
                      width: `${Math.max(
                        0,
                        Math.min(100, (credits.remaining / Math.max(1, credits.allowance)) * 100),
                      )}%`,
                    }}
                  />
                </span>
              </div>
            )}
            <div className="sidebar__account">{account.email}</div>
            <button type="button" className="navitem" onClick={() => void signOut()}>
              <span className="navitem__glyph">
                <Icon name="signOut" size={17} />
              </span>
              Sign out
            </button>
          </div>
        </nav>

        {/* Chat manages its own scrolling, so the shell must not add a second scroller around it.
            Set here rather than inferred with :has(), so the reason is visible where the screen is
            chosen. */}
        <main className={`main${destination === 'chat' ? ' main--flush' : ''}`}>
          {destination === 'home' && <Home onNavigate={setDestination} />}
          {destination === 'chat' && <Chat workspaces={workspaces} />}
          {destination === 'documents' && (
            <Documents workspaces={workspaces} workspace={workspace} onActivate={setWorkspace} />
          )}
          {destination === 'workspaces' && (
            <Workspaces
              workspaces={workspaces}
              active={workspace}
              onChanged={() => void loadWorkspaces()}
              onActivate={setWorkspace}
            />
          )}
          {destination === 'memory' && <MemoryBrowser workspaces={workspaces} />}
          {destination === 'settings' && <Settings />}
        </main>
      </div>
    </ChatProvider>
  );
}
