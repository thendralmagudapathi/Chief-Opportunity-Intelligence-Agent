/**
 * Typed API client.
 *
 * Errors are surfaced as `ApiError`, carrying the backend's problem-details
 * payload including the trace id, so a UI error message can be tied back to a
 * server-side investigation trace.
 */

import type {
  Goal,
  HealthResponse,
  OpportunityListItem,
  Page,
  ProblemDetails,
  ServiceInfo,
  TokenPair,
  User,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;
const TOKEN_KEY = "oia.access_token";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly problem: ProblemDetails | null,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { authenticated = true }: { authenticated?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  const token = authenticated ? getToken() : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, null, "Cannot reach the API. Is the backend running?");
  }

  if (response.status === 204) return undefined as T;

  const body = await response.text();
  const parsed = body ? (JSON.parse(body) as unknown) : null;

  if (!response.ok) {
    const problem = parsed as ProblemDetails | null;
    throw new ApiError(
      response.status,
      problem,
      problem?.detail ?? `Request failed with status ${response.status}`,
    );
  }
  return parsed as T;
}

export const api = {
  health: () => request<HealthResponse>("/health/ready", {}, { authenticated: false }),
  info: () => request<ServiceInfo>("/health/info", {}, { authenticated: false }),

  register: (email: string, password: string, fullName?: string) =>
    request<User>(
      "/auth/register",
      {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName ?? null }),
      },
      { authenticated: false },
    ),

  login: (email: string, password: string) =>
    request<TokenPair>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      { authenticated: false },
    ),

  me: () => request<User>("/auth/me"),

  goals: () => request<Goal[]>("/goals"),

  createGoal: (payload: {
    title: string;
    objective_profile: string;
    priority: number;
    desired_outcome?: string;
  }) => request<Goal>("/goals", { method: "POST", body: JSON.stringify(payload) }),

  deleteGoal: (id: string) => request<void>(`/goals/${id}`, { method: "DELETE" }),

  opportunities: (params: Record<string, string> = {}) => {
    const query = new URLSearchParams(params).toString();
    return request<Page<OpportunityListItem>>(
      `/opportunities${query ? `?${query}` : ""}`,
    );
  },
};
