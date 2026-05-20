import React from 'react';
import ReactDOM from 'react-dom/client';
import { MockProvider } from '@nekazari/module-kit/mock';
import Module from './Module';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MockProvider module={Module} />
  </React.StrictMode>
);
