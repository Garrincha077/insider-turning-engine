import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { EngineDashboard } from '@/components/engine-dashboard';
import '@/app/globals.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <EngineDashboard />
  </StrictMode>,
);
