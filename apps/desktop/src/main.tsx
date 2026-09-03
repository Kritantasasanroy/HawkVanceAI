import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App.js';
import { SessionProvider } from './session/session-context.js';
import './theme.css';

const root = document.getElementById('root');
if (root === null) {
  throw new Error('the page is missing its root element');
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <SessionProvider>
      <App />
    </SessionProvider>
  </React.StrictMode>,
);
