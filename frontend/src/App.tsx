/**
 * Standalone development wrapper.
 * Only used when running `pnpm dev` locally — not included in the IIFE bundle.
 */
import './i18n';
import React from 'react';
import { DevicesPage } from './pages/DevicesPage';

export default function App() {
  return <DevicesPage />;
}
