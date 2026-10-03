export type QualityMeasurement = {
  numerator: number;
  denominator: number;
  rate: number | null;
  threshold: number;
  result: 'PASS' | 'FAIL' | 'NOT_EVALUATED';
};

export type PublicationManifest = {
  schemaVersion: string;
  manifestId: string;
  runId: string;
  asOf: string;
  generatedAt: string;
  status: 'SUCCEEDED' | 'DEGRADED';
  scoreVersion: string;
  files: Array<{ path: string; size: number; sha256: string }>;
  watermarks: {
    secAcceptedThrough: string | null;
    marketSessionThrough: string | null;
    fundamentalsAvailableThrough: string | null;
  };
  universe: {
    issuerCount: number;
    activeTransactionCount: number;
    signalCount: number;
  };
  quality: {
    disposition: 'PASS' | 'DEGRADED' | 'BLOCKED';
    canonicalValid: boolean;
    methodologyComplete: boolean;
    benchmarkFresh: boolean;
    parseSuccess: QualityMeasurement;
    marketCoverage: QualityMeasurement;
    coreBranchCoverage: QualityMeasurement;
    issues: string[];
  };
};

export type ChannelStatus = {
  enabled: boolean;
  configured: boolean;
  recipientMasked: string | null;
  lastTestAt: string | null;
  lastTestStatus?: 'SENT' | 'FAILED' | 'UNCERTAIN' | null;
  testFailureCount?: number;
  lastSuccessAt: string | null;
  failureCount: number;
};

export type SettingsStatus = {
  schemaVersion: string;
  generatedAt: string;
  environment: 'local' | 'staging' | 'production';
  alertsAllowed: boolean;
  blockingReasons: string[];
  digest?: {
    enabled: boolean; secDay: string | null; status: 'READY' | 'BLOCKED';
    reasons: string[]; eventIds: string[]; excludedIssuers: number | null;
    minimumPurchaseUsd?: number; maximumItems?: number;
  };
  deliveryHistory?: Array<{
    kind: 'TEST' | 'SIGNAL' | 'DIGEST'; channel: 'telegram' | 'email';
    status: 'SENT' | 'FAILED' | 'UNCERTAIN' | 'SUPPRESSED' | 'CLAIMED'; at: string;
  }>;
  policy: {
    deliveryEnabled: boolean;
    minimumSeverity: 'INFO' | 'WATCH' | 'HIGH' | 'CRITICAL';
    alertTypes: Array<'MAJOR_INSIDER_BUY' | 'STEALTH_ACCUMULATION' | 'TURNING'>;
    cooldownDays: number;
    timezone: string;
    quietHours: { start: string; end: string } | null;
  };
  channels: {
    telegram: ChannelStatus;
    email: ChannelStatus;
  };
};

export function digestPolicySummary(digest: SettingsStatus['digest']) {
  if (digest?.minimumPurchaseUsd == null || digest.maximumItems == null) {
    return 'Selection thresholds are unavailable in this snapshot.';
  }
  return `Up to ${digest.maximumItems} purchases ≥ $${digest.minimumPurchaseUsd.toLocaleString('en-US')}.`;
}

export function rateLabel(measurement: QualityMeasurement) {
  return measurement.rate === null ? 'Not evaluated' : `${(measurement.rate * 100).toFixed(2)}%`;
}

export function humanReason(value: string) {
  return value.replaceAll('_', ' ').toLowerCase();
}

// Elapsed wall-clock time, not a market-session freshness assessment.
export function snapshotAgeLabel(asOf: string, now: number) {
  const timestamp = Date.parse(asOf);
  if (!Number.isFinite(timestamp) || !Number.isFinite(now)) return 'Unavailable';
  if (timestamp > now) return 'Snapshot is ahead of this device clock';
  const minutes = Math.floor((now - timestamp) / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}
