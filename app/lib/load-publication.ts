import type { DashboardData } from './dashboard-data';
import type { PublicationManifest, SettingsStatus } from './operations-data';
import { adaptResearch, validateResearch } from './research-v2';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import settingsSchema from '../../schemas/settings-status.schema.json';

const settingsValidator = new Ajv2020({ strict: false });
addFormats(settingsValidator);
const validSettings = settingsValidator.compile<SettingsStatus>(settingsSchema);

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
  if (!validSettings(settings) || settings.schemaVersion !== '1.0.0' || !settings.channels?.telegram ||
      !settings.channels?.email || !settings.policy || !Array.isArray(settings.blockingReasons)) {
    throw new Error('Settings contract mismatch');
  }
  if ((data.status === 'VALIDATED') !== (manifest.status === 'SUCCEEDED') ||
      (settings.alertsAllowed && manifest.quality.disposition !== 'PASS')) {
    throw new Error('Publication readiness is inconsistent');
  }
  const research = manifest.files.some((row) => row.path === 'research-v2.json')
    ? validateResearch(await verified<unknown>('research-v2.json'), manifest) : null;
  if (settings.digest) {
    if (!research || settings.digest.secDay !== ([...research.coverage.expectedSecDays].sort((a, b) => a.localeCompare(b)).at(-1) ?? null) ||
        settings.digest.eventIds.some((id) => !research.economicTransactions.some((row) => row.eventId === id)) ||
        (settings.digest.status === 'READY' && (!settings.digest.enabled || settings.digest.reasons.length > 0 ||
          !research.coverage.days.some((day) => day.day === settings.digest?.secDay && day.complete)))) {
      throw new Error('Digest status does not match the research publication');
    }
  }
  return { data: research ? adaptResearch(data, research) : data, manifest, settings };
}
