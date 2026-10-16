import type { PatientListItem } from '@navigator/api';
import { ChipSet, FilterChip, OutlinedCard, OutlinedTextField } from '@navigator/ui';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useShell } from '../App';
import { LevelChip, Load, RiskBadges } from '../components';
import { fmtDayTime, shortRegimen, TASK_STATUS, useApi } from '../lib';
import { controlled } from './Symptom';

export const DATASETS = [
  { id: 'dev', label: 'Vývojová sada' },
  { id: 'rozsirena', label: 'Rozšířená sada' },
];

export function PatientsPage() {
  const shell = useShell();
  const navigate = useNavigate();
  const [dataset, setDataset] = useState(shell.dataset);
  const [query, setQuery] = useState('');
  const patients = useApi<PatientListItem[]>(`/api/patients?dataset=${dataset}`);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Pacienti</h1>
          <p className="muted">Seřazeno podle posledního stupně</p>
        </div>
        <div className="row">
          <ChipSet>
            {DATASETS.map((item) => (
              <FilterChip key={item.id} label={item.label} selected={dataset === item.id} onClick={controlled(() => setDataset(item.id))} />
            ))}
          </ChipSet>
          <OutlinedTextField
            className="search"
            type="search"
            label="Hledat jméno, ID, léčbu"
            value={query}
            onInput={(event) => setQuery((event.target as HTMLInputElement).value)}
          />
        </div>
      </div>
      <Load source={patients} isEmpty={(items) => items.length === 0} emptyText="Žádní pacienti v této sadě.">
        {(items) => {
          const needle = query.trim().toLowerCase();
          const visible = items
            .filter((item) => !needle || `${item.name} ${item.patient_id} ${item.regimen} ${item.diagnosis}`.toLowerCase().includes(needle))
            .sort((left, right) => (right.last_level ?? 0) - (left.last_level ?? 0) || left.patient_id.localeCompare(right.patient_id));
          return (
            <OutlinedCard className="card flush">
              <table className="table">
                <thead>
                  <tr>
                    <th>Pacient</th>
                    <th>Diagnóza</th>
                    <th>Léčba · den cyklu</th>
                    <th>Riziko</th>
                    <th>Poslední stupeň</th>
                    <th>Poslední check-in</th>
                    <th>Úkol</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((item) => (
                    <tr key={item.patient_id} className="clickable" onClick={() => navigate(`/pacienti/${encodeURIComponent(item.patient_id)}`)}>
                      <th scope="row">
                        <Link to={`/pacienti/${encodeURIComponent(item.patient_id)}`}>
                          {item.name}, {item.age}
                        </Link>
                        <div className="muted small">
                          {item.patient_id}
                          {item.filled_by && item.filled_by !== 'pacient' && ` · vyplňuje ${item.filled_by}`}
                          {item.lang === 'sk' && ' · slovensky'}
                        </div>
                      </th>
                      <td className="ellipsis-cell" title={item.diagnosis}>
                        {item.diagnosis}
                      </td>
                      <td>
                        {shortRegimen(item.regimen)}
                        {item.cycle != null && <span className="muted"> · C{item.cycle}</span>}
                        {item.cycle_day != null && <span className="muted"> D{item.cycle_day}</span>}
                      </td>
                      <td>
                        <RiskBadges badges={item.risk_badges} />
                      </td>
                      <td>
                        <LevelChip level={item.last_level} />
                      </td>
                      <td>{item.last_checkin_at ? fmtDayTime(item.last_checkin_at) : '—'}</td>
                      <td>
                        {item.open_task ? (
                          <span className="status-pill" data-status={item.open_task.status}>
                            {TASK_STATUS[item.open_task.status] ?? item.open_task.status}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </OutlinedCard>
          );
        }}
      </Load>
    </div>
  );
}
