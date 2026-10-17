import arrowBackIcon from '@material-symbols/svg-400/outlined/arrow_back.svg?raw';
import callIcon from '@material-symbols/svg-400/outlined/call.svg?raw';
import chatIcon from '@material-symbols/svg-400/rounded/chat-fill.svg?raw';
import refreshIcon from '@material-symbols/svg-400/outlined/refresh.svg?raw';
import { Dialog, FilledButton, IconButton, OutlinedButton, OutlinedIconButton, SvgIcon, TextButton } from '@navigator/ui';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { ambulancePhone, phoneDigits, useApp, type CallTarget } from './app-state';

export function AiFab({ size = 'medium', intro }: { size?: 'small' | 'medium'; intro?: string }) {
  const { t, patientId } = useApp();
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className="ai-fab"
      data-size={size}
      data-glow={intro ? '' : undefined}
      aria-label={t.writeNavigator}
      title={t.writeNavigator}
      onClick={() => navigate('/navigator', intro ? { state: { intro, patientId } } : undefined)}
    >
      <SvgIcon svg={chatIcon} />
      <span className="ai-badge" aria-hidden="true">
        AI
      </span>
    </button>
  );
}

export function CallButton({ target }: { target: CallTarget }) {
  const ems = phoneDigits(target.tel).length <= 3;
  const Button = target.strong ? FilledButton : OutlinedButton;
  return (
    <Button className={ems ? 'danger' : undefined} href={`tel:${phoneDigits(target.tel)}`}>
      <SvgIcon slot="icon" svg={callIcon} />
      {target.label}
    </Button>
  );
}

export function CallButtons({ targets }: { targets: CallTarget[] }) {
  return (
    <div className="stack">
      {targets.map((target) => (
        <CallButton key={target.tel + target.label} target={target} />
      ))}
    </div>
  );
}

export function AmbulanceAnd155() {
  const { t, now, contacts } = useApp();
  return (
    <div className="row">
      <OutlinedButton className="danger" href={`tel:${phoneDigits(ambulancePhone(now, contacts))}`}>
        <SvgIcon slot="icon" svg={callIcon} />
        {t.ambulance}
      </OutlinedButton>
      <FilledButton className="danger" href={`tel:${contacts?.ems.phone || '155'}`}>
        <SvgIcon slot="icon" svg={callIcon} />
        155
      </FilledButton>
    </div>
  );
}

function WarningSigns() {
  const { t } = useApp();
  return (
    <ul className="bullets">
      <li>{t.warn1}</li>
      <li>{t.warn2}</li>
      <li>{t.warn3}</li>
      <li>{t.warn4}</li>
    </ul>
  );
}

export function CallNowCard() {
  const { t } = useApp();
  return (
    <section className="card card-danger">
      <h2 className="card-title">{t.callNowWhen}</h2>
      <WarningSigns />
      <AmbulanceAnd155 />
    </section>
  );
}

export function AcuteButton() {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  return (
    <>
      <OutlinedIconButton className="acute-button" aria-label={t.acuteTitle} title={t.acuteTitle} onClick={() => setOpen(true)}>
        <SvgIcon svg={callIcon} />
      </OutlinedIconButton>
      <Dialog open={open} onClosed={() => setOpen(false)}>
        <div slot="headline">{t.acuteTitle}</div>
        <div slot="content" className="stack">
          <p className="strong">{t.callNowWhen}</p>
          <WarningSigns />
          <AmbulanceAnd155 />
        </div>
        <div slot="actions">
          <TextButton onClick={() => setOpen(false)}>{t.close}</TextButton>
        </div>
      </Dialog>
    </>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useApp();
  return (
    <div className="banner" role="alert">
      <span>{message}</span>
      {onRetry && (
        <TextButton onClick={onRetry}>
          <SvgIcon slot="icon" svg={refreshIcon} />
          {t.retry}
        </TextButton>
      )}
    </div>
  );
}

export function BackButton({ onClick }: { onClick: () => void }) {
  const { t } = useApp();
  return (
    <IconButton aria-label={t.back} onClick={onClick}>
      <SvgIcon svg={arrowBackIcon} />
    </IconButton>
  );
}
