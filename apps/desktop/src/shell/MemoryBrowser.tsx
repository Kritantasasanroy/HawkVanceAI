import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Memory } from '../engine/engine-bridge.js';
import { LocalEngine } from '../engine/engine-bridge.js';
import type { WorkspaceRecord } from '../session/vault-store.js';

/// What HawkVance has learned, and the controls to change or delete any of it.
///
/// Deliberately plain. An earlier version showed storage tiers and confidence percentages, which
/// describe how the engine files things internally and mean nothing to the person reading them.
/// What somebody actually needs here is: what does it think it knows, and how do I remove that.

export function MemoryBrowser({
  workspaces,
}: {
  readonly workspaces: ReadonlyArray<WorkspaceRecord>;
}): JSX.Element {
  const [memories, setMemories] = useState<ReadonlyArray<Memory>>([]);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<{ id: string; content: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (): Promise<void> => {
    const found = await LocalEngine.searchMemories('', 200).catch(() => []);
    setMemories(found);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (needle.length === 0) {
      return memories;
    }
    return memories.filter((item) => item.content.toLowerCase().includes(needle));
  }, [memories, search]);

  /// Grouped by where it belongs, because that is the boundary that decides which chats can see it.
  const sections = useMemo(() => {
    const byPlace = new Map<string | null, Memory[]>();
    for (const item of visible) {
      const list = byPlace.get(item.workspaceId) ?? [];
      list.push(item);
      byPlace.set(item.workspaceId, list);
    }
    return [...byPlace.entries()].map(([workspaceId, items]) => ({
      key: workspaceId ?? 'global',
      title:
        workspaceId === null
          ? 'Global memory'
          : workspaces.find((item) => item.id === workspaceId)?.name ?? 'A deleted workspace',
      note:
        workspaceId === null
          ? 'A general picture of your work. Every Global chat can read these.'
          : 'Only chats in this workspace read these.',
      items,
    }));
  }, [visible, workspaces]);

  return (
    <>
      <div className="main__head">
        <div>
          <h1>Memory</h1>
          <p className="muted" style={{ margin: '4px 0 0' }}>
            What HawkVance has learned, and anything you want removed. All of it stays on this
            computer.
          </p>
        </div>
      </div>

      <section className="card">
        <div className="card__label">Find something</div>
        <input
          className="input"
          placeholder="Search what HawkVance remembers"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </section>

      {loading ? (
        <p className="muted" style={{ marginTop: 16 }}>
          Reading what is remembered…
        </p>
      ) : visible.length === 0 ? (
        <section className="card empty" style={{ marginTop: 16 }}>
          <h2 className="empty__title">
            {memories.length === 0 ? 'Nothing remembered yet' : 'Nothing matches that'}
          </h2>
          <p className="empty__body">
            {memories.length === 0
              ? 'Add a document or have a conversation, and what HawkVance learns will appear here for you to keep or delete.'
              : 'No memory matches what you searched for.'}
          </p>
        </section>
      ) : (
        <div style={{ marginTop: 16 }}>
          {sections.map((section) => (
            <div key={section.key} className="memorysection">
              <div className="memorysection__head">
                <div>
                  <h2 className="memorysection__title">{section.title}</h2>
                  <p className="tiny muted" style={{ margin: 0 }}>
                    {section.note}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn--quiet btn--danger"
                  onClick={() => {
                    const sure = window.confirm(
                      `Forget everything under ${section.title}? This cannot be undone.`,
                    );
                    if (!sure) {
                      return;
                    }
                    void Promise.all(
                      section.items.map((item) => LocalEngine.forget(item.id)),
                    ).then(refresh);
                  }}
                >
                  Forget all {section.items.length}
                </button>
              </div>

              <div className="memories">
                {section.items.map((item) => (
                  <article key={item.id} className="card memory">
                    <div className="memory__head">
                      {item.pinned && <span className="pill pill--ok">Kept</span>}
                      {item.observationCount > 1 && (
                        <span className="tiny muted">Seen {item.observationCount} times</span>
                      )}
                    </div>

                    {editing?.id === item.id ? (
                      <>
                        <textarea
                          className="input"
                          style={{ height: 80, padding: 10 }}
                          value={editing.content}
                          onChange={(event) =>
                            setEditing({ id: item.id, content: event.target.value })
                          }
                        />
                        <div className="memory__actions">
                          <button
                            type="button"
                            className="btn btn--primary"
                            onClick={() => {
                              void LocalEngine.editMemory(item.id, editing.content)
                                .then(() => setEditing(null))
                                .then(refresh);
                            }}
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
                        <p className="memory__content">{item.content}</p>
                        <div className="memory__actions">
                          <span className="tiny muted" style={{ marginRight: 'auto' }}>
                            {item.source || 'no source recorded'}
                          </span>
                          <button
                            type="button"
                            className="btn btn--quiet"
                            onClick={() => {
                              void LocalEngine.pinMemory(item.id, !item.pinned).then(refresh);
                            }}
                          >
                            {item.pinned ? 'Unpin' : 'Pin'}
                          </button>
                          <button
                            type="button"
                            className="btn btn--quiet"
                            onClick={() => setEditing({ id: item.id, content: item.content })}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="btn btn--quiet btn--danger"
                            onClick={() => {
                              void LocalEngine.forget(item.id).then(refresh);
                            }}
                          >
                            Forget
                          </button>
                        </div>
                      </>
                    )}
                  </article>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
