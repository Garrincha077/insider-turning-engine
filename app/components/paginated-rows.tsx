import { useState, type ReactNode } from 'react';
import { controlClass } from '@/lib/research';
import { usePreference } from '@/lib/local-preferences';

const isPageSize = (value: unknown): value is number => typeof value === 'number' && [25, 50, 100].includes(value);

/** Page the rendered rows only; callers retain the full sorted set for CSV. */
export function PaginatedRows<T>({ rows, label, children }: {
  rows: readonly T[]; label: string; children: (visible: readonly T[]) => ReactNode;
}) {
  const [requestedPage, setPage] = useState(0);
  const [pageSize, setPageSize] = usePreference(`${label.toLowerCase()}.pageSize`, 25, isPageSize);
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(requestedPage, pages - 1);
  const start = page * pageSize;
  function controls(position: string) {
    return <nav aria-label={`${label} pages (${position})`} className="my-4 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
      <output>Showing {rows.length ? start + 1 : 0}–{Math.min(start + pageSize, rows.length)} of {rows.length.toLocaleString('en-US')} · page {page + 1} of {pages}</output>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2">Rows per page<select aria-label={`${label} rows per page (${position})`} className={controlClass} value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(0); }}>{[25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
        <button className={controlClass} disabled={page === 0} onClick={() => setPage(0)}>First</button>
        <button className={controlClass} disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
        <button className={controlClass} disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</button>
        <button className={controlClass} disabled={page + 1 >= pages} onClick={() => setPage(pages - 1)}>Last</button>
      </div>
    </nav>;
  }
  return <>{controls('top')}{children(rows.slice(start, start + pageSize))}{controls('bottom')}<p className="text-xs text-muted-foreground">CSV export includes every matching row, across all pages.</p></>;
}
