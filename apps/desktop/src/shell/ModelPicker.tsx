import { useEffect, useRef, useState } from 'react';
import type { AvailableModel } from '../session/hawkvance-api.js';
import { Icon } from './Icon.js';

/// The model chooser, as a small button that opens a list.
///
/// It was a full-width dropdown with a label, which is a lot of permanent screen for something
/// people change rarely. This keeps the current choice readable at a glance and puts the rest of
/// the catalogue one click away, without a select element's habit of rendering eighteen rows of
/// raw model names.

export function ModelPicker({
  models,
  chosen,
  onChoose,
}: {
  readonly models: ReadonlyArray<AvailableModel>;
  readonly chosen: string;
  readonly onChoose: (id: string) => void;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  // Closes on a click anywhere else, and on Escape, which is what people expect of a popover and
  // what stops it sitting open over the conversation.
  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointer = (event: MouseEvent): void => {
      if (!container.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const current = models.find((model) => model.id === chosen);
  const capable = models.filter((model) => model.tier === 'premium' || model.tier === 'standard');
  const light = models.filter((model) => model.tier === 'economy');

  const group = (
    label: string,
    note: string,
    entries: ReadonlyArray<AvailableModel>,
  ): JSX.Element | null =>
    entries.length === 0 ? null : (
      <>
        <div className="modelmenu__group">
          <strong>{label}</strong>
          <span className="tiny muted">{note}</span>
        </div>
        {entries.map((model) => (
          <button
            key={model.id}
            type="button"
            className={`modelmenu__item${model.id === chosen ? ' modelmenu__item--chosen' : ''}`}
            onClick={() => {
              onChoose(model.id);
              setOpen(false);
            }}
          >
            <span>{model.label.replace(/\s*\(free\)\s*$/i, '')}</span>
            {model.id === chosen && <Icon name="check" size={14} />}
          </button>
        ))}
      </>
    );

  return (
    <div className="modelpicker" ref={container}>
      <button
        type="button"
        className="modelpicker__button"
        onClick={() => setOpen((current) => !current)}
        disabled={models.length === 0}
        aria-expanded={open}
        title="Choose which model answers"
      >
        <Icon name="models" size={15} />
        <span className="modelpicker__name">
          {current?.label.replace(/\s*\(free\)\s*$/i, '') ?? 'Automatic'}
        </span>
        <Icon name="chevron" size={13} />
      </button>

      {open && (
        <div className="modelmenu" role="menu">
          {group('Most capable', 'Free, like all of them', capable)}
          {group('Lightweight', 'Faster, smaller answers', light)}
        </div>
      )}
    </div>
  );
}
