import assignmentIcon from '@material-symbols/svg-400/outlined/assignment.svg?raw';
import forumIcon from '@material-symbols/svg-400/outlined/forum.svg?raw';
import historyIcon from '@material-symbols/svg-400/outlined/history.svg?raw';
import homeIcon from '@material-symbols/svg-400/outlined/home.svg?raw';
import wifiOffIcon from '@material-symbols/svg-400/outlined/wifi_off.svg?raw';
import { NavigationBar, NavigationTab, SvgIcon } from '@navigator/ui';
import { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router';
import { AppProvider, formatDayTime, useApp } from './app-state';
import { format } from './i18n';
import { Checkin } from './screens/Checkin';
import { History } from './screens/History';
import { Home } from './screens/Home';
import { Navigator } from './screens/Navigator';
import { Result } from './screens/Result';

const TABS = [
  { path: '/', icon: homeIcon, label: 'navHome' },
  { path: '/checkin', icon: assignmentIcon, label: 'navCheckin' },
  { path: '/navigator', icon: forumIcon, label: 'navChat' },
  { path: '/historie', icon: historyIcon, label: 'navHistory' },
] as const;

function DemoBar() {
  const { t, patients, patientId, setPatientId, now, locale, online, queued, demo } = useApp();
  return (
    <div className="demo-bar">
      <span className="demo-tag">{t.demo}</span>
      <select aria-label={t.demoPatient} value={patientId} onChange={(event) => setPatientId(event.target.value)}>
        {!patients.some((patient) => patient.patient_id === patientId) && <option value={patientId}>{patientId}</option>}
        {patients.map((patient) => (
          <option key={patient.patient_id} value={patient.patient_id}>
            {patient.patient_id} · {patient.name}
          </option>
        ))}
      </select>
      {demo && <span>{formatDayTime(now, locale)}</span>}
      {!online && (
        <span className="offline-chip">
          <SvgIcon svg={wifiOffIcon} />
          {t.offline}
        </span>
      )}
      {queued > 0 && <span>{format(t.queued, queued)}</span>}
    </div>
  );
}

function Shell() {
  const { t, lang, patientId } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  useEffect(() => {
    scrollTo(0, 0);
  }, [location.pathname]);
  const tabIndex = TABS.findIndex((tab) => tab.path === location.pathname);
  const showNav = tabIndex !== -1 && location.pathname !== '/checkin';

  return (
    <div className="app">
      <DemoBar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/checkin" element={<Checkin key={patientId} />} />
        <Route path="/vysledek" element={<Result />} />
        <Route path="/navigator" element={<Navigator key={patientId} />} />
        <Route path="/historie" element={<History />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {showNav && (
        <NavigationBar
          activeIndex={tabIndex}
          onActivated={(event) => {
            const tab = TABS[event.detail.activeIndex];
            if (tab.path !== location.pathname) navigate(tab.path);
          }}
        >
          {TABS.map((tab) => (
            <NavigationTab key={tab.path} label={t[tab.label]}>
              <SvgIcon slot="active-icon" svg={tab.icon} />
              <SvgIcon slot="inactive-icon" svg={tab.icon} />
            </NavigationTab>
          ))}
        </NavigationBar>
      )}
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Shell />
      </AppProvider>
    </BrowserRouter>
  );
}
