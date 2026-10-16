import callIcon from '@material-symbols/svg-400/outlined/call.svg?raw';
import checkCircleIcon from '@material-symbols/svg-400/outlined/check_circle.svg?raw';
import emergencyIcon from '@material-symbols/svg-400/outlined/emergency.svg?raw';
import infoIcon from '@material-symbols/svg-400/outlined/info.svg?raw';
import { SvgIcon } from './SvgIcon';

export type TriageLevel = 1 | 2 | 3 | 4;

export const TRIAGE_LEVELS: Record<TriageLevel, { icon: string; cs: string; sk: string; stepCs: string; stepSk: string }> = {
  1: { icon: checkCircleIcon, cs: 'Zelená', sk: 'Zelená', stepCs: 'Další sledování', stepSk: 'Ďalšie sledovanie' },
  2: { icon: infoIcon, cs: 'Žlutá', sk: 'Žltá', stepCs: 'Ozve se tým', stepSk: 'Ozve sa tím' },
  3: { icon: callIcon, cs: 'Oranžová', sk: 'Oranžová', stepCs: 'Telekonzultace dnes', stepSk: 'Telekonzultácia dnes' },
  4: { icon: emergencyIcon, cs: 'Červená', sk: 'Červená', stepCs: 'Volejte ihned', stepSk: 'Volajte ihneď' },
};

export function TriageChip({
  level,
  lang = 'cs',
  withStep = false,
}: {
  level: TriageLevel;
  lang?: 'cs' | 'sk';
  withStep?: boolean;
}) {
  const meta = TRIAGE_LEVELS[level];
  const label = lang === 'sk' ? meta.sk : meta.cs;
  const step = lang === 'sk' ? meta.stepSk : meta.stepCs;
  return (
    <span className="triage-chip" data-level={level}>
      <SvgIcon svg={meta.icon} />
      {withStep ? `${label} · ${step}` : label}
    </span>
  );
}
