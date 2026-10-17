import { api } from '@navigator/api';

export type PushState = 'unsupported' | 'ios-install' | 'denied' | 'off' | 'on';

const isIos = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
const isStandalone = () => matchMedia('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true;
const supported = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

async function currentSubscription() {
  const registration = await navigator.serviceWorker.getRegistration();
  return (await registration?.pushManager.getSubscription()) ?? null;
}

export async function pushState(): Promise<PushState> {
  if (!supported()) return isIos() && !isStandalone() ? 'ios-install' : 'unsupported';
  if (Notification.permission === 'denied') return 'denied';
  return (await currentSubscription()) ? 'on' : 'off';
}

function urlBase64ToUint8Array(base64Url: string) {
  const base64 = (base64Url + '='.repeat((4 - (base64Url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
}

const subscribe = (patientId: string, subscription: PushSubscription) =>
  api.post('/api/push/subscribe', { patient_id: patientId, subscription: subscription.toJSON(), user_agent: navigator.userAgent });

export async function enablePush(patientId: string): Promise<PushState> {
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return permission === 'denied' ? 'denied' : 'off';
  const { public_key } = await api.get<{ public_key: string }>('/api/push/key');
  const registration = await Promise.race([
    navigator.serviceWorker.ready,
    new Promise<never>((_, reject) => setTimeout(() => reject(new Error('Service worker is not active (vite dev has none).')), 10_000)),
  ]);
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(public_key),
  });
  await subscribe(patientId, subscription);
  return 'on';
}

export async function disablePush() {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api.post('/api/push/unsubscribe', { endpoint: subscription.endpoint });
  await subscription.unsubscribe();
}

export async function syncPushPatient(patientId: string) {
  try {
    if (!supported() || Notification.permission !== 'granted') return;
    const subscription = await currentSubscription();
    if (subscription) await subscribe(patientId, subscription);
  } catch {
    // offline or API down: the next patient change retries
  }
}
