# MEDDIONCO AI Navigator

Oncology patient navigator for [Rakathon 2026](https://www.rakathon.cz/eng) and the
[InterSystems challenge](https://developer.intersystems.com/intersystems-challenge-at-rakathon-2026/).

| Path | What | Dev port |
|---|---|---|
| `apps/patient-pwa` | PWA for patients: mobile-first, installable, works offline | 5173 |
| `apps/doctor-web` | Web app for doctors, desktop only (hidden below 1024 px) | 5174 |
| `packages/ui` | Shared Material 3 library used by both apps | – |
| `docs/intersystems.md` | What we take from InterSystems IRIS for Health and how | – |

Stack: React 19, Vite 8, TypeScript 7, pnpm workspaces, `vite-plugin-pwa`, Material Web (`@material/web`).

## Run

Needs Node ≥ 22.12 and pnpm 11.

```bash
pnpm install
pnpm dev:patient
pnpm dev:doctor
pnpm build
pnpm typecheck
pnpm test
```

## Material 3 (`@navigator/ui`)

- Components: `import { FilledButton, OutlinedTextField, NavigationBar } from '@navigator/ui'`. These are typed React
  wrappers over Material Web elements; events are `onInput`, `onChange`, `onClosed`, `onActivated` and so on.
- Styles: import `@navigator/ui/styles.css` once per app. It brings M3 color tokens (`--md-sys-color-*`),
  Roboto Flex and the type scale classes (`md-typescale-body-large`, `md-typescale-title-medium`, ...).
- Icons: pick one at [fonts.google.com/icons](https://fonts.google.com/icons), then
  `import icon from '@material-symbols/svg-400/outlined/<name>.svg?raw'` and render `<SvgIcon svg={icon} />`.
  Only imported icons are bundled.
- Brand color: change `SEED` in `packages/ui/scripts/tokens.mjs` and run `pnpm --filter @navigator/ui tokens`.
  Light and dark schemes are generated with `light-dark()`; the theme follows the OS, force one with
  `document.documentElement.style.colorScheme = 'dark'`.
- Material Web is in maintenance mode and has no top app bar, data table or date picker. Build those from the tokens
  (see `apps/*/src/app.css`); use `<input type="date">` for dates.
