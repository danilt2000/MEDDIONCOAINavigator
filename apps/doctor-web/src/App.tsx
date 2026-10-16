import calendarIcon from '@material-symbols/svg-400/outlined/calendar_month.svg?raw';
import dashboardIcon from '@material-symbols/svg-400/outlined/dashboard.svg?raw';
import groupIcon from '@material-symbols/svg-400/outlined/group.svg?raw';
import searchIcon from '@material-symbols/svg-400/outlined/search.svg?raw';
import { List, ListItem, OutlinedCard, OutlinedTextField, SvgIcon } from '@navigator/ui';
import { useState } from 'react';

const sections = [
  { label: 'Dashboard', icon: dashboardIcon },
  { label: 'Patients', icon: groupIcon },
  { label: 'Schedule', icon: calendarIcon },
];

export function App() {
  const [activeSection, setActiveSection] = useState(sections[0].label);

  return (
    <div className="layout">
      <nav className="sidebar">
        <h1 className="brand md-typescale-title-large">Onco Navigator</h1>
        <List>
          {sections.map((section) => (
            <ListItem
              key={section.label}
              type="button"
              className={section.label === activeSection ? 'active' : undefined}
              onClick={() => setActiveSection(section.label)}
            >
              <SvgIcon slot="start" svg={section.icon} />
              {section.label}
            </ListItem>
          ))}
        </List>
      </nav>
      <main className="main">
        <header className="toolbar">
          <h2 className="md-typescale-headline-small">{activeSection}</h2>
          <OutlinedTextField label="Search patients" type="search">
            <SvgIcon slot="leading-icon" svg={searchIcon} />
          </OutlinedTextField>
        </header>
        <OutlinedCard className="panel">
          <p className="md-typescale-body-large">Placeholder: {activeSection} view.</p>
        </OutlinedCard>
      </main>
    </div>
  );
}
