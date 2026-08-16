/**
 * Wire types mirroring backend/app/schemas. Kept hand-written for now; once the
 * schema stabilises these are generated from the OpenAPI document instead.
 */

export type HealthStatus = "ok" | "degraded" | "error";

export interface HealthCheck {
  name: string;
  status: HealthStatus;
  latency_ms: number | null;
  detail: string | null;
}

export interface HealthResponse {
  status: HealthStatus;
  checks: HealthCheck[];
}

export interface ServiceInfo {
  name: string;
  version: string;
  environment: string;
  git_sha: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  last_login_at: string | null;
}

export type ObjectiveProfile =
  | "career"
  | "income"
  | "business"
  | "learning"
  | "networking"
  | "startup"
  | "research";

export type GoalStatus = "active" | "paused" | "achieved" | "abandoned";

export interface Goal {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  objective_profile: ObjectiveProfile;
  priority: number;
  status: GoalStatus;
  deadline: string | null;
  desired_outcome: string | null;
  created_at: string;
  updated_at: string;
}

export type Recommendation =
  | "STRONGLY_PURSUE"
  | "PURSUE"
  | "CONSIDER"
  | "WAIT"
  | "LOW_PRIORITY"
  | "IGNORE"
  | "INELIGIBLE";

export interface OpportunityListItem {
  id: string;
  title: string;
  category: string;
  subcategory: string | null;
  organization_name: string | null;
  location_country: string | null;
  location_city: string | null;
  remote_status: string;
  deadline: string | null;
  discovered_at: string | null;
  freshness_score: number | null;
  status: string;
  source_url: string;
  summary: string | null;
  overall_score: string | null;
  recommendation: Recommendation | null;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
  total: number | null;
}

export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  trace_id: string;
  errors?: { field: string; message: string }[];
}
