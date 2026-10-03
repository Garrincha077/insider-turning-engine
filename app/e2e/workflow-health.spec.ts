import { expect, test } from '@playwright/test';
import { parseWorkflowRuns, workflowDuration } from '../lib/workflow-health';
import { ready, section } from './helpers';

const run = (id: number, event: string, conclusion: string, created: string) => ({
  id, event, conclusion, status: 'completed', head_branch: 'main',
  created_at: created, updated_at: created,
});

test('workflow evidence rejects invalid rows and uses the complete job span', () => {
  const rows = parseWorkflowRuns({ workflow_runs: [
    run(2, 'schedule', 'failure', '2026-10-03T12:00:00Z'),
    { ...run(3, 'push', 'success', '2026-10-03T13:00:00Z'), head_branch: 'feature' },
    run(1, 'schedule', 'success', '2026-10-02T12:00:00Z'),
  ] });
  expect(rows.map((row) => row.id)).toEqual([2, 1]);
  expect(() => parseWorkflowRuns({ workflow_runs: [{ ...run(4, 'push', 'success', 'bad'), id: -4 }] })).toThrow();
  expect(workflowDuration({ total_count: 2, jobs: [
    { started_at: '2026-10-03T12:01:00Z', completed_at: '2026-10-03T12:02:00Z' },
    { started_at: '2026-10-03T12:03:00Z', completed_at: '2026-10-03T12:06:00Z' },
  ] }, rows[0], Date.parse('2026-10-03T12:08:00Z'))).toBe(300_000);
  expect(workflowDuration({ total_count: 2, jobs: [] }, rows[0], Date.now())).toBeNull();
});

test('System Health distinguishes a UI deploy from a failed scheduled refresh', async ({ page }, testInfo) => {
  await page.route('https://api.github.com/repos/Garrincha077/insider-turning-engine/actions/workflows/pages.yml/runs**', (route) => {
    const query = new URL(route.request().url()).searchParams;
    const rows = query.get('status') === 'success'
      ? [run(390, 'schedule', 'success', '2026-09-30T07:15:00Z')]
      : query.get('event') === 'schedule'
        ? [run(400, 'schedule', 'failure', '2026-10-03T12:31:00Z')]
        : [run(401, 'push', 'success', '2026-10-03T13:30:00Z'),
          run(400, 'schedule', 'failure', '2026-10-03T12:31:00Z')];
    return route.fulfill({ json: { workflow_runs: rows } });
  });
  await page.route('https://api.github.com/repos/Garrincha077/insider-turning-engine/actions/runs/401/jobs**',
    (route) => route.fulfill({ json: { total_count: 1, jobs: [
      { started_at: '2026-10-03T13:31:00Z', completed_at: '2026-10-03T13:33:15Z' },
    ] } }));
  await ready(page, { mockWorkflow: false });
  await section(page, 'System Health');
  const panel = page.getByRole('region', { name: 'Daily workflow status' });
  await expect(panel).toContainText('UI-only deployment');
  await expect(panel).toContainText('Latest scheduled daily refresh');
  await expect(panel).toContainText('FAILURE');
  await expect(panel).toContainText('Last successful scheduled refresh');
  await expect(panel).toContainText('Job duration: 2m 15s');
  await expect(panel.getByRole('link', { name: 'Inspect run 400' }))
    .toHaveAttribute('href', 'https://github.com/Garrincha077/insider-turning-engine/actions/runs/400');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('workflow-health.png'), fullPage: true });
});

test('GitHub status outage is explicit while verified snapshot remains usable', async ({ page }) => {
  await page.route('https://api.github.com/repos/Garrincha077/insider-turning-engine/actions/workflows/pages.yml/runs**',
    (route) => route.fulfill({ status: 503, body: '' }));
  await ready(page, { mockWorkflow: false });
  await section(page, 'System Health');
  const panel = page.getByRole('region', { name: 'Daily workflow status' });
  await expect(panel).toContainText('GitHub workflow status unavailable');
  await expect(page.getByText('VERIFIED ON LOAD')).toBeVisible();
  await expect(panel.getByRole('link', { name: 'Open daily workflow in Actions' })).toBeVisible();
});
