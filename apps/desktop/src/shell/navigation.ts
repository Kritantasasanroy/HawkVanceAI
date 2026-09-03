/// Where the shell can go.
///
/// A named union rather than free strings, so a typo in a navigation call is a build error rather
/// than a button that quietly does nothing.
export type Destination =
  | 'home'
  | 'chat'
  | 'documents'
  | 'workspaces'
  | 'memory'
  | 'settings';
