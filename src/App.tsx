/**
 * Main page of the Device Management module — lazily loaded as `main` by
 * Module.tsx. Also rendered standalone by `pnpm dev` via src/main.tsx.
 */
import React from 'react';
import './index.css';
import { DevicesPage } from './pages/DevicesPage';

const App: React.FC = () => (
  <div className="w-full p-nkz-section">
    <DevicesPage />
  </div>
);

export default App;
