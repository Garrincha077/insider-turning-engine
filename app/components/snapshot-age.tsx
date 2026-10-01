import { useEffect, useState } from 'react';
import { snapshotAgeLabel } from '@/lib/operations-data';

export function SnapshotAge({ asOf }: { asOf: string }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return <span title="Elapsed wall-clock time since the data snapshot; not a market-session freshness check.">Snapshot age: {snapshotAgeLabel(asOf, now)}</span>;
}
