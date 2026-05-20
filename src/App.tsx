import React, { Suspense } from 'react';
import { NKZProvider } from '@nekazari/module-kit';
import { DevicesPage } from './pages/DevicesPage';
import './i18n';

export default function App() {
  return (
    <NKZProvider>
      <Suspense fallback={<div>Loading...</div>}>
        <DevicesPage />
      </Suspense>
    </NKZProvider>
  );
}
