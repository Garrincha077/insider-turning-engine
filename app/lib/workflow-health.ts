export const WORKFLOW_RUNS_URL = 'https://api.github.com/repos/Garrincha077/insider-turning-engine/actions/workflows/pages.yml/runs';
export const WORKFLOW_POLL_MS = 300_000;

export type WorkflowRun = {
  id: number; event: string; status: string; conclusion: string | null;
  createdAt: string; updatedAt: string;
};
export type WorkflowHealth = {
  checkedAt: string; latest: WorkflowRun | null; scheduled: WorkflowRun | null;
  lastSuccessfulScheduled: WorkflowRun | null; durationMs: number | null;
};
let cached: WorkflowHealth | null = null;

function instant(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

export function parseWorkflowRuns(value: unknown): WorkflowRun[] {
  const rows = (value as { workflow_runs?: unknown } | null)?.workflow_runs;
  if (!Array.isArray(rows) || rows.length > 15) throw new Error('Invalid GitHub workflow response.');
  return rows.map((row) => {
    if (!row || !Number.isSafeInteger(row.id) || row.id <= 0 ||
        typeof row.event !== 'string' || typeof row.status !== 'string' ||
        row.event.length > 80 || row.status.length > 80 ||
        !(row.conclusion === null || typeof row.conclusion === 'string') ||
        !instant(row.created_at) || !instant(row.updated_at)) {
      throw new Error('Invalid GitHub workflow response.');
    }
    return { id: row.id, event: row.event, status: row.status, conclusion: row.conclusion,
      createdAt: row.created_at, updatedAt: row.updated_at, branch: row.head_branch };
  }).filter((row) => row.branch === 'main')
    .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt) || b.id - a.id);
}

export function workflowDuration(jobsValue: unknown, run: WorkflowRun, now: number): number | null {
  const value = jobsValue as { jobs?: unknown; total_count?: unknown } | null;
  if (!value || !Array.isArray(value.jobs) || typeof value.total_count !== 'number' ||
      value.total_count > value.jobs.length) return null;
  const starts = value.jobs.map((job) => job?.started_at).filter(instant)
    .map(Date.parse).filter((at) => at >= Date.parse(run.createdAt));
  if (!starts.length) return null;
  const ends = value.jobs.map((job) => job?.completed_at).filter(instant).map(Date.parse);
  if (run.status === 'completed' && !ends.length) return null;
  const end = run.status === 'completed' ? Math.max(...ends) : now;
  const elapsed = end - Math.min(...starts);
  return Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : null;
}

export function durationLabel(value: number | null) {
  if (value === null) return 'Unavailable / not started';
  const seconds = Math.floor(value / 1000);
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export async function loadWorkflowHealth(signal: AbortSignal, force = false): Promise<WorkflowHealth> {
  const now = Date.now();
  if (!force && cached && now >= Date.parse(cached.checkedAt) &&
      now - Date.parse(cached.checkedAt) < WORKFLOW_POLL_MS) return cached;
  async function get(url: string): Promise<unknown> {
    const response = await fetch(url, { signal, cache: 'no-store', credentials: 'omit',
      headers: { Accept: 'application/vnd.github+json' } });
    if (!response.ok) throw new Error(`GitHub status unavailable (HTTP ${response.status}). Open Actions for details.`);
    return response.json();
  }
  const queries = ['branch=main&per_page=15', 'branch=main&event=schedule&per_page=1',
    'branch=main&event=schedule&status=success&per_page=1'];
  const [all, scheduled, success] = await Promise.all(queries.map(async (query) =>
    parseWorkflowRuns(await get(`${WORKFLOW_RUNS_URL}?${query}`))));
  const latest = all[0] ?? null;
  const jobs = latest ? await get(`https://api.github.com/repos/Garrincha077/insider-turning-engine/actions/runs/${latest.id}/jobs?per_page=100&filter=latest`) : null;
  const checkedAt = new Date().toISOString();
  const result = { checkedAt, latest, scheduled: scheduled.find((row) => row.event === 'schedule') ?? null,
    lastSuccessfulScheduled: success.find((row) => row.event === 'schedule' &&
      row.status === 'completed' && row.conclusion === 'success') ?? null,
    durationMs: latest ? workflowDuration(jobs, latest, Date.parse(checkedAt)) : null };
  if (!signal.aborted) cached = result;
  return result;
}
