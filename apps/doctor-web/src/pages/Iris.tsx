import {
  ApiError,
  api,
  type IrisMessage,
  type IrisMessageDetail,
  type IrisOverview,
  type IrisQuery,
  type IrisQueryResult,
  type IrisResourcePage,
  type IrisValue,
} from '@navigator/api';
import { FilledButton, OutlinedButton, OutlinedCard, SvgIcon } from '@navigator/ui';
import { useState } from 'react';
import { Link, Navigate, NavLink, useParams, useSearchParams } from 'react-router';
import { Kpi, Load } from '../components';
import { playIcon, warningIcon } from '../icons';
import { errorText, fmtDayTime, useApi } from '../lib';

const TABS = [
  ['prehled', 'Přehled'],
  ['sql', 'SQL'],
  ['fhir', 'FHIR'],
  ['produkce', 'Produkce'],
  ['odkazy', 'Odkazy'],
] as const;

const IRIS_DOWN = 'IRIS for Health teď není dostupná. Bez spuštěného kontejneru IRIS (lokální vývoj) je to v pořádku, na serveru to zkuste za chvíli znovu.';
const UNAVAILABLE = errorText(new ApiError(503, ''));
const CELL_LIMIT = 120;
const PORTAL = location.hostname === 'localhost' ? 'http://localhost:52773' : '';
const PORTAL_LINKS: [string, string, string][] = [
  ['Management Portal', '/csp/sys/UtilHome.csp', 'úvodní stránka portálu'],
  ['SQL explorer', '/csp/sys/exp/%25CSP.UI.Portal.SQL.Home.zen?$NAMESPACE=FHIRSERVER', 'libovolné SQL nad namespace FHIRSERVER'],
  ['FHIR management', '/csp/fhir-management/index.html', 'FHIR server, endpoint /fhir/r4 a FHIR SQL Builder'],
  ['Konfigurace produkce', '/csp/healthshare/fhirserver/EnsPortal.ProductionConfig.zen?PRODUCTION=MEDDI.Production', 'MEDDI.Production: služby, procesy a operace'],
  ['Message Viewer', '/csp/healthshare/fhirserver/EnsPortal.MessageViewer.zen', 'zprávy produkce a jejich vizuální trasa'],
];
const secondsFormat = new Intl.DateTimeFormat('cs-CZ', {
  timeZone: 'Europe/Prague',
  day: 'numeric',
  month: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

function irisError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 503) return IRIS_DOWN;
    try {
      const { detail } = JSON.parse(error.message);
      if (typeof detail === 'string') return detail;
    } catch {
      /* not a FastAPI error body */
    }
  }
  return errorText(error);
}

function useIris<T>(path: string | null) {
  const source = useApi<T>(path);
  return source.error === UNAVAILABLE ? { ...source, error: IRIS_DOWN } : source;
}

function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

const rowsText = (count: number) => `${count} ${count === 1 ? 'řádek' : count >= 2 && count <= 4 ? 'řádky' : 'řádků'}`;
const search = (values: Record<string, string | number | null>) =>
  `?${new URLSearchParams(Object.entries(values).filter((entry): entry is [string, string | number] => entry[1] !== null).map(([key, value]) => [key, String(value)]))}`;

export function IrisPage() {
  const { tab } = useParams();
  if (!TABS.some(([path]) => path === tab)) return <Navigate to="/iris/prehled" replace />;
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>InterSystems IRIS for Health</h1>
          <p className="muted">Pohled do úložiště, se kterým demo pracuje. Jen pro čtení: server spouští pouze předem připravené dotazy.</p>
        </div>
      </div>
      <nav className="subtabs" aria-label="Části IRIS">
        {TABS.map(([path, label]) => (
          <NavLink key={path} to={`/iris/${path}`}>
            {label}
          </NavLink>
        ))}
      </nav>
      {tab === 'prehled' && <OverviewTab />}
      {tab === 'sql' && <SqlTab />}
      {tab === 'fhir' && <FhirTab />}
      {tab === 'produkce' && <ProductionTab />}
      {tab === 'odkazy' && <LinksTab />}
    </div>
  );
}

