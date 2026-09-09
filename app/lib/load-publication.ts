import type { DashboardData } from './dashboard-data';
import type { PublicationManifest, SettingsStatus } from './operations-data';

export async function loadPublication(signal: AbortSignal) {
  const root = `${import.meta.env.BASE_URL}data/`;
  const response = await fetch(`${root}manifest.json`, { cache: 'no-store', signal });
  if (!response.ok) throw new Error('Publication manifest unavailable');
  const manifest = await response.json() as PublicationManifest;
  if (manifest.schemaVersion !== '1.0.0' || !Array.isArray(manifest.files) ||
      !manifest.quality || !manifest.watermarks || !manifest.universe ||
      !Array.isArray(manifest.quality.issues)) throw new Error('Unsupported publication manifest');
  async function verified<T>(name: string): Promise<T> {
    const entries = manifest.files.filter((item) => item.path === name);
    if (entries.length !== 1) throw new Error(`${name} missing from manifest`);
    const file = await fetch(`${root}${name}`, { cache: 'no-store', signal });
    if (!file.ok) throw new Error(`${name} unavailable`);
    const bytes = await file.arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
    if (bytes.byteLength !== entries[0].size || hash !== entries[0].sha256) {
      throw new Error(`${name} integrity mismatch; please reload`);
    }
    return JSON.parse(new TextDecoder().decode(bytes)) as T;
  }
  const [data, settings] = await Promise.all([
    verified<DashboardData>('dashboard.json'), verified<SettingsStatus>('settings-status.json'),
  ]);
  if (data.schemaVersion !== '1.0.0' || data.scoreVersion !== manifest.scoreVersion ||
      !Number.isFinite(Date.parse(data.generatedAt)) ||
      !['VALIDATED', 'EXPERIMENTAL', 'STALE'].includes(data.status) ||
      !Array.isArray(data.candidates) || !Array.isArray(data.filings) ||
      !Array.isArray(data.companySeries) || !Array.isArray(data.backtest) ||
      !Array.isArray(data.pulseHistory)) throw new Error('Dashboard contract mismatch');
  if (settings.schemaVersion !== '1.0.0' || !settings.channels?.telegram ||
      !settings.channels?.email || !settings.policy || !Array.isArray(settings.blockingReasons)) {
    throw new Error('Settings contract mismatch');
  }
  if ((data.status === 'VALIDATED') !== (manifest.status === 'SUCCEEDED') ||
      (settings.alertsAllowed && manifest.quality.disposition !== 'PASS')) {
    throw new Error('Publication readiness is inconsistent');
  }
  return { data, manifest, settings };
}
