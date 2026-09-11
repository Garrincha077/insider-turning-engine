import {
  AlertTriangle,
  BellOff,
  CheckCircle2,
  CircleSlash2,
  ExternalLink,
  Mail,
  MessageCircle,
  ShieldCheck,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import {
  type ChannelStatus,
  type PublicationManifest,
  type SettingsStatus,
  humanReason,
  rateLabel,
} from '@/lib/operations-data';

export function SystemHealthView({ manifest }: { manifest: PublicationManifest }) {
  const quality = manifest.quality;
  const checks = [
    { label: 'Canonical data', pass: quality.canonicalValid, detail: quality.canonicalValid ? 'Schema and hashes valid' : 'Canonical validation blocked' },
    { label: 'Methodology', pass: quality.methodologyComplete, detail: quality.methodologyComplete ? 'Frozen scoring contract' : 'Candidate scoring contract' },
    { label: 'Benchmark', pass: quality.benchmarkFresh, detail: quality.benchmarkFresh ? 'Fresh through latest session' : 'Stale or unavailable' },
    { label: 'SEC parsing', pass: quality.parseSuccess.result === 'PASS', detail: `${rateLabel(quality.parseSuccess)} · gate ${(quality.parseSuccess.threshold * 100).toFixed(1)}%` },
    { label: 'Market coverage', pass: quality.marketCoverage.result === 'PASS', detail: `${rateLabel(quality.marketCoverage)} · gate ${(quality.marketCoverage.threshold * 100).toFixed(0)}%` },
    { label: 'Core coverage', pass: quality.coreBranchCoverage.result === 'PASS', detail: `${rateLabel(quality.coreBranchCoverage)} · gate ${(quality.coreBranchCoverage.threshold * 100).toFixed(0)}%` },
  ];
  return <div className="space-y-6">
    <div className="grid gap-4 md:grid-cols-3">
      <StatusCard label="Dashboard integrity" value="VERIFIED ON LOAD" pass />
      <StatusCard label="Predictive model gate" value={quality.disposition} pass={quality.disposition === 'PASS'} />
      <StatusCard label="Run" value={manifest.runId} pass={quality.canonicalValid} mono />
    </div>
    <Panel title="Data and research checks" subtitle="Research gate failures do not turn verified SEC facts into unavailable data.">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{checks.map((check) => <div key={check.label} className="rounded-lg border border-border bg-background/35 p-4"><div className="flex items-center gap-2">{check.pass ? <CheckCircle2 className="size-4 text-emerald-300" /> : <AlertTriangle className="size-4 text-amber-300" />}<span className="text-sm font-semibold">{check.label}</span></div><p className="mt-2 text-xs text-muted-foreground">{check.detail}</p></div>)}</div>
    </Panel>
    <Panel title="Workflow evidence" subtitle="The published data is not proof that the latest scheduled refresh succeeded.">
      <p className="text-sm leading-6 text-muted-foreground">Published snapshot: {formatInstant(manifest.asOf)}. Last attempt and run duration are not included in this v1 manifest. If dates stop advancing, inspect the latest Actions run and its acquisition diagnostics; do not assume a newly deployed UI refreshed the data.</p>
      <a href="https://github.com/Garrincha077/insider-turning-engine/actions" target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm text-emerald-200 underline">Inspect workflow runs and failures</a>
    </Panel>
    <Panel title="Open blockers" subtitle="These reasons prevent a validated production claim">
      {quality.issues.length === 0 ? <SuccessMessage text="No publication-quality blockers are recorded." /> : <ReasonList reasons={quality.issues} />}
    </Panel>
  </div>;
}

export function DataCoverageView({ manifest }: { manifest: PublicationManifest }) {
  const measurements = [
    ['SEC parse success', manifest.quality.parseSuccess],
    ['Market coverage', manifest.quality.marketCoverage],
  ] as const;
  return <div className="space-y-6">
    <div className="grid gap-4 sm:grid-cols-3">
      <StatusCard label="Active issuers" value={String(manifest.universe.issuerCount)} pass={manifest.universe.issuerCount > 0} />
      <StatusCard label="Relevant transactions" value={String(manifest.universe.activeTransactionCount)} pass={manifest.universe.activeTransactionCount > 0} />
      <StatusCard label="Complete research scores" value={String(manifest.universe.signalCount)} pass={manifest.universe.signalCount > 0} />
    </div>
    <Panel title="Coverage evidence" subtitle="Market denominator is the selected fetch universe, not all US-listed companies.">
      <div className="space-y-4">{measurements.map(([label, value]) => <div key={label} className="grid gap-3 rounded-lg border border-border bg-background/35 p-4 sm:grid-cols-[1fr_auto_auto] sm:items-center"><div><p className="text-sm font-semibold">{label}</p><p className="mt-1 text-xs text-muted-foreground">{value.numerator.toLocaleString()} / {value.denominator.toLocaleString()} observed</p></div><span className="font-mono text-sm">{rateLabel(value)}</span><ResultBadge result={value.result} /></div>)}</div>
    </Panel>
    <Panel title="Source watermarks" subtitle="Latest data represented in this immutable snapshot">
      <div className="grid gap-4 md:grid-cols-2"><Watermark label="SEC accepted through" value={manifest.watermarks.secAcceptedThrough} /><Watermark label="Market session through" value={manifest.watermarks.marketSessionThrough} /></div>
    </Panel>
    <Panel title="Coverage gaps" subtitle="A missing measurement is not 100% coverage."><p className="text-sm leading-6 text-muted-foreground">Discovered filings, resolved identities, covered SEC days and exclusion counts are not fully represented in the legacy public manifest. A 90-day window is not yet verified. These measurements require the canonical v2 export; no market-wide completeness is claimed here.</p></Panel>
  </div>;
}

export function AlertCenterView({ settings }: { settings: SettingsStatus }) {
  const channels = Object.entries(settings.channels) as Array<[string, ChannelStatus]>;
  return <div className="space-y-6">
    <Panel title="Informational daily digest" subtitle="A separate channel policy, independent of experimental scores."><p className="text-sm leading-6 text-muted-foreground">Not enabled by this legacy snapshot. A trustworthy preview needs independent economic transactions, the latest complete SEC day and a durable day-level delivery claim. No message or “no new purchases” assertion is generated from incomplete v1 owner groups.</p><p className="mt-3 text-xs text-muted-foreground">Planned content: up to five new open-market purchases of at least $250,000, with SEC source links. No scores or trade recommendations.</p></Panel>
    <div className={`rounded-xl border p-5 ${settings.alertsAllowed ? 'border-emerald-400/25 bg-emerald-400/8' : 'border-amber-300/20 bg-amber-300/8'}`}><div className="flex items-start gap-3">{settings.alertsAllowed ? <ShieldCheck className="mt-0.5 size-5 text-emerald-300" /> : <BellOff className="mt-0.5 size-5 text-amber-300" />}<div><h2 className="text-sm font-semibold">{settings.alertsAllowed ? 'Actionable alerts enabled' : 'Actionable alerts blocked'}</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">Delivery requires a PASS snapshot, enabled policy, configured channel, and healthy outbox.</p></div></div></div>
    <div className="grid gap-4 md:grid-cols-2">{channels.map(([name, channel]) => <ChannelCard key={name} name={name} status={channel} />)}</div>
    <Panel title="Suppression reasons" subtitle="No blocked candidate is silently discarded">
      {settings.blockingReasons.length === 0 ? <SuccessMessage text="No global alert suppression is active." /> : <ReasonList reasons={settings.blockingReasons} />}
    </Panel>
    <Panel title="Delivery history" subtitle="Durable state ledger · latest 100 entries · SENT means provider acceptance">
      {!settings.deliveryHistory?.length ? <p className="text-xs text-muted-foreground">No recorded deliveries or tests.</p> :
        <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-2">Time (UTC)</th><th className="p-2">Channel</th><th className="p-2">Kind</th><th className="p-2">Result</th></tr></thead>
          <tbody>{settings.deliveryHistory.map((row, index) => <tr key={`${row.at}-${row.channel}-${index}`} className="border-t border-border"><td className="p-2">{formatInstant(row.at)}</td><td className="p-2">{row.channel}</td><td className="p-2">{row.kind}</td><td className="p-2">{row.status}</td></tr>)}</tbody>
        </table></div>}
    </Panel>
  </div>;
}

export function SettingsView({ settings }: { settings: SettingsStatus }) {
  const setupUrl = 'https://github.com/Garrincha077/insider-turning-engine/settings/environments';
  return <div className="space-y-6">
    <Panel title="Delivery channels" subtitle="Secrets stay in the protected GitHub production environment">
      <div className="grid gap-4 md:grid-cols-2"><ChannelCard name="telegram" status={settings.channels.telegram} /><ChannelCard name="email" status={settings.channels.email} /></div>
      <a href={setupUrl} target="_blank" rel="noreferrer" className="mt-5 inline-flex items-center gap-2 rounded-lg border border-emerald-400/25 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-400/15">Open GitHub Environment settings <ExternalLink className="size-3.5" /></a>
      <p className="mt-3 text-[11px] leading-5 text-muted-foreground">Telegram secrets: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Optional email: EMAIL_API_KEY, ALERT_EMAIL_FROM and ALERT_EMAIL_TO. Values are never emitted into Pages data. This page cannot save server settings.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">{Object.entries(settings.channels).map(([name, channel]) => <div key={name} className="rounded-lg border border-border p-3 text-xs"><p className="font-semibold capitalize">{name} delivery test: {channel.lastTestStatus ?? 'NOT TESTED'}</p><p className="mt-1 text-muted-foreground">Failed or uncertain tests: {channel.testFailureCount ?? 0}. Configuration alone does not confirm delivery.</p></div>)}</div>
      <a className="mt-4 inline-block text-xs text-emerald-200 underline" href="https://github.com/Garrincha077/insider-turning-engine/actions/workflows/test-alert-delivery.yml" target="_blank" rel="noreferrer">Open delivery test workflow</a>
    </Panel>
    <Panel title="Predictive alert policy" subtitle={`Versioned configuration · ${settings.environment} · separate from the factual digest`}>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><PolicyMetric label="Delivery switch" value={settings.policy.deliveryEnabled ? 'ENABLED' : 'OFF'} /><PolicyMetric label="Minimum severity" value={settings.policy.minimumSeverity} /><PolicyMetric label="Cooldown" value={`${settings.policy.cooldownDays} days`} /><PolicyMetric label="Timezone" value={settings.policy.timezone} /></div>
      <div className="mt-4 flex flex-wrap gap-2">{settings.policy.alertTypes.map((type) => <Badge key={type} variant="outline">{humanReason(type)}</Badge>)}</div>
    </Panel>
    <Panel title="Secret-handling boundary" subtitle="What this public page can and cannot do">
      <div className="grid gap-4 md:grid-cols-2"><Boundary icon={<CheckCircle2 className="size-4 text-emerald-300" />} title="Safe here" text="View masked configuration, policy, delivery health, and suppression reasons." /><Boundary icon={<CircleSlash2 className="size-4 text-amber-300" />} title="Never in Pages" text="Bot tokens, API keys, chat IDs, full email addresses, or editable secret fields." /></div>
    </Panel>
  </div>;
}

function ChannelCard({ name, status }: { name: string; status: ChannelStatus }) {
  const Icon = name === 'telegram' ? MessageCircle : Mail;
  const healthy = status.enabled && status.configured;
  return <div className="rounded-xl border border-border bg-card p-5"><div className="flex items-center justify-between"><div className="flex items-center gap-2"><Icon className="size-4 text-sky-300" /><span className="text-sm font-semibold capitalize">{name}</span></div><ResultBadge result={healthy ? 'PASS' : status.enabled ? 'FAIL' : 'NOT_EVALUATED'} /></div><dl className="mt-5 space-y-3 text-xs"><Row label="Configured" value={status.configured ? 'Yes' : 'Missing secrets'} /><Row label="Recipient" value={status.recipientMasked ?? 'Not available'} /><Row label="Last test" value={formatInstant(status.lastTestAt)} /><Row label="Last success" value={formatInstant(status.lastSuccessAt)} /><Row label="Failures" value={String(status.failureCount)} /></dl></div>;
}

function StatusCard({ label, value, pass, mono = false }: { label: string; value: string; pass: boolean; mono?: boolean }) { return <div className="rounded-xl border border-border bg-card p-5"><div className="flex items-center justify-between"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p>{pass ? <CheckCircle2 className="size-4 text-emerald-300" /> : <AlertTriangle className="size-4 text-amber-300" />}</div><p className={`mt-4 truncate text-lg font-semibold ${mono ? 'font-mono text-xs' : ''}`}>{value}</p></div>; }
function ResultBadge({ result }: { result: 'PASS' | 'FAIL' | 'NOT_EVALUATED' }) { const style = result === 'PASS' ? 'bg-emerald-400/10 text-emerald-200' : result === 'FAIL' ? 'bg-rose-400/10 text-rose-200' : 'bg-amber-300/10 text-amber-200'; return <Badge className={style}>{result.replace('_', ' ')}</Badge>; }
function Watermark({ label, value }: { label: string; value: string | null }) { return <div className="rounded-lg border border-border bg-background/35 p-4"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p><p className="mt-3 font-mono text-xs">{formatInstant(value)}</p></div>; }
function PolicyMetric({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-border bg-background/35 p-4"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p><p className="mt-2 font-mono text-sm font-semibold">{value}</p></div>; }
function Boundary({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) { return <div className="rounded-lg border border-border bg-background/35 p-4"><div className="flex items-center gap-2 text-sm font-semibold">{icon}{title}</div><p className="mt-2 text-xs leading-5 text-muted-foreground">{text}</p></div>; }
function Row({ label, value }: { label: string; value: string }) { return <div className="flex items-center justify-between gap-3 border-b border-border/60 pb-2"><dt className="text-muted-foreground">{label}</dt><dd className="truncate font-mono text-[11px]">{value}</dd></div>; }
function ReasonList({ reasons }: { reasons: string[] }) { return <div className="grid gap-2 md:grid-cols-2">{reasons.map((reason) => <div key={reason} className="flex items-start gap-2 rounded-lg border border-border bg-background/35 p-3 text-xs"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-300" /><span className="capitalize">{humanReason(reason)}</span></div>)}</div>; }
function SuccessMessage({ text }: { text: string }) { return <div className="flex items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/8 p-4 text-xs text-emerald-100"><CheckCircle2 className="size-4" />{text}</div>; }
function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) { return <section className="overflow-hidden rounded-xl border border-border bg-card"><div className="border-b border-border px-5 py-4"><h2 className="text-sm font-semibold">{title}</h2><p className="mt-1 text-xs text-muted-foreground">{subtitle}</p></div><div className="p-5">{children}</div></section>; }
function formatInstant(value: string | null) { if (!value) return 'Never'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? 'Invalid timestamp' : date.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }); }
