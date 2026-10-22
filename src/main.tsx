import React from 'react';
import ReactDOM from 'react-dom/client';
import { MockProvider } from '@nekazari/module-kit/mock';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MockProvider>
      <App />
    </MockProvider>
  </React.StrictMode>
);
