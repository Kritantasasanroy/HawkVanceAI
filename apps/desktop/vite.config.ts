import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/// Vite is only ever building for the Tauri webview here, never for a browser tab.
///
/// That is why the dev server binds a fixed port and refuses to hop to another one: the Rust side
/// is told a single address at build time, so a silently moved port would look like the app failing
/// to start rather than the server having relocated.
export default defineConfig({
  plugins: [react()],
  // TAURI_ is allowed through alongside VITE_ because the CLI sets the target triple and platform
  // in the environment, and the renderer occasionally needs to know which it is running on.
  envPrefix: ['VITE_', 'TAURI_'],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  build: {
    // WebView2 ships with a current Chromium, so there is nothing to gain from transpiling down.
    target: 'chrome110',
    sourcemap: true,
  },
});
