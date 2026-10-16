import calendarIcon from '@material-symbols/svg-400/outlined/calendar_month.svg?raw';
import chatIcon from '@material-symbols/svg-400/outlined/chat.svg?raw';
import homeIcon from '@material-symbols/svg-400/outlined/home.svg?raw';
import { ElevatedCard, FilledButton, NavigationBar, NavigationTab, SvgIcon } from '@navigator/ui';
import { useState } from 'react';

const tabs = [
  { label: 'Home', icon: homeIcon },
  { label: 'Treatment', icon: calendarIcon },
  { label: 'Messages', icon: chatIcon },
];

export function App() {
  const [activeIndex, setActiveIndex] = useState(0);

  return (
    <>
      <header className="top-app-bar md-typescale-title-large">Onco Navigator</header>
      <main className="content">
        <ElevatedCard className="card">
          <h2 className="md-typescale-title-medium">{tabs[activeIndex].label}</h2>
          <p className="md-typescale-body-medium">Placeholder screen.</p>
          <FilledButton>Get started</FilledButton>
        </ElevatedCard>
      </main>
      <NavigationBar activeIndex={activeIndex} onActivated={(event) => setActiveIndex(event.detail.activeIndex)}>
        {tabs.map((tab) => (
          <NavigationTab key={tab.label} label={tab.label}>
            <SvgIcon slot="active-icon" svg={tab.icon} />
            <SvgIcon slot="inactive-icon" svg={tab.icon} />
          </NavigationTab>
        ))}
      </NavigationBar>
    </>
  );
}
