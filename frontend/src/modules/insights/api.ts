import { api } from "@/shared/api/http";

export type Severity = "critical" | "warning" | "info";
export type AlertState = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";

export interface Alert {
  id: number;
  org_id: number;
  domain: "stock" | "expiry" | "order" | "budget" | "supply" | "platform" | string;
  kind: string;
  severity: Severity;
  status: AlertState;
  title: string;
  body: string;
  link: string | null;
  metrics: Record<string, unknown>;
  first_seen: string;
  last_seen: string;
  resolved_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface AlertCounts {
  critical: number;
  warning: number;
  info: number;
  total: number;
}

export interface Digest {
  id: number;
  headline: string;
  summary: string;
  actions: { title: string; detail: string; alert_id: number | null; link: string | null }[];
  generated_by: "ai" | "rules";
  model: string | null;
  created_at: string;
  stale: boolean;
}

export interface MonitorRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  status: "RUNNING" | "OK" | "PARTIAL" | "FAILED";
  trigger: string;
  findings: number;
  opened: number;
  resolved: number;
  notified: number;
  digests: number;
  errors: string[];
}

export interface AgentStatus {
  ai_enabled: boolean;
  model: string | null;
  monitor_enabled: boolean;
  interval_minutes: number;
  last_run: MonitorRun | null;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface Overview {
  services: Record<string, { up: boolean; latency_ms: number | null; detail: string | null }>;
  llm: { enabled: boolean; model: string; fallback_models: string[]; requests: number; failures: number; cost_usd: number; last_model: string | null; last_error: string | null };
  runs: MonitorRun[];
  alerts_by_severity: AlertCounts;
  alerts_by_domain: Record<string, number>;
  top_orgs: { org_id: number; critical: number; warning: number; info: number }[];
}

export const insightsApi = {
  status: () => api<AgentStatus>("agent", "/status"),
  alerts: (state: "live" | "resolved" | "all" = "live") => api<Alert[]>("agent", "/alerts", { query: { state } }),
  counts: () => api<AlertCounts>("agent", "/alerts/summary"),
  acknowledge: (id: number) => api<Alert>("agent", `/alerts/${id}/acknowledge`, { method: "POST" }),
  digest: () => api<Digest>("agent", "/digest"),
  refreshDigest: () => api<Digest>("agent", "/digest/refresh", { method: "POST" }),
  ask: (messages: ChatTurn[]) =>
    api<{ answer: string; model: string | null; tools_used: string[] }>("agent", "/assistant", { method: "POST", body: { messages } }),
  overview: () => api<Overview>("agent", "/admin/overview"),
  runNow: () => api<MonitorRun>("agent", "/admin/run", { method: "POST" }),
};

export const SEVERITY: Record<Severity, { label: string; color: string; order: number }> = {
  critical: { label: "Urgent", color: "red", order: 0 },
  warning: { label: "Review", color: "orange", order: 1 },
  info: { label: "FYI", color: "blue", order: 2 },
};

export const DOMAIN_LABEL: Record<string, string> = {
  stock: "Stock levels",
  expiry: "Expiry",
  order: "Orders",
  budget: "Budget",
  supply: "Supply",
  platform: "Platform",
};
