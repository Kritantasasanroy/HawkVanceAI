import { useMemo } from 'react';

/// Lets somebody point at a word in their own document and say "hide that one".
///
/// The text shown is the *sanitised* text, never the original. That is deliberate: this component
/// puts document content on screen, so it must only ever be handed content that is already safe to
/// have left the machine. Anything the detectors caught is already a placeholder here, which also
/// makes the remaining plain words exactly the ones worth reviewing.
///
/// Selection is by word rather than by free typing because the point is to catch what the
/// detectors missed, and a person spots that by reading, not by remembering.

const PLACEHOLDER = /^\[[A-Z][A-Z0-9_]*\]$/;

type Token = { readonly text: string; readonly kind: 'word' | 'space' | 'placeholder' };

function tokenise(text: string): ReadonlyArray<Token> {
  // Split on whitespace but keep it, so the preview still reads like the document.
  return text.split(/(\s+)/).map((piece) => {
    if (piece.length === 0 || /^\s+$/.test(piece)) {
      return { text: piece, kind: 'space' as const };
    }
    return { text: piece, kind: PLACEHOLDER.test(piece) ? 'placeholder' : 'word' };
  });
}

/// Punctuation is stripped for matching so clicking "Falcon." protects "Falcon", which is what the
/// person meant and what will match elsewhere in the document.
export function bareWord(raw: string): string {
  return raw.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
}

export function WordPicker({
  text,
  protectedTerms,
  onToggle,
  limit = 4000,
}: {
  readonly text: string;
  readonly protectedTerms: ReadonlyArray<string>;
  readonly onToggle: (word: string) => void;
  readonly limit?: number;
}): JSX.Element {
  const tokens = useMemo(() => tokenise(text.slice(0, limit)), [text, limit]);
  const protectedSet = useMemo(
    () => new Set(protectedTerms.map((term) => term.toLowerCase())),
    [protectedTerms],
  );

  return (
    <div className="picker">
      <p className="picker__hint tiny">Click any word to hide it. Grey blocks are already hidden.</p>
      <div className="picker__body">
        {tokens.map((token, index) => {
          if (token.kind === 'space') {
            return <span key={index}>{token.text}</span>;
          }
          if (token.kind === 'placeholder') {
            return (
              <span key={index} className="picker__hidden" title="Already hidden">
                {token.text}
              </span>
            );
          }

          const bare = bareWord(token.text);
          if (bare.length === 0) {
            return <span key={index}>{token.text}</span>;
          }
          const chosen = protectedSet.has(bare.toLowerCase());

          return (
            <button
              key={index}
              type="button"
              className={`picker__word${chosen ? ' picker__word--chosen' : ''}`}
              onClick={() => onToggle(bare)}
              aria-pressed={chosen}
              title={chosen ? `${bare} will be hidden` : `Hide ${bare}`}
            >
              {token.text}
            </button>
          );
        })}
        {text.length > limit && <span className="muted"> …</span>}
      </div>
    </div>
  );
}
