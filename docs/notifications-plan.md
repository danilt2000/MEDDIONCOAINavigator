# Notifications plan

Built so far: Web Push end to end for manual test sends. The patient turns notifications on in the PWA home screen
(card „Upozornění“); the clinician sends a test notification from https://lekar.nastasiya.com/#/test-notifikace;
a tap opens `/checkin` (or `/navigator`) for that patient. Code: `backend/app/services/push.py`,
`backend/app/api/push.py`, `apps/patient-pwa/public/push-sw.js`, `apps/patient-pwa/src/push.ts`,
`apps/doctor-web/src/pages/PushTest.tsx`. Subscriptions live in `backend/cache/push/subscriptions.json`.
Not built yet: the scheduler, automatic triggers, e-mail/SMS, settings and the FHIR audit trail below.

Goal: the patient gets a notification on the phone or by e-mail, taps it, and the app opens on the right screen.
The clinician gets red alerts even when the Fronta tab is closed.

## What triggers a notification

| Event | To | Opens |
|---|---|---|
| Check-in is due (per regimen schedule, e.g. daily at 18:00) | patient | `/checkin` |
| Missed check-in (2nd day in a row) | patient | `/checkin` |
| The team answered / closed the task | patient | `/navigator` |
| Follow-up question from triage („Kolik stupňů jste naměřil/a?“) | patient | `/navigator` |
| New red alert, nobody accepted it within the SLA | on-duty clinician | `lekar.nastasiya.com/#/fronta?task=…` |

No health data in the notification text itself (lock screen, mail servers): „Máte novou zprávu od týmu MOÚ“, never the
symptom or the level. The details are behind the tap, inside the app.

## Channels

1. **Web Push from the PWA** (first, no extra cost).
   - VAPID key pair in `.env`; `pywebpush` on the backend.
   - The PWA asks for permission after the first check-in, never on the first screen.
     Then it sends the `PushSubscription` to `POST /api/push/subscribe`, stored per patient and device.
   - The service worker handles `push` (shows the notification) and `notificationclick` (focuses an open app window or
     opens the URL from the payload).
   - Works on Android and desktop Chrome/Edge/Firefox. On iPhone only from iOS 16.4 and only once the app is added to
     the home screen, so the app shows a short „Přidat na plochu“ hint on iOS.
2. **E-mail** (fallback, and for patients without push).
   - A transactional provider (Resend / Mailgun / Amazon SES, EU region). SPF, DKIM and DMARC for `nastasiya.com`
     (Cloudflare already recommends them).
   - A signed one-time link (`/open?t=…`, valid 24 h) that logs the patient in and redirects to the target screen.
3. **SMS** (optional, later) for patients without a smartphone, via a Czech gateway; the same short text and link.

## Backend pieces

- `notifications` module: `notify(patient_id, kind, url)` picks the channels from the patient's preferences.
  It writes each send as FHIR `Communication` (category notification) for the audit trail, and retries failed sends.
- Scheduler: APScheduler inside the API, or a systemd timer, for due and missed check-ins. It follows the demo clock
  in demo mode.
- Hooks: `store.raise_task` (clinician alert when unaccepted after the SLA) and task actions „call“/„close“ (patient
  „team answered“).
  The triage follow-up question hooks into `navigator`.
- Optional InterSystems angle: route outbound notifications through `MEDDI.Production`, the same way as the alerts to
  MEDDI today. The message viewer then traces every notification.

## Patient app pieces

- Settings screen: channels (push / e-mail), quiet hours (e.g. 21:00–7:00, except red), language.
- Deep-link routes already exist (`/checkin`, `/navigator`, `/historie`); the click handler adds `?from=notification`
  for analytics.
- Consent text and opt-out (GDPR), stored with the preferences.

## Order of work

1. Web Push end to end: subscribe, „check-in due“, click opens `/checkin`. Test on Android and desktop.
2. „Team answered“ and follow-up question notifications.
3. Clinician red-alert push and e-mail.
4. E-mail channel with signed links, plus the DNS records for mail.
5. Settings screen, quiet hours, consent; then SMS if needed.

Done when, on a phone with the PWA installed, a due check-in at 18:00 shows a notification, a tap opens the
check-in screen, and the send appears as a `Communication` in IRIS.
