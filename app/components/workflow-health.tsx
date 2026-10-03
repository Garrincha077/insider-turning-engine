import { useEffect, useState } from 'react';
import { WORKFLOW_POLL_MS, durationLabel, loadWorkflowHealth, type WorkflowHealth, type WorkflowRun } from '@/lib/workflow-health';

export function WorkflowHealthPanel() {
  const [health, setHealth] = useState<WorkflowHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') setRevision((value) => value + 1);
    }, WORKFLOW_POLL_MS);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    loadWorkflowHealth(controller.signal, revision > 0).then((value) => {
      if (!controller.signal.aborted) { setHealth(value); setError(null); }
    }).catch(() => {
      if (!controller.signal.aborted) {
        setHealth(null);
        setError('GitHub workflow status unavailable. Data remains loaded; open Actions for the current outcome.');
      }
    });
    return () => controller.abort();
  }, [revision]);
  return <section className="rounded-xl border border-border bg-card p-5" aria-label="Daily workflow status">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-sm font-semibold">Daily workflow status</h2>
      <button type="button" onClick={() => setRevision((value) => value + 1)} className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-muted">Refresh workflow status</button>
    </div>
    <p className="mt-2 text-xs leading-5 text-muted-foreground">Read-only GitHub Actions status, checked every five minutes while this view is visible. A successful UI-only deploy is not a successful data refresh.</p>
    {error ? <output className="mt-4 block text-sm text-amber-200">{error}</output> : !health ? <output className="mt-4 block text-sm text-muted-foreground">Loading workflow status…</output> : <>
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <RunCard label="Latest workflow attempt" run={health.latest} duration={health.durationMs} />
        <RunCard label="Latest scheduled daily refresh" run={health.scheduled} />
        <RunCard label="Last successful scheduled refresh" run={health.lastSuccessfulScheduled} />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">Checked (UTC): {dateLabel(health.checkedAt)}. Job duration excludes the initial queue; a running duration is elapsed time, not an ETA.</p>
    </>}
    <a href="https://github.com/Garrincha077/insider-turning-engine/actions/workflows/pages.yml" target="_blank" rel="noreferrer" className="mt-4 inline-block text-xs text-emerald-200 underline">Open daily workflow in Actions</a>
  </section>;
}

function RunCard({ label, run, duration }: { label: string; run: WorkflowRun | null; duration?: number | null }) {
  const result = !run ? 'NO RECORDED RUN RETURNED' : run.status === 'completed'
    ? (run.conclusion ?? 'UNKNOWN').replaceAll('_', ' ').toUpperCase() : run.status.replaceAll('_', ' ').toUpperCase();
  const color = run?.status === 'completed' && run.conclusion === 'success' ? 'text-emerald-200'
    : run?.status === 'completed' ? 'text-amber-200' : 'text-muted-foreground';
  return <div className="min-w-0 rounded-lg border border-border p-3">
    <h3 className="text-xs font-semibold">{label}</h3><p className={`mt-2 text-sm font-semibold ${color}`}>{result}</p>
    {run && <div className="mt-2 space-y-1 text-xs text-muted-foreground">
      <p>Requested (UTC): {dateLabel(run.createdAt)}</p>
      <p>{run.event === 'push' ? 'UI-only deployment' : run.event === 'schedule' ? 'Scheduled data refresh' : 'Manual run — may include data refresh'}</p>
      {duration !== undefined && <p>Job duration: {durationLabel(duration)}</p>}
      <a href={`https://github.com/Garrincha077/insider-turning-engine/actions/runs/${run.id}`} target="_blank" rel="noreferrer" className="inline-block text-emerald-200 underline">Inspect run {run.id}</a>
    </div>}
  </div>;
}

function dateLabel(value: string) {
  return new Date(value).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' });
}
