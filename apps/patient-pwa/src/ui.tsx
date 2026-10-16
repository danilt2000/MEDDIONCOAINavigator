import arrowBackIcon from '@material-symbols/svg-400/outlined/arrow_back.svg?raw';
import callIcon from '@material-symbols/svg-400/outlined/call.svg?raw';
import refreshIcon from '@material-symbols/svg-400/outlined/refresh.svg?raw';
import { FilledButton, IconButton, OutlinedButton, SvgIcon, TextButton } from '@navigator/ui';
import { ambulancePhone, phoneDigits, useApp, type CallTarget } from './app-state';

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

export function CallNowCard() {
  const { t } = useApp();
  return (
    <section className="card card-danger">
      <h2 className="card-title">{t.callNowWhen}</h2>
      <ul className="bullets">
        <li>{t.warn1}</li>
        <li>{t.warn2}</li>
        <li>{t.warn3}</li>
        <li>{t.warn4}</li>
      </ul>
      <AmbulanceAnd155 />
    </section>
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
