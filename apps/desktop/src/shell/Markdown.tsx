import type { JSX, ReactNode } from 'react';

/// Renders an answer's markdown.
///
/// Produces React elements, never an HTML string, so there is no `dangerouslySetInnerHTML`
/// anywhere in the path. That matters more here than in most places: this is model output being
/// put on screen, and a model can be talked into emitting markup. By construction nothing here can
/// inject an element that this file does not itself create.
///
/// Anything it does not understand renders as literal text rather than being dropped, so a person
/// never silently loses part of an answer.

type Block =
  | { readonly kind: 'heading'; readonly level: 2 | 3 | 4; readonly text: string }
  | { readonly kind: 'paragraph'; readonly text: string }
  | { readonly kind: 'list'; readonly ordered: boolean; readonly items: ReadonlyArray<string> }
  | { readonly kind: 'code'; readonly text: string };

function parse(source: string): ReadonlyArray<Block> {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, '\n').split('\n');

  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? '';

    if (line.trim().startsWith('```')) {
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? '').trim().startsWith('```')) {
        body.push(lines[index] ?? '');
        index += 1;
      }
      index += 1;
      blocks.push({ kind: 'code', text: body.join('\n') });
      continue;
    }

    const heading = /^(#{2,4})\s+(.*)$/.exec(line);
    if (heading !== null) {
      const level = heading[1]?.length === 2 ? 2 : heading[1]?.length === 3 ? 3 : 4;
      blocks.push({ kind: 'heading', level, text: heading[2] ?? '' });
      index += 1;
      continue;
    }

    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (bullet !== null || numbered !== null) {
      const ordered = numbered !== null;
      const items: string[] = [];
      while (index < lines.length) {
        const candidate = lines[index] ?? '';
        const match = ordered
          ? /^\s*\d+[.)]\s+(.*)$/.exec(candidate)
          : /^\s*[-*]\s+(.*)$/.exec(candidate);
        if (match === null) {
          break;
        }
        items.push(match[1] ?? '');
        index += 1;
      }
      blocks.push({ kind: 'list', ordered, items });
      continue;
    }

    if (line.trim() === '') {
      index += 1;
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && (lines[index] ?? '').trim() !== '') {
      const candidate = lines[index] ?? '';
      if (/^(#{2,4})\s+/.test(candidate) || /^\s*([-*]|\d+[.)])\s+/.test(candidate)) {
        break;
      }
      paragraph.push(candidate);
      index += 1;
    }
    blocks.push({ kind: 'paragraph', text: paragraph.join(' ') });
  }

  return blocks;
}

/// Bold, italic and inline code, as elements.
function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_|`[^`]+`)/g;
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(pattern)) {
    const at = match.index ?? 0;
    if (at > cursor) {
      nodes.push(text.slice(cursor, at));
    }
    const token = match[0];
    if (token.startsWith('**') || token.startsWith('__')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('`')) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    key += 1;
    cursor = at + token.length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
}

export function Markdown({ source }: { readonly source: string }): JSX.Element {
  const blocks = parse(source);

  return (
    <div className="md">
      {blocks.map((block, index) => {
        if (block.kind === 'code') {
          return (
            <pre key={index}>
              <code>{block.text}</code>
            </pre>
          );
        }
        if (block.kind === 'heading') {
          const Tag = (['h2', 'h3', 'h4'] as const)[block.level - 2] ?? 'h4';
          return <Tag key={index}>{inline(block.text)}</Tag>;
        }
        if (block.kind === 'list') {
          const items = block.items.map((item, at) => <li key={at}>{inline(item)}</li>);
          return block.ordered ? <ol key={index}>{items}</ol> : <ul key={index}>{items}</ul>;
        }
        return <p key={index}>{inline(block.text)}</p>;
      })}
    </div>
  );
}