function OverviewTab() {
  const overview = useIris<IrisOverview>('/api/iris/overview');
  return (
    <Load source={overview}>
      {(data) => {
        const production = data.production;
        return (
          <>
            <div className="kpi-row">
              <Kpi label="Namespace" value={data.namespace} />
              <Kpi
                label="FHIR zdroje"
                value={data.fhir.reduce((sum, row) => sum + row.count, 0).toLocaleString('cs-CZ')}
                hint={`${data.fhir.length} typů`}
              />
              <Kpi
                label="Produkce"
                value={production ? (production.running ? 'běží' : 'stojí') : '—'}
                hint={production?.name ?? 'stav není k dispozici'}
                tone={production && !production.running ? 'alert' : undefined}
              />
              <Kpi
                label="Zprávy produkce"
                value={production ? production.messages.toLocaleString('cs-CZ') : '—'}
                hint={production?.last_message ? `poslední ${fmtDayTime(production.last_message)}` : undefined}
              />
            </div>
            <span className="muted small">{data.version}</span>
            <div className="two-col">
              <OutlinedCard className="card">
                <h2 className="section-title">FHIR zdroje podle typu (HSFHIR_X0001_R.Rsrc, Deleted = 0)</h2>
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>Typ</th>
                      <th>Počet</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.fhir.map((row) => (
                      <tr key={row.type}>
                        <th scope="row">
                          <Link to={`/iris/fhir${search({ type: row.type })}`}>{row.type}</Link>
                        </th>
                        <td>{row.count.toLocaleString('cs-CZ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </OutlinedCard>
              <div className="page">
                <OutlinedCard className="card">
                  <h2 className="section-title">SQL tabulky a pohledy MEDDI.*</h2>
                  <table className="table compact">
                    <thead>
                      <tr>
                        <th>Tabulka</th>
                        <th>Obsah</th>
                        <th>Řádků</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.tables.map((table) => (
                        <tr key={table.name}>
                          <th scope="row">
                            <code>{table.name}</code>
                          </th>
                          <td>{table.description}</td>
                          <td>{table.rows === null ? '—' : table.rows.toLocaleString('cs-CZ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </OutlinedCard>
                {production && (
                  <OutlinedCard className="card">
                    <h2 className="section-title">Komponenty produkce {production.name}</h2>
                    <table className="table compact">
                      <tbody>
                        {production.items.map((item) => (
                          <tr key={item.name}>
                            <th scope="row">{item.name}</th>
                            <td className="muted">{item.class_name}</td>
                            <td>{item.enabled ? 'zapnuto' : 'vypnuto'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </OutlinedCard>
                )}
              </div>
            </div>
          </>
        );
      }}
    </Load>
  );
}

function SqlTab() {
  const queries = useIris<IrisQuery[]>('/api/iris/queries');
  return <Load source={queries}>{(list) => list.map((query) => <QueryCard key={query.id} query={query} />)}</Load>;
}

function QueryCard({ query }: { query: IrisQuery }) {
  const [state, setState] = useState<{ running: boolean; result?: IrisQueryResult; error?: string }>({ running: false });
  const run = async () => {
    setState({ running: true });
    try {
      setState({ running: false, result: await api.post<IrisQueryResult>(`/api/iris/queries/${encodeURIComponent(query.id)}/run`) });
    } catch (error) {
      setState({ running: false, error: irisError(error) });
    }
  };
  const result = state.result;
  return (
    <OutlinedCard className="card">
      <div className="row space top">
        <div className="column">
          <h2 className="section-title">{query.title}</h2>
          <span className="muted">{query.description}</span>
        </div>
        <FilledButton onClick={run} disabled={state.running}>
          <SvgIcon slot="icon" svg={playIcon} />
          Spustit
        </FilledButton>
      </div>
      <pre className="iris-code">{query.sql}</pre>
      {state.error && (
        <div className="state state-error" role="status">
          <SvgIcon svg={warningIcon} />
          <span>{state.error}</span>
        </div>
      )}
      {result && (
        <>
          <span className="muted small">
            {rowsText(result.rows.length)} za {result.elapsed_ms} ms
            {result.truncated && ` · zobrazeno prvních ${result.rows.length}, další řádky server nevrací`}
          </span>
          {result.rows.length > 0 && (
            <div className="iris-scroll">
              <table className="table compact">
                <thead>
                  <tr>
                    {result.columns.map((column, index) => (
                      <th key={index}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((value, index) => (
                        <Cell key={index} value={value} />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </OutlinedCard>
  );
}

function Cell({ value }: { value: IrisValue }) {
  const [open, setOpen] = useState(false);
  if (value === null) return <td className="muted">NULL</td>;
  const text = String(value);
  if (text.length <= CELL_LIMIT) return <td>{text}</td>;
  return (
    <td>
      {open ? <pre className="iris-code">{pretty(text)}</pre> : `${text.slice(0, CELL_LIMIT)}…`}{' '}
      <button type="button" className="link-button" onClick={() => setOpen(!open)}>
        {open ? 'Sbalit' : 'Zobrazit celé'}
      </button>
    </td>
  );
}

function FhirTab() {
  const [params, setParams] = useSearchParams();
  const types = useIris<IrisOverview>('/api/iris/overview');
  const type = params.get('type') ?? 'Patient';
  const page = Math.max(0, Math.floor(Number(params.get('page'))) || 0);
  const selected = params.get('id');
  const resources = useIris<IrisResourcePage>(`/api/iris/fhir${search({ type, page })}`);
  const resource = useIris<Record<string, unknown>>(selected ? `/api/iris/fhir/${encodeURIComponent(type)}/${encodeURIComponent(selected)}` : null);

  return (
    <div className="two-col">
      <OutlinedCard className="card">
        <select className="native-select" aria-label="Typ zdroje" value={type} onChange={(event) => setParams(search({ type: event.target.value }))}>
          {(types.data?.fhir ?? [{ type, count: 0 }]).map((row) => (
            <option key={row.type} value={row.type}>
              {`${row.type} · ${row.count}`}
            </option>
          ))}
        </select>
        <Load source={resources} isEmpty={(data) => data.items.length === 0} emptyText="Žádné zdroje tohoto typu.">
          {(data) => {
            const pages = Math.max(1, Math.ceil(data.total / data.page_size));
            return (
              <>
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>Id</th>
                      <th>Změněno</th>
                      <th>Verze</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => (
                      <tr key={item.id} className={item.id === selected ? 'selected' : undefined}>
                        <th scope="row">
                          <Link to={search({ type, page, id: item.id })}>{item.id}</Link>
                        </th>
                        <td className="nowrap">{secondsFormat.format(new Date(item.last_modified))}</td>
                        <td>{item.version}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="row">
                  <OutlinedButton disabled={page === 0} onClick={() => setParams(search({ type, page: page - 1 }))}>
                    Novější
                  </OutlinedButton>
                  <span className="muted">
                    Strana {page + 1} z {pages} · celkem {data.total.toLocaleString('cs-CZ')} · nejnovější první
                  </span>
                  <OutlinedButton disabled={page + 1 >= pages} onClick={() => setParams(search({ type, page: page + 1 }))}>
                    Starší
                  </OutlinedButton>
                </div>
              </>
            );
          }}
        </Load>
      </OutlinedCard>
      <OutlinedCard className="card iris-side">
        <h2 className="section-title">{selected ? `${type}/${selected}` : 'Surové JSON'}</h2>
        {selected ? (
          <Load source={resource}>{(json) => <pre className="iris-code tall">{JSON.stringify(json, null, 2)}</pre>}</Load>
        ) : (
          <span className="muted">Vyberte zdroj vlevo.</span>
        )}
      </OutlinedCard>
    </div>
  );
}

function ProductionTab() {
  const [params] = useSearchParams();
  const session = params.get('session');
  const selected = params.get('id');
  const messages = useIris<IrisMessage[]>(`/api/iris/messages${session ? search({ session }) : ''}`);
  const detail = useIris<IrisMessageDetail>(selected ? `/api/iris/messages/${encodeURIComponent(selected)}` : null);

  return (
    <div className="two-col iris-wide-left">
      <OutlinedCard className="card">
        <div className="row space">
          <h2 className="section-title">{session ? `Trasa session ${session}` : 'Posledních 100 zpráv produkce (Ens.MessageHeader)'}</h2>
          {session && <Link to={search({})}>Všechny zprávy</Link>}
        </div>
        <Load source={messages} isEmpty={(list) => list.length === 0} emptyText="Produkce zatím nezpracovala žádnou zprávu.">
          {(list) => (
            <div className="iris-scroll">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Čas</th>
                    <th>Session</th>
                    <th>Odkud → kam</th>
                    <th>Třída zprávy</th>
                    <th>Stav</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((message) => (
                    <tr key={message.id} className={String(message.id) === selected ? 'selected' : undefined}>
                      <td className="nowrap">
                        <Link to={search({ session, id: message.id })}>{message.time ? secondsFormat.format(new Date(message.time)) : '—'}</Link>
                      </td>
                      <td>
                        <Link to={search({ session: message.session })}>{message.session}</Link>
                      </td>
                      <td>
                        {message.source} → {message.target}
                      </td>
                      <td>{message.body_class ?? '—'}</td>
                      <td className={message.error ? 'error-text' : undefined}>{message.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Load>
      </OutlinedCard>
      <OutlinedCard className="card iris-side">
        {selected ? (
          <Load source={detail}>
            {(message) => (
              <>
                <h2 className="section-title">
                  Zpráva {message.id} · {message.type}
                </h2>
                <span className="muted">
                  {message.source} → {message.target} · {message.body_class ?? 'bez těla'} · {message.status}
                </span>
                {message.body ? (
                  <pre className="iris-code tall">{pretty(message.body)}</pre>
                ) : (
                  <span className="muted">Tělo této třídy zprávy se tu nezobrazuje, najdete ho v Message Vieweru (záložka Odkazy).</span>
                )}
              </>
            )}
          </Load>
        ) : (
          <span className="muted">Vyberte zprávu vlevo (klikněte na čas). Číslo session ukáže celou trasu zprávy.</span>
        )}
      </OutlinedCard>
    </div>
  );
}

function LinksTab() {
  return (
    <OutlinedCard className="card">
      <h2 className="section-title">Management Portal IRIS</h2>
      <p>Portál je na tomto serveru pod /csp/ a vyžaduje přihlášení do IRIS. Druhá možnost je SSH tunel, portál je pak na http://localhost:52773/csp/sys/UtilHome.csp:</p>
      <pre className="iris-code">{'ssh -L 52773:127.0.0.1:52773 root@<server>'}</pre>
      <p className="muted">Přihlaste se účtem správce IRIS; přihlašovací údaje tu neuvádíme.</p>
      <table className="table compact">
        <tbody>
          {PORTAL_LINKS.map(([label, path, note]) => (
            <tr key={path}>
              <th scope="row">
                <a href={PORTAL + path} target="_blank" rel="noreferrer">
                  {label}
                </a>
              </th>
              <td>{note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </OutlinedCard>
  );
}
