"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { HealthResponse, ServiceInfo } from "@/lib/types";
import { EmptyState, Panel, Pill } from "@/components/ui";

export default function SystemPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [info, setInfo] = useState<ServiceInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.info()])
      .then(([h, i]) => {
        setHealth(h);
        setInfo(i);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">System</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Dependency readiness and build information.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-[var(--color-negative)]/30 bg-[var(--color-negative)]/10 px-4 py-3 text-sm text-[var(--color-negative)]">
          {error}
        </div>
      )}

      <Panel title="READINESS">
        <ul className="space-y-2">
          {(health?.checks ?? []).map((check) => (
            <li
              key={check.name}
              className="flex items-center justify-between rounded-lg bg-[var(--color-panel-raised)] px-3 py-2 text-sm"
            >
              <span>{check.name}</span>
              <span className="flex items-center gap-3">
                {check.latency_ms !== null && (
                  <span className="text-xs text-[var(--color-ink-muted)]">
                    {check.latency_ms} ms
                  </span>
                )}
                <Pill tone={check.status === "ok" ? "ok" : "error"}>{check.status}</Pill>
              </span>
            </li>
          ))}
          {!health && <li className="text-sm text-[var(--color-ink-muted)]">Loading…</li>}
        </ul>
      </Panel>

      <Panel title="BUILD">
        {info ? (
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-[var(--color-ink-muted)]">Service</dt>
            <dd>{info.name}</dd>
            <dt className="text-[var(--color-ink-muted)]">Version</dt>
            <dd className="font-mono text-xs">{info.version}</dd>
            <dt className="text-[var(--color-ink-muted)]">Environment</dt>
            <dd className="font-mono text-xs">{info.environment}</dd>
            <dt className="text-[var(--color-ink-muted)]">Commit</dt>
            <dd className="font-mono text-xs">{info.git_sha}</dd>
          </dl>
        ) : (
          <p className="text-sm text-[var(--color-ink-muted)]">Loading…</p>
        )}
      </Panel>

      <Panel title="AGENT TRACE">
        <EmptyState
          title="No investigations yet"
          detail="Every investigation gets a trace id at the API boundary, persisted across agent_runs, agent_tasks and tool_calls. This page renders those rows once the agent graph lands in Phase 4 — it does not depend on an external tracing service being reachable."
          hint="GET /api/v1/agent-runs/{id}"
        />
      </Panel>
    </div>
  );
}
