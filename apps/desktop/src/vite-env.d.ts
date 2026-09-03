/// <reference types="vite/client" />

/// Vite rewrites an image import into a URL string at build time. Without this declaration
/// TypeScript sees an unresolvable module rather than a bundled asset.
declare module '*.png' {
  const source: string;
  export default source;
}

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_NEON_AUTH_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
