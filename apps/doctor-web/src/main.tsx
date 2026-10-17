import '@navigator/ui/styles.css';
import './app.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createHashRouter, Navigate, RouterProvider } from 'react-router';
import { App } from './App';
import { DayPage, RegimenPage } from './pages/Day';
import { MonitoringPage } from './pages/Monitoring';
import { PatientDetailPage } from './pages/PatientDetail';
import { PatientsPage } from './pages/Patients';
import { PushTestPage } from './pages/PushTest';
import { QueuePage } from './pages/Queue';
import { RulesPage } from './pages/Rules';
import { SymptomPage } from './pages/Symptom';

const router = createHashRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/fronta" replace /> },
      { path: 'fronta', element: <QueuePage /> },
      { path: 'monitoring', element: <MonitoringPage /> },
      { path: 'monitoring/den/:date', element: <DayPage /> },
      { path: 'monitoring/priznak/:symptom', element: <SymptomPage /> },
      { path: 'pacienti', element: <PatientsPage /> },
      { path: 'pacienti/:id', element: <PatientDetailPage /> },
      { path: 'monitoring/lecba/:regimen', element: <RegimenPage /> },
      { path: 'pravidla', element: <RulesPage /> },
      { path: 'test-notifikace', element: <PushTestPage /> },
      { path: '*', element: <Navigate to="/fronta" replace /> },
    ],
  },
]);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
