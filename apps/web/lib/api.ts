/**
 * Typed client for the surveillance API.
 *
 * Two things here are deliberate rather than incidental:
 *
 * 1. `ApiError` carries the field-level messages the API returns, so a form can
 *    render "affected_count cannot exceed herd_size" next to the input that
 *    caused it instead of showing a generic failure.
 * 2. A network failure is distinguished from a rejection. The field app has to
 *    tell them apart: one means "queue this and try later", the other means
 *    "this will never succeed, show the farmer what to change".
 */

import type {
  Alert, Animal, AssistantAnswer, Case, Cluster, Coverage, Farm, HealthReport,
  Performance, ReportDraft, ScopeSummary, SyncResult, Taxonomy, TimelineEvent,
  User, Village, VillageRow,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

const TOKEN_KEY = "vanraksha.token";

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: FieldError[];
  /** True when the request never reached the server. */
  readonly offline: boolean;

  constructor(
    message: string,
    status: number,
    fieldErrors: FieldError[] = [],
    offline = false,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.offline = offline;
  }

  /** Whether queueing and retrying could plausibly succeed. */
  get isRetryable(): boolean {
    return this.offline || this.status === 0 || this.status >= 500;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    // Private browsing and blocked site data both throw here.
    return null;
  }
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* Nothing useful to do; the session simply does not persist. */
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: Record<string, string>;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form, signal } = options;
  const headers: Record<string, string> = {};

  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload: BodyInit | undefined;
  if (form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    payload = new URLSearchParams(form).toString();
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method, headers, body: payload, signal,
    });
  } catch (cause) {
    throw new ApiError(
      "Could not reach the server. Your work is saved on this device and will be sent when you are back online.",
      0, [], true,
    );
  }

  if (response.status === 204) return undefined as T;

  let data: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }

  if (!response.ok) {
    const shape = (data ?? {}) as { detail?: unknown; errors?: FieldError[] };
    const detail =
      typeof shape.detail === "string" ? shape.detail : `Request failed (${response.status}).`;
    throw new ApiError(detail, response.status, shape.errors ?? []);
  }

  return data as T;
}

export const api = {
  // ------------------------------------------------------------------- auth
  async login(email: string, password: string) {
    const token = await request<{
      access_token: string; role: string; user_id: string; full_name: string;
    }>("/auth/login", { method: "POST", form: { username: email, password } });
    setToken(token.access_token);
    return token;
  },

  logout() {
    setToken(null);
  },

  register(payload: { email: string; password: string; full_name: string; phone?: string }) {
    return request<User>("/auth/register", { method: "POST", body: payload });
  },

  me: () => request<User>("/auth/me"),

  // ---------------------------------------------------------------- reports
  createReport: (draft: ReportDraft) =>
    request<HealthReport>("/reports", { method: "POST", body: draft }),

  syncReports: (reports: ReportDraft[], deviceId?: string) =>
    request<SyncResult>("/reports/sync", {
      method: "POST",
      body: { reports, device_id: deviceId ?? null },
    }),

  listReports: (params: { days?: number; band?: string; limit?: number } = {}) =>
    request<HealthReport[]>(`/reports${query(params)}`),

  getReport: (id: string) => request<HealthReport>(`/reports/${id}`),

  taxonomy: () => request<Taxonomy>("/reports/taxonomy"),

  // -------------------------------------------------------------- livestock
  listVillages: () => request<Village[]>("/villages"),
  listFarms: () => request<Farm[]>("/farms"),
  listAnimals: (farmId?: string) =>
    request<Animal[]>(`/animals${farmId ? `?farm_id=${encodeURIComponent(farmId)}` : ""}`),
  animalTimeline: (id: string) =>
    request<{ animal: Animal; events: TimelineEvent[] }>(`/animals/${id}/timeline`),

  // ------------------------------------------------------------------ cases
  caseQueue: (params: { mine_only?: boolean; include_closed?: boolean } = {}) =>
    request<Case[]>(`/cases/queue${query(params)}`),
  assignCase: (id: string, veterinarianId: string) =>
    request<Case>(`/cases/${id}/assign`, {
      method: "POST", body: { veterinarian_id: veterinarianId },
    }),
  updateCase: (id: string, patch: { status?: string; outcome?: string; resolution_notes?: string }) =>
    request<Case>(`/cases/${id}`, { method: "PATCH", body: patch }),

  // ----------------------------------------------------------- surveillance
  listClusters: (params: { status?: string; days?: number } = {}) =>
    request<Cluster[]>(`/clusters${query(params)}`),
  getCluster: (id: string) => request<Cluster>(`/clusters/${id}`),
  reviewCluster: (id: string, outcome: string, notes = "") =>
    request<Cluster>(`/clusters/${id}/review`, { method: "POST", body: { outcome, notes } }),
  runSweep: (windowDays = 21) =>
    request<{ clusters_detected: number; reports_considered: number }>(
      `/surveillance/sweep?window_days=${windowDays}`, { method: "POST" },
    ),

  listAlerts: (params: { unacknowledged_only?: boolean; days?: number } = {}) =>
    request<Alert[]>(`/alerts${query(params)}`),
  acknowledgeAlert: (id: string) =>
    request<Alert>(`/alerts/${id}/acknowledge`, { method: "POST" }),

  // -------------------------------------------------------------- analytics
  summary: (days = 30) => request<ScopeSummary>(`/analytics/summary?days=${days}`),
  villageRows: (days = 30) => request<VillageRow[]>(`/analytics/villages?days=${days}`),
  performance: (days = 90) => request<Performance>(`/analytics/performance?days=${days}`),
  coverage: () => request<Coverage>("/analytics/vaccination-coverage"),
  ask: (question: string, days = 30) =>
    request<AssistantAnswer>("/analytics/assistant", {
      method: "POST", body: { question, days },
    }),
};

function query(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(
    ([, value]) => value !== undefined && value !== null && value !== "",
  );
  if (!entries.length) return "";
  return `?${entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&")}`;
}
