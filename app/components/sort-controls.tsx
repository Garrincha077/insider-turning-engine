import { usePreference, isString, isBoolean } from '../lib/local-preferences';
import { ArrowDown, ArrowUp } from 'lucide-react';

export type SortField<T> = {
  id: string;
  label: string;
  value: (row: T) => number | string | null | undefined;
};

export function sortRows<T>(rows: readonly T[], field: SortField<T>, descending: boolean): T[] {
  // Never mutate a shared snapshot. Missing/non-finite values stay last in either direction.
  return [...rows].sort((a, b) => {
    const left = field.value(a);
    const right = field.value(b);
    const missing = (value: typeof left) => value == null || (typeof value === 'number' && !Number.isFinite(value));
    if (missing(left)) return missing(right) ? 0 : 1;
    if (missing(right)) return -1;
    const compared = typeof left === 'number' && typeof right === 'number'
      ? left - right : String(left).localeCompare(String(right), 'en', { numeric: true });
    return descending ? -compared : compared;
  });
}

export function useRowSort<T>(rows: readonly T[], fields: readonly SortField<T>[], initial: string, storageKey = initial) {
  const [fieldId, setFieldId] = usePreference(`${storageKey}.sort`, initial, isString);
  const [descending, setDescending] = usePreference(`${storageKey}.descending`, true, isBoolean);
  const field = fields.find((item) => item.id === fieldId) ?? fields[0];
  const choose = (id: string) => { setFieldId(id); setDescending(true); };
  const toggle = (id: string) => {
    if (id !== field.id) choose(id);
    else setDescending((previous) => !previous);
  };
  return { rows: sortRows(rows, field, descending), fieldId: field.id, descending,
    choose, toggle, reverse: () => setDescending((previous) => !previous) };
}

export function SortControls({ fields, fieldId, descending, onField, onReverse }: {
  fields: readonly { id: string; label: string }[];
  fieldId: string;
  descending: boolean;
  onField: (id: string) => void;
  onReverse: () => void;
}) {
  const Arrow = descending ? ArrowDown : ArrowUp;
  return <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
    <label className="flex items-center gap-2 text-muted-foreground">Sort by
      <select aria-label="Sort by" value={fieldId} onChange={(event) => onField(event.target.value)}
        className="h-9 rounded-md border border-border bg-card px-2 text-foreground focus-visible:outline-2 focus-visible:outline-emerald-300">
        {fields.map((field) => <option key={field.id} value={field.id}>{field.label}</option>)}
      </select>
    </label>
    <button type="button" onClick={onReverse} className="flex h-9 items-center gap-2 rounded-md border border-border px-3 hover:bg-accent focus-visible:outline-2 focus-visible:outline-emerald-300"
      aria-label={descending ? 'Largest first; switch to smallest first' : 'Smallest first; switch to largest first'}>
      <Arrow className="size-3.5" aria-hidden="true" />{descending ? 'Largest / newest first' : 'Smallest / oldest first'}
    </button>
  </div>;
}
