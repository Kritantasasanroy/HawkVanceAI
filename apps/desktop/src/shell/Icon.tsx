/// The app's icons, drawn rather than typed.
///
/// Emoji were a mistake here for three reasons: they render as a different picture on every
/// platform and font, they carry colour that fights whatever palette the app is using, and they
/// look like a placeholder in a product people are being asked to trust with private documents.
/// These are inline paths, so they inherit the surrounding colour, stay sharp at any size, and
/// need no network request, which matters for an app that must work offline.
///
/// Every icon sits beside a text label, so all of them are hidden from screen readers.

export type IconName =
  | 'home'
  | 'chat'
  | 'document'
  | 'workspace'
  | 'memory'
  | 'privacy'
  | 'models'
  | 'settings'
  | 'signOut'
  | 'plus'
  | 'trash'
  | 'send'
  | 'globe'
  | 'check'
  | 'chevron'
  | 'arrowLeft'
  | 'edit'
  | 'pin';

const paths: Record<IconName, string> = {
  home: 'M3 10.2 12 3l9 7.2V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  chat: 'M21 12a8 8 0 0 1-8 8H7l-4 3v-5.6A8 8 0 0 1 13 4a8 8 0 0 1 8 8z',
  document: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h4',
  workspace: 'M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  memory:
    'M12 4a4 4 0 0 0-4 4 3 3 0 0 0-1 5.8V16a3 3 0 0 0 5 2.2 3 3 0 0 0 5-2.2v-2.2A3 3 0 0 0 16 8a4 4 0 0 0-4-4zM12 4v15',
  privacy: 'M6 10V8a6 6 0 1 1 12 0v2M5 10h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z',
  models: 'M13 2 4 14h6l-1 8 9-12h-6z',
  settings:
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 9 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.6 9a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z',
  signOut: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  plus: 'M12 5v14M5 12h14',
  trash: 'M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6M10 11v6M14 11v6',
  send: 'M22 2 11 13M22 2l-7 20-4-9-9-4z',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z',
  check: 'M20 6 9 17l-5-5',
  chevron: 'm6 9 6 6 6-6',
  // Points at the edge it would fold the panel towards. Rotated by CSS for the other direction,
  // so open and closed are the same shape turned around rather than two pictures to learn.
  arrowLeft: 'M19 12H5M11 6l-6 6 6 6',
  edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z',
  pin: 'M12 17v5M9 3h6l-1 6 3 3v2H7v-2l3-3z',
};

export function Icon({
  name,
  size = 18,
  className,
}: {
  readonly name: IconName;
  readonly size?: number;
  readonly className?: string;
}): JSX.Element {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
    >
      <path d={paths[name]} />
    </svg>
  );
}
