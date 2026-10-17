import '@navigator/ui/styles.css';
import './app.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createHashRouter, Navigate, RouterProvider, useLocation } from 'react-router';
import { App } from './App';
import { DayPage, RegimenPage } from './pages/Day';
import { IrisPage } from './pages/Iris';
import { MonitoringPage } from './pages/Monitoring';
import { NotificationLogPage, NotificationRulesPage, NotificationsPage } from './pages/Notifications';
import { PatientDetailPage } from './pages/PatientDetail';
import { PatientsPage } from './pages/Patients';
import { PushTestPage } from './pages/PushTest';
import { QueuePage } from './pages/Queue';
import { RulesPage } from './pages/Rules';
import { SymptomPage } from './pages/Symptom';

function KeepQueryRedirect({ to }: { to: string }) {
  return <Navigate to={{ pathname: to, search: useLocation().search }} replace />;
}

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
      {
        path: 'notifikace',
        element: <NotificationsPage />,
        children: [
          { index: true, element: <PushTestPage /> },
          { path: 'pravidla', element: <NotificationRulesPage /> },
          { path: 'historie', element: <NotificationLogPage /> },
        ],
      },
      { path: 'test-notifikace', element: <KeepQueryRedirect to="/notifikace" /> },
      { path: 'iris', element: <Navigate to="/iris/prehled" replace /> },
      { path: 'iris/:tab', element: <IrisPage /> },
      { path: '*', element: <Navigate to="/fronta" replace /> },
    ],
  },
]);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
