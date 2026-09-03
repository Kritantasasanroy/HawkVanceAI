import { useCallback, useEffect, useState } from 'react';
import { LocalEngine } from '../engine/engine-bridge.js';
import type { WorkspaceRecord } from '../session/vault-store.js';
import { VaultStore } from '../session/vault-store.js';

/// Projects, kept apart.
///
/// The separation is the point rather than a convenience: a workspace's documents and memory are
/// only ever read by chats in that workspace, so work for one client cannot surface in an answer
/// about another.

export function Workspaces({
  workspaces,
  active,
  onChanged,
  onActivate,
}: {
  readonly workspaces: ReadonlyArray<WorkspaceRecord>;
  readonly active: WorkspaceRecord | null;
  readonly onChanged: () => void;
  readonly onActivate: (workspace: WorkspaceRecord | null) => void;
}): JSX.Element {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
    const read = async (): Promise<void> => {
      const entries = await Promise.all(
        workspaces.map(async (item) => {
          const documents = await VaultStore.documents(item.id).catch(() => []);
          return [item.id, documents.length] as const;
        }),
      );
      if (!cancelled) {
        setCounts(Object.fromEntries(entries));
      }
    };
    void read();
    return () => {
      cancelled = true;
    };
  }, [workspaces]);

  const create = useCallback(async (): Promise<void> => {
    const trimmed = name.trim();
    if (trimmed.length === 0) {
      return;
    }
    const now = new Date().toISOString();
    await VaultStore.saveWorkspace({
      id: crypto.randomUUID(),
      name: trimmed,
      description: description.trim(),
      createdAt: now,
      updatedAt: now,
    });
    setName('');
    setDescription('');
    onChanged();
  }, [description, name, onChanged]);

  /// Deleting takes the documents and the memory with it.
  ///
  /// Said plainly before it happens rather than discovered afterwards, because there is no undo
  /// for this and the vault is the only copy.
  const remove = useCallback(
    async (workspace: WorkspaceRecord): Promise<void> => {
      const sure = window.confirm(
        `Delete ${workspace.name}? Its documents and everything HawkVance remembers about it are deleted too, and this cannot be undone.`,
      );
      if (!sure) {
        return;
      }
      await LocalEngine.forgetWorkspace(workspace.id).catch(() => undefined);
      await VaultStore.deleteWorkspace(workspace.id);
      if (active?.id === workspace.id) {
        onActivate(null);
      }
      onChanged();
    },
    [active, onActivate, onChanged],
  );

  const rename = useCallback(
    async (workspace: WorkspaceRecord, next: string): Promise<void> => {
      const trimmed = next.trim();
      if (trimmed.length === 0) {
        return;
      }
      await VaultStore.saveWorkspace({
        ...workspace,
        name: trimmed,
        updatedAt: new Date().toISOString(),
      });
      setEditing(null);
      onChanged();
    },
    [onChanged],
  );

  return (
    <>
      <div className="main__head">
        <div>
          <h1>Workspaces</h1>
          <p className="muted" style={{ margin: '4px 0 0' }}>
            Keep separate pieces of work apart. Each one has its own documents and its own memory.
          </p>
        </div>
      </div>

      <section className="card">
        <div className="card__label">Start a new one</div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.4fr) auto',
            gap: 10,
          }}
        >
          <input
            className="input"
            placeholder="Name, such as a client or project"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <input
            className="input"
            placeholder="What it is for (optional)"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void create()}
            disabled={name.trim().length === 0}
          >
            Create
          </button>
        </div>
      </section>

      {workspaces.length === 0 ? (
        <section className="card empty" style={{ marginTop: 16 }}>
          <h2 className="empty__title">No workspaces yet</h2>
          <p className="empty__body">
            Until you make one, everything you add goes to Global memory, which every Global chat
            can read. A workspace is how you keep the files and memory for one project to itself.
          </p>
        </section>
      ) : (
        <div className="memories" style={{ marginTop: 16 }}>
          {workspaces.map((workspace) => (
            <article key={workspace.id} className="card memory">
              <div className="memory__head">
                {active?.id === workspace.id && <span className="pill pill--ok">Current</span>}
                <span className="tiny muted">
                  {counts[workspace.id] ?? 0}{' '}
                  {(counts[workspace.id] ?? 0) === 1 ? 'document' : 'documents'}
                </span>
              </div>

              {editing?.id === workspace.id ? (
                <>
                  <input
                    className="input"
                    value={editing.name}
                    onChange={(event) => setEditing({ id: workspace.id, name: event.target.value })}
                  />
                  <div className="memory__actions">
                    <button
                      type="button"
                      className="btn btn--primary"
                      onClick={() => void rename(workspace, editing.name)}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => setEditing(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="memory__content">
                    <strong>{workspace.name}</strong>
                    {workspace.description.trim().length > 0 && (
                      <>
                        <br />
                        <span className="tiny muted">{workspace.description}</span>
                      </>
                    )}
                  </p>
                  <div className="memory__actions">
                    <span className="tiny muted" style={{ marginRight: 'auto' }}>
                      started {new Date(workspace.createdAt).toLocaleDateString()}
                    </span>
                    {active?.id !== workspace.id && (
                      <button
                        type="button"
                        className="btn btn--quiet"
                        onClick={() => onActivate(workspace)}
                      >
                        Use this
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn--quiet"
                      onClick={() => setEditing({ id: workspace.id, name: workspace.name })}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      className="btn btn--quiet btn--danger"
                      onClick={() => void remove(workspace)}
                    >
                      Delete
                    </button>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      )}
    </>
  );
}
