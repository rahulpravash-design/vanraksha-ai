/** Shapes mirrored from the API's response models. */

import type { Band } from "./bands";

export type Role =
  | "farmer" | "field_worker" | "veterinarian" | "lab"
  | "block_admin" | "district_admin" | "super_admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  phone: string | null;
  language: string;
  village_id: string | null;
  block: string | null;
  district: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Contribution {
  rule_id: string;
  factor: string;
  points: number;
  evidence: string;
}

export interface Caution {
  caution_id: string;
  title: string;
  rationale: string;
  actions: string[];
  zoonotic: boolean;
  notifiable: boolean;
}

export interface Assessment {
  id: string;
  report_id: string;
  score: number;
  band: Band;
  contributions: Contribution[];
  syndromes: string[];
  dominant_syndrome: string | null;
  cautions: Caution[];
  recommended_action: string;
  response_target_hours: number;
  completeness: number;
  engine_version: string;
  created_at: string;
}

export interface HealthReport {
  id: string;
  client_uuid: string;
  animal_id: string | null;
  farm_id: string | null;
  village_id: string | null;
  reporter_id: string;
  species: string;
  reported_at: string;
  received_at: string;
  symptoms_text: string;
  symptom_codes: string[];
  unmatched_terms: string[];
  temperature_c: number | null;
  duration_hours: number | null;
  affected_count: number;
  deaths_count: number;
  herd_size: number | null;
  latitude: number | null;
  longitude: number | null;
  notes: string;
  submitted_offline: boolean;
  assessment: Assessment | null;
}

export interface ReportDraft {
  client_uuid: string;
  species: string;
  symptoms: string[];
  symptoms_text?: string;
  animal_id?: string | null;
  farm_id?: string | null;
  village_id?: string | null;
  reported_at?: string;
  temperature_c?: number | null;
  duration_hours?: number | null;
  affected_count?: number;
  deaths_count?: number;
  herd_size?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  notes?: string;
  submitted_offline?: boolean;
}

export interface Case {
  id: string;
  report_id: string;
  status: "open" | "assigned" | "in_progress" | "awaiting_lab" | "resolved" | "closed";
  band: Band;
  assigned_vet_id: string | null;
  opened_at: string;
  assigned_at: string | null;
  first_response_at: string | null;
  closed_at: string | null;
  due_at: string | null;
  outcome: string | null;
  resolution_notes: string;
  cluster_id: string | null;
  is_overdue: boolean;
}

export interface Cluster {
  id: string;
  signature: string;
  status: "active" | "under_investigation" | "confirmed" | "dismissed" | "resolved";
  centroid_lat: number;
  centroid_lon: number;
  radius_km: number;
  first_seen: string;
  last_seen: string;
  report_count: number;
  animal_count: number;
  death_count: number;
  severity_score: number;
  growth_ratio: number;
  dominant_syndrome: string | null;
  villages: string[];
  species: string[];
  report_ids: string[];
  top_symptoms: { code: string; count: number }[];
  explanation: string;
  detector_version: string;
  detected_at: string;
  review_outcome: string | null;
  review_notes: string;
}

export interface Alert {
  id: string;
  dedupe_key: string;
  kind: string;
  severity: number;
  title: string;
  body: string;
  scope: string;
  audiences: string[];
  evidence: Record<string, unknown>;
  raised_at: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface Village {
  id: string;
  name: string;
  block: string;
  district: string;
  state: string;
  latitude: number;
  longitude: number;
  livestock_population: number;
}

export interface VillageRow extends Village {
  village_id: string;
  report_count: number;
  animal_count: number;
  death_count: number;
  escalated_count: number;
}

export interface Farm {
  id: string;
  name: string;
  owner_id: string;
  village_id: string;
  latitude: number;
  longitude: number;
  herd_size: number;
  created_at: string;
}

export interface Animal {
  id: string;
  tag: string;
  species: string;
  breed: string | null;
  sex: string | null;
  date_of_birth: string | null;
  farm_id: string;
  status: "active" | "sold" | "deceased";
  is_pregnant: boolean;
  is_lactating: boolean;
  age_months: number | null;
  created_at: string;
}

export interface TimelineEvent {
  type: "health_report" | "vaccination" | "treatment";
  at: string;
  id: string;
  summary: string;
  band?: string | null;
  score?: number | null;
  deaths?: number;
  next_due?: string | null;
  withdrawal_until?: string | null;
}

export interface ScopeSummary {
  scope: string;
  period_days: number;
  report_count: number;
  previous_period_count: number;
  animal_count: number;
  death_count: number;
  open_cases: number;
  overdue_cases: number;
  active_clusters: number;
  overdue_vaccinations: number;
  band_counts: Record<string, number>;
  syndrome_counts: Record<string, number>;
  top_symptoms: { code: string; count: number }[];
  weekly_series: { period_start: string; count: number }[];
  trend: string;
}

export interface Performance {
  period_days: number;
  reports: number;
  cases: number;
  median_reporting_lag_hours: number | null;
  median_assignment_hours: number | null;
  median_resolution_hours: number | null;
  sla_met_rate: number | null;
  offline_share: number | null;
  data_completeness: number | null;
}

export interface Coverage {
  animals: number;
  covered: number;
  overdue: number;
  never: number;
  coverage_rate: number | null;
}

export interface SymptomTerm {
  code: string;
  label: string;
  syndromes: string[];
  severity_weight: number;
  synonyms: string[];
}

export interface Taxonomy {
  syndromes: { code: string; label: string }[];
  symptoms: SymptomTerm[];
}

export interface SyncItemResult {
  client_uuid: string;
  status: "accepted" | "duplicate" | "rejected";
  report_id: string | null;
  band: string | null;
  detail: string | null;
}

export interface SyncResult {
  accepted: number;
  duplicates: number;
  rejected: number;
  results: SyncItemResult[];
  server_time: string;
}

export interface AssistantAnswer {
  answer: string;
  source: string;
  grounded_in: string;
  guardrail: string | null;
  assistant_version: string;
}
