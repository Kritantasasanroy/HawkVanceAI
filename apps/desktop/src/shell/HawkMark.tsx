import hawkMark from '../assets/hawk-mark.png';

/// The HawkVance mark.
///
/// The source is the real artwork at `assets/hawkvance-logo.png`, copied here for Vite to bundle.
/// The same file is what `scripts/make-icons.py` generates every installer and website icon from,
/// so the mark in the window, on the taskbar and on the download page cannot drift apart.
///
/// Black linework on transparency reads on both the dark sidebar and a light page without any
/// colour trick, which is why this stays a plain image rather than inline paths.

export function HawkMark({ size = 24 }: { size?: number }): JSX.Element {
  return <img src={hawkMark} width={size} height={size} alt="" />;
}
